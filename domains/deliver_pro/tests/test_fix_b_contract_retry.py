"""Tests for F-B: verify_worker_output failure_class + contract_violation retry path.

FixFlow 测试 A：修复必须可自动化验证。
覆盖：
- _detect_substance helper
- verify_worker_output 缺 DELIVERABLE.md + 有实质文件 → contract_violation
- verify_worker_output 缺 DELIVERABLE.md + 无实质文件 → substance_failure
- DELIVERABLE.md 过短 + 有实质文件 → contract_violation
- mark_worker_failed 写入 failure_class 到 MANIFEST
- retry 拾取：contract_violation 进入 retry params + prompt 含反馈段
- substance_failure 不进入 retry
- 预算耗尽不进入 retry
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domains.deliver_pro.contracts import (
    ConcurrencyPlan,
    ExecutionPlan,
    TaskNode,
    Wave,
    WorkPackage,
)
from domains.deliver_pro.wp_runner import DeliverWPRunner


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def wp():
    return WorkPackage(
        wp_id="WP-001",
        title="Test Feature",
        objective="Build a test feature",
        scenario="code",
    )


@pytest.fixture
def bb_path(tmp_path):
    return tmp_path / "blackboard" / "test_project"


@pytest.fixture
def orchestrator(wp, bb_path):
    return DeliverWPRunner(wp, bb_path, project_name="test_project")


@pytest.fixture
def sample_plan():
    return ExecutionPlan(
        wp_id="WP-001",
        scenario="code",
        task_graph=[
            TaskNode(task_id="T-001", title="Root task", scenario_type="code"),
        ],
        concurrency_plan=ConcurrencyPlan(
            suggested_parallelism=1,
            waves=[Wave(wave=1, task_ids=["T-001"])],
        ),
    )


# ============================================================================
# _detect_substance
# ============================================================================

class TestDetectSubstance:
    def test_empty_dir(self, orchestrator, tmp_path):
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        assert orchestrator._detect_substance(output_dir) is False

    def test_only_metadata_files(self, orchestrator, tmp_path):
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        (output_dir / "MANIFEST.json").write_text("{}", encoding="utf-8")
        (output_dir / "EVIDENCE.md").write_text("# Evidence\n", encoding="utf-8")
        (output_dir / "ISSUES.md").write_text("无\n", encoding="utf-8")
        assert orchestrator._detect_substance(output_dir) is False

    def test_small_file_ignored(self, orchestrator, tmp_path):
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        # 50 字节 < 100 阈值
        (output_dir / "notes.txt").write_text("x" * 50, encoding="utf-8")
        assert orchestrator._detect_substance(output_dir) is False

    def test_substantial_file_detected(self, orchestrator, tmp_path):
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        # 200 字节 > 100 阈值
        (output_dir / "report.md").write_text("x" * 200, encoding="utf-8")
        assert orchestrator._detect_substance(output_dir) is True

    def test_deliverable_excluded(self, orchestrator, tmp_path):
        """DELIVERABLE.md 即使很大也被排除（避免 too short 分支误判）"""
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        (output_dir / "DELIVERABLE.md").write_text("x" * 500, encoding="utf-8")
        assert orchestrator._detect_substance(output_dir) is False

    def test_nested_substantial_file(self, orchestrator, tmp_path):
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        sub = output_dir / "src"
        sub.mkdir()
        (sub / "main.py").write_text("x" * 200, encoding="utf-8")
        assert orchestrator._detect_substance(output_dir) is True


# ============================================================================
# mark_worker_failed with failure_class
# ============================================================================

class TestMarkWorkerFailedFailureClass:
    def test_no_failure_class(self, orchestrator, tmp_path):
        """未提供 failure_class → MANIFEST 不含该字段（向后兼容）"""
        orchestrator.worker_outputs_dir = tmp_path
        orchestrator.mark_worker_failed("T-001", "some reason")
        manifest = json.loads((tmp_path / "T-001" / "MANIFEST.json").read_text())
        assert "failure_class" not in manifest
        assert manifest["status"] == "FAILED"

    def test_with_failure_class(self, orchestrator, tmp_path):
        """提供 failure_class → MANIFEST 含该字段"""
        orchestrator.worker_outputs_dir = tmp_path
        orchestrator.mark_worker_failed("T-001", "missing files", failure_class="contract_violation")
        manifest = json.loads((tmp_path / "T-001" / "MANIFEST.json").read_text())
        assert manifest["failure_class"] == "contract_violation"
        assert manifest["status"] == "FAILED"

    def test_substance_failure_class(self, orchestrator, tmp_path):
        orchestrator.worker_outputs_dir = tmp_path
        orchestrator.mark_worker_failed("T-001", "no output", failure_class="substance_failure")
        manifest = json.loads((tmp_path / "T-001" / "MANIFEST.json").read_text())
        assert manifest["failure_class"] == "substance_failure"


# ============================================================================
# verify_worker_output failure classification
# ============================================================================

class TestVerifyWorkerOutputFailureClass:
    def test_missing_deliverable_with_substance(self, orchestrator, tmp_path):
        """缺 DELIVERABLE.md + 有实质文件 → contract_violation"""
        # 必须使用 orchestrator.worker_outputs_dir 作为基路径，
        # 因为 mark_worker_failed 写入 self.worker_outputs_dir / task_id / MANIFEST.json
        task_id = "T-001"
        output_dir = orchestrator.worker_outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        # 有实质文件（>100 字节）
        (output_dir / "report.md").write_text("x" * 200, encoding="utf-8")
        # 无 DELIVERABLE.md，无 MANIFEST.json

        orchestrator.verify_worker_output(task_id, output_dir)

        manifest = json.loads((output_dir / "MANIFEST.json").read_text())
        assert manifest["failure_class"] == "contract_violation"
        assert manifest["status"] == "FAILED"

    def test_missing_deliverable_no_substance(self, orchestrator, tmp_path):
        """缺 DELIVERABLE.md + 无实质文件 → substance_failure"""
        task_id = "T-001"
        output_dir = orchestrator.worker_outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        # 无任何实质文件

        orchestrator.verify_worker_output(task_id, output_dir)

        manifest = json.loads((output_dir / "MANIFEST.json").read_text())
        assert manifest["failure_class"] == "substance_failure"
        assert manifest["status"] == "FAILED"

    def test_short_deliverable_with_substance(self, orchestrator, tmp_path):
        """DELIVERABLE.md 过短 + 有实质文件 → contract_violation"""
        task_id = "T-001"
        output_dir = orchestrator.worker_outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "DELIVERABLE.md").write_text("Short", encoding="utf-8")
        # 注意：mark_worker_failed 会读取现有 MANIFEST 并更新，
        # 所以这里预置的 MANIFEST 会被覆盖为 FAILED + failure_class
        (output_dir / "MANIFEST.json").write_text("{}", encoding="utf-8")
        # 有实质文件
        (output_dir / "analysis.md").write_text("x" * 200, encoding="utf-8")

        orchestrator.verify_worker_output(task_id, output_dir)

        manifest = json.loads((output_dir / "MANIFEST.json").read_text())
        assert manifest["failure_class"] == "contract_violation"

    def test_short_deliverable_no_substance(self, orchestrator, tmp_path):
        """DELIVERABLE.md 过短 + 无实质文件 → substance_failure"""
        task_id = "T-001"
        output_dir = orchestrator.worker_outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "DELIVERABLE.md").write_text("Short", encoding="utf-8")
        (output_dir / "MANIFEST.json").write_text("{}", encoding="utf-8")

        orchestrator.verify_worker_output(task_id, output_dir)

        manifest = json.loads((output_dir / "MANIFEST.json").read_text())
        assert manifest["failure_class"] == "substance_failure"


# ============================================================================
# Retry pickup: contract_violation enters retry, substance_failure does not
# ============================================================================

class TestContractViolationRetryPickup:
    """测试 orchestrator._prepare_worker_retries 的 contract_violation 分支。"""

    @pytest.fixture
    def mock_driver(self, tmp_path):
        driver = MagicMock()
        driver.worker_outputs_dir = tmp_path / "outputs"
        driver.worker_outputs_dir.mkdir(parents=True, exist_ok=True)

        # Mock orchestrator with _prepare_single_worker_spawn returning realistic params
        def fake_prepare(task_node, plan):
            task_id = task_node.task_id
            output_dir = driver.worker_outputs_dir / task_id
            output_dir.mkdir(parents=True, exist_ok=True)
            # 模拟 auto_bootstrap：写 prompt 文件并返回引用字符串
            stages_dir = tmp_path / "stages"
            stages_dir.mkdir(parents=True, exist_ok=True)
            prompt_file = stages_dir / f"_bootstrap_worker_{task_id}.md"
            prompt_file.write_text(f"# Worker Prompt for {task_id}\nDo the task.\n", encoding="utf-8")
            return {
                "runtime": "subagent",
                "mode": "run",
                "label": f"deliver-worker-wp001-{task_id.lower()}",
                "task_id": task_id,
                "task": f"## 环境\n- DeepFlow root: `{tmp_path}`\n\n用 `read` 工具读取: `{prompt_file}`\n",
                "thinking": "high",
                "timeoutSeconds": 300000,
            }

        driver.orch._prepare_single_worker_spawn.side_effect = fake_prepare
        driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
                TaskNode(task_id="T-002", title="Task 2", scenario_type="code"),
                TaskNode(task_id="T-003", title="Task 3", scenario_type="code"),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=3,
                waves=[Wave(wave=1, task_ids=["T-001", "T-002", "T-003"])],
            ),
        )
        # _derive_worker_progress: T-001 contract_violation, T-002 substance_failure,
        # T-003 contract_violation but budget exhausted
        driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": set(),
            "failed": {"T-001", "T-002", "T-003"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }
        return driver

    @pytest.fixture
    def orch_instance(self, tmp_path):
        """Create a minimal orchestrator-like object for _prepare_worker_retries."""
        from domains.deliver_pro.orchestrator import DeliverOrchestrator
        # 使用 MagicMock 绕过 __init__
        instance = MagicMock(spec=DeliverOrchestrator)
        instance.progress = {
            "WP-001": {
                "task_attempts": {
                    "T-001": 1,  # contract_violation, under budget → should retry
                    "T-002": 1,  # substance_failure → should NOT retry
                    "T-003": 3,  # contract_violation, budget exhausted → should NOT retry
                },
            }
        }
        # Bind the real method
        instance._prepare_worker_retries = DeliverOrchestrator._prepare_worker_retries.__get__(
            instance, DeliverOrchestrator
        )
        return instance

    def _write_manifest(self, driver, task_id, failure_class=None):
        manifest_path = driver.worker_outputs_dir / task_id / "MANIFEST.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": task_id,
            "status": "FAILED",
            "failure_reason": "test failure",
        }
        if failure_class:
            data["failure_class"] = failure_class
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

    def test_contract_violation_enters_retry(self, orch_instance, mock_driver, tmp_path):
        """contract_violation + 预算未耗尽 → 进入 retry params"""
        self._write_manifest(mock_driver, "T-001", "contract_violation")
        self._write_manifest(mock_driver, "T-002", "substance_failure")
        self._write_manifest(mock_driver, "T-003", "contract_violation")

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        # T-001 should be in retry params
        task_ids_in_retry = [p.get("task_id") for p in params]
        assert "T-001" in task_ids_in_retry, f"T-001 should be in retry, got {task_ids_in_retry}"

        # T-001 prompt should contain feedback section
        t001_params = next(p for p in params if p.get("task_id") == "T-001")
        prompt_file_match = re.search(r"读取:\s*`([^`]+)`", t001_params["task"])
        assert prompt_file_match, "Could not find prompt file path in task bootstrap string"
        prompt_content = Path(prompt_file_match.group(1)).read_text(encoding="utf-8")
        assert "上次失败反馈（契约违规重试）" in prompt_content
        assert "DELIVERABLE.md" in prompt_content

        # T-001 should have TASK_RETRY_CONTRACT alert
        t001_alerts = [a for a in alerts if "T-001" in a.get("message", "")]
        assert any(a["code"] == "TASK_RETRY_CONTRACT" for a in t001_alerts)

    def test_substance_failure_not_retried(self, orch_instance, mock_driver, tmp_path):
        """substance_failure → 不进入 retry"""
        self._write_manifest(mock_driver, "T-001", "contract_violation")
        self._write_manifest(mock_driver, "T-002", "substance_failure")
        self._write_manifest(mock_driver, "T-003", "contract_violation")

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids_in_retry = [p.get("task_id") for p in params]
        assert "T-002" not in task_ids_in_retry, "T-002 (substance_failure) should NOT be retried"

    def test_budget_exhausted_not_retried(self, orch_instance, mock_driver, tmp_path):
        """contract_violation + 预算耗尽 → 不进入 retry，但有 EXHAUSTED 告警"""
        self._write_manifest(mock_driver, "T-001", "contract_violation")
        self._write_manifest(mock_driver, "T-002", "substance_failure")
        self._write_manifest(mock_driver, "T-003", "contract_violation")

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids_in_retry = [p.get("task_id") for p in params]
        assert "T-003" not in task_ids_in_retry, "T-003 (budget exhausted) should NOT be retried"

        # Should have TASK_RETRY_CONTRACT_EXHAUSTED alert for T-003
        t003_alerts = [a for a in alerts if "T-003" in a.get("message", "")]
        assert any(a["code"] == "TASK_RETRY_CONTRACT_EXHAUSTED" for a in t003_alerts)
