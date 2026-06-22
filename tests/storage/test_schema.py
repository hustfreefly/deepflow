"""
Schema 管理器测试。

测试 Schema 版本管理和迁移功能。
"""

import pytest
import shutil
import json
import tempfile
from pathlib import Path
from typing import List, Dict, Any

from src.deepflow.storage.sqlite_engine import SQLiteEngine
from src.deepflow.storage.schema_manager import SchemaManager


class TestSchemaManager:
    """Schema 管理器测试类。"""
    
    def test_get_current_version_initial(self, tmp_path: Path):
        """测试初始版本号（0 表示未初始化）。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        assert schema.get_current_version() == 0
        
        engine.close()
    
    def test_create_initial_schema(self, tmp_path: Path):
        """测试创建初始 schema。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建 schema
        schema.create_initial_schema()
        
        # 验证版本号
        assert schema.get_current_version() == 1
        
        # 验证表存在
        cursor = engine.conn.cursor()
        
        tables = [
            "events",
            "runs",
            "prompts",
            "gate_results",
            "run_summaries",
            "health_metrics",
            "schema_versions",
        ]
        
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            assert cursor.fetchone() is not None, f"Table {table} not found"
        
        # 验证视图存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='collection_coverage'")
        assert cursor.fetchone() is not None
        
        engine.close()
    
    def test_register_migration(self, tmp_path: Path):
        """测试迁移函数注册。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建初始 schema
        schema.create_initial_schema()
        
        # 注册迁移函数
        migration_called = []
        
        def migration_v2(conn):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE events ADD COLUMN new_field TEXT")
            migration_called.append(True)
        
        schema.register_migration(2, migration_v2)
        
        # 验证迁移已注册
        assert 2 in schema._migrations
        
        engine.close()
    
    def test_migrate_expand_migrate_contract(self, tmp_path: Path):
        """测试 expand-migrate-contract 模式迁移。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建初始 schema
        schema.create_initial_schema()
        
        # 注册 V2 迁移（expand）
        def migration_v2(conn):
            cursor = conn.cursor()
            # Expand: 创建临时表
            cursor.execute("CREATE TABLE temp_events AS SELECT * FROM events WHERE 1=0")
            # Migrate: 迁移数据
            cursor.execute("ALTER TABLE events ADD COLUMN version INTEGER DEFAULT 1")
            cursor.execute("ALTER TABLE events ADD COLUMN processed INTEGER DEFAULT 0")
            # Contract: 删除临时表
            cursor.execute("DROP TABLE temp_events")
        
        schema.register_migration(2, migration_v2)
        
        # 执行迁移
        schema.migrate(2)
        
        # 验证版本号
        assert schema.get_current_version() == 2
        
        # 验证新字段存在
        cursor = engine.conn.cursor()
        cursor.execute("PRAGMA table_info(events)")
        columns = {col[1] for col in cursor.fetchall()}
        assert "version" in columns
        assert "processed" in columns
        
        engine.close()
    
    def test_migrate_auto_backup(self, tmp_path: Path):
        """测试迁移前自动备份。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建初始 schema
        schema.create_initial_schema()
        
        # 插入测试数据
        cursor = engine.conn.cursor()
        cursor.execute("""
            CREATE TABLE test_data (
                id INTEGER PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("INSERT INTO test_data (value) VALUES (?)", ("original",))
        engine.conn.commit()
        
        # 注册迁移函数
        def migration_v2(conn):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE test_data ADD COLUMN new_value TEXT")
        
        schema.register_migration(2, migration_v2)
        
        # 执行迁移
        schema.migrate(2)
        
        # 验证备份文件存在
        backups = list(schema.backup_dir.glob("deepflow_backup_v*.db"))
        assert len(backups) > 0
        
        engine.close()
    
    def test_migrate_failure_restore(self, tmp_path: Path):
        """测试迁移失败时的恢复。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建初始 schema
        schema.create_initial_schema()
        
        # 创建测试表
        cursor = engine.conn.cursor()
        cursor.execute("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("INSERT INTO test_table (value) VALUES ('original')")
        engine.conn.commit()
        
        # 注册失败的迁移函数
        def failing_migration(conn):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE test_table ADD COLUMN new_col TEXT")
            # 模拟失败
            raise RuntimeError("Migration failed!")
        
        schema.register_migration(2, failing_migration)
        
        # 执行迁移（应该失败）
        with pytest.raises(RuntimeError, match="Migration failed!"):
            schema.migrate(2)
        
        # 验证版本仍为 1（未更新）
        assert schema.get_current_version() == 1
        
        # 验证数据未损坏
        cursor.execute("SELECT * FROM test_table")
        rows = cursor.fetchall()
        assert len(rows) == 1
        
        engine.close()
    
    def test_migrate_skip_if_up_to_date(self, tmp_path: Path):
        """测试升级到最新版本时跳过。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建初始 schema
        schema.create_initial_schema()
        
        # 再次调用 migrate(1) 应该跳过
        schema.migrate(1)
        
        # 验证版本号
        assert schema.get_current_version() == 1
        
        engine.close()
    
    def test_migrate_downgrade_not_allowed(self, tmp_path: Path):
        """测试降级不被允许。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建初始 schema
        schema.create_initial_schema()
        
        # 尝试降级（应该失败）
        with pytest.raises(ValueError, match="Target version.*is less than current version"):
            schema.migrate(0)
        
        engine.close()
    
    def test_drop_schema(self, tmp_path: Path):
        """测试删除 schema。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建 schema
        schema.create_initial_schema()
        
        # 删除 schema
        schema.drop_schema()
        
        # 验证表已删除
        cursor = engine.conn.cursor()
        
        tables = [
            "events",
            "runs",
            "prompts",
            "gate_results",
            "run_summaries",
            "health_metrics",
            "schema_versions",
        ]
        
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            assert cursor.fetchone() is None, f"Table {table} should be deleted"
        
        # 验证视图已删除
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='collection_coverage'")
        assert cursor.fetchone() is None
        
        engine.close()
    
    def test_context_manager(self, tmp_path: Path):
        """测试 SchemaManager 上下文管理器。"""
        db_path = str(tmp_path / "test.db")
        
        with SQLiteEngine(db_path) as engine:
            with SchemaManager(engine) as schema:
                schema.create_initial_schema()
                assert schema.get_current_version() == 1
        
        # 验证连接已关闭
        assert engine._conn is None
        assert schema._internal_conn is None
    
    def test_schema_with_realistic_data(self, tmp_path: Path):
        """测试带真实数据的 schema。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建 schema
        schema.create_initial_schema()
        
        # 插入测试数据
        cursor = engine.conn.cursor()
        
        # 插入 events
        cursor.execute("""
            INSERT INTO events (
                run_id, event_type, event_seq, timestamp,
                worker_id, phase_name, duration_ms, tokens_in,
                tokens_out, cost, model, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "run-001", "start", 1, "2026-06-22T20:00:00.000Z",
            "worker-001", "inference", 1500, 1000, 500,
            0.025, "gpt-4", "success"
        ))
        
        # 插入 runs
        cursor.execute("""
            INSERT INTO runs (run_id, started_at, status, total_duration_ms)
            VALUES (?, ?, ?, ?)
        """, ("run-001", "2026-06-22T20:00:00.000Z", "completed", 1500))
        
        # 插入 prompts
        cursor.execute("""
            INSERT INTO prompts (
                prompt_id, version, raw_hash, effective_hash,
                content, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "prompt-001", "1", "hash1", "hash2",
            "Test prompt", "2026-06-22T20:00:00.000Z"
        ))
        
        # 插入 gate_results
        cursor.execute("""
            INSERT INTO gate_results (
                run_id, phase_name, gate_name, result, timestamp
            ) VALUES (?, ?, ?, ?, ?)
        """, ("run-001", "inference", "accuracy", "pass", "2026-06-22T20:00:01.000Z"))
        
        # 插入 run_summaries
        cursor.execute("""
            INSERT INTO run_summaries (
                run_id, total_duration_ms, total_cost,
                total_tokens, retry_count, event_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("run-001", 1500, 0.025, 1500, 0, 1, "2026-06-22T20:00:01.000Z"))
        
        # 插入 health_metrics
        cursor.execute("""
            INSERT INTO health_metrics (
                metric_name, metric_value, threshold, status, measured_at
            ) VALUES (?, ?, ?, ?, ?)
        """, ("latency", 1.5, 2.0, "healthy", "2026-06-22T20:00:00.000Z"))
        
        engine.conn.commit()
        
        # 验证数据
        cursor.execute("SELECT COUNT(*) FROM events")
        assert cursor.fetchone()[0] == 1
        
        cursor.execute("SELECT COUNT(*) FROM runs")
        assert cursor.fetchone()[0] == 1
        
        cursor.execute("SELECT COUNT(*) FROM collection_coverage")
        assert cursor.fetchone()[0] == 1
        
        engine.close()
    
    def test_prerequisites_for_migrations(self, tmp_path: Path):
        """测试迁移 prerequisites（创建 schema_versions 表）。"""
        db_path = str(tmp_path / "test.db")
        engine = SQLiteEngine(db_path)
        schema = SchemaManager(engine)
        
        # 创建初始 schema（这会创建 schema_versions 表）
        schema.create_initial_schema()
        
        # 验证 schema_versions 表存在且有版本 1
        cursor = engine.conn.cursor()
        cursor.execute("SELECT * FROM schema_versions WHERE version = 1")
        row = cursor.fetchone()
        assert row is not None
        
        engine.close()
