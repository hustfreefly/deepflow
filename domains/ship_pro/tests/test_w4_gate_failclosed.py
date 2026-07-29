"""W4-F3/F4: Gate fail-closed + serving_principles 生产方补建。

F3: LLM API 任何失败 → gate 判定 FAIL（不 pass）。
F4: Ship Pro 从 guardrails 确定性派生 serving_principles 并注入 ship_package。
"""
import json

import pytest

from domains.ship_pro.conservation_judge import run_conservation_judge
from domains.ship_pro.contracts.gates import (
    CompletenessGate,
    HarnessV3,
    InformationConservationGate,
)
from domains.ship_pro.orchestrator.ship_orchestrator import (
    ShipOrchestrator,
    _derive_serving_principles,
)


# ============================================================================
# F3: Gate fail-closed
# ============================================================================

class TestGateFailClosed:
    """mock LLM API 失败/超时 → gate 不得 pass"""

    def test_conservation_judge_llm_exception_returns_fail(self):
        def failing_llm(prompt):
            raise TimeoutError("LLM API timeout")

        result = run_conservation_judge(
            [{"name": "anchor1", "constraint": "c"}],
            {"work_packages": [], "statistics": {}},
            failing_llm,
        )
        assert result["verdict"] == "FAIL"
        assert result["below_threshold"] is True
        assert "error" in result

    def test_conservation_judge_garbage_output_returns_fail(self):
        result = run_conservation_judge(
            [{"name": "anchor1", "constraint": "c"}],
            {"work_packages": [], "statistics": {}},
            lambda p: "抱歉，我无法理解这个请求",
        )
        assert result["verdict"] == "FAIL"
        assert result["below_threshold"] is True

    def test_info_conservation_gate_missing_judge_raises(self):
        with pytest.raises(ValueError, match="info_conservation"):
            InformationConservationGate.check({}, {}, judge_results=None)
        with pytest.raises(ValueError, match="info_conservation"):
            InformationConservationGate.check({}, {}, judge_results={})

    def test_completeness_gate_missing_judge_raises(self):
        with pytest.raises(ValueError, match="completeness"):
            CompletenessGate.check({}, {}, judge_results=None)

    def test_harness_gate_missing_judge_raises(self):
        valid_package = {"work_packages": [
            {"id": f"WP-{i}", "acceptance_criteria": ["a", "b"]} for i in range(3)
        ]}
        with pytest.raises(ValueError, match="harness_v3"):
            HarnessV3.check(valid_package, judge_results=None)

    def test_gate_error_verdict_defaults_to_fail(self):
        """LLM API 错误残骸（无 passed 字段）→ passed=False，不得静默 PASS"""
        error_verdict = {"info_conservation": {"error": "API 500"}}
        result = InformationConservationGate.check({}, {}, judge_results=error_verdict)
        assert result.passed is False

        error_verdict2 = {"completeness": {"error": "timeout"}}
        result2 = CompletenessGate.check({}, {}, judge_results=error_verdict2)
        assert result2.passed is False


class TestAnalyzeWorkerMustFailuresFailClosed:
    """analyze_worker_must_failures: 缺失/畸形 judge 结果 = FAIL，不静默跳过"""

    def _orch(self, tmp_path):
        return ShipOrchestrator(tmp_path)

    def test_missing_judge_with_must_constraints_is_failure(self, tmp_path):
        orch = self._orch(tmp_path)
        planner = {"workers": [
            {"role": "core", "must_constraints": ["必须保留 anchor"]},
            {"role": "docs", "must_constraints": []},
        ]}
        # core 有 MUST 约束但 judge 结果缺失（LLM API 失败未产出）
        failures = orch.analyze_worker_must_failures({}, planner)
        assert len(failures) == 1
        assert failures[0]["role"] == "core"
        assert "Judge 结果缺失" in failures[0]["issues"][0]

    def test_error_verdict_without_passed_is_failure(self, tmp_path):
        orch = self._orch(tmp_path)
        planner = {"workers": [{"role": "core", "must_constraints": ["c"]}]}
        judge_results = {"worker_must_core": {"error": "API timeout"}}
        failures = orch.analyze_worker_must_failures(judge_results, planner)
        assert len(failures) == 1
        assert failures[0]["role"] == "core"

    def test_no_must_constraints_no_judge_is_not_failure(self, tmp_path):
        orch = self._orch(tmp_path)
        planner = {"workers": [{"role": "docs", "must_constraints": []}]}
        failures = orch.analyze_worker_must_failures({}, planner)
        assert failures == []

    def test_passed_verdict_is_not_failure(self, tmp_path):
        orch = self._orch(tmp_path)
        planner = {"workers": [{"role": "core", "must_constraints": ["c"]}]}
        judge_results = {"worker_must_core": {"passed": True, "issues": []}}
        failures = orch.analyze_worker_must_failures(judge_results, planner)
        assert failures == []


