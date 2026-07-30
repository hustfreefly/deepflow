"""Tests for Final Synthesis 架构（2026-07-29）。

覆盖：
- 交付物契约推断（infer_deliverable_contract）
- Final Synthesis 触发条件
- 语义回溯 Gate（LLM-as-Judge：MUST-missing raise / SHOULD-missing 显式记录 / fail-closed）
- living_spec 缺失 raise
- 完成宣告条件变更
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ship_package_data():
    return {
        "work_packages": [
            {"wp_id": "AAA-001", "dependencies": [], "title": "Alpha"},
        ],
        "dependency_graph": {
            "execution_layers": [["AAA-001"]],
        },
    }


@pytest.fixture
def mock_blackboard(tmp_path, ship_package_data):
    project_name = "test-final-synthesis"
    bb_root = tmp_path / "blackboard"
    ship_dir = bb_root / project_name / "ship_pro" / "stages"
    ship_dir.mkdir(parents=True)
    (ship_dir / "ship_package.json").write_text(json.dumps(ship_package_data))
    return bb_root, project_name


@contextmanager
def _make_orchestrator(mock_blackboard):
    bb_root, project_name = mock_blackboard
    with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
        from domains.deliver_pro.orchestrator import DeliverOrchestrator
        orch = DeliverOrchestrator(project_name)
        yield orch, bb_root, project_name


def _wp_dir(bb_root, project_name, wp_id):
    return bb_root / project_name / "deliver_pro" / wp_id.lower().replace("-", "_")


def _setup_done_wp(bb_root, project_name, wp_id):
    """构造 DONE 状态的 WP。"""
    stages = _wp_dir(bb_root, project_name, wp_id) / "stages"
    stages.mkdir(parents=True)
    (stages / "final_deliverable").mkdir(exist_ok=True)
    (stages / "final_deliverable" / "out.md").write_text("x" * 60)
    (stages / "delivery_manifest.json").write_text('{"wp_id": "TEST-001"}')
    return stages


def _setup_living_spec(bb_root, project_name, content=None):
    """创建 living_spec.json。"""
    data_dir = bb_root / project_name / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    spec = content or {
        "requirements": [
            {"id": "R1", "text": "Core feature A", "priority": "MUST"},
            {"id": "R2", "text": "Nice-to-have B", "priority": "SHOULD"},
        ],
        "sections": ["Introduction", "Implementation", "Testing"],
    }
    (data_dir / "living_spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    return data_dir / "living_spec.json"


# ---------------------------------------------------------------------------
# 交付物契约推断
# ---------------------------------------------------------------------------

class TestInferDeliverableContract:
    def test_should_infer_contract_when_missing(self, mock_blackboard):
        """无 contract 文件时应推断。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            assert orch._should_infer_contract() is True

    def test_should_not_infer_contract_when_exists(self, mock_blackboard):
        """有 contract 文件时不应推断。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            (bb_root / project / "_deliverable_contract.json").write_text("{}")
            assert orch._should_infer_contract() is False

    def test_build_infer_contract_action(self, mock_blackboard):
        """构建 infer_deliverable_contract 动作。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_living_spec(bb_root, project)
            action = orch._build_infer_contract_action()
            assert action["action"] == "infer_deliverable_contract"
            assert action["wp_id"] == "BATCH"
            assert "living_spec" in action["task"]
            assert "deliverable_type" in action["task"]

    def test_living_spec_missing_raises(self, mock_blackboard):
        """living_spec 缺失时 _read_living_spec 应 raise ValueError。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            with pytest.raises(ValueError, match="living_spec not found"):
                orch._read_living_spec()

    def test_pulse_triggers_infer_contract(self, mock_blackboard):
        """pulse() 在无 contract + 有 living_spec 时应触发推断动作。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_living_spec(bb_root, project)
            with patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()
            assert report["status"] == "active"
            assert len(report["actions"]) == 1
            assert report["actions"][0]["action"] == "infer_deliverable_contract"

    def test_pulse_living_spec_missing_raises(self, mock_blackboard):
        """pulse() 在无 contract + 无 living_spec 时应 raise ValueError（不静默跳过）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            # 不创建 living_spec
            with patch.object(orch, "_count_in_flight", return_value=0):
                with pytest.raises(ValueError, match="living_spec not found"):
                    orch.pulse()


# ---------------------------------------------------------------------------
# Final Synthesis 触发条件
# ---------------------------------------------------------------------------

class TestFinalSynthesisTrigger:
    def test_should_trigger_when_all_done(self, mock_blackboard):
        """全部 WP DONE + contract 存在 + 无 done 标记 → 应触发。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_done_wp(bb_root, project, "AAA-001")
            (bb_root / project / "_deliverable_contract.json").write_text(json.dumps({
                "deliverable_type": "report",
                "req_elements": [],
            }))
            assert orch._should_trigger_final_synthesis() is True

    def test_should_not_trigger_when_wp_not_done(self, mock_blackboard):
        """WP 未全部 DONE → 不应触发。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            # WP 处于 PENDING 状态（无 stages）
            (bb_root / project / "_deliverable_contract.json").write_text("{}")
            assert orch._should_trigger_final_synthesis() is False

    def test_should_not_trigger_when_no_contract(self, mock_blackboard):
        """无 contract → 不应触发。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_done_wp(bb_root, project, "AAA-001")
            assert orch._should_trigger_final_synthesis() is False

    def test_should_not_trigger_when_already_done(self, mock_blackboard):
        """已有 _final_deliverable_done.json → 不应触发。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_done_wp(bb_root, project, "AAA-001")
            (bb_root / project / "_deliverable_contract.json").write_text("{}")
            (bb_root / project / "_final_deliverable_done.json").write_text("{}")
            assert orch._should_trigger_final_synthesis() is False


# ---------------------------------------------------------------------------
# 语义回溯 Gate（LLM-as-Judge）
# ---------------------------------------------------------------------------

class TestSemanticGate:
    def test_build_run_final_gate_action(self, mock_blackboard):
        """构建 run_final_gate 动作（LLM-as-Judge spawn）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            contract = {
                "deliverable_type": "report",
                "req_elements": [
                    {"element": "Core feature A", "criticality": "MUST"},
                ],
            }
            (bb_root / project / "_deliverable_contract.json").write_text(json.dumps(contract))
            synthesis_dir = bb_root / project / "final_synthesis"
            synthesis_dir.mkdir(parents=True)
            (synthesis_dir / "report.md").write_text("Some synthesis output")
            
            action = orch._build_run_final_gate_action()
            assert action["action"] == "run_final_gate"
            assert action["wp_id"] == "BATCH"
            assert "LLM-as-Judge" in action["task"]
            assert "COVERED|PARTIAL|MISSING" in action["task"]
            assert str(orch._final_gate_report_path()) in action["task"]

    def test_process_gate_report_must_missing_raises(self, mock_blackboard):
        """MUST 要素 MISSING → _process_gate_report raise ValueError（HARD_BLOCK）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            # 模拟 LLM 写的 gate report（MUST MISSING）
            report = {
                "gaps": [
                    {"element": "Core feature A", "criticality": "MUST", "status": "MISSING", "reason": "Not addressed"},
                ],
            }
            (bb_root / project / "_final_gate_report.json").write_text(json.dumps(report))
            
            with pytest.raises(ValueError, match="HARD_BLOCK"):
                orch._process_gate_report()

    def test_process_gate_report_should_missing_records_gap(self, mock_blackboard):
        """SHOULD 要素 MISSING → 显式记录到 gaps（不阻断）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            report = {
                "gaps": [
                    {"element": "Core feature A", "criticality": "MUST", "status": "COVERED", "reason": "Fully addressed"},
                    {"element": "Nice-to-have B", "criticality": "SHOULD", "status": "MISSING", "reason": "Not addressed"},
                ],
            }
            (bb_root / project / "_final_gate_report.json").write_text(json.dumps(report))
            
            result = orch._process_gate_report()
            assert result["passed"] is True
            should_gaps = [g for g in result["gaps"] if g["criticality"] == "SHOULD" and g["status"] == "MISSING"]
            assert len(should_gaps) == 1
            assert should_gaps[0]["element"] == "Nice-to-have B"

    def test_process_gate_report_all_covered_passes(self, mock_blackboard):
        """全部要素 COVERED → Gate 通过。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            report = {
                "gaps": [
                    {"element": "Feature A", "criticality": "MUST", "status": "COVERED", "reason": "Addressed"},
                    {"element": "Feature B", "criticality": "SHOULD", "status": "COVERED", "reason": "Addressed"},
                ],
            }
            (bb_root / project / "_final_gate_report.json").write_text(json.dumps(report))
            
            result = orch._process_gate_report()
            assert result["passed"] is True
            assert all(g["status"] == "COVERED" for g in result["gaps"])

    def test_process_gate_report_missing_file_raises(self, mock_blackboard):
        """Gate report 文件不存在 → raise（fail-closed）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            # 不创建 gate report
            with pytest.raises(ValueError, match="Gate report not found"):
                orch._process_gate_report()

    def test_process_gate_report_invalid_json_raises(self, mock_blackboard):
        """Gate report 非法 JSON → raise（fail-closed）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            (bb_root / project / "_final_gate_report.json").write_text("invalid json{{")
            
            with pytest.raises(ValueError, match="invalid JSON"):
                orch._process_gate_report()

    def test_process_gate_report_missing_gaps_array_raises(self, mock_blackboard):
        """Gate report 缺少 gaps 数组 → raise（fail-closed）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            report = {"some_other_field": "value"}
            (bb_root / project / "_final_gate_report.json").write_text(json.dumps(report))
            
            with pytest.raises(ValueError, match="missing 'gaps' array"):
                orch._process_gate_report()


