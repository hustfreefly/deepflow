"""
Pipeline Watcher — 运行时监控

职责：
1. 监控 Pipeline 运行状态（模块进度、超时、降级）
2. 记录运行时指标（每模块 duration、gate results）
3. 异常告警（模块失败、超时、降级触发）
4. 生成 Pipeline 运行报告

[R1-P1 采纳] 与 cron_watcher 职责分离：
- cron_watcher: 定时检查 cron jobs
- PipelineWatcher: 实时监控 Pipeline 运行
"""
import logging
import time
import json
import threading
from typing import Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class PipelineWatcher:
    """
    Pipeline 运行时监控器
    
    监控维度：
    1. 模块状态（PENDING/RUNNING/COMPLETE/FAILED/DEGRADED/TIMEOUT）
    2. 时间指标（每模块 start/end/duration）
    3. Gate 结果（Gate A/B verdict + score）
    4. 降级记录（哪些模块降级、降级原因）
    5. 异常记录（错误类型、错误消息）
    """
    
    def __init__(self, output_dir: str = None, alert_callback: Callable = None):
        self.output_dir = Path(output_dir or ".")
        self.alert_callback = alert_callback
        self._state = {}
        self._alerts = []
        self._lock = threading.Lock()
    
    def on_module_start(self, module_name: str):
        """模块开始执行"""
        with self._lock:
            self._state[module_name] = {
                "status": "RUNNING",
                "start_time": time.time(),
                "end_time": None,
                "duration": None,
                "gate_a": None,
                "gate_b": None,
                "degraded": False,
                "error": None,
            }
            logger.info(f"[Watcher] Module '{module_name}' started")
    
    def on_module_complete(self, module_name: str, output: dict = None):
        """模块执行完成"""
        with self._lock:
            if module_name in self._state:
                state = self._state[module_name]
                state["status"] = "COMPLETE"
                state["end_time"] = time.time()
                state["duration"] = state["end_time"] - state["start_time"]
                
                # 提取 Gate 结果（防御性：gate_a/gate_b 可能是 str 而非 dict）
                if output and isinstance(output, dict):
                    gate_a = output.get("gate_a", {})
                    gate_b = output.get("gate_b", {})
                    state["gate_a"] = gate_a.get("verdict") if isinstance(gate_a, dict) else gate_a
                    state["gate_b"] = gate_b.get("verdict") if isinstance(gate_b, dict) else gate_b
                    state["degraded"] = output.get("status") == "DEGRADED"
                
                logger.info(f"[Watcher] Module '{module_name}' completed in {state['duration']:.1f}s")
    
    def on_module_failed(self, module_name: str, error: Exception):
        """模块执行失败"""
        with self._lock:
            if module_name in self._state:
                state = self._state[module_name]
                state["status"] = "FAILED"
                state["end_time"] = time.time()
                state["duration"] = state["end_time"] - state["start_time"]
                state["error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
            
            self._add_alert(f"Module '{module_name}' failed: {error}")
            logger.error(f"[Watcher] Module '{module_name}' failed: {error}")
    
    def on_module_timeout(self, module_name: str, timeout_seconds: int):
        """模块执行超时"""
        with self._lock:
            if module_name in self._state:
                state = self._state[module_name]
                state["status"] = "TIMEOUT"
                state["end_time"] = time.time()
                state["duration"] = timeout_seconds
            
            self._add_alert(f"Module '{module_name}' timed out after {timeout_seconds}s")
            logger.warning(f"[Watcher] Module '{module_name}' timed out ({timeout_seconds}s)")
    
    def on_module_degraded(self, module_name: str, reason: str):
        """模块降级"""
        with self._lock:
            if module_name in self._state:
                state = self._state[module_name]
                state["status"] = "DEGRADED"
                state["degraded"] = True
                state["degradation_reason"] = reason
            
            self._add_alert(f"Module '{module_name}' degraded: {reason}")
            logger.warning(f"[Watcher] Module '{module_name}' degraded: {reason}")
    
    def get_status(self) -> dict:
        """获取当前状态快照"""
        with self._lock:
            return {
                "modules": dict(self._state),
                "alerts": list(self._alerts),
                "timestamp": time.time(),
            }
    
    def get_summary(self) -> dict:
        """获取摘要"""
        with self._lock:
            total = len(self._state)
            complete = sum(1 for s in self._state.values() if s["status"] == "COMPLETE")
            failed = sum(1 for s in self._state.values() if s["status"] == "FAILED")
            degraded = sum(1 for s in self._state.values() if s.get("degraded"))
            timed_out = sum(1 for s in self._state.values() if s["status"] == "TIMEOUT")
            
            total_duration = sum(
                s.get("duration", 0) or 0 for s in self._state.values()
            )
            
            return {
                "total_modules": total,
                "complete": complete,
                "failed": failed,
                "degraded": degraded,
                "timed_out": timed_out,
                "total_duration": total_duration,
                "alert_count": len(self._alerts),
                "pipeline_status": self._determine_pipeline_status(),
            }
    
    def generate_report(self) -> dict:
        """生成 Pipeline 运行报告"""
        summary = self.get_summary()
        status = self.get_status()
        
        report = {
            "report_type": "pipeline_watcher_report",
            "generated_at": time.time(),
            "summary": summary,
            "module_details": status["modules"],
            "alerts": status["alerts"],
        }
        
        # 保存到文件
        try:
            report_path = self.output_dir / "pipeline_watcher_report.json"
            report_path.write_text(json.dumps(report, indent=2, default=str))
            logger.info(f"[Watcher] Report saved to {report_path}")
        except Exception as e:
            logger.warning(f"[Watcher] Failed to save report: {e}")
        
        return report
    
    def _determine_pipeline_status(self) -> str:
        """判定 Pipeline 整体状态"""
        statuses = [s["status"] for s in self._state.values()]
        
        if not statuses:
            return "PENDING"
        
        if all(s in ("COMPLETE", "DEGRADED") for s in statuses):
            if any(s == "DEGRADED" for s in statuses):
                return "COMPLETE_DEGRADED"
            return "COMPLETE"
        
        if any(s == "FAILED" for s in statuses):
            return "FAILED"
        
        if any(s == "TIMEOUT" for s in statuses):
            return "PARTIAL_TIMEOUT"
        
        if any(s == "RUNNING" for s in statuses):
            return "RUNNING"
        
        return "UNKNOWN"
    
    def _add_alert(self, message: str):
        """添加告警"""
        alert = {
            "message": message,
            "timestamp": time.time(),
        }
        self._alerts.append(alert)
        
        # 触发回调
        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception as e:
                logger.warning(f"[Watcher] Alert callback failed: {e}")
