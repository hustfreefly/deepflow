"""
L2 健康度诊断引擎集成测试。

测试与 SQLite 存储引擎的完整集成。
"""

import pytest
import tempfile
import time
from pathlib import Path

from src.deepflow.analysis.l2_health import (
    AlertLevel,
    RetryPattern,
    L2Result,
    L2Engine,
)
from src.deepflow.storage.sqlite_engine import SQLiteEngine


class TestL2HealthIntegration:
    """L2 健康度诊断引擎集成测试类。"""
    
    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录。"""
        with tempfile.TemporaryDirectory(prefix="deepflow_test_") as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def engine_with_schema(self, temp_dir: Path) -> SQLiteEngine:
        """创建 SQLite 引擎并初始化完整 schema。"""
        db_path = str(temp_dir / "deepflow_test.db")
        engine = SQLiteEngine(db_path)
        
        # 初始化 schema
        cursor = engine.conn.cursor()
        
        # events 表
        cursor.execute("""
            CREATE TABLE events (
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
        
        # gate_results 表
        cursor.execute("""
            CREATE TABLE gate_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                result TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        
        engine.conn.commit()
        yield engine
        engine.close()
    
    def test_full_diagnose_workflow(self, engine_with_schema: SQLiteEngine):
        """测试完整的诊断工作流。"""
        engine = engine_with_schema
        
        # 插入历史数据（5次运行）
        for i in range(1, 6):
            events = [
                {
                    "run_id": f"run-{i:03d}",
                    "event_type": "transformer",
                    "event_seq": 1,
                    "timestamp": f"2026-06-22T19:{i:02d}:00.000Z",
                    "worker_id": "worker-001",
                    "phase_name": "inference",
                    "duration_ms": 100 + i * 10,
                    "tokens_in": 1000,
                    "tokens_out": 500,
                    "cost": 0.01,
                    "model": "gpt-4",
                    "status": "success",
                },
            ]
            engine.insert_events(events)
            
            # gate 结果
            cursor = engine.conn.cursor()
            for phase in ["quality_gate", "logic_gate"]:
                cursor.execute("""
                    INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (f"run-{i:03d}", phase, "gate1", "pass", f"2026-06-22T20:00:{i:02d}.000Z"))
        engine.conn.commit()
        
        # 插入当前 run（耗时异常：300ms，中位数约150ms，2倍阈值=300ms）
        events = [
            {
                "run_id": "run-current",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T21:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 350,  # > 300ms，触发告警
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        engine.insert_events(events)
        
        cursor = engine.conn.cursor()
        for phase in ["quality_gate", "logic_gate"]:
            cursor.execute("""
                INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, ("run-current", phase, "gate1", "pass", "2026-06-22T21:00:01.000Z"))
        engine.conn.commit()
        
        # 执行诊断
        l2_engine = L2Engine(engine)
        start = time.time()
        result = l2_engine.diagnose("run-current")
        duration_ms = (time.time() - start) * 1000
        
        # 验证结果
        assert result.run_id == "run-current"
        assert isinstance(result, L2Result)
        assert result.duration_ms < 500  # 性能要求
        
        # 验证耗时告警
        duration_alerts = [a for a in result.worker_alerts if a.metric == "duration_ms"]
        assert len(duration_alerts) >= 1
        assert duration_alerts[0].level in (AlertLevel.WARN, AlertLevel.CRITICAL)
        assert duration_alerts[0].value > duration_alerts[0].threshold
        
        # 验证 context 使用率
        usage = result.context_usage.get("worker-001", 0)
        assert usage >= 0  # 正常值
        
        # 验证 token 异常（应该没有异常，因为 token 量正常）
        # 1500 tokens，中位数约 1500，偏差应该在正常范围内
        
        # 验证重试模式（所有 pass，应该是 fast_converge 或 converging）
        # 由于历史 run 中是 pass，当前 run 也是 pass，会被识别为 converging
        # （因为 pass 率单调上升：0 -> 1）
        for phase, pattern in result.retry_patterns.items():
            assert pattern in (RetryPattern.FAST_CONVERGE, RetryPattern.CONVERGING)
        
        # 验证诊断耗时
        assert duration_ms < 500
    
    def test_multiple_workers(self, engine_with_schema: SQLiteEngine):
        """测试多个 worker 的诊断。"""
        engine = engine_with_schema
        
        # 插入多个 worker 的数据
        workers = ["worker-001", "worker-002", "worker-003"]
        
        for run_id in range(1, 6):
            for worker_id in workers:
                events = [
                    {
                        "run_id": f"run-{run_id:03d}",
                        "event_type": "transformer",
                        "event_seq": 1,
                        "timestamp": f"2026-06-22T19:{run_id:02d}:00.000Z",
                        "worker_id": worker_id,
                        "phase_name": "inference",
                        "duration_ms": 100,
                        "tokens_in": 1000,
                        "tokens_out": 500,
                        "cost": 0.01,
                        "model": "gpt-4",
                        "status": "success",
                    },
                ]
                engine.insert_events(events)
        
        # 插入 current run（某个 worker 耗时异常）
        events = [
            {
                "run_id": "run-current",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T21:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 500,  # 异常
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-current",
                "event_type": "transformer",
                "event_seq": 2,
                "timestamp": "2026-06-22T21:00:00.500Z",
                "worker_id": "worker-002",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        engine.insert_events(events)
        
        cursor = engine.conn.cursor()
        cursor.execute("""
            INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, ("run-current", "quality_gate", "gate1", "pass", "2026-06-22T21:00:01.000Z"))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-current")
        
        # 验证 worker-001 有告警，worker-002 没有
        worker_001_alerts = [a for a in result.worker_alerts 
                            if a.worker_id == "worker-001"]
        worker_002_alerts = [a for a in result.worker_alerts 
                            if a.worker_id == "worker-002"]
        
        assert len(worker_001_alerts) >= 1  # worker-001 应该有告警
        assert len(worker_002_alerts) == 0  # worker-002 应该没有告警
    
    def test_empty_run(self, engine_with_schema: SQLiteEngine):
        """测试空 run 的诊断。"""
        engine = engine_with_schema
        
        # 插入一些历史数据
        events = [
            {
                "run_id": "run-001",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T19:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        engine.insert_events(events)
        
        # 诊断一个不存在的 run
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("non-existent-run")
        
        # 应该返回空结果
        assert len(result.worker_alerts) == 0
        assert len(result.token_anomalies) == 0
        assert len(result.retry_patterns) == 0
        assert len(result.context_usage) == 0
