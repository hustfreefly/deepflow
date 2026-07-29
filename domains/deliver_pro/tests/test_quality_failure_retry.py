"""Tests for quality_failure retry extension (F-B 自然延伸).

覆盖规格要求：
1. quality_failure 任务被重试循环拾取，params 含 quality_feedback 反馈文本
2. quality_feedback 缺失 → 跳过 + warning（不派发）
3. deps 未全 COMPLETE 的 quality 任务不派发（但守卫类 3 仍拦截终态）
4. L1 豁免对 quality_failure 生效；预算耗尽不豁免
5. 守卫类 3 对 quality_failure 生效
6. contract_violation 全部现有测试保持绿（回归）— 由 test_fix_b_*.py 覆盖
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domains.deliver_pro.contracts import (
    ConcurrencyPlan,
    ExecutionPlan,
    TaskNode,
    Wave,
)
from domains.deliver_pro.orchestrator import DeliverOrchestrator, RETRY_BUDGET


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_driver(tmp_path):
    driver = MagicMock()
    driver.worker_outputs_dir = tmp_path / "outputs"
    driver.worker_outputs_dir.mkdir(parents=True, exist_ok=True)

    def fake_prepare(task_node, plan):
        task_id = task_node.task_id
        output_dir = driver.worker_outputs_dir / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        stages_dir = tmp_path / "stages"
        stages_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = stages_dir / f"_bootstrap_worker_{task_id}.md"
        prompt_file.write_text(f"# Worker Prompt for {task_id}\nDo the task.\n", encoding="utf-8")
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": f"deliver-worker-{task_id.lower()}",
            "task_id": task_id,
            "task": f"## 环境\n- DeepFlow root: `{tmp_path}`\n\n用 `read` 工具读取: `{prompt_file}`\n",
            "thinking": "high",
            "timeoutSeconds": 300000,
        }

    driver.orch._prepare_single_worker_spawn.side_effect = fake_prepare
    return driver


@pytest.fixture
def orch_instance(tmp_path):
    instance = MagicMock(spec=DeliverOrchestrator)
    instance.progress = {}
    instance.blackboard_root = tmp_path / "blackboard"
    instance.project_name = "test_project"
    instance._prepare_worker_retries = DeliverOrchestrator._prepare_worker_retries.__get__(
        instance, DeliverOrchestrator
    )
    instance._filter_spawnable_tasks = DeliverOrchestrator._filter_spawnable_tasks.__get__(
        instance, DeliverOrchestrator
    )
    instance._wp_dir = DeliverOrchestrator._wp_dir.__get__(instance, DeliverOrchestrator)
    instance._get_wp_project_name = DeliverOrchestrator._get_wp_project_name.__get__(
        instance, DeliverOrchestrator
    )
    return instance


def _write_manifest(wo_dir, task_id, failure_class=None, quality_feedback=None, failure_reason="test"):
    manifest_path = wo_dir / task_id / "MANIFEST.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "task_id": task_id,
        "status": "FAILED",
        "failure_reason": failure_reason,
    }
    if failure_class:
        data["failure_class"] = failure_class
    if quality_feedback is not None:
        data["quality_feedback"] = quality_feedback
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    return manifest_path


def _make_params(task_ids):
    return [
        {"task_id": tid, "runtime": "subagent", "mode": "run", "task": f"do {tid}"}
        for tid in task_ids
    ]


def _setup_wp_dirs(orch, wp_id):
    wp_dir = orch._wp_dir(wp_id)
    wo = wp_dir / "stages" / "worker_outputs"
    wo.mkdir(parents=True, exist_ok=True)
    return wo


# ============================================================================
# Test 1: quality_failure 被重试循环拾取 + feedback 文本正确
# ============================================================================

class TestQualityFailureRetryPickup:
    def test_quality_failure_enters_retry_with_feedback(self, orch_instance, mock_driver, tmp_path):
        """quality_failure + quality_feedback 存在 → 进入 retry，prompt 含失败原因"""
        _write_manifest(
            mock_driver.worker_outputs_dir, "T-001",
            failure_class="quality_failure",
            quality_feedback="算术错误：总成本计算使用了错误的汇率（1.2 应为 7.2）",
        )
        mock_driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=1,
                waves=[Wave(wave=1, task_ids=["T-001"])],
            ),
        )
        mock_driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": set(),
            "failed": {"T-001"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }
        orch_instance.progress = {
            "WP-001": {"task_attempts": {"T-001": 1}},
        }

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids = [p.get("task_id") for p in params]
        assert "T-001" in task_ids, f"T-001 should be in retry, got {task_ids}"

        # Verify feedback text in prompt file
        t001_params = next(p for p in params if p.get("task_id") == "T-001")
        prompt_match = re.search(r"读取:\s*`([^`]+)`", t001_params["task"])
        assert prompt_match
        prompt_content = Path(prompt_match.group(1)).read_text(encoding="utf-8")
        assert "质量验证 FAIL" in prompt_content
        assert "算术错误" in prompt_content
        assert "汇率" in prompt_content

        # Verify alert code
        t001_alerts = [a for a in alerts if "T-001" in a.get("message", "")]
        assert any(a["code"] == "TASK_RETRY_QUALITY" for a in t001_alerts)


# ============================================================================
# Test 2: quality_feedback 缺失 → 跳过 + warning
# ============================================================================

class TestQualityFeedbackMissing:
    def test_no_quality_feedback_skips_task(self, orch_instance, mock_driver, tmp_path, caplog):
        """quality_failure 但无 quality_feedback → 跳过 + warning"""
        _write_manifest(
            mock_driver.worker_outputs_dir, "T-001",
            failure_class="quality_failure",
            # 不写 quality_feedback
        )
        mock_driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=1,
                waves=[Wave(wave=1, task_ids=["T-001"])],
            ),
        )
        mock_driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": set(),
            "failed": {"T-001"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }
        orch_instance.progress = {
            "WP-001": {"task_attempts": {"T-001": 1}},
        }

        import logging
        with caplog.at_level(logging.WARNING):
            params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids = [p.get("task_id") for p in params]
        assert "T-001" not in task_ids, "T-001 should NOT be in retry without quality_feedback"

        # Verify warning was logged
        assert any("quality_feedback" in record.message for record in caplog.records)


# ============================================================================
# Test 3: deps 未全 COMPLETE → 不派发
# ============================================================================

class TestQualityFailureDepsNotComplete:
    def test_deps_not_complete_skips_dispatch(self, orch_instance, mock_driver, tmp_path):
        """quality_failure + deps 含 running → 不派发"""
        _write_manifest(
            mock_driver.worker_outputs_dir, "T-002",
            failure_class="quality_failure",
            quality_feedback="数据引用过时",
        )
        # T-002 depends on T-001 which is still running
        mock_driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
                TaskNode(task_id="T-002", title="Task 2", scenario_type="code", depends_on=["T-001"]),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=2,
                waves=[Wave(wave=1, task_ids=["T-001", "T-002"])],
            ),
        )
        mock_driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": {"T-001"},  # T-001 still running
            "failed": {"T-002"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }
        orch_instance.progress = {
            "WP-001": {"task_attempts": {"T-002": 1}},
        }

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids = [p.get("task_id") for p in params]
        assert "T-002" not in task_ids, "T-002 should NOT be dispatched when T-001 is still running"

    def test_deps_all_complete_allows_dispatch(self, orch_instance, mock_driver, tmp_path):
        """quality_failure + deps 全 COMPLETE → 正常派发"""
        _write_manifest(
            mock_driver.worker_outputs_dir, "T-002",
            failure_class="quality_failure",
            quality_feedback="数据引用过时",
        )
        mock_driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
                TaskNode(task_id="T-002", title="Task 2", scenario_type="code", depends_on=["T-001"]),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=2,
                waves=[Wave(wave=1, task_ids=["T-001", "T-002"])],
            ),
        )
        mock_driver.orch._derive_worker_progress.return_value = {
            "completed": {"T-001"},  # T-001 completed
            "running": set(),
            "failed": {"T-002"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }
        orch_instance.progress = {
            "WP-001": {"task_attempts": {"T-002": 1}},
        }

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids = [p.get("task_id") for p in params]
        assert "T-002" in task_ids, "T-002 should be dispatched when all deps are COMPLETE"


# ============================================================================
# Test 4: L1 豁免对 quality_failure 生效；预算耗尽不豁免
# ============================================================================

class TestL1QualityFailureExemption:
    def test_quality_failure_survives_l1(self, orch_instance, tmp_path):
        """quality_failure + 预算未耗尽 → params 过 L1 存活"""
        wp_id = "WP-QF-001"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        _write_manifest(wo, "T-001", failure_class="quality_failure", quality_feedback="test")

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": 1},
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 1, f"quality_failure params should survive L1, got {len(result)}"
        assert result[0]["task_id"] == "T-001"

    def test_quality_failure_budget_exhausted_filtered(self, orch_instance, tmp_path):
        """quality_failure + 预算耗尽 → 被 L1 过滤"""
        wp_id = "WP-QF-002"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        _write_manifest(wo, "T-001", failure_class="quality_failure", quality_feedback="test")

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": RETRY_BUDGET},
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 0, "quality_failure with exhausted budget should be filtered"


# ============================================================================
# Test 5: 守卫类 3 对 quality_failure 生效
# ============================================================================

class TestGuardClass3QualityFailure:
    """守卫类 3 _has_unexecuted_tasks 对 quality_failure 生效。"""

    def test_guard3_quality_failure_intercepts(self, orch_instance, tmp_path):
        """quality_failure + 预算未耗尽 → 守卫类 3 拦截终态（返回非空）"""
        wp_id = "WP-QF-003"
        # Use the real driver mock approach
        driver = MagicMock()
        wo = tmp_path / "worker_outputs"
        driver.worker_outputs_dir = wo
        _write_manifest(wo, "T-001", failure_class="quality_failure", quality_feedback="test")

        driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id=wp_id,
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=1,
                waves=[Wave(wave=1, task_ids=["T-001"])],
            ),
        )
        driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": set(),
            "failed": {"T-001"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }

        orch_instance.progress = {
            wp_id: {"task_attempts": {"T-001": 1}},
        }

        # Bind the real _has_unexecuted_tasks method
        orch_instance._has_unexecuted_tasks = DeliverOrchestrator._has_unexecuted_tasks.__get__(
            orch_instance, DeliverOrchestrator
        )

        result = orch_instance._has_unexecuted_tasks(wp_id, driver)
        assert "T-001" in result, f"Guard class 3 should intercept quality_failure T-001, got {result}"

    def test_guard3_quality_failure_budget_exhausted_no_intercept(self, orch_instance, tmp_path):
        """quality_failure + 预算耗尽 → 守卫类 3 不拦截（已无救）"""
        wp_id = "WP-QF-004"
        driver = MagicMock()
        wo = tmp_path / "worker_outputs"
        driver.worker_outputs_dir = wo
        _write_manifest(wo, "T-001", failure_class="quality_failure", quality_feedback="test")

        driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id=wp_id,
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=1,
                waves=[Wave(wave=1, task_ids=["T-001"])],
            ),
        )
        driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": set(),
            "failed": {"T-001"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }

        orch_instance.progress = {
            wp_id: {"task_attempts": {"T-001": RETRY_BUDGET}},  # budget exhausted
        }

        orch_instance._has_unexecuted_tasks = DeliverOrchestrator._has_unexecuted_tasks.__get__(
            orch_instance, DeliverOrchestrator
        )

        result = orch_instance._has_unexecuted_tasks(wp_id, driver)
        assert "T-001" not in result, "Guard class 3 should NOT intercept when budget exhausted"


# ============================================================================
# Test 6: contract_violation 回归（现有路径不被破坏）
# ============================================================================

class TestContractViolationRegression:
    """确保 contract_violation 现有路径不被破坏。"""

    def test_contract_violation_still_retried(self, orch_instance, mock_driver, tmp_path):
        """contract_violation 仍然被重试循环拾取"""
        _write_manifest(
            mock_driver.worker_outputs_dir, "T-001",
            failure_class="contract_violation",
        )
        mock_driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=1,
                waves=[Wave(wave=1, task_ids=["T-001"])],
            ),
        )
        mock_driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": set(),
            "failed": {"T-001"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }
        orch_instance.progress = {
            "WP-001": {"task_attempts": {"T-001": 1}},
        }

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids = [p.get("task_id") for p in params]
        assert "T-001" in task_ids

        # Verify contract_violation feedback (not quality_feedback)
        t001_params = next(p for p in params if p.get("task_id") == "T-001")
        prompt_match = re.search(r"读取:\s*`([^`]+)`", t001_params["task"])
        assert prompt_match
        prompt_content = Path(prompt_match.group(1)).read_text(encoding="utf-8")
        assert "契约违规重试" in prompt_content
        assert "DELIVERABLE.md" in prompt_content

    def test_substance_failure_still_not_retried(self, orch_instance, mock_driver, tmp_path):
        """substance_failure 仍然不被重试"""
        _write_manifest(
            mock_driver.worker_outputs_dir, "T-001",
            failure_class="substance_failure",
        )
        mock_driver.orch.load_execution_plan.return_value = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id="T-001", title="Task 1", scenario_type="code"),
            ],
            concurrency_plan=ConcurrencyPlan(
                suggested_parallelism=1,
                waves=[Wave(wave=1, task_ids=["T-001"])],
            ),
        )
        mock_driver.orch._derive_worker_progress.return_value = {
            "completed": set(),
            "running": set(),
            "failed": {"T-001"},
            "blocked": set(),
            "timed_out": set(),
            "pending": set(),
        }
        orch_instance.progress = {
            "WP-001": {"task_attempts": {"T-001": 1}},
        }

        params, alerts = orch_instance._prepare_worker_retries("WP-001", mock_driver)

        task_ids = [p.get("task_id") for p in params]
        assert "T-001" not in task_ids
