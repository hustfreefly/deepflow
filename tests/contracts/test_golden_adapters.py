"""Golden scenario adapters: deterministic real-path execution.

These adapters do not call an LLM. They exercise real product code paths and
feed a normalized result into the golden evaluator. LLM-dependent scenarios
belong to the dry-run layer, not this file.
"""

from __future__ import annotations

from core.golden.scenarios import evaluate_result, load_scenarios
from domains.deliver_pro import pulse_cli
from domains.deliver_pro.smart_assembler import SmartAssembler


class _Resp:
    status_code = 200
    text = "ok"

    def json(self):
        return {"code": 0}

    def raise_for_status(self):
        return None


def _critical():
    return [{"severity": "CRITICAL", "code": "TEST", "message": "boom"}]


def test_golden_del_001_real_pulse_dry_run(monkeypatch):
    """golden-del-001: CRITICAL alerts are suppressed unless explicitly enabled."""
    monkeypatch.delenv("DEEPFLOW_PULSE_ALLOW_ALERTS", raising=False)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.invalid/webhook")
    calls = []
    monkeypatch.setattr(
        pulse_cli.requests,
        "post",
        lambda *args, **kwargs: calls.append((args, kwargs)) or _Resp(),
    )

    # Real product path, not a mock of the decision itself.
    pulse_cli._send_feishu_alert(_critical(), "golden-test")

    result = {
        "routed_to": "deliver_pro",
        "alerts_sent": bool(calls),
        "stopped_at": "validation_gate",
        "blocker": True,
    }
    scenario = next(
        item for item in load_scenarios().scenarios if item.id == "golden-del-001"
    )
    assert evaluate_result(scenario, result) == []


def test_golden_del_003_missing_artifacts_block(tmp_path):
    """golden-del-003: missing worker artifacts must block, not silently skip."""
    plan = {"task_graph": [{"task_id": "T-001"}, {"task_id": "T-002"}]}
    assembler = SmartAssembler(
        worker_outputs_dir=tmp_path / "workers",
        plan_data=plan,
        output_dir=tmp_path / "out",
    )

    # Real deterministic assembly path: empty worker dirs -> all tasks missing.
    assembly = assembler.run()
    assert assembly.status == "ASSEMBLY_ERROR"
    assert assembly.coverage_gaps == ["T-001", "T-002"]

    result = {
        "blocker": assembly.status != "READY_FOR_VALIDATE",
        "stopped_at": "validation_gate",
        "generated": [],
    }
    scenario = next(
        item for item in load_scenarios().scenarios if item.id == "golden-del-003"
    )
    assert evaluate_result(scenario, result) == []