# ---------------------------------------------------------------------------
# 完成宣告条件
# ---------------------------------------------------------------------------

class TestCompletionConditions:
    def test_completion_requires_final_synthesis(self, mock_blackboard):
        """全部 WP DONE 但无 final_synthesis_done → 不宣告完成。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_done_wp(bb_root, project, "AAA-001")
            _setup_living_spec(bb_root, project)  # 需要 living_spec 以避免 raise
            # 创建 contract 以避免 infer_contract 动作
            (bb_root / project / "_deliverable_contract.json").write_text(json.dumps({
                "deliverable_type": "report",
                "req_elements": [],
            }))
            with patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()
            # 不应宣告 completed（因为缺少 final_synthesis_done）
            assert report["status"] != "completed"

    def test_completion_with_final_synthesis_done(self, mock_blackboard):
        """全部 WP DONE + final_synthesis_done → 宣告完成。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_done_wp(bb_root, project, "AAA-001")
            _setup_living_spec(bb_root, project)  # 需要 living_spec 以避免 raise
            # 创建 contract 以避免 infer_contract 动作
            (bb_root / project / "_deliverable_contract.json").write_text(json.dumps({
                "deliverable_type": "report",
                "req_elements": [],
            }))
            (bb_root / project / "_final_deliverable_done.json").write_text(json.dumps({
                "completed_at": time.time(),
                "gate_passed": True,
            }))
            with patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()
            assert report["status"] == "completed"
            # 验证 completed 标记包含 final_synthesis_done
            completed = json.loads((bb_root / project / ".deliver_completed.json").read_text())
            assert completed["final_synthesis_done"] is True


