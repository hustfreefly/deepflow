"""G3: golden behavior scenarios are executable contracts, not docs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core.golden.scenarios import (
    CONTRACT_PATH,
    EXPECTED_SCENARIO_COUNT,
    evaluate_result,
    load_scenarios,
    validate_coverage,
)

ROOT = Path(__file__).resolve().parents[2]


def test_contract_file_lives_in_cage():
    assert CONTRACT_PATH == ROOT / "cage" / "active" / "golden_behavior_v1.0.yaml"
    assert CONTRACT_PATH.exists()


def test_exactly_twenty_scenarios():
    data = load_scenarios()
    assert len(data.scenarios) == EXPECTED_SCENARIO_COUNT


def test_scenario_ids_unique_and_prefixed():
    data = load_scenarios()
    ids = [s.id for s in data.scenarios]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("golden-") for i in ids)


def test_coverage_contract():
    data = load_scenarios()
    assert validate_coverage(data) == []


def test_every_scenario_has_deterministic_expectation_and_rubric():
    data = load_scenarios()
    for scenario in data.scenarios:
        assert scenario.rubric.strip(), scenario.id
        assert scenario.expect.has_assertion(), scenario.id


def test_cage_loader_accepts_contract():
    from core.cage.active_contracts import validate_all

    results, global_errors = validate_all()
    assert not global_errors, global_errors
    result = next(r for r in results if r.path.name == CONTRACT_PATH.name)
    assert result.valid, result.errors


def test_evaluator_passes_on_matching_result():
    data = load_scenarios()
    scenario = next(s for s in data.scenarios if s.id == "golden-spec-001")
    result = {
        "routed_to": "spec_pro",
        "asked_clarification": True,
        "questions": ["目标用户是谁？"],
        "generated": [],
        "text": "请补充目标与验收标准。",
        "alerts_sent": False,
    }
    assert evaluate_result(scenario, result) == []


def test_evaluator_flags_violations():
    data = load_scenarios()
    scenario = next(s for s in data.scenarios if s.id == "golden-spec-001")
    result = {
        "routed_to": "solution_pro",
        "asked_clarification": False,
        "questions": [],
        "generated": ["solution_document"],
        "text": "方案如下",
        "alerts_sent": False,
    }
    failures = evaluate_result(scenario, result)
    assert any("routed_to" in f for f in failures)
    assert any("asked_clarification" in f for f in failures)
    assert any("solution_document" in f for f in failures)


def test_cli_validate_runs():
    proc = subprocess.run(
        [sys.executable, "scripts/run_golden_scenarios.py", "--validate"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "scenarios: 20/20" in proc.stdout
