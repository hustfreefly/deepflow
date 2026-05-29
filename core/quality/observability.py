"""
Observability — V1.0 PipelineEngine 可观测性组件

职责：结构化日志 + 指标收集 + 全链路追踪
设计：静态方法接口，零外部依赖，structlog 未安装时回退 stdlib logging。

Author: 小满
Date: 2026-04-18
"""

import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


# ── Structured Logger (structlog → stdlib fallback) ──

try:
    import structlog as _sl
    _sl.configure(
        processors=[
            _sl.processors.TimeStamper(fmt="iso"),
            _sl.processors.add_log_level,
            _sl.processors.JSONRenderer(),
        ],
        logger_factory=_sl.PrintLoggerFactory(),
    )
    def _get_structured_logger(name: str = "v3") -> Any:
        return _sl.get_logger(name)
except ImportError:
    class _FallbackLogger:
        def __init__(self, name: str = "v3") -> None:
            self._logger = logging.getLogger(name)
            if not self._logger.handlers:
                h = logging.StreamHandler()
                h.setFormatter(logging.Formatter("%(message)s"))
                self._logger.addHandler(h)
                self._logger.setLevel(logging.INFO)
        def _log(self, level: int, event: str, **kw: Any) -> None:
            entry = {"ts": time.time(), "level": logging.getLevelName(level),
                     "logger": self._logger.name, "event": event, **kw}
            self._logger.log(level, json.dumps(entry, ensure_ascii=False))
        def info(self, event: str, **kw: Any) -> None:  self._log(logging.INFO, event, **kw)
        def warning(self, event: str, **kw: Any) -> None: self._log(logging.WARNING, event, **kw)
        def error(self, event: str, **kw: Any) -> None:  self._log(logging.ERROR, event, **kw)
        def debug(self, event: str, **kw: Any) -> None: self._log(logging.DEBUG, event, **kw)
        def critical(self, event: str, **kw: Any) -> None: self._log(logging.CRITICAL, event, **kw)
        def exception(self, event: str, **kw: Any) -> None: self._log(logging.ERROR, event, exc_info=True, **kw)
    def _get_structured_logger(name: str = "v3") -> _FallbackLogger:
        return _FallbackLogger(name)


# ── Metric Store (thread-safe, Prometheus-style) ──

class _MetricStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, Dict[str, float]] = {}

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = {"count": 0, "sum": 0.0, "mean": 0.0}
            s = self._histograms[key]
            s["count"] += 1
            s["mean"] += (value - s["mean"]) / s["count"]
            s["sum"] += value

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: {"count": v["count"], "sum": v["sum"], "avg": v["mean"]}
                               for k, v in self._histograms.items()},
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear(); self._gauges.clear(); self._histograms.clear()

    @staticmethod
    def _key(name: str, labels: Optional[Dict[str, str]] = None) -> str:
        if not labels:
            return name
        return f"{name}{{{','.join(f'{k}={v}' for k, v in sorted(labels.items()))}}}"


# ── Trace Context ──

class _TraceContext:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, str] = {}
        self._spans: Dict[str, List[Dict[str, Any]]] = {}

    def create(self, session_id: str) -> str:
        with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            tid = uuid.uuid4().hex[:16]
            self._sessions[session_id] = tid
            self._spans[tid] = []
            return tid

    def lookup(self, session_id: str) -> Optional[str]:
        with self._lock:
            return self._sessions.get(session_id)

    def push(self, tid: str, stage: str, agent: str) -> Dict[str, Any]:
        span = {"stage": stage, "agent": agent, "start": time.time(),
                "end": None, "success": None, "duration": None}
        with self._lock:
            if tid in self._spans:
                self._spans[tid].append(span)
        return span

    def pop(self, tid: str, success: bool) -> Optional[Dict[str, Any]]:
        with self._lock:
            spans = self._spans.get(tid, [])
            if not spans:
                return None
            span = spans[-1]
            span["end"] = time.time()
            span["success"] = success
            span["duration"] = span["end"] - span["start"]
            return span

    def get(self, tid: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._spans.get(tid, []))

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear(); self._spans.clear()


# ── Global Singletons ──

_store = _MetricStore()
_trace = _TraceContext()
_log = _get_structured_logger()


# ── Observability Public API ──

class Observability:
    """可观测性静态接口：日志 + 指标 + 追踪。"""

    @staticmethod
    def get_logger(name: str = "v3") -> Any:
        return _get_structured_logger(name)

    @staticmethod
    def init_trace(session_id: str) -> str:
        tid = _trace.create(session_id)
        _log.info("trace_init", trace_id=tid, session_id=session_id)
        Observability.record_counter("trace_count")
        return tid

    @staticmethod
    def log_stage_start(stage: str, agent: str, trace_id: str, **kw: Any) -> None:
        _trace.push(trace_id, stage, agent)
        _log.info("stage_start", trace_id=trace_id, stage=stage, agent=agent, **kw)
        Observability.record_counter("stage_starts", labels={"stage": stage, "agent": agent})

    @staticmethod
    def log_stage_end(stage: str, success: bool, duration: float, trace_id: str, **kw: Any) -> None:
        span = _trace.pop(trace_id, success)
        _log.info("stage_end" if success else "stage_fail",
                   trace_id=trace_id, stage=stage, success=success,
                   duration=round(duration, 3), **kw)
        if success:
            Observability.record_counter("stage_successes", labels={"stage": stage})
        else:
            Observability.record_counter("stage_failures", labels={"stage": stage})
        Observability.record_histogram("stage_duration_seconds", duration, labels={"stage": stage})

    @staticmethod
    def record_counter(name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        _store.counter(name, value, labels)

    @staticmethod
    def record_gauge(name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        _store.gauge(name, value, labels)

    @staticmethod
    def record_histogram(name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        _store.histogram(name, value, labels)

    @staticmethod
    def record_quality_score(score: float, stage: str, trace_id: Optional[str] = None) -> None:
        if not (0.0 <= score <= 1.0):
            _log.warning("quality_score_oor", score=score, stage=stage)
            score = max(0.0, min(1.0, score))
        _store.gauge("quality_score", score, {"stage": stage})
        _store.histogram("quality_scores", score, {"stage": stage})

    @staticmethod
    def record_convergence(round_num: int, converged: bool, reason: str = "") -> None:
        _store.gauge("convergence_round", float(round_num))
        _store.counter("convergence_events", labels={"converged": str(converged), "reason": reason or "continue"})

    @staticmethod
    def record_error(error_type: str, message: str, stage: str = "", trace_id: Optional[str] = None) -> None:
        labels: Dict[str, str] = {"error_type": error_type}
        if stage:
            labels["stage"] = stage
        _store.counter("error_count", labels=labels)
        _log.error("error", error_type=error_type, message=message, stage=stage, trace_id=trace_id)

    @staticmethod
    def get_metrics() -> Dict[str, Any]:
        return _store.snapshot()

    @staticmethod
    def get_trace(trace_id: str) -> List[Dict[str, Any]]:
        return _trace.get(trace_id)

    @staticmethod
    def get_session_trace(session_id: str) -> Optional[List[Dict[str, Any]]]:
        tid = _trace.lookup(session_id)
        return _trace.get(tid) if tid else None

    @staticmethod
    def reset() -> None:
        _store.reset()
        _trace.reset()
