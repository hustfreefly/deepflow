"""W4-F4/F5: deliver 侧 serving_principles 包级 fallback + ship_context 死路径清理。

F4: _adapt_ship_pro_wp 支持 package_serving_principles fallback（semantic_anchors 同款模式）。
F5: ship_context.json reader 已删除，Worker prompt 不含 {ship_context} 占位符。
"""
import json

import pytest

from domains.deliver_pro import _adapt_ship_pro_wp
from domains.deliver_pro.contracts import WorkPackage
from domains.deliver_pro.prompt_registry import load_prompt


def _ship_wp():
    return {
        "id": "CORE-001",
        "title": "核心实现",
        "description": "实现核心管线逻辑",
        "acceptance_criteria": ["ac1", "ac2"],
        "deliverables": ["d1"],
        "effort_hours": 4,
    }


class TestServingPrinciplesFallback:
    """F4 端到端消费侧：ship_package 包级 → WP serving_principles 非空"""

    def test_wp_level_priority(self):
        wp = _ship_wp()
        wp["serving_principles"] = [{"obligation": "WP 级原则"}]
        adapted = _adapt_ship_pro_wp(wp, package_serving_principles=[{"obligation": "包级原则"}])
        assert adapted["serving_principles"] == [{"obligation": "WP 级原则"}]

    def test_package_level_fallback(self):
        adapted = _adapt_ship_pro_wp(
            _ship_wp(),
            package_serving_principles=[
                {"obligation": "保持真实性", "source": "guardrails.always_do"},
                {"anti_pattern": "虚构数据", "source": "guardrails.never_do"},
            ],
        )
        assert len(adapted["serving_principles"]) == 2

        # 端到端：适配结果可通过 Deliver WP 契约验证
        wp_obj = WorkPackage.model_validate(adapted)
        assert len(wp_obj.serving_principles) == 2

    def test_no_data_stays_empty(self):
        adapted = _adapt_ship_pro_wp(_ship_wp())
        assert adapted["serving_principles"] == []
        wp_obj = WorkPackage.model_validate(adapted)
        assert wp_obj.serving_principles == []


class TestShipContextCleanup:
    """F5: ship_context 死路径已清理"""

    def test_worker_prompt_no_ship_context_placeholder(self):
        prompt = load_prompt(
            "deliver_worker_base",
            task_id="T-001",
            wp_id="WP-001",
            project_name="test_project",
            wp_subdir="wp_001",
            scenario="code",
            dependencies="无",
            forced_actions="无",
            title="测试任务",
            description="测试描述",
            acceptance_criteria="- ac1\n- ac2",
            expected_outputs="- out.txt (text)",
        )
        assert "{ship_context}" not in prompt
        assert "ShipPackage 上下文" not in prompt

    def test_wp_runner_has_no_ship_context_reader(self):
        from domains.deliver_pro.wp_runner import DeliverWPRunner

        assert not hasattr(DeliverWPRunner, "_load_ship_context")
        assert not hasattr(DeliverWPRunner, "_format_ship_context")

    def test_wp_runner_init_works(self, tmp_path):
        """wp_runner 初始化不报错（ship_context 清理后）"""
        from domains.deliver_pro.wp_runner import DeliverWPRunner

        wp = WorkPackage.model_validate(_adapt_ship_pro_wp(_ship_wp()))
        bb = tmp_path / "blackboard" / "test_project"
        bb.mkdir(parents=True)
        runner = DeliverWPRunner(wp=wp, blackboard_path=bb)
        assert runner.wp.wp_id == "CORE-001"
