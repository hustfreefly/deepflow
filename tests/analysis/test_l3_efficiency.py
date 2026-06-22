"""
L3 效率分析引擎测试。

测试 WP-011：L3 效率分析引擎的完整功能：
- 耗时排名（Worker/Phase 两个维度）
- Token 浪费检测（retry_count × avg_tokens）
- 重试成本分析（token/cost/duration 增量）
- 跨运行趋势对比（duration/cost/tokens/pass_rate 四项变化）
- 性能：< 2s
- 边界情况（无 retry、单次运行）
"""

import pytest
import time
from pathlib import Path
from typing import List, Dict, Any

from src.deepflow.storage.sqlite_engine import SQLiteEngine
from src.deepflow.storage.schema_manager import SchemaManager
from src.deepflow.analysis.l3_efficiency import L3Engine, EfficiencyReport


# 测试数据库路径
TEST_DB_PATH = ":memory:"


def create_test_schema(engine: SQLiteEngine):
    """创建测试用的完整 schema"""
    schema_manager = SchemaManager(engine)
    schema_manager.create_initial_schema()


def insert_events(engine: SQLiteEngine, events: List[Dict[str, Any]]):
    """插入测试事件"""
    schema_manager = SchemaManager(engine)
    schema_manager.create_initial_schema()
    engine.insert_events(events)


