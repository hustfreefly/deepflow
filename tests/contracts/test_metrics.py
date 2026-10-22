"""Contract tests for scripts/metrics.py (P0-4)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "metrics.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=ROOT,
    )


def _record(path, task="T1", passed_n="7", failed_n="0"):
    return run(
        "record", "--file", str(path), "--task", task, "--model", "m",
        "--duration", "1.5", "--passed", passed_n, "--failed", failed_n,
        "--commit", "abc123",
    )


def test_record_and_summary(tmp_path):
    path = tmp_path / "metrics.jsonl"
    assert _record(path).returncode == 0
    assert _record(path, task="T2", passed_n="3", failed_n="1").returncode == 0
    p = run("summary", "--file", str(path), "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data["count"] == 2
    assert data["passed"] == 10
    assert data["failed"] == 1
    assert abs(data["duration_total"] - 3.0) < 1e-6


def test_missing_field_rejected(tmp_path):
    path = tmp_path / "metrics.jsonl"
    p = run("record", "--file", str(path), "--model", "m",
            "--duration", "1", "--passed", "1", "--failed", "0",
            "--commit", "abc")
    assert p.returncode != 0
    assert not path.exists()