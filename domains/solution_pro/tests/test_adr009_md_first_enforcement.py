"""ADR-009 Phase 6: MD-first 防回归测试

确保交付物 stage（frozen_spec, final_solution, solution_document）
始终使用 MD 格式作为主要真相源，不会退化为 JSON 主写入。

运行:
  cd ~/.openclaw/workspace/.deepflow && python3 -m pytest \
    domains/solution_pro/tests/test_adr009_md_first_enforcement.py -v
"""

import pytest
import json
import tempfile
from pathlib import Path


DELIVERY_STAGES = ["frozen_spec", "final_solution", "solution_document"]


@pytest.fixture
def bb(tmp_path):
    """创建临时 BlackboardManager"""
    from core.blackboard.blackboard_manager import BlackboardManager
    return BlackboardManager(session_id="adr009_test", base_dir=tmp_path)


class TestMDFirstEnforcement:
    """确保交付物 stage 是 MD-first"""

    @pytest.mark.parametrize("stage_name", DELIVERY_STAGES)
    def test_write_stage_str_creates_md(self, bb, stage_name):
        """写入 str 内容到交付物 stage 应生成 .md 文件"""
        md_content = f"# Test {stage_name}\n\nThis is MD content."
        result = bb.write_stage(stage_name, md_content)
        assert result is True

        # .md 文件应存在
        md_path = bb._stage_path(stage_name, ".md")
        assert md_path.exists(), f"{stage_name} .md file should exist after write_stage(str)"

        # .json 文件不应存在
        json_path = bb._stage_path(stage_name, ".json")
        assert not json_path.exists(), f"{stage_name} .json file should NOT exist after write_stage(str)"

    @pytest.mark.parametrize("stage_name", DELIVERY_STAGES)
    def test_read_stage_prefers_md(self, bb, stage_name):
        """read_stage 应优先读 .md 文件"""
        md_content = f"# MD First Content\n\nThis is the truth source."
        bb.write_stage(stage_name, md_content)

        # read_stage 应返回 MD 内容（文本）
        content = bb.read_stage(stage_name, as_text=True)
        assert content == md_content

    @pytest.mark.parametrize("stage_name", DELIVERY_STAGES)
    def test_read_stage_fallback_to_json(self, bb, stage_name):
        """read_stage 在无 .md 时应 fallback 到 .json"""
        # 直接写入 .json（模拟旧数据）
        json_data = {"test": "data", "stage": stage_name}
        json_path = bb._stage_path(stage_name, ".json")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(json_data), encoding="utf-8")

        # .md 不应存在
        md_path = bb._stage_path(stage_name, ".md")
        assert not md_path.exists()

        # read_stage 应能读 .json 并解析
        content = bb.read_stage(stage_name)
        assert content == json_data

    @pytest.mark.parametrize("stage_name", DELIVERY_STAGES)
    def test_md_takes_precedence_over_json(self, bb, stage_name):
        """当 .md 和 .json 同时存在时，.md 优先"""
        md_content = f"# MD Truth\n\nMD is the source of truth."
        json_data = {"test": "old_json_data"}

        # 同时写入 .md 和 .json
        bb.write_stage(stage_name, md_content)
        json_path = bb._stage_path(stage_name, ".json")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(json_data), encoding="utf-8")

        # read_stage(as_text=True) 应返回 .md 内容
        content = bb.read_stage(stage_name, as_text=True)
        assert content == md_content
        assert "old_json_data" not in content


class TestStagePathRegistry:
    """确保 STAGE_PATH_REGISTRY 中交付物路径是 .md"""

    def test_frozen_spec_registry_is_md(self):
        """STAGE_PATH_REGISTRY['frozen_spec'] 应是 .md 路径"""
        from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY
        path = STAGE_PATH_REGISTRY.get("frozen_spec", "")
        assert path.endswith(".md"), f"frozen_spec registry path should be .md, got: {path}"

    def test_final_solution_registry_is_md(self):
        """STAGE_PATH_REGISTRY['final_solution'] 应是 .md 路径"""
        from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY
        path = STAGE_PATH_REGISTRY.get("final_solution", "")
        assert path.endswith(".md"), f"final_solution registry path should be .md, got: {path}"

    def test_solution_document_registry_is_md(self):
        """STAGE_PATH_REGISTRY['solution_document'] 应是 .md 路径"""
        from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY
        path = STAGE_PATH_REGISTRY.get("solution_document", "")
        assert path.endswith(".md"), f"solution_document registry path should be .md, got: {path}"


class TestControlContract:
    """确保 control_contract 中不包含 frozen_spec.json 硬编码"""

    def test_control_contract_frozen_spec_path_is_md(self):
        """build_control_contract 返回的 frozen_spec_path 应是 .md"""
        # 检查源码中不包含硬编码的 frozen_spec.json
        import inspect
        from domains.solution_pro import control_contract
        source = inspect.getsource(control_contract)
        assert 'frozen_spec.json' not in source, (
            "control_contract.py should not contain hardcoded 'frozen_spec.json'"
        )


class TestNoJsonPrimaryWrite:
    """扫描源码，确保没有交付物 JSON 主写入"""

    def test_no_direct_json_write_for_delivery_stages(self):
        """代码中不应直接写入交付物 .json（排除 fallback 读取）"""
        import re
        source_dir = Path(__file__).parent.parent
        # 扫描 .py 文件（排除 tests/ 和 __pycache__）
        patterns = [
            r'write.*final_solution\.json',
            r'write.*solution_document\.json',
            r'write_stage.*final_solution.*\.json',
        ]
        violations = []
        for py_file in source_dir.rglob("*.py"):
            if "__pycache__" in str(py_file) or "/tests/" in str(py_file):
                continue
            content = py_file.read_text(encoding="utf-8")
            for pattern in patterns:
                if re.search(pattern, content):
                    violations.append(f"{py_file.relative_to(source_dir)}: {pattern}")

        assert not violations, (
            f"Found direct JSON write for delivery stages:\n" +
            "\n".join(violations) +
            "\nUse write_stage(stage_name, md_string) for MD-first output."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
