"""P0-1: Deliver Pro project_name sanitize 回归测试

验证含 / 的 project_name 被正确处理（替换为 _），防止路径穿越。
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_run_deliver_pro_sanitizes_slash_in_project_name():
    """project_name 含 / 时，sanitize 后应替换为 _"""
    # 模拟 BLACKBOARD_ROOT 和 ship_package 存在
    with patch("domains.deliver_pro.BLACKBOARD_ROOT", Path("/tmp/test_bb")) as mock_bb:
        with patch("domains.deliver_pro.DEEPFLOW_ROOT", Path("/tmp/df")):
            with patch("domains.deliver_pro.Path.read_text", return_value="{}"):
                # 模拟 ship_package.json 存在
                with patch("domains.deliver_pro.Path.exists", return_value=True):
                    with patch("domains.deliver_pro.auto_bootstrap", return_value="mock_task"):
                        from domains.deliver_pro import run_deliver_pro
                        result = run_deliver_pro("foo/bar")
                        # project_name 应被 sanitize
                        assert result["project_name"] == "foo_bar"
                        assert "/" not in result["project_name"]


def test_run_deliver_pro_sanitizes_dotdot_in_project_name():
    """project_name 含 .. 时，sanitize 后应替换为 _"""
    with patch("domains.deliver_pro.BLACKBOARD_ROOT", Path("/tmp/test_bb")):
        with patch("domains.deliver_pro.DEEPFLOW_ROOT", Path("/tmp/df")):
            with patch("domains.deliver_pro.Path.read_text", return_value="{}"):
                with patch("domains.deliver_pro.Path.exists", return_value=True):
                    with patch("domains.deliver_pro.auto_bootstrap", return_value="mock_task"):
                        from domains.deliver_pro import run_deliver_pro
                        result = run_deliver_pro("../etc/passwd")
                        assert ".." not in result["project_name"]
                        assert "/" not in result["project_name"]


def test_deliver_orchestrator_sanitizes_project_name():
    """DeliverOrchestrator.__init__ 也应 sanitize project_name"""
    from domains.deliver_pro.orchestrator import DeliverOrchestrator

    with patch("domains.deliver_pro.orchestrator.DeliverOrchestrator._find_ship_package") as mock_find:
        mock_find.side_effect = FileNotFoundError()
        orch = DeliverOrchestrator("foo/bar")
        assert orch.project_name == "foo_bar"
        assert "/" not in orch.project_name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
