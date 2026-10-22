"""Contract tests for P1 dev-ops weapons."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_script(name, *args):
    path = ROOT / "scripts" / name
    assert path.exists(), f"missing weapon: {path}"
    command = (
        ["bash", str(path)] if path.suffix == ".sh" else [sys.executable, str(path)]
    )
    return subprocess.run(
        command + list(args), capture_output=True, text=True, cwd=ROOT
    )


def test_worktree_help():
    p = run_script("worktree.sh", "--help")
    assert p.returncode == 0, p.stderr
    assert "create" in p.stdout


def test_worktree_unknown_rejected():
    p = run_script("worktree.sh", "bogus")
    assert p.returncode == 2


def test_selfcheck_json():
    p = run_script("selfcheck.py", "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    data = json.loads(p.stdout)
    assert data["status"] in {"PASS", "WARN"}
    checks = {c["name"]: c for c in data["checks"]}
    assert {"python", "pytest", "contract_gate", "scripts"} <= set(checks)
    assert checks["contract_gate"]["status"] == "PASS"


def _request(tmp_path, **overrides):
    payload = {
        "agent": "expert",
        "model": "modelstudio/qwen3.8-max",
        "executor_model": "deepseek/deepseek-flash",
        "task": "do work",
    }
    payload.update(overrides)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_spawn_guard_missing_model(tmp_path):
    p = run_script("spawn_guard.py", "--request", str(_request(tmp_path, model="")))
    assert p.returncode == 2


def test_spawn_guard_same_model_redteam(tmp_path):
    p = run_script(
        "spawn_guard.py",
        "--request",
        str(_request(tmp_path, agent="redteam", model="deepseek/deepseek-flash")),
    )
    assert p.returncode == 3


def test_spawn_guard_heterogeneous_ok(tmp_path):
    p = run_script("spawn_guard.py", "--request", str(_request(tmp_path)))
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout)["ok"] is True


def test_spawn_guard_oversized_task(tmp_path):
    p = run_script(
        "spawn_guard.py", "--request", str(_request(tmp_path, task="x" * 4000))
    )
    assert p.returncode == 4
