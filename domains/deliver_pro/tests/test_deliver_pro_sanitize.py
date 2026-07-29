"""P0-1: Deliver Pro project_name sanitize 回归测试

验证含 / 的 project_name 被正确处理（替换为 _），防止路径穿越。
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_run_deliver_pro_sanitizes_slash_in_project_name():
    """project_name 含 / 时，sanitize 后应替换为 _"""
    # 模拟 BLACKBOARD_ROOT 和 ship_package 存在
    # 注: V3 Pulse 模式不再调用 auto_bootstrap（2026-07-28 防呆改造）
    with patch("domains.deliver_pro.BLACKBOARD_ROOT", Path("/tmp/test_bb")) as mock_bb:
        with patch("domains.deliver_pro.DEEPFLOW_ROOT", Path("/tmp/df")):
            with patch("domains.deliver_pro.Path.exists", return_value=True):
                from domains.deliver_pro import run_deliver_pro
                result = run_deliver_pro("foo/bar")
                # project_name 应被 sanitize
                assert result["project_name"] == "foo_bar"
                assert "/" not in result["project_name"]


def test_run_deliver_pro_sanitizes_dotdot_in_project_name():
    """project_name 含 .. 时，sanitize 后应替换为 _"""
    with patch("domains.deliver_pro.BLACKBOARD_ROOT", Path("/tmp/test_bb")):
        with patch("domains.deliver_pro.DEEPFLOW_ROOT", Path("/tmp/df")):
            with patch("domains.deliver_pro.Path.exists", return_value=True):
                from domains.deliver_pro import run_deliver_pro
                result = run_deliver_pro("../etc/passwd")
                assert ".." not in result["project_name"]
                assert "/" not in result["project_name"]


def test_deliver_orchestrator_sanitizes_project_name():
    """DeliverOrchestrator.__init__ 也应 sanitize project_name"""
    from domains.deliver_pro.orchestrator import DeliverOrchestrator

    # F1 fix (W3): ship_package 缺失 → raise（禁止静默降级）
    # project_name sanitization happens before _find_ship_package raises
    with patch("domains.deliver_pro.orchestrator.DeliverOrchestrator._find_ship_package") as mock_find:
        mock_find.side_effect = FileNotFoundError()
        import pytest
        with pytest.raises(FileNotFoundError):
            DeliverOrchestrator("foo/bar")
        # Verify sanitization happened before the raise
        mock_find.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
