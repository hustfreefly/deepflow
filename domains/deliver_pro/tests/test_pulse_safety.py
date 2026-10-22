"""Safety hardening: blackboard root isolation + pulse alert dry-run."""

import os
import subprocess
import sys
from pathlib import Path

from domains.deliver_pro import pulse_cli

ROOT = Path(__file__).resolve().parents[3]


class _Resp:
    status_code = 200
    text = "ok"

    def json(self):
        return {"code": 0}

    def raise_for_status(self):
        return None


def _critical():
    return [{"severity": "CRITICAL", "code": "TEST", "message": "boom"}]


def test_blackboard_root_respects_env(tmp_path):
    env = os.environ.copy()
    env["DEEPFLOW_BLACKBOARD_ROOT"] = str(tmp_path / "bb")
    out = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import domains.deliver_pro as d; print(d.BLACKBOARD_ROOT)",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert out.strip() == str(tmp_path / "bb")


def test_pulse_alert_suppressed_by_default(monkeypatch):
    monkeypatch.delenv("DEEPFLOW_PULSE_ALLOW_ALERTS", raising=False)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.invalid/webhook")
    calls = []
    monkeypatch.setattr(
        pulse_cli.requests,
        "post",
        lambda *a, **k: calls.append((a, k)) or _Resp(),
    )
    pulse_cli._send_feishu_alert(_critical(), "test-project")
    assert calls == []


def test_pulse_alert_sends_when_enabled(monkeypatch):
    monkeypatch.setenv("DEEPFLOW_PULSE_ALLOW_ALERTS", "1")
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.invalid/webhook")
    calls = []
    monkeypatch.setattr(
        pulse_cli.requests,
        "post",
        lambda *a, **k: calls.append((a, k)) or _Resp(),
    )
    pulse_cli._send_feishu_alert(_critical(), "test-project")
    assert len(calls) == 1