# ---------------------------------------------------------------------------
# PulseAction 契约扩展
# ---------------------------------------------------------------------------

class TestPulseActionExtension:
    def test_accepts_infer_deliverable_contract(self):
        """PulseAction 接受 infer_deliverable_contract action。"""
        from domains.deliver_pro.contracts.pulse_report import PulseAction
        action = PulseAction(
            wp_id="BATCH",
            action="infer_deliverable_contract",
            task="Infer contract from living_spec",
            label="infer-contract-test",
        )
        assert action.action == "infer_deliverable_contract"

    def test_accepts_final_synthesis(self):
        """PulseAction 接受 final_synthesis action。"""
        from domains.deliver_pro.contracts.pulse_report import PulseAction
        action = PulseAction(
            wp_id="BATCH",
            action="final_synthesis",
            task="Generate final deliverable",
            label="final-synthesis-test",
        )
        assert action.action == "final_synthesis"

    def test_accepts_run_final_gate(self):
        """PulseAction 接受 run_final_gate action。"""
        from domains.deliver_pro.contracts.pulse_report import PulseAction
        action = PulseAction(
            wp_id="BATCH",
            action="run_final_gate",
            task="LLM-as-Judge semantic gate",
            label="final-gate-test",
        )
        assert action.action == "run_final_gate"
