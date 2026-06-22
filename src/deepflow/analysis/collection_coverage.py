"""
Per-Event-Type 覆盖率追踪（DF-004）

实现覆盖率追踪和告警功能：
- 区分 always_expected / conditionally_expected / optional
- 条件告警：有 gate 但 gate_check=0 → critical
- error=0 → 永不告警（正确行为）
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from src.deepflow.storage.sqlite_engine import SQLiteEngine


@dataclass
class CoverageAlert:
    """覆盖率告警信息"""
    event_type: str
    status: str  # "ok" | "warn" | "critical"
    consecutive_missing: int
    message: str


class CoverageTracker:
    """
    Per-Event-Type 覆盖率追踪
    
    实现 DF-004：Per-Event-Type 覆盖率追踪，提供：
    - 区分 always_expected / conditionally_expected / optional
    - 条件告警：有 gate 但 gate_check=0 → critical
    - error=0 → 永不告警（正确行为）
    - 告警阈值：连续缺失达到阈值时发出告警
    """
    
    # 期望事件类型定义
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
    
    # 告警阈值
    CRITICAL_THRESHOLD = 2  # 连续 2 次缺失 → critical
    WARN_THRESHOLD = 3      # 连续 3 次缺失 → warn
    
    def __init__(self, engine: SQLiteEngine):
        """
        初始化覆盖率追踪器
        
        Args:
            engine: SQLite 引擎实例
        """
        self._engine = engine
    
    def evaluate(self, run_id: str) -> List[CoverageAlert]:
        """
        评估当前运行的事件覆盖率
        
        评估逻辑：
        1. 获取当前运行的事件类型
        2. 计算每个类型的覆盖率状态
        3. 检查条件告警（如：有 gate 但 gate_check=0）
        4. 检查历史连续缺失次数
        
        Args:
            run_id: 运行 ID
            
        Returns:
            list[CoverageAlert]: 告警列表
        """
        alerts: List[CoverageAlert] = []
        
        # 获取当前运行的事件类型
        event_results = self._engine.execute("""
            SELECT DISTINCT event_type FROM events WHERE run_id = ?
        """, (run_id, ))
        existing_types = {row["event_type"] for row in event_results}
        
        # 获取此运行是否有 gate 检查
        gate_check_count = self._engine.execute("""
            SELECT COUNT(*) as count FROM gate_results WHERE run_id = ?
        """, (run_id, ))[0]["count"]
        
        for event_type, expected_level in self.EXPECTED_EVENT_TYPES.items():
            is_present = event_type in existing_types
            
            # 计算连续缺失次数（历史趋势）
            consecutive_missing = self._count_consecutive_missing(event_type, run_id)
            
            # 跳过当前缺失但历史正常的事件（阈值未达）
            if not is_present and consecutive_missing < self.WARN_THRESHOLD:
                continue
            
            # 构建告警消息
            if is_present:
                status = "ok"
                message = f"{event_type} 已覆盖"
            else:
                # 根据类型和条件计算状态
                status = self._calculate_status(event_type, consecutive_missing, gate_check_count)
                missing_reason = self._get_missing_reason(event_type, is_present, gate_check_count)
                message = f"{event_type} 未覆盖：{missing_reason}"
            
            alerts.append(CoverageAlert(
                event_type=event_type,
                status=status,
                consecutive_missing=consecutive_missing,
                message=message
            ))
        
        return alerts
    
    def get_historical_coverage(self, event_type: str, last_n: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近 N 次运行的覆盖率趋势
        
        Args:
            event_type: 事件类型
            last_n: 最近 N 次运行
            
        Returns:
            list[dict]: 每次运行的覆盖率信息
        """
        # 获取最近 N 次运行
        runs = self._engine.execute("""
            SELECT DISTINCT run_id FROM events 
            ORDER BY run_id DESC LIMIT ?
        """, (last_n, ))
        
        result = []
        for run_row in runs:
            run_id = run_row["run_id"]
            
            # 检查事件类型是否存在
            count_results = self._engine.execute("""
                SELECT COUNT(*) as count FROM events 
                WHERE run_id = ? AND event_type = ?
            """, (run_id, event_type))
            
            is_present = count_results[0]["count"] > 0
            
            result.append({
                "run_id": run_id,
                "event_type": event_type,
                "is_present": is_present,
                "timestamp": self._get_run_timestamp(run_id)
            })
        
        return result
    
    def _count_consecutive_missing(self, event_type: str, current_run_id: str) -> int:
        """
        计算事件类型连续缺失的次数
        
        从当前运行开始向前追溯，统计连续缺失的运行次数
        
        Args:
            event_type: 事件类型
            current_run_id: 当前运行 ID
            
        Returns:
            int: 连续缺失次数
        """
        # 获取所有运行 ID（按时间倒序）
        runs = self._engine.execute("""
            SELECT DISTINCT run_id FROM events 
            ORDER BY run_id DESC
        """)
        
        consecutive_missing = 0
        found_current = False
        
        for run_row in runs:
            run_id = run_row["run_id"]
            
            # 找到当前运行
            if run_id == current_run_id:
                found_current = True
                continue
            
            # 如果还没找到当前运行，跳过
            if not found_current:
                continue
            
            # 检查事件类型是否存在
            count_results = self._engine.execute("""
                SELECT COUNT(*) as count FROM events 
                WHERE run_id = ? AND event_type = ?
            """, (run_id, event_type))
            
            if count_results[0]["count"] > 0:
                # 找到有事件的运行，停止计数
                break
            
            # 连续缺失
            consecutive_missing += 1
        
        return consecutive_missing
    
    def _calculate_status(
        self, 
        event_type: str, 
        consecutive_missing: int,
        gate_check_count: int
    ) -> str:
        """
        计算覆盖率状态
        
        逻辑：
        - error=0 → ok（正确行为，永不告警）
        - 有 gate 但 gate_check=0 且连续缺失 >= 2 → critical
        - 连续缺失 >= warn_threshold → warn
        - 连续缺失 >= critical_threshold → critical
        - 其他 → ok
        
        Args:
            event_type: 事件类型
            consecutive_missing: 连续缺失次数
            gate_check_count: gate 检查次数
            
        Returns:
            str: "ok" | "warn" | "critical"
        """
        # error=0 → 永不告警（正确行为）
        if event_type == "error" and gate_check_count == 0:
            return "ok"
        
        # 有 gate 但 gate_check=0
        if event_type == "gate_check" and gate_check_count > 0:
            # 获取 gate_check 事件是否存在
            count_results = self._engine.execute("""
                SELECT COUNT(*) as count FROM events WHERE event_type = ?
            """, ("gate_check", ))
            
            if count_results[0]["count"] == 0:
                return "critical"
        
        # 根据连续缺失次数判断
        if consecutive_missing >= self.CRITICAL_THRESHOLD:
            return "critical"
        elif consecutive_missing >= self.WARN_THRESHOLD:
            return "warn"
        
        return "ok"
    
    def _get_missing_reason(
        self, 
        event_type: str, 
        is_present: bool,
        gate_check_count: int
    ) -> str:
        """
        获取缺失原因描述
        
        Args:
            event_type: 事件类型
            is_present: 是否存在
            gate_check_count: gate 检查次数
            
        Returns:
            str: 缺失原因描述
        """
        if event_type == "error":
            return "正常完成，无错误事件（符合预期）"
        elif event_type == "gate_check" and gate_check_count > 0:
            return "检测到 gate_check 显式声明但事件缺失（异常）"
        elif event_type == "llm_call":
            return "LLM 调用事件缺失（可能使用了缓存或本地执行）"
        elif event_type == "phase_start" or event_type == "phase_end":
            return "阶段事件缺失（可能阶段未正确启动/结束）"
        elif event_type == "worker_start" or event_type == "worker_end":
            return "Worker 事件缺失（可选，不影响主要流程）"
        elif event_type == "retry":
            return "重试事件缺失（可能未触发重试）"
        
        return "事件类型缺失（需检查采集器配置）"
    
    def _get_run_timestamp(self, run_id: str) -> Optional[str]:
        """
        获取运行的时间戳
        
        Args:
            run_id: 运行 ID
            
        Returns:
            Optional[str]: 运行的起始时间戳，如果不存在则返回 None
        """
        results = self._engine.execute("""
            SELECT MIN(timestamp) as timestamp FROM events WHERE run_id = ?
        """, (run_id, ))
        
        if results and len(results) > 0:
            return results[0]["timestamp"]
        return None
