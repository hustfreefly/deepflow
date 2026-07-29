"""W2 静默降级治理测试

覆盖 3 个修复点：
1. user_input 校验（P0-2a）：None/空/纯空白 → raise ValueError
2. mkdir 顺序（P0-2b）：校验失败时目录未被创建
3. frozen_spec.md 渲染失败 → raise（P0-3）
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestP02aUserInputValidation:
    """P0-2a: user_input 校验"""

    def test_none_raises(self):
        from domains.solution_pro import run_solution_pro
        with pytest.raises(ValueError, match="user_input 为 None"):
            run_solution_pro(user_input=None)

    def test_empty_string_raises(self):
        from domains.solution_pro import run_solution_pro
        with pytest.raises(ValueError, match="空字符串或纯空白"):
            run_solution_pro(user_input="")

    def test_whitespace_only_raises(self):
        from domains.solution_pro import run_solution_pro
        with pytest.raises(ValueError, match="空字符串或纯空白"):
            run_solution_pro(user_input="   \n\t  ")

    def test_non_string_raises(self):
        from domains.solution_pro import run_solution_pro
        with pytest.raises(ValueError, match="必须是 str"):
            run_solution_pro(user_input=12345)

    def test_non_string_list_raises(self):
        from domains.solution_pro import run_solution_pro
        with pytest.raises(ValueError, match="必须是 str"):
            run_solution_pro(user_input=["a", "b"])


class TestP02bMkdirOrder:
    """P0-2b: 校验失败时目录未被创建"""

    def test_validation_failure_no_mkdir(self, tmp_path):
        """user_input 为空时，blackboard session 目录不应被创建"""
        from domains.solution_pro import run_solution_pro

        blackboard_root = tmp_path / "blackboard"
        blackboard_root.mkdir()

        # 需要让 BlackboardManager 使用 tmp_path 作为 base_dir
        with patch(
            "domains.solution_pro.BlackboardManager"
        ) as MockBM:
            mock_bm = MagicMock()
            mock_bm.session_id = "test_session"
            mock_bm.session_dir = blackboard_root / "test_session"
            MockBM.return_value = mock_bm

            with pytest.raises(ValueError, match="user_input 为 None"):
                run_solution_pro(user_input=None)

            # init_session 不应被调用
            mock_bm.init_session.assert_not_called()

    def test_requirement_index_failure_no_mkdir(self, tmp_path):
        """living_spec 校验失败（requirement_index 为空）时，init_session 不应被调用"""
        from domains.solution_pro import run_solution_pro

        with patch(
            "domains.solution_pro.BlackboardManager"
        ) as MockBM:
            mock_bm = MagicMock()
            mock_bm.session_id = "test_session"
            mock_bm.session_dir = tmp_path / "test_session"
            mock_bm._base = tmp_path
            MockBM.return_value = mock_bm

            # 提供 living_spec 但无 requirement_index
            with pytest.raises(ValueError, match="requirement_index 为空"):
                run_solution_pro(
                    user_input="test requirement",
                    living_spec={"confirmed": {}, "narrative": ""},
                )

            # init_session 不应被调用
            mock_bm.init_session.assert_not_called()


class TestP03FrozenSpecMdRenderRaise:
    """P0-3: frozen_spec.md 渲染失败 → raise"""

    def test_render_failure_raises(self, tmp_path):
        """render_frozen_spec_md 抛异常时，run_solution_pro 必须 raise（不能只 warning）"""
        from domains.solution_pro import run_solution_pro

        with patch(
            "domains.solution_pro.BlackboardManager"
        ) as MockBM:
            mock_bm = MagicMock()
            mock_bm.session_id = "test_session"
            mock_bm.session_dir = tmp_path / "test_session"
            mock_bm._base = tmp_path
            MockBM.return_value = mock_bm

            # 提供合法的 living_spec
            living_spec = {
                "requirement_index": ["REQ-1"],
                "semantic_anchors": ["anchor1"],
            }

            # mock render_frozen_spec_md 抛异常
            with patch(
                "domains.solution_pro.frozen_living_md.render_frozen_spec_md",
                side_effect=RuntimeError("render boom"),
            ):
                with pytest.raises(RuntimeError, match="render boom"):
                    run_solution_pro(
                        user_input="test input for rendering",
                        living_spec=living_spec,
                    )
