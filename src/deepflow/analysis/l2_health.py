"""
L2 健康度诊断引擎。

实现 Worker 耗时告警、context 使用率监控、token 异常检测、重试模式分类。
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum

from src.deepflow.storage.sqlite_engine import SQLiteEngine


class AlertLevel(Enum):
    """告警级别枚举。"""
    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"


class RetryPattern(Enum):
    """重试模式枚举。"""
    FAST_CONVERGE = "fast_converge"     # 首次 retry 即 pass
    CONVERGING = "converging"           # gate pass 率单调上升
    OSCILLATING = "oscillating"         # pass/fail 交替 ≥ 2 次
    DIVERGING = "diverging"             # 持续 fail


@dataclass
class WorkerAlert:
    """Worker 告警数据类。"""
    worker_id: str
    level: AlertLevel
    metric: str
    value: float
    threshold: float
    message: str


@dataclass
class L2Result:
    """L2 健康度诊断结果。"""
    run_id: str
    worker_alerts: list[WorkerAlert]
    retry_patterns: dict  # {phase_name: RetryPattern}
    context_usage: dict   # {worker_id: usage_ratio}
    token_anomalies: list[dict]
    duration_ms: float
    timestamp: str


class L2Engine:
    """
    L2 健康度诊断引擎。
    
    提供以下诊断能力：
    - Worker 耗时告警（相对阈值：中位数倍数）
    - Context 使用率监控
    - Token 异常检测
    - 重试模式分类
    
    性能目标：< 500ms 完成诊断
    
    Args:
        engine: SQLite 存储引擎实例
        config: 配置字典，包含阈值等参数
    """
    
    def __init__(self, engine: SQLiteEngine, config: Optional[dict] = None):
        """
        初始化 L2 引擎。
        
        Args:
            engine: SQLite 存储引擎实例
            config: 配置字典，包含阈值等参数
        """
        self._engine = engine
        default_config = self._default_config()
        # 合并用户配置和默认配置
        self._config = {**default_config}
        if config:
            self._config.update(config)
    
    def _default_config(self) -> dict:
        """
        返回默认阈值配置。
        
        Returns:
            默认配置字典：
            - worker_duration_multiplier: 2.0 (中位数的 2 倍)
            - min_runs_for_relative: 5 (至少 5 次运行后才用相对阈值)
            - context_usage_warn: 0.8 (80% 使用率告警)
            - context_usage_critical: 0.95 (95% 使用率严重告警)
            - token_anomaly_multiplier: 3.0 (token 数 3 倍偏差)
        """
        return {
            "worker_duration_multiplier": 2.0,
            "min_runs_for_relative": 5,
            "context_usage_warn": 0.8,
            "context_usage_critical": 0.95,
            "token_anomaly_multiplier": 3.0,
        }
    
    def diagnose(self, run_id: str) -> L2Result:
        """
        执行 L2 健康度诊断。
        
        包含以下子诊断：
        1. Worker 耗时告警（相对阈值：中位数倍数）
        2. Context 使用率监控
        3. Token 异常检测
        4. 重试模式分类
        
        Args:
            run_id: 运行ID
            
        Returns:
            L2Result 对象，包含所有诊断结果
            
        性能：< 500ms 完成
        """
        start_time = time.time()
        
        worker_alerts = self._check_worker_duration(run_id)
        context_usage = self._check_context_usage(run_id)
        token_anomalies = self._check_token_anomalies(run_id)
        retry_patterns = self._classify_retry_patterns(run_id)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return L2Result(
            run_id=run_id,
            worker_alerts=worker_alerts,
            retry_patterns=retry_patterns,
            context_usage=context_usage,
            token_anomalies=token_anomalies,
            duration_ms=duration_ms,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    
    def _get_median(self, values: list[float]) -> float:
        """
        计算中位数。
        
        Args:
            values: 数值列表
            
        Returns:
            中位数值
        """
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        mid = n // 2
        
        if n % 2 == 0:
            return (sorted_values[mid - 1] + sorted_values[mid]) / 2
        else:
            return sorted_values[mid]
    
    def _check_worker_duration(self, run_id: str) -> list[WorkerAlert]:
        """
        Worker 耗时告警。
        
        逻辑：
        - 获取该 worker 的历史中位数耗时（排除当前 run）
        - 当前耗时 > 中位数 * multiplier → 告警
        - 至少 min_runs_for_relative 次运行后才使用相对阈值
        
        Args:
            run_id: 运行ID
            
        Returns:
            WorkerAlert 列表
        """
        alerts: list[WorkerAlert] = []
        multiplier = self._config["worker_duration_multiplier"]
        min_runs = self._config["min_runs_for_relative"]
        
        # 查询当前 run_id 的所有 events
        events = self._engine.execute(
            """
            SELECT worker_id, duration_ms
            FROM events
            WHERE run_id = ?
            AND duration_ms IS NOT NULL
            AND duration_ms > 0
            """,
            (run_id,)
        )
        
        if not events:
            return alerts
        
        # 按 worker_id 分组
        from collections import defaultdict
        worker_current_durations: dict[str, float] = {}
        
        for event in events:
            worker_id = event["worker_id"]
            duration_ms = event["duration_ms"]
            # 取当前 run 中该 worker 的最大 duration
            worker_current_durations[worker_id] = max(
                worker_current_durations.get(worker_id, 0),
                duration_ms
            )
        
        # 对每个 worker 进行告警判断
        for worker_id, current_duration in worker_current_durations.items():
            if current_duration == 0:
                continue
            
            # 查询该 worker 在其他 run 中的历史耗时
            history = self._engine.execute(
                """
                SELECT duration_ms
                FROM events
                WHERE worker_id = ?
                AND run_id != ?
                AND duration_ms IS NOT NULL
                AND duration_ms > 0
                """,
                (worker_id, run_id)
            )
            
            if not history:
                continue
            
            # 计算历史中位数
            history_durations = [h["duration_ms"] for h in history]
            
            # 至少需要 min_runs 次历史运行才使用相对阈值
            if len(history_durations) < min_runs:
                continue
            
            median_duration = self._get_median(history_durations)
            
            # 告警逻辑
            if median_duration > 0:
                threshold = median_duration * multiplier
                
                if current_duration > threshold:
                    if current_duration > threshold * 1.5:
                        level = AlertLevel.CRITICAL
                    else:
                        level = AlertLevel.WARN
                    
                    alerts.append(WorkerAlert(
                        worker_id=worker_id,
                        level=level,
                        metric="duration_ms",
                        value=current_duration,
                        threshold=threshold,
                        message=f"Worker {worker_id} duration {current_duration:.2f}ms > "
                               f"{threshold:.2f}ms (median: {median_duration:.2f}ms * {multiplier})",
                    ))
        
        return alerts
    
    def _check_context_usage(self, run_id: str) -> dict[str, float]:
        """
        Context 使用率检查。
        
        计算每个 worker 的 context 使用率：
        - tokens_used / context_window_size
        - > 80% → warn
        - > 95% → critical
        
        Args:
            run_id: 运行ID
            
        Returns:
            {worker_id: usage_ratio} 字典
        """
        # 假设 context window 为 128K tokens（常见值）
        CONTEXT_WINDOW_SIZE = 128000
        
        # 查询当前 run_id 的 token 使用情况
        events = self._engine.execute(
            """
            SELECT worker_id, SUM(tokens_in) as total_tokens_in, 
                   SUM(tokens_out) as total_tokens_out
            FROM events
            WHERE run_id = ?
            GROUP BY worker_id
            """,
            (run_id,)
        )
        
        context_usage: dict[str, float] = {}
        
        for event in events:
            worker_id = event["worker_id"]
            tokens_in = event["total_tokens_in"] or 0
            tokens_out = event["total_tokens_out"] or 0
            
            # tokens_used 通常指输入 tokens（prompt tokens）
            tokens_used = tokens_in
            usage_ratio = tokens_used / CONTEXT_WINDOW_SIZE
            
            context_usage[worker_id] = usage_ratio
        
        return context_usage
    
    def _check_token_anomalies(self, run_id: str) -> list[dict]:
        """
        Token 异常检测。
        
        逻辑：
        - 与历史中位数对比
        - 偏差 > multiplier → 异常
        
        Args:
            run_id: 运行ID
            
        Returns:
            Token 异常列表
        """
        anomalies: list[dict] = []
        multiplier = self._config["token_anomaly_multiplier"]
        
        # 查询当前 run_id 的 token 总量
        events = self._engine.execute(
            """
            SELECT SUM(tokens_in) as total_tokens_in, 
                   SUM(tokens_out) as total_tokens_out,
                   SUM(tokens_in) + SUM(tokens_out) as total_tokens
            FROM events
            WHERE run_id = ?
            """,
            (run_id,)
        )
        
        current_run = events[0] if events else {}
        current_total = current_run.get("total_tokens") or 0
        
        if current_total == 0:
            return anomalies
        
        # 查询历史所有 run 的 token 总量
        history = self._engine.execute(
            """
            SELECT run_id, 
                   SUM(tokens_in) + SUM(tokens_out) as total_tokens
            FROM events
            GROUP BY run_id
            HAVING total_tokens > 0
            """
        )
        
        if len(history) < 2:
            # 至少需要 2 次运行才能计算中位数
            return anomalies
        
        # 计算历史中位数
        all_totals = [row["total_tokens"] for row in history if row["total_tokens"] > 0]
        
        if not all_totals:
            return anomalies
        
        median_tokens = self._get_median(all_totals)
        
        if median_tokens == 0:
            return anomalies
        
        # 检查当前 run 是否异常
        deviation = current_total / median_tokens
        
        if deviation > multiplier or deviation < (1 / multiplier):
            anomalies.append({
                "run_id": run_id,
                "metric": "total_tokens",
                "value": current_total,
                "median": median_tokens,
                "deviation": deviation,
                "threshold_multiplier": multiplier,
                "is_anomaly": True,
                "message": f"Token count {current_total} deviates "
                          f"{deviation:.2f}x from median {median_tokens}",
            })
        
        return anomalies
    
    def _classify_retry_patterns(self, run_id: str) -> dict[str, RetryPattern]:
        """
        重试模式分类。
        
        分类逻辑：
        - 快速收敛：首次 retry 即 pass
        - 收敛型：gate pass 率单调上升
        - 振荡型：pass/fail 交替 ≥ 2 次
        - 发散型：持续 fail
        
        Args:
            run_id: 运行ID
            
        Returns:
            {phase_name: RetryPattern} 字典
        """
        # 查询 gate 结果
        gate_results = self._engine.execute(
            """
            SELECT phase_name, result, timestamp
            FROM gate_results
            WHERE run_id = ?
            ORDER BY timestamp ASC
            """,
            (run_id,)
        )
        
        if not gate_results:
            return {}
        
        # 按 phase_name 分组
        from collections import defaultdict
        phase_results: dict[str, list[dict]] = defaultdict(list)
        
        for result in gate_results:
            phase_name = result["phase_name"]
            phase_results[phase_name].append(result)
        
        patterns: dict[str, RetryPattern] = {}
        
        for phase_name, results in phase_results.items():
            pattern = self._classify_single_phase(results)
            patterns[phase_name] = pattern
        
        return patterns
    
    def _classify_single_phase(self, results: list[dict]) -> RetryPattern:
        """
        分类单个 phase 的重试模式。
        
        Args:
            results: gate 结果列表
            
        Returns:
            RetryPattern 枚举值
        """
        if not results:
            return RetryPattern.DIVERGING
        
        # 提取 pass/fail 序列
        # 假设 result 字段为 "pass" 或 "fail"（或包含这些值）
        statuses: list[str] = []
        
        for result in results:
            result_str = str(result.get("result", "")).lower().strip()
            # 先检查 exact match，再检查常见变体
            if result_str in ("pass", "passed", "success", "passed", "ok", "passed", "passed", "passed"):
                statuses.append("pass")
            elif result_str in ("fail", "failed", "failure", "error", "failed", "failed"):
                statuses.append("fail")
            else:
                # 尝试更智能的匹配
                if "pass" in result_str:
                    statuses.append("pass")
                elif "fail" in result_str:
                    statuses.append("fail")
                else:
                    # 未知状态，默认为 fail
                    statuses.append("fail")
        
        if not statuses:
            return RetryPattern.DIVERGING
        
        n = len(statuses)
        
        # 分类逻辑（按优先级顺序检查）
        
        # 1. 振荡模式：pass/fail 交替 ≥ 2 次（最高优先级）
        oscillation_count = 0
        for i in range(1, n):
            if statuses[i] != statuses[i - 1]:
                oscillation_count += 1
        
        if oscillation_count >= 2:
            return RetryPattern.OSCILLATING
        
        # 2. 发散模式：持续 fail（所有都是 fail）
        if all(s == "fail" for s in statuses):
            return RetryPattern.DIVERGING
        
        # 3. 快速收敛：第2次就是 pass（首次retry即pass）
        if n >= 2 and statuses[1] == "pass":
            return RetryPattern.FAST_CONVERGE
        
        # 4. 收敛模式：pass 率单调上升（不包括快速收敛）
        pass_count = 0
        prev_pass_rate = 0.0
        converging = True
        
        for i, status in enumerate(statuses, 1):
            if status == "pass":
                pass_count += 1
            current_pass_rate = pass_count / i
            
            # 检查 pass 率是否单调不下降（允许相等）
            if i > 1 and current_pass_rate < prev_pass_rate - 0.01:  # 允许小误差
                converging = False
                break
            
            prev_pass_rate = current_pass_rate
        
        if converging and pass_count > 0:
            return RetryPattern.CONVERGING
        
        # 5. 单次 pass（仅1次尝试且为 pass）
        if n == 1 and statuses[0] == "pass":
            return RetryPattern.FAST_CONVERGE
        
        # 6. 无法分类，默认为发散
        return RetryPattern.DIVERGING
