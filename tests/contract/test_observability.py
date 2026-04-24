"""Contract tests for observability module."""

import time
import pytest

from observability import Observability


@pytest.fixture(autouse=True)
def _reset():
    """Reset metrics and traces after each test."""
    Observability.reset()
    yield
    Observability.reset()


class TestObservabilityContract:
    """L1: Interface contract — all public methods exist."""

    def test_get_logger_returns_logger(self):
        logger = Observability.get_logger("test")
        assert logger is not None
        assert hasattr(logger, "info")

    def test_init_trace_returns_16_char_hex(self):
        trace_id = Observability.init_trace("sess_001")
        assert len(trace_id) == 16
        assert all(c in "0123456789abcdef" for c in trace_id)

    def test_init_trace_idempotent(self):
        t1 = Observability.init_trace("sess_002")
        t2 = Observability.init_trace("sess_002")
        assert t1 == t2

    def test_log_stage_start_end_no_crash(self):
        tid = Observability.init_trace("sess_003")
        Observability.log_stage_start("plan", "planner", tid)
        time.sleep(0.01)
        Observability.log_stage_end("plan", True, 0.01, tid)
        spans = Observability.get_trace(tid)
        assert len(spans) == 1
        assert spans[0]["success"] is True

    def test_log_stage_end_empty_stack_no_crash(self):
        tid = Observability.init_trace("sess_004")
        # Pop without push — must not raise
        Observability.log_stage_end("unknown", False, 0.0, tid)


class TestMetricContract:
    """L2: Metric recording behavior."""

    def test_counter_increments(self):
        Observability.record_counter("test_ctr", 1.0)
        Observability.record_counter("test_ctr", 2.0)
        m = Observability.get_metrics()
        assert m["counters"]["test_ctr"] == 3.0

    def test_gauge_set(self):
        Observability.record_gauge("test_gauge", 0.85)
        m = Observability.get_metrics()
        assert abs(m["gauges"]["test_gauge"] - 0.85) < 0.001

    def test_histogram_aggregation(self):
        for v in [0.1, 0.2, 0.3]:
            Observability.record_histogram("test_hist", v)
        m = Observability.get_metrics()
        h = m["histograms"]["test_hist"]
        assert h["count"] == 3
        assert abs(h["avg"] - 0.2) < 0.001

    def test_quality_score_clamped(self):
        Observability.record_quality_score(1.5, "plan")  # out of range
        m = Observability.get_metrics()
        assert abs(m["gauges"]["quality_score{stage=plan}"] - 1.0) < 0.001

    def test_convergence_recorded(self):
        Observability.record_convergence(3, True, "score_reached")
        m = Observability.get_metrics()
        assert abs(m["gauges"]["convergence_round"] - 3.0) < 0.001

    def test_error_recorded(self):
        Observability.record_error("TimeoutError", "timed out", "execute")
        m = Observability.get_metrics()
        assert "error_count{error_type=TimeoutError,stage=execute}" in m["counters"]


class TestTraceContract:
    """L3: Trace behavior."""

    def test_full_pipeline_trace(self):
        tid = Observability.init_trace("sess_005")
        stages = [
            ("plan", "planner", 0.1),
            ("execute", "researcher", 0.15),
            ("critique", "auditor", 0.08),
        ]
        for name, agent, dur in stages:
            Observability.log_stage_start(name, agent, tid)
            Observability.log_stage_end(name, True, dur, tid)
        spans = Observability.get_trace(tid)
        assert len(spans) == 3
        assert spans[0]["agent"] == "planner"
        assert spans[-1]["stage"] == "critique"

    def test_get_session_trace(self):
        tid = Observability.init_trace("lookup_sess")
        Observability.log_stage_start("plan", "planner", tid)
        Observability.log_stage_end("plan", True, 0.1, tid)
        spans = Observability.get_session_trace("lookup_sess")
        assert len(spans) == 1
        assert Observability.get_session_trace("no_such") is None

    def test_reset_clears_all(self):
        Observability.init_trace("sess_006")
        Observability.record_counter("ctr", 5.0)
        Observability.reset()
        m = Observability.get_metrics()
        assert m["counters"] == {}
        assert Observability.get_session_trace("sess_006") is None
