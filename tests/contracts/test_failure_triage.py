"""Contract test for the Phase 0 failure triage tool."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "failure_triage.py"


def test_triage_cli_classifies_known_pass(tmp_path):
    log = tmp_path / "baseline.log"
    log.write_text(
        "FAILED tests/contracts/test_cage.py::test_active_contracts_exist - assert\n"
        "FAILED                                                                   [ 50%]\n",
        encoding="utf-8",
    )
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--log", str(log), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data["total"] == 1
    assert data["counts"]["isolation-pass"] == 1
    assert (
        data["results"][0]["test"]
        == "tests/contracts/test_cage.py::test_active_contracts_exist"
    )
