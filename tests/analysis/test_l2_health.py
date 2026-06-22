"""
L2 健康度诊断引擎测试。

测试 Worker 耗时告警、context 使用率监控、token 异常检测、重试模式分类。
"""

import pytest
import json
import tempfile
import time
from pathlib import Path
from typing import List, Dict, Any

from src.deepflow.analysis.l2_health import (
    AlertLevel,
    RetryPattern,
    WorkerAlert,
    L2Result,
    L2Engine,
)
from src.deepflow.storage.sqlite_engine import SQLiteEngine


class TestL2HealthEngine:
    """L2 健康度诊断引擎测试类。"""
    
    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录。"""
        with tempfile.TemporaryDirectory(prefix="deepflow_test_") as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def engine(self, temp_dir: Path) -> SQLiteEngine:
        """创建 SQLite 引擎并初始化 schema。"""
        db_path = str(temp_dir / "test.db")
        eng = SQLiteEngine(db_path)
        
        # 创建完整 schema
        cursor = eng.conn.cursor()
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
        eng.conn.commit()
        
        yield eng
        eng.close()
    
    def test_default_config(self):
        """测试默认配置。"""
        # 创建内存数据库
        eng = SQLiteEngine(":memory:")
        l2_engine = L2Engine(eng)
        
        config = l2_engine._config
        
        assert config["worker_duration_multiplier"] == 2.0
        assert config["min_runs_for_relative"] == 5
        assert config["context_usage_warn"] == 0.8
        assert config["context_usage_critical"] == 0.95
        assert config["token_anomaly_multiplier"] == 3.0
        
        eng.close()
    
    def test_custom_config(self, engine: SQLiteEngine):
        """测试自定义配置。"""
        custom_config = {
            "worker_duration_multiplier": 3.0,
            "min_runs_for_relative": 10,
            "context_usage_warn": 0.75,
            "context_usage_critical": 0.9,
            "token_anomaly_multiplier": 2.5,
        }
        
        l2_engine = L2Engine(engine, custom_config)
        
        assert l2_engine._config["worker_duration_multiplier"] == 3.0
        assert l2_engine._config["min_runs_for_relative"] == 10
        assert l2_engine._config["context_usage_warn"] == 0.75
        assert l2_engine._config["context_usage_critical"] == 0.9
        assert l2_engine._config["token_anomaly_multiplier"] == 2.5
    
    def test_worker_duration_normal(self, engine: SQLiteEngine):
        """测试 Worker 耗时正常（无告警）。"""
        # 插入测试数据：耗时在正常范围内
        events = [
            {
                "run_id": "run-001",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
            {
                "run_id": "run-002",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:01:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 110,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
            {
                "run_id": "run-003",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:02:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 120,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
            {
                "run_id": "run-004",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:03:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 115,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
            {
                "run_id": "run-005",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:04:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 105,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
            {
                "run_id": "run-006",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:05:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 110,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-006")
        
        # 应该没有耗时告警
        duration_alerts = [a for a in result.worker_alerts if a.metric == "duration_ms"]
        assert len(duration_alerts) == 0
    
    def test_worker_duration_warning(self, engine: SQLiteEngine):
        """测试 Worker 耗时告警（warn 级别）。"""
        # 插入历史数据：中位数约为 100ms
        events = [
            {"run_id": f"run-{i:03d}", "event_type": "transformer", "event_seq": 1,
             "timestamp": f"2026-06-22T19:{i:02d}:00.000Z", "worker_id": "worker-001",
             "phase_name": "inference", "duration_ms": 100 + i * 5,
             "tokens_in": 1000, "tokens_out": 500, "cost": 0.01, "model": "test-model",
             "status": "success"}
            for i in range(1, 6)
        ]
        
        # 当前 run：耗时 250ms（中位数约 125ms * 2.0 = 250ms 阈值）
        events.append({
            "run_id": "run-current",
            "event_type": "transformer",
            "event_seq": 1,
            "timestamp": "2026-06-22T20:00:00.000Z",
            "worker_id": "worker-001",
            "phase_name": "inference",
            "duration_ms": 250,  # 刚好达到阈值
            "tokens_in": 1000,
            "tokens_out": 500,
            "cost": 0.01,
            "model": "test-model",
            "status": "success",
        })
        
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-current")
        
        # 应该有耗时告警
        duration_alerts = [a for a in result.worker_alerts if a.metric == "duration_ms"]
        assert len(duration_alerts) >= 1
        assert duration_alerts[0].level == AlertLevel.WARN
    
    def test_worker_duration_critical(self, engine: SQLiteEngine):
        """测试 Worker 耗时严重告警（critical 级别）。"""
        # 插入历史数据：中位数约为 100ms
        events = [
            {"run_id": f"run-{i:03d}", "event_type": "transformer", "event_seq": 1,
             "timestamp": f"2026-06-22T19:{i:02d}:00.000Z", "worker_id": "worker-001",
             "phase_name": "inference", "duration_ms": 100,
             "tokens_in": 1000, "tokens_out": 500, "cost": 0.01, "model": "test-model",
             "status": "success"}
            for i in range(1, 6)
        ]
        
        # 当前 run：耗时 800ms（中位数 100ms * 2.0 * 1.5 = 300ms，800 > 300）
        events.append({
            "run_id": "run-current",
            "event_type": "transformer",
            "event_seq": 1,
            "timestamp": "2026-06-22T20:00:00.000Z",
            "worker_id": "worker-001",
            "phase_name": "inference",
            "duration_ms": 800,  # 超过 1.5 倍阈值，critical
            "tokens_in": 1000,
            "tokens_out": 500,
            "cost": 0.01,
            "model": "test-model",
            "status": "success",
        })
        
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-current")
        
        # 应该有严重耗时告警
        duration_alerts = [a for a in result.worker_alerts if a.metric == "duration_ms"]
        assert len(duration_alerts) >= 1
        assert duration_alerts[0].level == AlertLevel.CRITICAL
    
    def test_context_usage_normal(self, engine: SQLiteEngine):
        """测试 Context 使用率正常。"""
        # 插入数据：使用率约 1%
        events = [
            {
                "run_id": "run-001",
                "event_type": "start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 1000,  # 1000 / 128000 = 0.78%
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        # 使用率应该正常
        usage = result.context_usage.get("worker-001", 0)
        assert usage < 0.8  # < 80%
    
    def test_context_usage_warn(self, engine: SQLiteEngine):
        """测试 Context 使用率告警（warn 级别）。"""
        # 插入数据：使用率约 85%
        events = [
            {
                "run_id": "run-001",
                "event_type": "start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 110000,  # 110000 / 128000 = 85.9%
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        # 使用率应该告警
        usage = result.context_usage.get("worker-001", 0)
        assert usage >= 0.8  # >= 80%
    
    def test_context_usage_critical(self, engine: SQLiteEngine):
        """测试 Context 使用率严重告警（critical 级别）。"""
        # 插入数据：使用率约 98%
        events = [
            {
                "run_id": "run-001",
                "event_type": "start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 125000,  # 125000 / 128000 = 97.7%
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        # 使用率应该严重告警
        usage = result.context_usage.get("worker-001", 0)
        assert usage >= 0.95  # >= 95%
    
    def test_token_anomaly_normal(self, engine: SQLiteEngine):
        """测试 Token 异常检测正常（无异常）。"""
        # 插入多次运行：token 总量约 1500
        for i in range(1, 6):
            events = [
                {
                    "run_id": f"run-{i:03d}",
                    "event_type": "start",
                    "event_seq": 1,
                    "timestamp": f"2026-06-22T19:{i:02d}:00.000Z",
                    "worker_id": "worker-001",
                    "phase_name": "inference",
                    "duration_ms": 100,
                    "tokens_in": 1000,
                    "tokens_out": 500,
                    "cost": 0.01,
                    "model": "test-model",
                    "status": "success",
                },
            ]
            engine.insert_events(events)
        
        # 当前 run：token 总量 1500（正常）
        events = [
            {
                "run_id": "run-current",
                "event_type": "start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-current")
        
        # 应该没有 token 异常
        assert len(result.token_anomalies) == 0
    
    def test_token_anomaly_high(self, engine: SQLiteEngine):
        """测试 Token 异常检测（高 token）。"""
        # 插入多次运行：token 总量约 1500
        for i in range(1, 6):
            events = [
                {
                    "run_id": f"run-{i:03d}",
                    "event_type": "start",
                    "event_seq": 1,
                    "timestamp": f"2026-06-22T19:{i:02d}:00.000Z",
                    "worker_id": "worker-001",
                    "phase_name": "inference",
                    "duration_ms": 100,
                    "tokens_in": 1000,
                    "tokens_out": 500,
                    "cost": 0.01,
                    "model": "test-model",
                    "status": "success",
                },
            ]
            engine.insert_events(events)
        
        # 当前 run：token 总量 5000（3 倍中位数，异常）
        events = [
            {
                "run_id": "run-current",
                "event_type": "start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 5000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-current")
        
        # 应该有 token 异常
        assert len(result.token_anomalies) >= 1
        assert result.token_anomalies[0]["is_anomaly"] is True
    
    def test_token_anomaly_low(self, engine: SQLiteEngine):
        """测试 Token 异常检测（低 token）。"""
        # 插入多次运行：token 总量约 1500
        for i in range(1, 6):
            events = [
                {
                    "run_id": f"run-{i:03d}",
                    "event_type": "start",
                    "event_seq": 1,
                    "timestamp": f"2026-06-22T19:{i:02d}:00.000Z",
                    "worker_id": "worker-001",
                    "phase_name": "inference",
                    "duration_ms": 100,
                    "tokens_in": 1000,
                    "tokens_out": 500,
                    "cost": 0.01,
                    "model": "test-model",
                    "status": "success",
                },
            ]
            engine.insert_events(events)
        
        # 当前 run：token 总量 200（中位数 1500 的 1/7.5，小于 1/3，异常）
        events = [
            {
                "run_id": "run-current",
                "event_type": "start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 200,
                "tokens_out": 50,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        engine.insert_events(events)
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-current")
        
        # 应该有 token 异常
        assert len(result.token_anomalies) >= 1
        assert result.token_anomalies[0]["is_anomaly"] is True
    
    def test_retry_pattern_fast_converge(self, engine: SQLiteEngine):
        """测试重试模式：快速收敛（首次 retry 即 pass）。"""
        # 插入 gate 结果：fail, pass（仅2次尝试）
        gate_results = [
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate1",
             "result": "fail", "timestamp": "2026-06-22T20:00:00.000Z"},  # 初始尝试失败
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate2",
             "result": "pass", "timestamp": "2026-06-22T20:00:01.000Z"},  # 首次 retry 即通过
        ]
        
        cursor = engine.conn.cursor()
        for gr in gate_results:
            cursor.execute("""
                INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (gr["run_id"], gr["phase_name"], gr["gate_name"], gr["result"], gr["timestamp"]))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        assert result.retry_patterns["quality_gate"] == RetryPattern.FAST_CONVERGE
    
    def test_retry_pattern_converging(self, engine: SQLiteEngine):
        """测试重试模式：收敛型（pass 率单调上升）。"""
        # 插入 gate 结果：fail, fail, pass, pass
        gate_results = [
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate1",
             "result": "fail", "timestamp": "2026-06-22T20:00:00.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate2",
             "result": "fail", "timestamp": "2026-06-22T20:00:01.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate3",
             "result": "pass", "timestamp": "2026-06-22T20:00:02.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate4",
             "result": "pass", "timestamp": "2026-06-22T20:00:03.000Z"},
        ]
        
        cursor = engine.conn.cursor()
        for gr in gate_results:
            cursor.execute("""
                INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (gr["run_id"], gr["phase_name"], gr["gate_name"], gr["result"], gr["timestamp"]))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        assert result.retry_patterns["quality_gate"] == RetryPattern.CONVERGING
    
    def test_retry_pattern_oscillating(self, engine: SQLiteEngine):
        """测试重试模式：振荡型（pass/fail 交替 ≥ 2 次）。"""
        # 插入 gate 结果：fail, pass, fail, pass
        gate_results = [
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate1",
             "result": "fail", "timestamp": "2026-06-22T20:00:00.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate2",
             "result": "pass", "timestamp": "2026-06-22T20:00:01.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate3",
             "result": "fail", "timestamp": "2026-06-22T20:00:02.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate4",
             "result": "pass", "timestamp": "2026-06-22T20:00:03.000Z"},
        ]
        
        cursor = engine.conn.cursor()
        for gr in gate_results:
            cursor.execute("""
                INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (gr["run_id"], gr["phase_name"], gr["gate_name"], gr["result"], gr["timestamp"]))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        assert result.retry_patterns["quality_gate"] == RetryPattern.OSCILLATING
    
    def test_retry_pattern_diverging(self, engine: SQLiteEngine):
        """测试重试模式：发散型（持续 fail）。"""
        # 插入 gate 结果：fail, fail, fail
        gate_results = [
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate1",
             "result": "fail", "timestamp": "2026-06-22T20:00:00.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate2",
             "result": "fail", "timestamp": "2026-06-22T20:00:01.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate3",
             "result": "fail", "timestamp": "2026-06-22T20:00:02.000Z"},
        ]
        
        cursor = engine.conn.cursor()
        for gr in gate_results:
            cursor.execute("""
                INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (gr["run_id"], gr["phase_name"], gr["gate_name"], gr["result"], gr["timestamp"]))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        assert result.retry_patterns["quality_gate"] == RetryPattern.DIVERGING
    
    def test_diagnose_performance(self, engine: SQLiteEngine):
        """测试诊断性能：< 500ms。"""
        # 插入大量数据
        for run_id in range(1, 21):
            events = [
                {
                    "run_id": f"run-{run_id:03d}",
                    "event_type": "transformer",
                    "event_seq": 1,
                    "timestamp": f"2026-06-22T19:{run_id:02d}:00.000Z",
                    "worker_id": f"worker-{run_id % 5:03d}",
                    "phase_name": "inference",
                    "duration_ms": 100 + run_id * 10,
                    "tokens_in": 1000,
                    "tokens_out": 500,
                    "cost": 0.01,
                    "model": "test-model",
                    "status": "success",
                },
            ]
            engine.insert_events(events)
        
        # 插入 gate 结果
        for phase in ["quality_gate", "logic_gate"]:
            for i in range(1, 6):
                cursor = engine.conn.cursor()
                cursor.execute("""
                    INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, ("run-current", phase, f"gate{i}", "pass", f"2026-06-22T20:00:{i:02d}.000Z"))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        
        # 诊断性能测试
        start = time.time()
        result = l2_engine.diagnose("run-current")
        duration_ms = (time.time() - start) * 1000
        
        assert duration_ms < 500
        assert result.duration_ms < 500
    
    def test_diagnose_result_structure(self, engine: SQLiteEngine):
        """测试诊断结果结构。"""
        # 插入数据
        events = [
            {
                "run_id": "run-001",
                "event_type": "transformer",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "worker_id": "worker-001",
                "phase_name": "inference",
                "duration_ms": 100,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "test-model",
                "status": "success",
            },
        ]
        engine.insert_events(events)
        
        cursor = engine.conn.cursor()
        cursor.execute("""
            INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, ("run-001", "quality_gate", "gate1", "pass", "2026-06-22T20:00:01.000Z"))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        # 检查结果结构
        assert result.run_id == "run-001"
        assert isinstance(result.worker_alerts, list)
        assert isinstance(result.retry_patterns, dict)
        assert isinstance(result.context_usage, dict)
        assert isinstance(result.token_anomalies, list)
        assert result.duration_ms > 0
        assert result.timestamp > ""
    
    def test_multiple_phases_retry_patterns(self, engine: SQLiteEngine):
        """测试多个 phase 的重试模式分类。"""
        # 插入 gate 结果：不同 phase 不同模式
        gate_results = [
            # quality_gate: fast_converge（2次尝试：fail, pass）
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate1",
             "result": "fail", "timestamp": "2026-06-22T20:00:00.000Z"},
            {"run_id": "run-001", "phase_name": "quality_gate", "gate_name": "gate2",
             "result": "pass", "timestamp": "2026-06-22T20:00:01.000Z"},
            # logic_gate: diverging
            {"run_id": "run-001", "phase_name": "logic_gate", "gate_name": "gate1",
             "result": "fail", "timestamp": "2026-06-22T20:01:00.000Z"},
            {"run_id": "run-001", "phase_name": "logic_gate", "gate_name": "gate2",
             "result": "fail", "timestamp": "2026-06-22T20:01:01.000Z"},
            {"run_id": "run-001", "phase_name": "logic_gate", "gate_name": "gate3",
             "result": "fail", "timestamp": "2026-06-22T20:01:02.000Z"},
        ]
        
        cursor = engine.conn.cursor()
        for gr in gate_results:
            cursor.execute("""
                INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (gr["run_id"], gr["phase_name"], gr["gate_name"], gr["result"], gr["timestamp"]))
        engine.conn.commit()
        
        l2_engine = L2Engine(engine)
        result = l2_engine.diagnose("run-001")
        
        assert result.retry_patterns["quality_gate"] == RetryPattern.FAST_CONVERGE
        assert result.retry_patterns["logic_gate"] == RetryPattern.DIVERGING
