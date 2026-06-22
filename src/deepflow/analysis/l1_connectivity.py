"""
L1 连通性检查引擎。

实现 WP-006（L1 连通性检查引擎）的核心功能：
- 阶段完整性检查
- 数据完整性评分
- Per-event-type 覆盖率
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import time

from src.deepflow.storage.sqlite_engine import SQLiteEngine


@dataclass
class L1Result:
    """L1 连通性检查结果"""
    run_id: str
    phase_completeness: dict  # {phase_name: bool}
    all_phases_present: bool
    data_integrity_score: float  # 0.0 ~ 1.0
    event_type_coverage: dict  # {event_type: "present" | "missing" | "optional"}
    duration_ms: float  # 检查耗时
    timestamp: str


class L1Engine:
    """
    L1 连通性检查引擎
    
    实现 WP-006：L1 连通性检查引擎，负责：
    1. 阶段完整性检查 — 检查 phase_start/phase_end 配对
    2. 数据完整性评分 — 加权计算（critical 类型权重 0.2，normal 0.1）
    3. Per-event-type 覆盖率 — 区分 always/conditionally/optional
    
    性能目标：< 100ms 完成检查
    """
    
    # 预期事件类型列表及其期望级别
    EXPECTED_EVENT_TYPES = {
        "phase_start": "always_expected",
        "phase_end": "always_expected",
        "worker_start": "optional",
        "worker_end": "optional",
        "gate_check": "conditionally_expected",
        "retry": "conditionally_expected",
        "error": "conditionally_expected",
        "llm_call": "conditionally_expected",
    }
    
    def __init__(self, engine: SQLiteEngine):
        """
        初始化 L1 连通性检查引擎
        
        Args:
            engine: SQLite 引擎实例
        """
        self._engine = engine
    
    def check(self, run_id: str) -> L1Result:
        """
        执行 L1 连通性检查
        
        执行流程：
        1. 阶段完整性 — 检查 phase_start/phase_end 配对
        2. 数据完整性评分 — 加权计算（critical 类型权重 0.2，normal 0.1）
        3. Per-event-type 覆盖率 — 区分 always/conditionally/optional
        
        性能目标：< 100ms 完成
        
        Args:
            run_id: 运行 ID
            
        Returns:
            L1Result: 检查结果
        """
        start_time = time.time()
        
        # 1. 阶段完整性检查
        phase_completeness = self._check_phase_completeness(run_id)
        all_phases_present = all(phase_completeness.values())
        
        # 2. 数据完整性评分
        data_integrity_score = self._calculate_integrity_score(run_id)
        
        # 3. Per-event-type 覆盖率
        event_type_coverage = self._check_event_coverage(run_id)
        
        # 计算耗时
        duration_ms = (time.time() - start_time) * 1000
        
        return L1Result(
            run_id=run_id,
            phase_completeness=phase_completeness,
            all_phases_present=all_phases_present,
            data_integrity_score=data_integrity_score,
            event_type_coverage=event_type_coverage,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    def _check_phase_completeness(self, run_id: str) -> dict:
        """
        检查每个阶段的 start/end 配对
        
        Args:
            run_id: 运行 ID
            
        Returns:
            {phase_name: bool} 每个阶段是否有完整的 start/end 配对
        """
        # 获取所有 phase_name 的Distinct 值
        results = self._engine.execute("""
            SELECT DISTINCT phase_name FROM events 
            WHERE run_id = ? AND phase_name IS NOT NULL
        """, (run_id,))
        
        phases = [row["phase_name"] for row in results]
        
        result = {}
        for phase in phases:
            # 检查是否有 phase_start
            start_results = self._engine.execute("""
                SELECT COUNT(*) as count FROM events
                WHERE run_id = ? AND phase_name = ? AND event_type = ?
            """, (run_id, phase, "phase_start"))
            start_count = start_results[0]["count"]
            
            # 检查是否有 phase_end
            end_results = self._engine.execute("""
                SELECT COUNT(*) as count FROM events
                WHERE run_id = ? AND phase_name = ? AND event_type = ?
            """, (run_id, phase, "phase_end"))
            end_count = end_results[0]["count"]
            
            # 至少要有 begin 和 end
            result[phase] = start_count >= 1 and end_count >= 1
        
        return result
    
    def _calculate_integrity_score(self, run_id: str) -> float:
        """
        数据完整性评分
        
        计算逻辑：
        - always_expected 类型存在 → +0.2/类型
        - conditionally_expected 类型存在 → +0.1/类型（如果有条件触发）
        - optional 类型不影响分数
        
        Args:
            run_id: 运行 ID
            
        Returns:
            float: 完整性评分（0.0 ~ 1.0）
        """
        # 获取运行中实际存在的事件类型
        event_results = self._engine.execute("""
            SELECT DISTINCT event_type FROM events WHERE run_id = ?
        """, (run_id, ))
        existing_types = {row["event_type"] for row in event_results}
        
        score = 0.0
        max_score = 0.0
        
        for event_type, expected_level in self.EXPECTED_EVENT_TYPES.items():
            if expected_level == "always_expected":
                max_score += 0.2
                if event_type in existing_types:
                    score += 0.2
            elif expected_level == "conditionally_expected":
                max_score += 0.1
                if event_type in existing_types:
                    score += 0.1
            # optional 不影响分数
        
        # 返回评分（归一化到 0.0 ~ 1.0）
        if max_score == 0:
            return 1.0
        return min(1.0, score / max_score)
    
    def _check_event_coverage(self, run_id: str) -> dict:
        """
        Per-event-type 覆盖率
        
        分类规则：
        - always_expected: 必须存在，否则 missing
        - conditionally_expected: 根据条件判断，存在则 present，否则 optional
        - optional: 存在则 present，不存在则 optional
        
        Args:
            run_id: 运行 ID
            
        Returns:
            {event_type: "present" | "missing" | "optional"}
        """
        # 获取运行中实际存在的事件类型
        event_results = self._engine.execute("""
            SELECT DISTINCT event_type FROM events WHERE run_id = ?
        """, (run_id, ))
        existing_types = {row["event_type"] for row in event_results}
        
        result = {}
        for event_type, expected_level in self.EXPECTED_EVENT_TYPES.items():
            if expected_level == "always_expected":
                # always_expected: 必须存在
                result[event_type] = "present" if event_type in existing_types else "missing"
            elif expected_level == "conditionally_expected":
                # conditionally_expected: 条件性
                result[event_type] = "present" if event_type in existing_types else "optional"
            else:  # optional
                # optional: 存在则 present，否则 optional
                result[event_type] = "present" if event_type in existing_types else "optional"
        
        return result
