"""P2-3: Spec Pro resume 入口回归测试

验证 resume 从正确轮次恢复执行。
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_cmd_resume_loads_state_and_resumes():
    """cmd_resume 应加载状态并从 current_round 恢复"""
    from domains.spec_pro.spec_pro_api import cmd_resume

    mock_state = {
        "session_id": "spec_test_001",
        "base_path": "/tmp/test_bb/spec_test_001",
        "scenario": "genesis",
        "mode": "standard",
        "current_round": 3,
        "state": "in_progress",
    }

    mock_coord = MagicMock()
    mock_coord.session_id = "spec_test_001"
    mock_coord.build_next_round_task.return_value = {"task": "mock_task"}

    with patch("domains.spec_pro.spec_pro_api.load_coord_state", return_value=mock_state):
        with patch("domains.spec_pro.spec_pro_api.reconstruct_coord", return_value=mock_coord):
            with patch("domains.spec_pro.spec_pro_api.save_coord_state"):
                args = MagicMock()
                args.session_id = "spec_test_001"

                result = cmd_resume(args)

                assert result["success"] is True
                assert result["resumed_from_round"] == 3
                assert result["session_id"] == "spec_test_001"


def test_cmd_resume_handles_missing_state():
    """cmd_resume 应优雅处理缺失状态"""
    from domains.spec_pro.spec_pro_api import cmd_resume

    with patch("domains.spec_pro.spec_pro_api.load_coord_state", side_effect=ValueError("No state")):
        args = MagicMock()
        args.session_id = "nonexistent_session"

        result = cmd_resume(args)

        assert result["success"] is False
        assert "Failed to load session state" in result["error"]


def test_resume_cli_parser_exists():
    """验证 resume 子命令已注册到 argparse"""
    import argparse
    from domains.spec_pro.spec_pro_api import main

    # 验证 resume 命令被识别（不实际执行）
    with patch("domains.spec_pro.spec_pro_api.cmd_resume", return_value={"success": True}):
        with patch("sys.argv", ["spec_pro_api.py", "resume", "spec_test_001"]):
            # main() 应能解析 resume 命令并调用 cmd_resume
            result = main()
            assert result == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