def insert_gate_results(engine: SQLiteEngine, gate_results: List[Dict[str, Any]]):
    """插入 gate 结果"""
    cursor = engine.conn.cursor()
    for result in gate_results:
        cursor.execute("""
            INSERT INTO gate_results (run_id, phase_name, gate_name, result, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (
            result.get("run_id"),
            result.get("phase_name"),
            result.get("gate_name"),
            result.get("result"),
            result.get("timestamp", "2026-06-22T20:00:00.000Z"),
        ))
    engine.conn.commit()


class TestL3Efficiency:
    """L3 效率分析引擎测试类"""
    
    def test_duration_ranking(self, temp_dir: Path):
        """
        测试耗时排名正确性
        
        - Worker 耗时排名
        - Phase 耗时排名
        - 包含百分比占比
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建事件数据
        events = [
            # Phase 1: data_collection
            {
                "run_id": "run-001",
                "event_type": "phase_start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "data_collection",
            },
            {
                "run_id": "run-001",
                "event_type": "llm_call",
                "event_seq": 2,
                "timestamp": "2026-06-22T20:00:01.000Z",
                "phase_name": "data_collection",
                "worker_id": "worker-001",
                "duration_ms": 1000,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-001",
                "event_type": "llm_call",
                "event_seq": 3,
                "timestamp": "2026-06-22T20:00:02.000Z",
                "phase_name": "data_collection",
                "worker_id": "worker-002",
                "duration_ms": 2000,
                "tokens_in": 2000,
                "tokens_out": 1000,
                "cost": 0.02,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-001",
                "event_type": "phase_end",
                "event_seq": 4,
                "timestamp": "2026-06-22T20:00:03.000Z",
                "phase_name": "data_collection",
            },
            # Phase 2: analysis
            {
                "run_id": "run-001",
                "event_type": "phase_start",
                "event_seq": 5,
                "timestamp": "2026-06-22T20:00:04.000Z",
                "phase_name": "analysis",
            },
            {
                "run_id": "run-001",
                "event_type": "llm_call",
                "event_seq": 6,
                "timestamp": "2026-06-22T20:00:05.000Z",
                "phase_name": "analysis",
                "worker_id": "worker-001",
                "duration_ms": 1500,
                "tokens_in": 1500,
                "tokens_out": 750,
                "cost": 0.015,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-001",
                "event_type": "phase_end",
                "event_seq": 7,
                "timestamp": "2026-06-22T20:00:06.000Z",
                "phase_name": "analysis",
            },
        ]
        insert_events(engine, events)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-001")
        
        # 验证耗时排名
        assert len(report.duration_ranking) > 0
        
        # 验证 Worker 排名
        worker_rankings = [r for r in report.duration_ranking if r["type"] == "worker"]
        assert len(worker_rankings) >= 2
        
        # worker-002 总耗时 2000ms，应该排在前面
        worker_002 = next((w for w in worker_rankings if w["worker_id"] == "worker-002"), None)
        assert worker_002 is not None
        assert worker_002["total_duration_ms"] == 2000
        
        # 验证百分比占比
        assert "percentage" in worker_002
        assert worker_002["percentage"] >= 0
        
        # 验证 Phase 排名
        phase_rankings = [r for r in report.duration_ranking if r["type"] == "phase"]
        assert len(phase_rankings) >= 2
        
        # data_collection 总耗时 3000ms，analysis 总耗时 1500ms
        data_collection = next((p for p in phase_rankings if p["phase_name"] == "data_collection"), None)
        analysis = next((p for p in phase_rankings if p["phase_name"] == "analysis"), None)
        
        assert data_collection is not None
        assert analysis is not None
        assert data_collection["total_duration_ms"] == 3000
        assert analysis["total_duration_ms"] == 1500
        
        # 验证百分比
        assert data_collection["percentage"] > analysis["percentage"]
        
        engine.close()
    
    def test_token_waste_detection(self, temp_dir: Path):
        """
        测试 Token 浪费检测
        
        - 找出 retry 导致重复执行的 worker
        - 计算浪费的 tokens = retry_count × avg_tokens_per_call
        - 计算浪费的 cost
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建事件数据（包含 retry 事件）
        events = [
            # Normal execution
            {
                "run_id": "run-002",
                "event_type": "llm_call",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
            # Retry 1
            {
                "run_id": "run-002",
                "event_type": "retry",
                "event_seq": 2,
                "timestamp": "2026-06-22T20:00:01.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "retry",
            },
            # Retry 2
            {
                "run_id": "run-002",
                "event_type": "retry",
                "event_seq": 3,
                "timestamp": "2026-06-22T20:00:02.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "retry",
            },
            # Final success
            {
                "run_id": "run-002",
                "event_type": "llm_call",
                "event_seq": 4,
                "timestamp": "2026-06-22T20:00:03.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        insert_events(engine, events)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-002")
        
        # 验证 Token 浪费检测
        assert len(report.token_waste) > 0
        
        # worker-001 应该有浪费记录
        waste = next((w for w in report.token_waste if w["worker_id"] == "worker-001"), None)
        assert waste is not None
        
        # 验证浪费计算
        # retry_count = 2（retry 事件数）
        # avg_tokens_in = 1000（所有事件的平均）
        # waste_tokens_in = 2 × 1000 = 2000
        assert waste["retry_count"] == 2
        assert waste["waste_tokens_in"] == 2000
        
        # waste_cost = 2 × 0.01 = 0.02
        assert waste["waste_cost"] == 0.02
        
        engine.close()
    
    def test_no_retry_no_waste(self, temp_dir: Path):
        """
        测试无 retry 情况下的 Token 浪费检测
        
        - 没有 retry 事件
        - token_waste 应该为空列表
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建事件数据（无 retry）
        events = [
            {
                "run_id": "run-003",
                "event_type": "llm_call",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        insert_events(engine, events)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-003")
        
        # 验证 no retry no waste
        assert len(report.token_waste) == 0
        
        engine.close()
    
    def test_retry_cost_analysis(self, temp_dir: Path):
        """
        测试重试成本分析
        
        - 总 retry 次数
        - 总额外 token 消耗
        - 总额外 cost
        - 总额外 duration
        - 按 phase 分组
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建事件数据（包含 retry 事件）
        events = [
            # Phase 1: generation
            {
                "run_id": "run-004",
                "event_type": "llm_call",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-004",
                "event_type": "retry",
                "event_seq": 2,
                "timestamp": "2026-06-22T20:00:01.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "retry",
            },
            # Phase 2: validation
            {
                "run_id": "run-004",
                "event_type": "llm_call",
                "event_seq": 3,
                "timestamp": "2026-06-22T20:00:02.000Z",
                "phase_name": "validation",
                "worker_id": "worker-002",
                "duration_ms": 300,
                "tokens_in": 500,
                "tokens_out": 250,
                "cost": 0.005,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        insert_events(engine, events)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-004")
        
        # 验证重试成本分析
        assert report.retry_cost is not None
        assert report.retry_cost["total_retry_count"] == 1
        assert report.retry_cost["total_extra_tokens_in"] == 1000
        assert report.retry_cost["total_extra_cost"] == 0.01
        
        # 验证按 phase 分组
        assert len(report.retry_cost["by_phase"]) >= 1
        generation_phase = next(
            (p for p in report.retry_cost["by_phase"] if p["phase_name"] == "generation"),
            None
        )
        assert generation_phase is not None
        assert generation_phase["retry_count"] == 1
        
        engine.close()
    
    def test_trend_comparison(self, temp_dir: Path):
        """
        测试跨运行趋势对比
        
        - 总 duration 变化（绝对 + 百分比）
        - 总 cost 变化
        - 总 tokens 变化
        - gate pass rate 变化
        - 按 phase 对比
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建 baseline run
        baseline_events = [
            {
                "run_id": "run-baseline",
                "event_type": "llm_call",
                "event_seq": 1,
                "timestamp": "2026-06-22T19:00:00.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 1000,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        insert_events(engine, baseline_events)
        insert_gate_results(engine, [
            {
                "run_id": "run-baseline",
                "phase_name": "generation",
                "gate_name": "quality_gate",
                "result": "pass",
                "timestamp": "2026-06-22T19:00:01.000Z",
            },
        ])
        
        # 构建 current run（耗时更少）
        current_events = [
            {
                "run_id": "run-current",
                "event_type": "llm_call",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 800,
                "tokens_out": 400,
                "cost": 0.008,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        insert_events(engine, current_events)
        insert_gate_results(engine, [
            {
                "run_id": "run-current",
                "phase_name": "generation",
                "gate_name": "quality_gate",
                "result": "pass",
                "timestamp": "2026-06-22T20:00:01.000Z",
            },
        ])
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-current", compare_with="run-baseline")
        
        # 验证趋势对比
        assert report.trend_comparison is not None
        assert report.trend_comparison["baseline_run_id"] == "run-baseline"
        assert report.trend_comparison["current_run_id"] == "run-current"
        
        # Duration 变化：current 500ms < baseline 1000ms
        duration_change = report.trend_comparison["duration_change"]
        assert duration_change["current"] == 500
        assert duration_change["baseline"] == 1000
        assert duration_change["absolute_change"] == -500
        assert duration_change["percentage_change"] == -50.0
        assert duration_change["is_improvement"] is True
        
        # Cost 变化
        cost_change = report.trend_comparison["cost_change"]
        assert cost_change["current"] == 0.008
        assert cost_change["baseline"] == 0.01
        assert cost_change["absolute_change"] == -0.002
        
        # Tokens 变化
        tokens_change = report.trend_comparison["tokens_change"]
        assert tokens_change["current"] == 1200  # 800 + 400
        assert tokens_change["baseline"] == 1500  # 1000 + 500
        
        # Gate pass rate 改变（都是 100%）
        pass_rate_change = report.trend_comparison["pass_rate_change"]
        assert pass_rate_change["current"] == 100.0
        assert pass_rate_change["baseline"] == 100.0
        
        # 验证按 phase 对比
        assert len(report.trend_comparison["by_phase"]) >= 1
        generation_phase = next(
            (p for p in report.trend_comparison["by_phase"] if p["phase_name"] == "generation"),
            None
        )
        assert generation_phase is not None
        assert generation_phase["absolute_change"] == -500  # 500 - 1000
        
        engine.close()
    
    def test_performance_under_2s(self, temp_dir: Path):
        """
        测试性能：< 2s 完成分析
        
        为确保性能，使用内存数据库并预填充大量数据
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 预填充大量事件
        events = []
        for i in range(100):
            events.append({
                "run_id": "run-perf",
                "event_type": "llm_call",
                "event_seq": i,
                "timestamp": f"2026-06-22T20:00:{i:02d}.000Z",
                "phase_name": f"phase_{i // 10}",
                "worker_id": f"worker_{i % 10}",
                "duration_ms": 100 + i * 10,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            })
        
        # 添加一些 retry 事件
        for i in range(10):
            events.append({
                "run_id": "run-perf",
                "event_type": "retry",
                "event_seq": 100 + i,
                "timestamp": f"2026-06-22T20:{50 + i:02d}:00.000Z",
                "phase_name": f"phase_{i // 5}",
                "worker_id": f"worker_{i % 10}",
                "duration_ms": 100,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "retry",
            })
        
        insert_events(engine, events)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        start_time = time.time()
        report = l3_engine.analyze("run-perf")
        duration_ms = (time.time() - start_time) * 1000
        
        # 性能检查
        assert report.duration_ms < 2000  # < 2s
        assert duration_ms < 2000
        
        engine.close()
    
    def test_run_summaries(self, temp_dir: Path):
        """
        测试获取最近 N 次运行的摘要数据
        
        - 获取最近 10 次运行
        - 包含 duration、cost、tokens、pass_rate
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建 5 次运行
        for run_num in range(5):
            run_id = f"run-summary-{run_num}"
            events = [
                {
                    "run_id": run_id,
                    "event_type": "llm_call",
                    "event_seq": 1,
                    "timestamp": f"2026-06-22T20:{run_num:02d}:00.000Z",
                    "phase_name": "generation",
                    "worker_id": "worker-001",
                    "duration_ms": 500 + run_num * 100,
                    "tokens_in": 1000,
                    "tokens_out": 500,
                    "cost": 0.01,
                    "model": "gpt-4",
                    "status": "success",
                },
            ]
            insert_events(engine, events)
            insert_gate_results(engine, [
                {
                    "run_id": run_id,
                    "phase_name": "generation",
                    "gate_name": "quality_gate",
                    "result": "pass",
                    "timestamp": f"2026-06-22T20:{run_num:02d}:01.000Z",
                },
            ])
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        summaries = l3_engine.get_run_summaries(last_n=10)
        
        # 验证摘要数量
        assert len(summaries) == 5
        
        # 验证摘要内容
        for summary in summaries:
            assert "run_id" in summary
            assert "total_duration_ms" in summary
            assert "total_cost" in summary
            assert "total_tokens" in summary
            assert "pass_rate" in summary
        
        # 验证排序（按 run_id 升序）
        run_ids = [s["run_id"] for s in summaries]
        assert run_ids == sorted(run_ids)
        
        engine.close()
    
    def test_empty_run(self, temp_dir: Path):
        """
        测试空运行的边界情况
        
        - 没有事件
        - 返回空列表或零值
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-empty")
        
        # 验证空运行的结果
        assert report.duration_ranking == []
        assert report.token_waste == []
        assert report.retry_cost["total_retry_count"] == 0
        
        engine.close()
    
    def test_single_run_without_comparison(self, temp_dir: Path):
        """
        测试单次运行（无对比）的边界情况
        
        - 只提供 run_id
        - trend_comparison 为 None
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建单次运行
        events = [
            {
                "run_id": "run-single",
                "event_type": "llm_call",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        insert_events(engine, events)
        
        # 执行 L3 效率分析（无对比）
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-single")
        
        # 验证单次运行的结果
        assert report.trend_comparison is None
        assert report.duration_ranking is not None
        
        engine.close()


class TestL3EdgeCases:
    """L3 效率分析边缘情况测试"""
    
    def test_multiple_workers_same_phase(self, temp_dir: Path):
        """
        测试多个 worker 属于同一个 phase
        
        - Worker 耗时分别统计
        - Phase 耗时汇总
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建事件数据
        events = [
            {
                "run_id": "run-multi-worker",
                "event_type": "phase_start",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "processing",
            },
            {
                "run_id": "run-multi-worker",
                "event_type": "llm_call",
                "event_seq": 2,
                "timestamp": "2026-06-22T20:00:01.000Z",
                "phase_name": "processing",
                "worker_id": "worker-a",
                "duration_ms": 1000,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-multi-worker",
                "event_type": "llm_call",
                "event_seq": 3,
                "timestamp": "2026-06-22T20:00:02.000Z",
                "phase_name": "processing",
                "worker_id": "worker-b",
                "duration_ms": 1500,
                "tokens_in": 1500,
                "tokens_out": 750,
                "cost": 0.015,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-multi-worker",
                "event_type": "phase_end",
                "event_seq": 4,
                "timestamp": "2026-06-22T20:00:03.000Z",
                "phase_name": "processing",
            },
        ]
        insert_events(engine, events)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-multi-worker")
        
        # 验证 Worker 排名
        worker_rankings = [r for r in report.duration_ranking if r["type"] == "worker"]
        assert len(worker_rankings) == 2
        
        worker_a = next((w for w in worker_rankings if w["worker_id"] == "worker-a"), None)
        worker_b = next((w for w in worker_rankings if w["worker_id"] == "worker-b"), None)
        
        assert worker_a is not None
        assert worker_b is not None
        assert worker_a["total_duration_ms"] == 1000
        assert worker_b["total_duration_ms"] == 1500
        
        # 验证 Phase 排名（汇总两个 worker 的耗时）
        phase_rankings = [r for r in report.duration_ranking if r["type"] == "phase"]
        processing_phase = next((p for p in phase_rankings if p["phase_name"] == "processing"), None)
        
        assert processing_phase is not None
        assert processing_phase["total_duration_ms"] == 2500  # 1000 + 1500
        
        engine.close()
    
    def test_worker_with_various_durations(self, temp_dir: Path):
        """
        测试 worker 的多种耗时情况
        
        - 包含 min/max/avg 统计
        """
        db_path = str(temp_dir / "test.db")
        engine = SQLiteEngine(db_path)
        create_test_schema(engine)
        
        # 构建事件数据（worker 多次调用）
        events = [
            {
                "run_id": "run-various-durations",
                "event_type": "llm_call",
                "event_seq": 1,
                "timestamp": "2026-06-22T20:00:00.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 100,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-various-durations",
                "event_type": "llm_call",
                "event_seq": 2,
                "timestamp": "2026-06-22T20:00:01.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 500,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
            {
                "run_id": "run-various-durations",
                "event_type": "llm_call",
                "event_seq": 3,
                "timestamp": "2026-06-22T20:00:02.000Z",
                "phase_name": "generation",
                "worker_id": "worker-001",
                "duration_ms": 1000,
                "tokens_in": 1000,
                "tokens_out": 500,
                "cost": 0.01,
                "model": "gpt-4",
                "status": "success",
            },
        ]
        insert_events(engine, events)
        
        # 执行 L3 效率分析
        l3_engine = L3Engine(engine)
        report = l3_engine.analyze("run-various-durations")
        
        # 验证 Worker 统计
        worker_rankings = [r for r in report.duration_ranking if r["type"] == "worker"]
        worker = next((w for w in worker_rankings if w["worker_id"] == "worker-001"), None)
        
        assert worker is not None
        assert worker["total_duration_ms"] == 1600  # 100 + 500 + 1000
        assert worker["call_count"] == 3
        assert abs(worker["avg_duration_ms"] - 533.33) < 0.1  # 1600 / 3
        assert worker["max_duration_ms"] == 1000
        assert worker["min_duration_ms"] == 100
        
        engine.close()


# 帮助函数：临时目录 fixture
@pytest.fixture
def temp_dir() -> Path:
    """创建临时目录用于测试数据库"""
    import tempfile
    tmp_path = tempfile.mkdtemp(prefix="deepflow_l3_test_")
    try:
        yield Path(tmp_path)
    finally:
        import shutil
        shutil.rmtree(tmp_path, ignore_errors=True)