# ============================================================================
# F4: serving_principles 生产方补建
# ============================================================================

class TestDeriveServingPrinciples:
    def test_explicit_passthrough(self):
        explicit = [{"obligation": "x"}]
        assert _derive_serving_principles({"serving_principles": explicit}) == explicit

    def test_derive_from_guardrails_dict(self):
        sol_input = {"guardrails": {
            "always_do": ["保持真实性", "保留证据链"],
            "never_do": ["虚构数据"],
        }}
        result = _derive_serving_principles(sol_input)
        assert len(result) == 3
        obligations = [p["obligation"] for p in result if "obligation" in p]
        anti_patterns = [p["anti_pattern"] for p in result if "anti_pattern" in p]
        assert obligations == ["保持真实性", "保留证据链"]
        assert anti_patterns == ["虚构数据"]

    def test_derive_from_guardrails_list(self):
        result = _derive_serving_principles({"guardrails": ["g1", "g2"]})
        assert len(result) == 2
        assert all("obligation" in p for p in result)

    def test_no_data_returns_empty(self):
        assert _derive_serving_principles({}) == []
        assert _derive_serving_principles({"guardrails": {}}) == []


class TestValidateShipPackageInjectsServingPrinciples:
    """端到端：solution_pro_input(guardrails) → validate → ship_package 注入"""

    def _setup_blackboard(self, tmp_path, sol_input, ship_package):
        stages = tmp_path / "stages"
        stages.mkdir(parents=True)
        (stages / "ship_package.json").write_text(
            json.dumps(ship_package, ensure_ascii=False), encoding="utf-8"
        )
        (stages / "solution_pro_input.json").write_text(
            json.dumps(sol_input, ensure_ascii=False), encoding="utf-8"
        )
        return tmp_path

    def _ship_package(self):
        return {
            "solution_name": "test",
            "work_packages": [
                {
                    "id": "CORE-001",
                    "title": "核心实现",
                    "description": "x" * 120,
                    "acceptance_criteria": ["ac1", "ac2"],
                    "deliverables": ["d1"],
                    "effort_hours": 4,
                }
            ],
            "semantic_anchors": [],
        }

    def test_injects_derived_serving_principles(self, tmp_path):
        sol_input = {
            "requirements": [{"id": "REQ-001"}],
            "semantic_anchors": [],
            "guardrails": {"always_do": ["保持真实性"], "never_do": ["虚构数据"]},
        }
        bp = self._setup_blackboard(tmp_path, sol_input, self._ship_package())
        orch = ShipOrchestrator(bp)
        result = orch.validate_ship_package_v8(str(bp))

        assert result["valid"] is True
        assert result["serving_principles_count"] == 2

        written = json.loads((bp / "stages" / "ship_package.json").read_text(encoding="utf-8"))
        sp = written["serving_principles"]
        assert len(sp) == 2
        assert any(p.get("obligation") == "保持真实性" for p in sp)
        assert any(p.get("anti_pattern") == "虚构数据" for p in sp)

    def test_no_guardrails_no_injection(self, tmp_path):
        sol_input = {"requirements": [{"id": "REQ-001"}], "semantic_anchors": []}
        bp = self._setup_blackboard(tmp_path, sol_input, self._ship_package())
        orch = ShipOrchestrator(bp)
        result = orch.validate_ship_package_v8(str(bp))

        assert result["valid"] is True
        assert result["serving_principles_count"] == 0
        written = json.loads((bp / "stages" / "ship_package.json").read_text(encoding="utf-8"))
        assert "serving_principles" not in written

    def test_existing_wp_level_not_overwritten(self, tmp_path):
        package = self._ship_package()
        package["serving_principles"] = [{"obligation": "已有原则"}]
        sol_input = {
            "requirements": [{"id": "REQ-001"}],
            "semantic_anchors": [],
            "guardrails": {"always_do": ["保持真实性"]},
        }
        bp = self._setup_blackboard(tmp_path, sol_input, package)
        orch = ShipOrchestrator(bp)
        orch.validate_ship_package_v8(str(bp))

        written = json.loads((bp / "stages" / "ship_package.json").read_text(encoding="utf-8"))
        assert written["serving_principles"] == [{"obligation": "已有原则"}]
