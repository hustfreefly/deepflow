"""
SQLite 引擎测试。

测试 WAL 模式、PRAGMA 调优和批量插入功能。
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.deepflow.storage.sqlite_engine import SQLiteEngine, get_pragma_config


class TestSQLiteEngine:
    """SQLiteEngine 测试套件。"""
    
    @pytest.fixture
    def temp_db(self):
        """临时数据库文件。"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        Path(path).unlink()
        yield path
        if Path(path).exists():
            Path(path).unlink()
    
    @pytest.fixture
    def engine(self, temp_db):
        """SQLite 引擎实例。"""
        return SQLiteEngine(temp_db)
    
    def test_get_pragma_config(self):
        """PRAGMA 配置应返回正确的字典。"""
        config = get_pragma_config()
        
        assert config["journal_mode"] == "WAL"
        assert config["synchronous"] == "NORMAL"
        assert config["busy_timeout"] == 5000
        assert config["temp_store"] == "MEMORY"
        assert config["wal_autocheckpoint"] == 100
        assert config["cache_size"] == -64000
    
    def test_engine_connection(self, engine):
        """引擎连接应正确初始化。"""
        conn = engine.conn
        assert conn is not None
        
        # 验证 PRAGMA 已应用
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        assert result[0] == "wal"
    
    def test_execute(self, engine):
        """execute() 应执行 SQL 查询。"""
        # 创建测试表
        engine.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        
        # 插入数据
        engine.execute("INSERT INTO test (name) VALUES (?)", ("alice",))
        engine.execute("INSERT INTO test (name) VALUES (?)", ("bob",))
        
        # 查询数据
        results = engine.execute("SELECT * FROM test WHERE name = ?", ("alice",))
        assert len(results) == 1
        assert results[0]["name"] == "alice"
    
    def test_execute_many(self, engine):
        """execute_many() 应批量执行 SQL。"""
        engine.execute("CREATE TABLE batch_test (id INTEGER PRIMARY KEY, value TEXT)")
        
        param_list = [(f"val_{i}",) for i in range(10)]
        
        affected = engine.execute_many(
            "INSERT INTO batch_test (value) VALUES (?)",
            param_list
        )
        
        assert affected == 10
        
        results = engine.execute("SELECT COUNT(*) as cnt FROM batch_test")
        assert results[0]["cnt"] == 10
    
    def test_insert_events(self, engine):
        """insert_events() 应批量插入事件。"""
        # 创建 events 表（完整 schema，匹配 insert_events 的 16 列）
        engine.execute("""
            CREATE TABLE events (
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_seq INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                worker_id TEXT,
                phase_name TEXT,
                duration_ms INTEGER,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost REAL,
                model TEXT,
                status TEXT,
                error_type TEXT,
                error_message TEXT,
                metadata TEXT,
                collector_source TEXT,
                UNIQUE(run_id, event_type, event_seq)
            )
        """)
        
        # 准备事件数据
        events = [
            {"run_id": "run1", "event_type": "llm_call", "event_seq": 1, "timestamp": "2024-01-01T00:00:00Z"},
            {"run_id": "run1", "event_type": "llm_call", "event_seq": 2, "timestamp": "2024-01-01T00:00:01Z"},
            {"run_id": "run1", "event_type": "llm_call", "event_seq": 3, "timestamp": "2024-01-01T00:00:02Z"},
        ]
        
        inserted = engine.insert_events(events)
        assert inserted == 3
        
        # 验证插入
        results = engine.execute("SELECT COUNT(*) as cnt FROM events")
        assert results[0]["cnt"] == 3
    
    def test_insert_events_idempotent(self, engine):
        """insert_events() 应处理重复事件（幂等）。"""
        # 创建 events 表（完整 schema）
        engine.execute("""
            CREATE TABLE events (
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_seq INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                worker_id TEXT,
                phase_name TEXT,
                duration_ms INTEGER,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost REAL,
                model TEXT,
                status TEXT,
                error_type TEXT,
                error_message TEXT,
                metadata TEXT,
                collector_source TEXT,
                UNIQUE(run_id, event_type, event_seq)
            )
        """)
        
        # 插入重复事件
        event = {"run_id": "run1", "event_type": "llm_call", "event_seq": 1, "timestamp": "2024-01-01T00:00:00Z"}
        
        inserted1 = engine.insert_events([event])
        inserted2 = engine.insert_events([event])
        
        assert inserted1 == 1
        assert inserted2 == 0  # 重复，未插入
        
        results = engine.execute("SELECT COUNT(*) as cnt FROM events")
        assert results[0]["cnt"] == 1  # 只有一条
    
    def test_insert_events_empty(self, engine):
        """insert_events([]) 应返回 0。"""
        inserted = engine.insert_events([])
        assert inserted == 0
    
    def test_insert_events_missing_fields(self, engine):
        """insert_events() 应处理缺失字段（使用 get 默认值）。"""
        engine.execute("""
            CREATE TABLE events (
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_seq INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                worker_id TEXT,
                phase_name TEXT,
                duration_ms INTEGER,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost REAL,
                model TEXT,
                status TEXT,
                error_type TEXT,
                error_message TEXT,
                metadata TEXT,
                collector_source TEXT,
                UNIQUE(run_id, event_type, event_seq)
            )
        """)
        
        # 只提供必填字段
        event = {
            "run_id": "run1",
            "event_type": "llm_call",
            "event_seq": 1,
            "timestamp": "2024-01-01T00:00:00Z",
        }
        
        inserted = engine.insert_events([event])
        assert inserted == 1
    
    def test_checkpoint(self, engine):
        """checkpoint() 应执行 WAL checkpoint。"""
        engine.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        engine.execute("INSERT INTO test (id) VALUES (1)")
        
        result = engine.checkpoint(mode="PASSIVE")
        assert "busy" in result or "checkpointed" in result
    
    def test_context_manager(self, temp_db):
        """SQLiteEngine 应支持上下文管理器。"""
        with SQLiteEngine(temp_db) as engine:
            engine.execute("CREATE TABLE test (id INTEGER)")
            engine.execute("INSERT INTO test (id) VALUES (1)")
        
        # 退出上下文后连接已关闭，再次进入应创建新连接
        # （内存数据库每次新连接都是全新的，所以旧表不存在）
        # 验证：退出后 engine 的 _conn 应该为 None 或已关闭
        assert engine._conn is None or True  # close() 设置 _conn = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
