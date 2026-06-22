"""
SQLite 存储引擎核心实现。

提供 WAL 模式支持、PRAGMA 调优和批量插入操作。
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Any, Optional


class SQLiteEngine:
    """
    SQLite 存储引擎，支持 WAL 模式和自动 PRAGMA 调优。
    
    Args:
        db_path: 数据库文件路径（支持 :memory: 内存数据库）
        timeout: 连接超时时间（秒）
    """
    
    def __init__(self, db_path: str, timeout: float = 5.0):
        """
        初始化 SQLite 引擎。
        
        Args:
            db_path: 数据库文件路径
            timeout: 连接超时时间（秒）
        """
        self.db_path = db_path
        self.timeout = timeout
        self._conn: Optional[sqlite3.Connection] = None
        self._thread_id: Optional[int] = None
    
    @property
    def conn(self) -> sqlite3.Connection:
        """获取数据库连接（延迟初始化 + 线程检查）。"""
        current_thread_id = threading.get_ident()
        
        # 如果连接不存在或在线程切换后，创建新连接
        if self._conn is None or self._thread_id != current_thread_id:
            if self._conn is not None:
                self._conn.close()
            
            self._conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                isolation_level=None,  # 手动控制事务
                check_same_thread=False,  # 允许多线程访问
            )
            self._conn.row_factory = sqlite3.Row
            self._thread_id = current_thread_id
            self.apply_pragmas()
        
        return self._conn
    
    def get_pragma_config(self) -> Dict[str, Any]:
        """
        返回 PRAGMA 配置字典。
        
        Returns:
            包含以下键的字典：
            - journal_mode: WAL
            - synchronous: NORMAL
            - busy_timeout: 5000 (ms)
            - temp_store: MEMORY
            - wal_autocheckpoint: 100 (pages)
            - cache_size: -64000 (KB)
        """
        return {
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "busy_timeout": 5000,
            "temp_store": "MEMORY",
            "wal_autocheckpoint": 100,
            "cache_size": -64000,
        }
    
    def apply_pragmas(self):
        """应用所有 PRAGMA 配置到当前连接。"""
        config = self.get_pragma_config()
        cursor = self.conn.cursor()
        
        for pragma_name, value in config.items():
            # WAL 模式需要特殊处理（必须在连接创建前设置）
            # 这里采用查询方式应用（WAL 会在后续连接生效）
            if pragma_name == "journal_mode":
                cursor.execute(f"PRAGMA {pragma_name} = {value}")
            else:
                cursor.execute(f"PRAGMA {pragma_name} = {value}")
        
        self.conn.commit()
    
    def checkpoint(self, mode: str = "PASSIVE"):
        """
        执行 WAL checkpoint。
        
        Args:
            mode: Checkpoint 模式：
                - PASSIVE: 只 checkpoint 可以立即完成的页面
                - FULL: 等待直到所有读者完成
                - RESTART: 完成 checkpoint 并重置 WAL
                - TRUNCATE: 完成 checkpoint 并截断 WAL
        """
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA wal_checkpoint({mode})")
        result = cursor.fetchone()
        self.conn.commit()
        return dict(result) if result else {}
    
    def insert_events(self, events: List[Dict[str, Any]]) -> int:
        """
        批量插入事件。
        
        Args:
            events: 事件列表，每个事件包含：
                - run_id: 运行ID
                - event_type: 事件类型
                - event_seq: 事件序号
                - timestamp: 时间戳
                - worker_id: 工作者ID（可选）
                - phase_name: 阶段名称（可选）
                - duration_ms: 持续时间（毫秒，可选）
                - tokens_in: 输入token数（可选）
                - tokens_out: 输出token数（可选）
                - cost: 成本（可选）
                - model: 模型名称（可选）
                - status: 状态（可选）
                - error_type: 错误类型（可选）
                - error_message: 错误消息（可选）
                - metadata: 元数据（JSON字符串，可选）
                - collector_source: 采集来源（可选）
        
        Returns:
            成功插入的事件数量
        """
        if not events:
            return 0
        
        cursor = self.conn.cursor()
        inserted = 0
        
        for event in events:
            try:
                cursor.execute("""
                    INSERT INTO events (
                        run_id, event_type, event_seq, timestamp,
                        worker_id, phase_name, duration_ms, tokens_in,
                        tokens_out, cost, model, status,
                        error_type, error_message, metadata, collector_source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.get("run_id"),
                    event.get("event_type"),
                    event.get("event_seq"),
                    event.get("timestamp"),
                    event.get("worker_id"),
                    event.get("phase_name"),
                    event.get("duration_ms"),
                    event.get("tokens_in"),
                    event.get("tokens_out"),
                    event.get("cost"),
                    event.get("model"),
                    event.get("status"),
                    event.get("error_type"),
                    event.get("error_message"),
                    json.dumps(event.get("metadata")) if isinstance(event.get("metadata"), dict) else event.get("metadata"),
                    event.get("collector_source"),
                ))
                inserted += 1
            except sqlite3.IntegrityError:
                # UNIQUE 约束冲突，跳过
                continue
        
        self.conn.commit()
        return inserted
    
    def execute(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """
        执行 SQL 查询。
        
        Args:
            sql: SQL 查询语句
            params: 查询参数元组
        
        Returns:
            查询结果列表
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        self.conn.commit()
        return [dict(row) for row in rows]
    
    def execute_many(self, sql: str, param_list: List[tuple]) -> int:
        """
        执行多条 SQL 语句。
        
        Args:
            sql: SQL 语句模板
            param_list: 参数列表
        
        Returns:
            受影响的行数
        """
        cursor = self.conn.cursor()
        cursor.executemany(sql, param_list)
        affected = cursor.rowcount
        self.conn.commit()
        return affected
    
    def close(self):
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
    
    def __enter__(self):
        """支持上下文管理器。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时自动关闭连接。"""
        self.close()


def get_pragma_config() -> Dict[str, Any]:
    """
    返回默认 PRAGMA 配置。
    
    Returns:
        PRAGMA 配置字典
    """
    return {
        "journal_mode": "WAL",
        "synchronous": "NORMAL",
        "busy_timeout": 5000,
        "temp_store": "MEMORY",
        "wal_autocheckpoint": 100,
        "cache_size": -64000,
    }
