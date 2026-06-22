"""
Schema 版本管理器。

实现 expand-migrate-contract 模式，支持自动备份和版本控制。
"""

import sqlite3
import shutil
import time
from pathlib import Path
from typing import Dict, Callable, List, Any, Optional


class SchemaManager:
    """
    Schema 版本管理器。
    
    支持：
    - 自动备份当前数据库
    - 版本号管理
    - expand-migrate-contract 模式迁移
    
    Args:
        engine: SQLite 引擎实例
        backup_dir: 备份文件目录
    """
    
    def __init__(self, engine: "SQLiteEngine", backup_dir: Optional[str] = None):
        """
        初始化 Schema 管理器。
        
        Args:
            engine: SQLite 引擎实例
            backup_dir: 备份文件目录（默认为数据库文件所在目录）
        """
        from .sqlite_engine import SQLiteEngine
        
        self.engine = engine
        self.db_path = engine.db_path
        self.backup_dir = Path(backup_dir) if backup_dir else Path(self.db_path).parent
        
        # 确保备份目录存在
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 内部连接用于 schema 管理
        self._internal_conn: Optional[sqlite3.Connection] = None
    
    @property
    def internal_conn(self) -> sqlite3.Connection:
        """获取内部连接。"""
        if self._internal_conn is None:
            self._internal_conn = sqlite3.connect(self.db_path, timeout=5.0)
        return self._internal_conn
    
    def get_current_version(self) -> int:
        """
        获取当前 schema 版本。
        
        Returns:
            当前版本号（0 表示未初始化）
        """
        cursor = self.internal_conn.cursor()
        
        try:
            cursor.execute("SELECT version FROM schema_versions ORDER BY version DESC LIMIT 1")
            result = cursor.fetchone()
            return result[0] if result else 0
        except sqlite3.OperationalError:
            # schema_versions 表不存在
            return 0
    
    def register_migration(self, version: int, migration_fn: Callable[[sqlite3.Connection], None]):
        """
        注册迁移函数。
        
        Args:
            version: 目标版本号
            migration_fn: 迁移函数，接受 connection 参数
        """
        if not hasattr(self, "_migrations"):
            self._migrations: Dict[int, Callable] = {}
        self._migrations[version] = migration_fn
    
    def migrate(self, target_version: int):
        """
        执行迁移（expand-migrate-contract 模式）。
        
        Args:
            target_version: 目标版本号
        
        Raises:
            ValueError: 目标版本小于当前版本
        """
        current_version = self.get_current_version()
        
        if target_version < current_version:
            raise ValueError(
                f"Target version {target_version} is less than current version {current_version}"
            )
        
        if target_version == current_version:
            return  # 已是最新版本
        
        # 1. Expand: 创建临时迁移表（如果需要）
        self._expand_phase(current_version, target_version)
        
        try:
            # 2. Migrate: 逐版本迁移
            for version in range(current_version + 1, target_version + 1):
                if hasattr(self, "_migrations") and version in self._migrations:
                    migration_fn = self._migrations[version]
                    self._execute_with_backup(migration_fn, version)
                else:
                    # 默认迁移：创建 schema_versions 表
                    self._create_schema_versions_table()
            
            # 3. Contract: 清理临时表（如果需要）
            self._contract_phase(current_version, target_version)
            
        except Exception as e:
            # 迁移失败时恢复备份
            self._restore_backup()
            raise e
    
    def _execute_with_backup(
        self,
        migration_fn: Callable[[sqlite3.Connection], None],
        version: int
    ):
        """
        带备份的迁移执行。
        
        Args:
            migration_fn: 迁移函数
            version: 目标版本号
        """
        # 自动备份（使用时间戳避免覆盖）
        timestamp = int(time.time() * 1000)
        backup_path = self.backup_dir / f"deepflow_backup_v{version}_{timestamp}.db"
        self._backup_db(backup_path)
        
        try:
            # 执行迁移
            migration_fn(self.internal_conn)
            self.internal_conn.commit()
            
            # 更新版本号
            self._update_version(version)
            
        except Exception:
            # 迁移失败，恢复备份
            self._restore_backup(backup_path)
            raise
    
    def _backup_db(self, backup_path: Path):
        """
        备份数据库。
        
        Args:
            backup_path: 备份文件路径
        """
        # 执行 checkpoint 确保 WAL 数据写入
        self.engine.checkpoint(mode="FULL")
        
        # 复制数据库文件
        db_file = Path(self.db_path)
        if db_file.exists():
            shutil.copy2(db_file, backup_path)
    
    def _restore_backup(self, backup_path: Optional[Path] = None):
        """
        恢复备份。
        
        Args:
            backup_path: 备份文件路径（默认使用最新备份）
        """
        if backup_path is None:
            # 查找最新备份
            backups = list(self.backup_dir.glob("deepflow_backup_v*.db"))
            if not backups:
                return
            backup_path = max(backups, key=lambda p: p.stat().st_mtime)
        
        if backup_path.exists():
            # 执行 checkpoint
            self.engine.checkpoint(mode="FULL")
            
            # 恢复备份
            db_file = Path(self.db_path)
            if db_file.exists():
                db_file.unlink()
            shutil.copy2(backup_path, db_file)
    
    def _update_version(self, version: int):
        """
        更新版本号。
        
        Args:
            version: 新版本号
        """
        cursor = self.internal_conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO schema_versions (version, migrated_at)
            VALUES (?, ?)
        """, (version, time.strftime("%Y-%m-%d %H:%M:%S")))
        self.internal_conn.commit()
    
    def _create_schema_versions_table(self):
        """创建 schema_versions 表。"""
        cursor = self.internal_conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_versions (
                version INTEGER PRIMARY KEY,
                migrated_at TEXT NOT NULL
            )
        """)
        self.internal_conn.commit()
    
    def create_initial_schema(self):
        """创建初始 schema（V1）"""
        cursor = self.internal_conn.cursor()
        
        # 1. events 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        
        # 2. runs 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                completed_at TEXT,
                status TEXT,
                total_duration_ms INTEGER,
                total_cost REAL,
                total_tokens INTEGER
            )
        """)
        
        # 3. prompts 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id TEXT NOT NULL,
                version TEXT NOT NULL,
                raw_hash TEXT NOT NULL,
                effective_hash TEXT NOT NULL,
                content TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(prompt_id, version)
            )
        """)
        
        # 4. gate_results 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gate_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                result TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        
        # 5. run_summaries 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS run_summaries (
                run_id TEXT PRIMARY KEY,
                total_duration_ms INTEGER,
                total_cost REAL,
                total_tokens INTEGER,
                retry_count INTEGER,
                gate_pass_rate REAL,
                event_count INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        
        # 6. health_metrics 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                threshold REAL,
                status TEXT,
                measured_at TEXT NOT NULL
            )
        """)
        
        # 7. collection_coverage VIEW
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS collection_coverage AS
            SELECT 
                e.run_id,
                COUNT(DISTINCT e.event_type) as event_types_count,
                COUNT(DISTINCT e.worker_id) as workers_count,
                COUNT(DISTINCT e.phase_name) as phases_count,
                MIN(e.timestamp) as first_event,
                MAX(e.timestamp) as last_event,
                SUM(e.duration_ms) as total_duration_ms,
                SUM(e.tokens_in) as total_tokens_in,
                SUM(e.tokens_out) as total_tokens_out,
                SUM(e.cost) as total_cost
            FROM events e
            GROUP BY e.run_id
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_run_id_timestamp 
            ON events(run_id, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_worker_id_timestamp 
            ON events(worker_id, timestamp)
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_run_type_seq 
            ON events(run_id, event_type, event_seq)
        """)
        
        self.internal_conn.commit()
        
        # 初始化版本表
        self._create_schema_versions_table()
        self._update_version(1)
    
    def drop_schema(self):
        """删除所有表和视图。"""
        cursor = self.internal_conn.cursor()
        
        # 删除视图
        cursor.execute("DROP VIEW IF EXISTS collection_coverage")
        
        # 删除表
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
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        
        # 删除索引
        indexes = [
            "idx_events_run_id_timestamp",
            "idx_events_worker_id_timestamp",
            "idx_events_run_type_seq",
        ]
        
        for index in indexes:
            cursor.execute(f"DROP INDEX IF EXISTS {index}")
        
        self.internal_conn.commit()
    
    def _expand_phase(self, current_version: int, target_version: int):
        """
        Expand 阶段：创建临时表或新结构。
        
        Args:
            current_version: 当前版本
            target_version: 目标版本
        """
        # 默认实现：无额外操作
        pass
    
    def _contract_phase(self, current_version: int, target_version: int):
        """
        Contract 阶段：清理临时表或旧结构。
        
        Args:
            current_version: 当前版本
            target_version: 目标版本
        """
        # 默认实现：无清理操作
        pass
    
    def close(self):
        """关闭内部连接。"""
        if self._internal_conn is not None:
            self._internal_conn.close()
            self._internal_conn = None
    
    def __enter__(self):
        """支持上下文管理器。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时自动关闭连接。"""
        self.close()
