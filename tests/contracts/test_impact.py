"""Contract tests for scripts/impact.py (P0-1)."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "impact.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_contract_change_selects_contract_tests():
    p = run("--changed", "core/cage/active_contracts.py", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert "tests/contracts" in data["targets"]
    assert data["fallback_full_suite"] is False


def test_domain_change_selects_domain_tests():
    p = run("--changed", "domains/spec_pro/coordinator.py", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert "domains/spec_pro/tests" in data["targets"]


def test_unknown_path_falls_back_to_full_suite():
    p = run("--changed", "some/unknown/file.xyz", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data["fallback_full_suite"] is True
    assert data["targets"] == ["."]


def test_empty_change_is_rejected():
    p = run("--changed", "--json")
    assert p.returncode != 0
