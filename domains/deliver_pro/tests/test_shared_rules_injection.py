"""Shared subagent rules must be injected into every Deliver Pro prompt builder.

Regression guard for the worker prompt path that dropped rules_section
(wp_runner.py template branch returned prompt + semantic_context_section only).
"""

import pytest

from domains.deliver_pro.contracts import ExecutionPlan, TaskNode, WorkPackage
from domains.deliver_pro.wp_runner import DeliverWPRunner

MARKER = "SHARED_RULES_MARKER_FOR_TEST"


@pytest.fixture
def runner(tmp_path):
    wp = WorkPackage(wp_id="WP-001", title="Test", objective="Test", scenario="code")
    runner = DeliverWPRunner(
        wp, tmp_path / "blackboard" / "test_project", project_name="test_project"
    )
    runner._load_shared_rules = lambda: MARKER
    return runner


@pytest.fixture
def plan():
    return ExecutionPlan(
        wp_id="WP-001",
        scenario="code",
        task_graph=[TaskNode(task_id="T-001", title="Root", scenario_type="code")],
    )


def test_analyze_prompt_includes_shared_rules(runner):
    assert MARKER in runner._build_analyze_prompt()


def test_worker_prompt_includes_shared_rules(runner, plan):
    assert MARKER in runner._build_worker_prompt(plan.task_graph[0], plan)


def test_integrate_prompt_includes_shared_rules(runner, plan):
    assert MARKER in runner._build_integrate_prompt(plan, [])


def test_validate_prompt_includes_shared_rules(runner, plan):
    assert MARKER in runner._build_validate_prompt(plan, 1)


def test_package_prompt_includes_shared_rules(runner, plan):
    assert MARKER in runner._build_package_prompt(plan)
