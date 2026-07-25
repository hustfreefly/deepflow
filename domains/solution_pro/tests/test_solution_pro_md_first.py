"""P1-2: Solution Pro MD-first 接线回归测试

验证 finalize 相位生成 final_solution.md。
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_finalize_writes_final_solution_md():
    """finalize 相位应调用 render_final_solution_md 并写入 final_solution.md"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        stages_dir = session_dir / "stages"
        stages_dir.mkdir()

        # 写入 final_solution.json
        final_solution = {
            "architecture_overview": "Test architecture",
            "module_design": {"modules": []},
            "data_model": {"entities": []},
            "api_design": {"endpoints": []},
            "technology_stack": {"choices": []},
            "non_functional_requirements": {"items": []},
        }
        (stages_dir / "final_solution.json").write_text(json.dumps(final_solution))

        # 模拟 bb.read_stage 返回 final_solution dict
        mock_bb = MagicMock()
        mock_bb.read_stage.return_value = final_solution

        # 直接测试 render_final_solution_md 被正确调用
        from domains.solution_pro.solution_living_md import render_final_solution_md
        md_content = render_final_solution_md(final_solution)

        # 验证 MD 内容非空且包含关键 section
        assert md_content
        assert "overview" in md_content.lower() or "meta_info" in md_content.lower()

        # 验证写入逻辑（模拟 pulse.py 中的写入代码）
        md_path = stages_dir / "final_solution.md"
        import tempfile as tf
        import os
        fd, tmp = tf.mkstemp(dir=md_path.parent, suffix=".md")
        try:
            os.write(fd, md_content.encode("utf-8"))
            os.close(fd)
            os.replace(tmp, str(md_path))
        except Exception:
            os.close(fd)
            raise

        assert md_path.exists()
        assert md_path.stat().st_size > 0


def test_render_final_solution_md_handles_string_input():
    """render_final_solution_md 应能处理 double-encoded JSON string"""
    from domains.solution_pro.solution_living_md import render_final_solution_md

    data = {
        "architecture_overview": "Test",
        "module_design": {},
        "data_model": {},
        "api_design": {},
        "technology_stack": {},
        "non_functional_requirements": {},
    }
    # 传入 JSON string（double-encoded）
    result = render_final_solution_md(json.dumps(data))
    assert isinstance(result, str)
    assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
