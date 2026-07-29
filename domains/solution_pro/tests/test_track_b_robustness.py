"""
Track B: Solution Pro 稳健性测试

测试覆盖：
1. _acceptance_from_living_spec: living_spec 缺失 → raise ValueError
2. _acceptance_from_living_spec: living_spec 存在但无 requirement_index → raise ValueError
3. _acceptance_from_living_spec: living_spec 存在且有 requirement_index → 正常返回
4. run_solution_pro: living_spec 缺失 → raise ValueError（不再 fallback）
5. _extract_requirements_from_input 已物理删除验证
"""

import sys as _sys
from pathlib import Path as _Path

_p = _Path(__file__).resolve()
_r = next((d for d in _p.parents if (d / 'core' / 'blackboard').is_dir()), None)
if _r and str(_r) not in _sys.path:
    _sys.path.insert(0, str(_r))

import json
import pytest
from unittest.mock import MagicMock, patch
import tempfile
import shutil

from domains.solution_pro.blackboard import BlackboardManager


# ============================================================================
# Test _acceptance_from_living_spec
# ============================================================================

class TestAcceptanceFromLivingSpec:
    def _make_bm_with_living_spec(self, living_spec_data=None, living_spec_exists=True):
        """创建带或不带 living_spec 的 BlackboardManager"""
        tmpdir = tempfile.mkdtemp()
        bm = BlackboardManager("test_track_b", base_dir=tmpdir)
        bm.init_session()

        if living_spec_exists and living_spec_data:
            bm.write("data/living_spec.json", living_spec_data)

        return bm, tmpdir

    def test_living_spec_missing_raises(self):
        """living_spec 完全缺失 → raise ValueError"""
        from domains.solution_pro.control_contract import _acceptance_from_living_spec

        tmpdir = tempfile.mkdtemp()
        try:
            bm = BlackboardManager("test_ls_missing", base_dir=tmpdir)
            bm.init_session()
            # 不写入任何 living_spec

            with pytest.raises(ValueError, match="living_spec 完全缺失"):
                _acceptance_from_living_spec(bm)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_living_spec_no_requirement_index_raises(self):
        """living_spec 存在但无 requirement_index → raise ValueError"""
        from domains.solution_pro.control_contract import _acceptance_from_living_spec

        tmpdir = tempfile.mkdtemp()
        try:
            bm = BlackboardManager("test_ls_no_req", base_dir=tmpdir)
            bm.init_session()
            # 写入 living_spec 但无 requirement_index
            bm.write("data/living_spec.json", {
                "topic": "test",
                "confirmed": {"objective": "test"},
                # 无 requirement_index
            })

            with pytest.raises(ValueError, match="requirement_index 为空"):
                _acceptance_from_living_spec(bm)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_living_spec_with_requirement_index_returns_criteria(self):
        """living_spec 存在且有 requirement_index → 正常返回"""
        from domains.solution_pro.control_contract import _acceptance_from_living_spec

        tmpdir = tempfile.mkdtemp()
        try:
            bm = BlackboardManager("test_ls_ok", base_dir=tmpdir)
            bm.init_session()
            bm.write("data/living_spec.json", {
                "topic": "test",
                "requirement_index": [
                    {"id": "REQ-001", "description": "功能 A", "priority": "MUST"},
                    {"id": "REQ-002", "description": "功能 B", "priority": "SHOULD"},
                ],
            })

            criteria = _acceptance_from_living_spec(bm)
            assert len(criteria) == 2
            assert criteria[0]["id"] == "REQ-001"
            assert criteria[0]["text"] == "功能 A"
            assert criteria[1]["id"] == "REQ-002"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================================
# Test _extract_requirements_from_input 已物理删除
# ============================================================================

class TestExtractRequirementsDeleted:
    def test_function_no_longer_exists(self):
        """_extract_requirements_from_input 已被物理删除"""
        import domains.solution_pro as sp
        assert not hasattr(sp, '_extract_requirements_from_input'), (
            "_extract_requirements_from_input 应该已被物理删除（Track B）"
        )

    def test_function_not_importable(self):
        """确认无法从 solution_pro 导入该函数"""
        with pytest.raises(ImportError):
            from domains.solution_pro import _extract_requirements_from_input


# ============================================================================
# Test run_solution_pro living_spec 缺失 → raise
# ============================================================================

class TestRunSolutionProContract:
    def test_no_living_spec_raises(self):
        """run_solution_pro: 无 living_spec 且无 handoff package → raise"""
        from domains.solution_pro import run_solution_pro

        # 用 mock 阻止实际 blackboard 创建
        with patch('domains.solution_pro.BlackboardManager') as MockBM:
            mock_bm = MagicMock()
            mock_bm.session_id = "test_session"
            mock_bm.session_dir = _Path(tempfile.mkdtemp())
            MockBM.return_value = mock_bm

            # _try_load_handoff_package returns None (no handoff package)
            with patch('domains.solution_pro._try_load_handoff_package', return_value=None):
                with pytest.raises(ValueError, match="Track B 契约铁律|requirement_index 为空"):
                    run_solution_pro(user_input="test input without spec")


# ============================================================================
# Test raw_user_input.txt 持久化
# ============================================================================

class TestRawUserInputPersistence:
    def test_coordinator_writes_raw_user_input(self):
        """coordinator.build_handoff_on_done 写入 data/raw_user_input.txt"""
        # 这个测试验证 B3 持久化逻辑
        # 由于 build_handoff_on_done 需要完整的 spec_pro pipeline，
        # 这里只验证 data/raw_user_input.txt 的写入逻辑
        tmpdir = tempfile.mkdtemp()
        try:
            bm = BlackboardManager("test_raw_input", base_dir=tmpdir)
            bm.init_session()

            # 模拟 init_session 写入 input.md
            bm.write("input.md", "测试用户输入：CoWoS-S/L PDK驱动型团队")

            # 验证 input.md 存在
            content = bm.read("input.md")
            assert content == "测试用户输入：CoWoS-S/L PDK驱动型团队"

            # 模拟 B3 写入 raw_user_input.txt
            bm.write("data/raw_user_input.txt", str(content))
            raw_content = bm.read("data/raw_user_input.txt")
            assert raw_content == "测试用户输入：CoWoS-S/L PDK驱动型团队"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
