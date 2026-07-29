"""
W1 分钟级修复测试：4 处入口校验 + import 修复验证

覆盖：
1. scripts/start_solution_pro.py import 修复（run_solution_pro_agent → run_solution_pro）
2. ship_pro.run_ship_pro: project_name 空值校验
3. deliver_pro.run_deliver_pro: project_name 空值校验
4. spec_pro.coordinator.build_next_round_task: user_response 空值校验
"""
import pytest
import sys
import os

# 确保 .deepflow 在 path 中
DEEPFLOW_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if DEEPFLOW_ROOT not in sys.path:
    sys.path.insert(0, DEEPFLOW_ROOT)


# ── Fix 1: import 修复 ─────────────────────────────────────────────

class TestStartSolutionProImport:
    """验证 scripts/start_solution_pro.py 的 import 已修复"""

    def test_run_solution_pro_importable(self):
        """run_solution_pro 应可从 domains.solution_pro 导入"""
        from domains.solution_pro import run_solution_pro
        assert callable(run_solution_pro)
        assert run_solution_pro.__name__ == "run_solution_pro"

    def test_no_run_solution_pro_agent(self):
        """run_solution_pro_agent 不应存在于 domains.solution_pro"""
        import domains.solution_pro as sp
        assert not hasattr(sp, "run_solution_pro_agent"), \
            "run_solution_pro_agent 应已改名为 run_solution_pro"

    def test_script_ast_no_broken_import(self):
        """脚本 AST 中不应有 run_solution_pro_agent 的 import"""
        import ast
        script_path = os.path.join(DEEPFLOW_ROOT, "scripts", "start_solution_pro.py")
        with open(script_path) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "solution_pro" in node.module:
                    names = [alias.name for alias in node.names]
                    assert "run_solution_pro_agent" not in names, \
                        f"脚本仍 import run_solution_pro_agent: {names}"
                    assert "run_solution_pro" in names, \
                        f"脚本应 import run_solution_pro: {names}"


# ── Fix 2: ship_pro project_name 校验 ──────────────────────────────

class TestShipProProjectNameValidation:
    """ship_pro.run_ship_pro 入口校验 project_name"""

    def test_none_raises(self):
        from domains.ship_pro import run_ship_pro
        with pytest.raises(ValueError, match="project_name"):
            run_ship_pro(project_name=None)

    def test_empty_string_raises(self):
        from domains.ship_pro import run_ship_pro
        with pytest.raises(ValueError, match="project_name"):
            run_ship_pro(project_name="")

    def test_whitespace_only_raises(self):
        from domains.ship_pro import run_ship_pro
        with pytest.raises(ValueError, match="project_name"):
            run_ship_pro(project_name="   ")

    def test_valid_name_passes_validation(self):
        """合法 project_name 不应触发 ValueError（后续可能因缺少 blackboard 而报其他错）"""
        from domains.ship_pro import run_ship_pro
        # 合法名称但 blackboard 不存在 → 应抛 FileNotFoundError 而非 ValueError
        with pytest.raises((FileNotFoundError, Exception)) as exc_info:
            run_ship_pro(project_name="test_nonexistent_project_w1")
        # 确认不是 ValueError（即通过了 project_name 校验）
        assert not isinstance(exc_info.value, ValueError)


# ── Fix 3: deliver_pro project_name 校验 ───────────────────────────

class TestDeliverProProjectNameValidation:
    """deliver_pro.run_deliver_pro 入口校验 project_name"""

    def test_none_raises(self):
        from domains.deliver_pro import run_deliver_pro
        with pytest.raises(ValueError, match="project_name"):
            run_deliver_pro(project_name=None)

    def test_empty_string_raises(self):
        from domains.deliver_pro import run_deliver_pro
        with pytest.raises(ValueError, match="project_name"):
            run_deliver_pro(project_name="")

    def test_whitespace_only_raises(self):
        from domains.deliver_pro import run_deliver_pro
        with pytest.raises(ValueError, match="project_name"):
            run_deliver_pro(project_name="   ")

    def test_valid_name_passes_validation(self):
        """合法 project_name 不应触发 ValueError"""
        from domains.deliver_pro import run_deliver_pro
        # 合法名称但缺少 ship_package → 应抛 FileNotFoundError 而非 ValueError
        with pytest.raises(FileNotFoundError):
            run_deliver_pro(project_name="test_nonexistent_project_w1")


# ── Fix 4: spec_pro coordinator user_response 校验 ─────────────────

class TestSpecProUserResponseValidation:
    """spec_pro coordinator.build_next_round_task 入口校验 user_response"""

    def _make_coordinator(self):
        """创建一个已初始化的 coordinator 实例"""
        from domains.spec_pro.coordinator import SpecProCoordinator
        coord = SpecProCoordinator(mode="quick")
        # 模拟初始化状态（避免真正写文件）
        coord.session_id = "test_w1_session"
        coord._bb = _FakeBlackboard()
        return coord

    def test_none_raises(self):
        coord = self._make_coordinator()
        with pytest.raises(ValueError, match="user_response"):
            coord.build_next_round_task(user_response=None)

    def test_empty_string_raises(self):
        coord = self._make_coordinator()
        with pytest.raises(ValueError, match="user_response"):
            coord.build_next_round_task(user_response="")

    def test_whitespace_only_raises(self):
        coord = self._make_coordinator()
        with pytest.raises(ValueError, match="user_response"):
            coord.build_next_round_task(user_response="   \t\n  ")

    def test_valid_response_passes(self):
        """合法 user_response 应通过校验（不 raise ValueError）"""
        coord = self._make_coordinator()
        # 合法输入不应触发 ValueError
        result = coord.build_next_round_task(user_response="我们需要一个登录功能")
        assert isinstance(result, dict)
        assert "coordinator_task" in result or "action" in result


class _FakeBlackboard:
    """最小 mock，让 coordinator 的 _bb.write 不报错"""
    def __init__(self):
        self._data = {}
        self.session_dir = "/tmp/w1_fake_session"

    def write(self, path, data, subdir=None):
        self._data[path] = data

    def read_json(self, path, default=None):
        return self._data.get(path, default)

    def read(self, path, default=None):
        return self._data.get(path, default)

    def read_stage_raw(self, filename, default=None):
        return self._data.get(filename, default)
