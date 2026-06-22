"""
L3 效率分析引擎。

实现 WP-011（L3 效率分析引擎）的核心功能：
- 耗时排名 — Worker/Phase 耗时排名
- Token 浪费检测 — retry 导致的额外 token 消耗
- 重试成本分析 — 每次 retry 的 token/cost/duration 增量
- 跨运行趋势对比 — 与上一次或指定运行对比
"""

import time
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from src.deepflow.storage.sqlite_engine import SQLiteEngine


@dataclass
class EfficiencyReport:
    """L3 效率分析报告"""
    run_id: str
    duration_ranking: list[dict]      # Worker/Phase 耗时排名
    token_waste: list[dict]            # Token 浪费检测
    retry_cost: dict                   # 重试成本分析
    trend_comparison: Optional[dict]   # 跨运行趋势对比
    duration_ms: float
    timestamp: str


class L3Engine:
    """
    L3 效率分析引擎
    
    实现 WP-011：L3 效率分析引擎，负责：
    1. 耗时排名 — Worker/Phase 按 duration 排序
    2. Token 浪费检测 — retry 导致的额外 token 消耗
    3. 重试成本分析 — 每次 retry 的 token/cost/duration 增量
    4. 跨运行趋势对比 — 与上一次或指定运行对比
    
    性能目标：< 2s 完成
    """
    
    def __init__(self, engine: SQLiteEngine):
        """
        初始化 L3 效率分析引擎
        
        Args:
            engine: SQLite 引擎实例
        """
        self._engine = engine
    
    def analyze(self, run_id: str, compare_with: Optional[str] = None) -> EfficiencyReport:
        """
        执行 L3 效率分析
        
        执行流程：
        1. 耗时排名 — Worker/Phase 按 duration 排序
        2. Token 浪费检测 — retry 导致的额外 token 消耗
        3. 重试成本分析 — 每次 retry 的 token/cost/duration 增量
        4. 跨运行趋势对比 — 与上一次或指定运行对比
        
        性能目标：< 2s 完成
        
        Args:
            run_id: 运行ID
            compare_with: 可选，用于对比的运行ID
            
        Returns:
            EfficiencyReport: 分析报告
        """
        start_time = time.time()
        
        # 1. 耗时排名
        duration_ranking = self._rank_durations(run_id)
        
        # 2. Token 浪费检测
        token_waste = self._detect_token_waste(run_id)
        
        # 3. 重试成本分析
        retry_cost = self._analyze_retry_cost(run_id)
        
        # 4. 跨运行趋势对比
        trend_comparison = None
        if compare_with:
            trend_comparison = self._compare_trend(run_id, compare_with)
        
        # 计算耗时
        duration_ms = (time.time() - start_time) * 1000
        
        return EfficiencyReport(
            run_id=run_id,
            duration_ranking=duration_ranking,
            token_waste=token_waste,
            retry_cost=retry_cost,
            trend_comparison=trend_comparison,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    def _rank_durations(self, run_id: str) -> list[dict]:
        """
        耗时排名
        
        包含两个维度：
        1. 按 Worker 排名（duration_ms DESC）
        2. 按 Phase 排名
        
        Args:
            run_id: 运行ID
            
        Returns:
            包含 worker_ranking 和 phase_ranking 的列表
        """
        result = []
        
        # 1. Worker 耗时排名
        worker_results = self._engine.execute("""
            SELECT 
                worker_id,
                SUM(duration_ms) as total_duration_ms,
                COUNT(*) AS call_count,
                AVG(duration_ms) as avg_duration_ms,
                MAX(duration_ms) as max_duration_ms,
                MIN(duration_ms) as min_duration_ms
            FROM events
            WHERE run_id = ? 
            AND worker_id IS NOT NULL 
            AND duration_ms IS NOT NULL 
            AND duration_ms > 0
            GROUP BY worker_id
            ORDER BY total_duration_ms DESC
        """, (run_id,))
        
        worker_ranking = []
        for row in worker_results:
            worker_ranking.append({
                "type": "worker",
                "worker_id": row["worker_id"],
                "total_duration_ms": row["total_duration_ms"],
                "call_count": row["call_count"],
                "avg_duration_ms": row["avg_duration_ms"],
                "max_duration_ms": row["max_duration_ms"],
                "min_duration_ms": row["min_duration_ms"],
                "percentage": 0.0,  # 会在 Phase 排名后计算
            })
        
        # 2. Phase 耗时排名
        phase_results = self._engine.execute("""
            SELECT 
                phase_name,
                SUM(duration_ms) as total_duration_ms,
                COUNT(*) AS call_count,
                AVG(duration_ms) as avg_duration_ms,
                MAX(duration_ms) as max_duration_ms,
                MIN(duration_ms) as min_duration_ms
            FROM events
            WHERE run_id = ? 
            AND phase_name IS NOT NULL 
            AND duration_ms IS NOT NULL 
            AND duration_ms > 0
            GROUP BY phase_name
            ORDER BY total_duration_ms DESC
        """, (run_id,))
        
        phase_ranking = []
        total_duration = 0.0
        for row in phase_results:
            total_duration += row["total_duration_ms"]
            phase_ranking.append({
                "type": "phase",
                "phase_name": row["phase_name"],
                "total_duration_ms": row["total_duration_ms"],
                "call_count": row["call_count"],
                "avg_duration_ms": row["avg_duration_ms"],
                "max_duration_ms": row["max_duration_ms"],
                "min_duration_ms": row["min_duration_ms"],
                "percentage": 0.0,  # 之后计算
            })
        
        # 计算百分比占比
        if total_duration > 0:
            for item in phase_ranking:
                item["percentage"] = round((item["total_duration_ms"] / total_duration) * 100, 2)
        
        # 计算 Worker 的总耗时占比
        worker_total_duration = sum(w["total_duration_ms"] for w in worker_ranking)
        if worker_total_duration > 0:
            for item in worker_ranking:
                item["percentage"] = round((item["total_duration_ms"] / worker_total_duration) * 100, 2)
        
        result.extend(worker_ranking)
        result.extend(phase_ranking)
        
        return result
    
    def _detect_token_waste(self, run_id: str) -> list[dict]:
        """
        Token 浪费检测
        
        找出 retry 导致重复执行的 worker，计算浪费的 tokens 和 cost
        
        Args:
            run_id: 运行ID
            
        Returns:
            Token 浪费列表
        """
        wastes = []
        
        # 查询每个 worker 的事件详情（包含 retry 事件）
        worker_events = self._engine.execute("""
            SELECT 
                worker_id,
                event_type,
                duration_ms,
                tokens_in,
                tokens_out,
                cost
            FROM events
            WHERE run_id = ?
            AND worker_id IS NOT NULL
            ORDER BY timestamp ASC
        """, (run_id,))
        
        if not worker_events:
            return wastes
        
        # 按 worker_id 分组
        from collections import defaultdict
        worker_calls: dict[str, list[dict]] = defaultdict(list)
        
        for event in worker_events:
            worker_id = event["worker_id"]
            worker_calls[worker_id].append(event)
        
        # 计算每个 worker 的浪费
        for worker_id, calls in worker_calls.items():
            # 统计重试次数（retry 事件或多次 llm_call）
            retry_count = sum(1 for c in calls if c["event_type"] == "retry")
            
            # 如果有 retry 事件，说明有重试
            if retry_count > 0:
                # 计算该 worker 的平均 tokens per call
                total_tokens_in = sum(c.get("tokens_in") or 0 for c in calls)
                total_tokens_out = sum(c.get("tokens_out") or 0 for c in calls)
                total_calls = len(calls)
                
                avg_tokens_in = total_tokens_in / total_calls if total_calls > 0 else 0
                avg_tokens_out = total_tokens_out / total_calls if total_calls > 0 else 0
                
                # 浪费的 tokens = retry_count * avg_tokens
                waste_tokens_in = int(retry_count * avg_tokens_in)
                waste_tokens_out = int(retry_count * avg_tokens_out)
                
                # 计算浪费的成本（基于重试次数）
                total_cost = sum(c.get("cost") or 0 for c in calls)
                avg_cost = total_cost / total_calls if total_calls > 0 else 0
                waste_cost = round(retry_count * avg_cost, 6)
                
                wastes.append({
                    "worker_id": worker_id,
                    "retry_count": retry_count,
                    "waste_tokens_in": waste_tokens_in,
                    "waste_tokens_out": waste_tokens_out,
                    "waste_tokens_total": waste_tokens_in + waste_tokens_out,
                    "waste_cost": waste_cost,
                    "avg_tokens_in": round(avg_tokens_in, 2),
                    "avg_tokens_out": round(avg_tokens_out, 2),
                })
        
        return wastes
    
    def _analyze_retry_cost(self, run_id: str) -> dict:
        """
        重试成本分析
        
        包含：
        - 总 retry 次数
        - 总额外 token 消耗
        - 总额外 cost
        - 总额外 duration
        - 按 phase 分组
        
        Args:
            run_id: 运行ID
            
        Returns:
            重试成本分析字典
        """
        result = {
            "total_retry_count": 0,
            "total_extra_tokens_in": 0,
            "total_extra_tokens_out": 0,
            "total_extra_cost": 0.0,
            "total_extra_duration_ms": 0,
            "by_phase": [],
        }
        
        # 查询所有 retry 事件
        retry_events = self._engine.execute("""
            SELECT 
                event_type,
                phase_name,
                duration_ms,
                tokens_in,
                tokens_out,
                cost,
                timestamp
            FROM events
            WHERE run_id = ?
            AND (event_type = 'retry' OR event_type = 'llm_call')
            ORDER BY timestamp ASC
        """, (run_id,))
        
        if not retry_events:
            return result
        
        # 统计重试信息
        from collections import defaultdict
        phase_stats: dict[str, dict] = defaultdict(lambda: {
            "retry_count": 0,
            "extra_tokens_in": 0,
            "extra_tokens_out": 0,
            "extra_cost": 0.0,
            "extra_duration_ms": 0,
        })
        
        worker_events: dict[str, list[dict]] = defaultdict(list)
        
        for event in retry_events:
            worker_id = self._get_worker_id_from_event(event, run_id)
            worker_events[worker_id].append(event)
            
            # 判断是否为重试
            is_retry = event["event_type"] == "retry"
            
            if is_retry:
                phase = event.get("phase_name") or "unknown"
                phase_stats[phase]["retry_count"] += 1
                phase_stats[phase]["extra_tokens_in"] += (event.get("tokens_in") or 0)
                phase_stats[phase]["extra_tokens_out"] += (event.get("tokens_out") or 0)
                phase_stats[phase]["extra_cost"] += (event.get("cost") or 0)
                phase_stats[phase]["extra_duration_ms"] += (event.get("duration_ms") or 0)
                
                result["total_retry_count"] += 1
                result["total_extra_tokens_in"] += (event.get("tokens_in") or 0)
                result["total_extra_tokens_out"] += (event.get("tokens_out") or 0)
                result["total_extra_cost"] += (event.get("cost") or 0)
                result["total_extra_duration_ms"] += (event.get("duration_ms") or 0)
        
        # 按 phase 分组统计
        for phase, stats in phase_stats.items():
            if stats["retry_count"] > 0:
                result["by_phase"].append({
                    "phase_name": phase,
                    "retry_count": stats["retry_count"],
                    "extra_tokens_in": stats["extra_tokens_in"],
                    "extra_tokens_out": stats["extra_tokens_out"],
                    "extra_cost": round(stats["extra_cost"], 6),
                    "extra_duration_ms": stats["extra_duration_ms"],
                })
        
        # 按 retry_count 排序
        result["by_phase"].sort(key=lambda x: x["retry_count"], reverse=True)
        
        return result
    
    def _get_worker_id_from_event(self, event: dict, run_id: str) -> str:
        """
        从事件中获取 worker_id
        
        Args:
            event: 事件字典
            run_id: 运行ID
            
        Returns:
            worker_id 字符串
        """
        worker_id = event.get("worker_id")
        
        if worker_id:
            return worker_id
        
        # 如果 event 中没有 worker_id，尝试从事件类型推断
        event_type = event.get("event_type", "")
        
        if event_type == "llm_call":
            # 从事件序列获取该事件的排序位置
            event_seq = event.get("event_seq", 0)
            return f"worker-{event_seq}"
        
        return "unknown"
    
    def _compare_trend(self, run_id: str, baseline_run_id: str) -> dict:
        """
        跨运行趋势对比
        
        对比两项：
        - 总 duration 变化（绝对 + 百分比）
        - 总 cost 变化
        - 总 tokens 变化
        - gate pass rate 变化
        - 按 phase 对比
        
        Args:
            run_id: 当前运行ID
            baseline_run_id: 基准运行ID
            
        Returns:
            趋势对比字典
        """
        result = {
            "current_run_id": run_id,
            "baseline_run_id": baseline_run_id,
            "duration_change": {},
            "cost_change": {},
            "tokens_change": {},
            "pass_rate_change": {},
            "by_phase": [],
        }
        
        # 获取两个运行的汇总数据
        current_summary = self._get_run_summary(run_id)
        baseline_summary = self._get_run_summary(baseline_run_id)
        
        if not current_summary or not baseline_summary:
            return result
        
        # 1. Duration 变化
        current_duration = current_summary.get("total_duration_ms", 0)
        baseline_duration = baseline_summary.get("total_duration_ms", 0)
        duration_diff = current_duration - baseline_duration
        duration_change_pct = (duration_diff / baseline_duration * 100) if baseline_duration > 0 else 0
        
        result["duration_change"] = {
            "current": current_duration,
            "baseline": baseline_duration,
            "absolute_change": duration_diff,
            "percentage_change": round(duration_change_pct, 2),
            "is_improvement": duration_diff < 0,
        }
        
        # 2. Cost 变化
        current_cost = current_summary.get("total_cost", 0)
        baseline_cost = baseline_summary.get("total_cost", 0)
        cost_diff = current_cost - baseline_cost
        cost_change_pct = (cost_diff / baseline_cost * 100) if baseline_cost > 0 else 0
        
        result["cost_change"] = {
            "current": round(current_cost, 6),
            "baseline": round(baseline_cost, 6),
            "absolute_change": round(cost_diff, 6),
            "percentage_change": round(cost_change_pct, 2),
            "is_improvement": cost_diff < 0,
        }
        
        # 3. Tokens 变化
        current_tokens = current_summary.get("total_tokens", 0)
        baseline_tokens = baseline_summary.get("total_tokens", 0)
        tokens_diff = current_tokens - baseline_tokens
        tokens_change_pct = (tokens_diff / baseline_tokens * 100) if baseline_tokens > 0 else 0
        
        result["tokens_change"] = {
            "current": current_tokens,
            "baseline": baseline_tokens,
            "absolute_change": tokens_diff,
            "percentage_change": round(tokens_change_pct, 2),
            "is_improvement": tokens_diff < 0,
        }
        
        # 4. Gate Pass Rate 变化
        current_pass_rate = current_summary.get("pass_rate", 0)
        baseline_pass_rate = baseline_summary.get("pass_rate", 0)
        pass_rate_diff = current_pass_rate - baseline_pass_rate
        
        result["pass_rate_change"] = {
            "current": round(current_pass_rate * 100, 2),
            "baseline": round(baseline_pass_rate * 100, 2),
            "absolute_change": round(pass_rate_diff * 100, 2),
            "percentage_change": round(pass_rate_diff * 100, 2),
            "is_improvement": pass_rate_diff > 0,
        }
        
        # 5. 按 phase 对比
        current_phases = self._get_phase_durations(run_id)
        baseline_phases = self._get_phase_durations(baseline_run_id)
        
        all_phases = set(current_phases.keys()) | set(baseline_phases.keys())
        
        for phase in all_phases:
            current_dur = current_phases.get(phase, 0)
            baseline_dur = baseline_phases.get(phase, 0)
            
            phase_diff = current_dur - baseline_dur
            phase_change_pct = (phase_diff / baseline_dur * 100) if baseline_dur > 0 else 0
            
            result["by_phase"].append({
                "phase_name": phase,
                "current_duration_ms": current_dur,
                "baseline_duration_ms": baseline_dur,
                "absolute_change": phase_diff,
                "percentage_change": round(phase_change_pct, 2),
            })
        
        return result
    
    def _get_run_summary(self, run_id: str) -> Optional[dict]:
        """
        获取运行汇总数据
        
        Args:
            run_id: 运行ID
            
        Returns:
            包含运行汇总信息的字典
        """
        # 获取总 duration、cost、tokens
        summary = self._engine.execute("""
            SELECT 
                run_id,
                SUM(duration_ms) as total_duration_ms,
                SUM(cost) as total_cost,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out
            FROM events
            WHERE run_id = ?
            GROUP BY run_id
        """, (run_id,))
        
        if not summary:
            return None
        
        row = summary[0]
        total_tokens = (row.get("total_tokens_in") or 0) + (row.get("total_tokens_out") or 0)
        
        return {
            "run_id": row["run_id"],
            "total_duration_ms": row["total_duration_ms"] or 0,
            "total_cost": row["total_cost"] or 0,
            "total_tokens": total_tokens,
            "pass_rate": self._calculate_pass_rate(run_id),
        }
    
    def _calculate_pass_rate(self, run_id: str) -> float:
        """
        计算 gate pass rate
        
        Args:
            run_id: 运行ID
            
        Returns:
            pass rate (0.0 ~ 1.0)
        """
        # 查询 gate 结果
        gate_results = self._engine.execute("""
            SELECT result FROM gate_results WHERE run_id = ?
        """, (run_id,))
        
        if not gate_results:
            return 0.0
        
        pass_count = sum(1 for r in gate_results if "pass" in str(r["result"]).lower())
        total_count = len(gate_results)
        
        return pass_count / total_count if total_count > 0 else 0.0
    
    def _get_phase_durations(self, run_id: str) -> dict[str, int]:
        """
        获取每个 phase 的总耗时
        
        Args:
            run_id: 运行ID
            
        Returns:
            {phase_name: total_duration_ms} 字典
        """
        phases = self._engine.execute("""
            SELECT 
                phase_name,
                SUM(duration_ms) as total_duration_ms
            FROM events
            WHERE run_id = ?
            AND phase_name IS NOT NULL
            AND duration_ms IS NOT NULL
            GROUP BY phase_name
        """, (run_id,))
        
        return {row["phase_name"]: row["total_duration_ms"] or 0 for row in phases}
    
    def get_run_summaries(self, last_n: int = 10) -> list[dict]:
        """
        获取最近 N 次运行的摘要数据
        
        Args:
            last_n: 最近 N 次运行
            
        Returns:
            运行摘要列表
        """
        # 获取最近 N 次运行的 run_id
        runs = self._engine.execute("""
            SELECT DISTINCT run_id FROM events 
            ORDER BY run_id DESC LIMIT ?
        """, (last_n,))
        
        summaries = []
        for row in runs:
            run_id = row["run_id"]
            summary = self._get_run_summary(run_id)
            if summary:
                summaries.append(summary)
        
        # 按 run_id 升序排序（最早的在前）
        summaries.sort(key=lambda x: x["run_id"])
        
        return summaries
