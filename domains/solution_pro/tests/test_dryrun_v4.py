"""
DryRun 测试 — V4.0 简化验证

使用 pytest + tmp_path，Mock sessions_spawn 和 wait_for_module，
验证状态机转移、完成标记、Fail Fast、断点恢复。

运行: cd /Users/allen/.openclaw/workspace/.deepflow && python3 -m pytest domains/solution_pro/tests/test_dryrun_v4.py -v
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def bb(tmp_path):
    """创建临时 BlackboardManager"""
    from core.blackboard.blackboard_manager import BlackboardManager
    manager = BlackboardManager(session_id="dryrun_v4_test", base_dir=tmp_path)
    return manager


@pytest.fixture
def session_dir(bb):
    """返回 session 目录"""
    # 确保 session_dir 存在（BlackboardManager 延迟创建）
    bb.session_dir.mkdir(parents=True, exist_ok=True)
    return bb.session_dir


@pytest.fixture
def state_mgr(session_dir):
    """创建 SingleSourceStateManager"""
    from core.process_manager import SingleSourceStateManager
    return SingleSourceStateManager(str(session_dir))


@pytest.fixture
def lifecycle(session_dir):
    """创建 ModuleLifecycleManager"""
    from core.process_manager import ModuleLifecycleManager
    return ModuleLifecycleManager(str(session_dir))


@pytest.fixture
def frozen_spec(bb):
    """写入最小 frozen_spec（ADR-009: MD-first）"""
    spec = {
        "requirements": [
            {"id": "REQ-1", "text": "Test requirement"},
        ],
        "architecture_version": "v4.0",
    }
    # ADR-009: 写入 MD 格式
    try:
        from domains.solution_pro.frozen_living_md import render_frozen_spec_md
        md_content = render_frozen_spec_md(spec)
        bb.write("data/frozen_spec.md", md_content)
    except ImportError:
        # Fallback to JSON if renderer unavailable
        bb.write("data/frozen_spec.json", spec)
    return spec


@pytest.fixture
def mock_spawn():
    """Mock sessions_spawn — 使用 MagicMock（sessions_spawn 不是 Python 模块属性，无法 patch）"""
    m = MagicMock()
    return m


# ============================================================================
# Helper Functions
# ============================================================================

def write_run_completed(session_dir, module):
    """模拟 SingleSourceStateManager 标记模块完成（写入 .run.json）
    
    必须符合 RunRecordContract:
    - module, run_id, attempt, status, started_at(float), last_heartbeat(float), completed_at(float|None)
    """
    import time
    runs_dir = session_dir / ".runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_file = runs_dir / f"{module}.run.json"
    now = time.time()
    run_data = {
        "module": module,
        "run_id": f"run_{module}_001",
        "attempt": 1,
        "status": "completed",
        "started_at": now - 10,
        "last_heartbeat": now - 5,
        "completed_at": now,
        "output_files": {},
    }
    run_file.write_text(json.dumps(run_data))


def simulate_module_failure(bb, module):
    """模拟模块失败 → 写 .failed"""
    bb.write_stage(".failed", {
        "session_id": "dryrun_v4_test",
        "failed_module": module,
        "failed_at": datetime.utcnow().isoformat() + "Z",
        "reason": "MISSING",
        "architecture_version": "v4.0",
    })


# ============================================================================
# 3.1 正常流程测试
# ============================================================================

class TestHappyPath:
    """正常全流程测试"""

    def test_happy_path_all_modules(self, bb, session_dir, state_mgr, frozen_spec):
        """验证: Planning → Research → Summary → .completed"""
        # 模拟 3 个模块全部完成
        for module in ["planning", "research", "summary"]:
            write_run_completed(session_dir, module)

        # 验证所有模块状态为 completed
        assert state_mgr.is_module_completed("planning")
        assert state_mgr.is_module_completed("research")
        assert state_mgr.is_module_completed("summary")

        # 模拟写入 .completed
        bb.write_stage(".completed", {
            "session_id": "dryrun_v4_test",
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "modules_completed": ["planning", "research", "summary"],
            "architecture_version": "v4.0",
        })

        # 验证 .completed 文件存在
        completed_path = session_dir / "stages" / ".completed.json"
        assert completed_path.exists()

        content = json.loads(completed_path.read_text())
        assert content["status"] == "completed"
        assert content["architecture_version"] == "v4.0"
        assert set(content["modules_completed"]) == {"planning", "research", "summary"}

    def test_completion_marker_fields(self, bb, session_dir):
        """验证: .completed 只包含最小必要字段"""
        bb.write_stage(".completed", {
            "session_id": "dryrun_v4_test",
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "modules_completed": ["planning", "research", "summary"],
            "architecture_version": "v4.0",
        })

        completed_path = session_dir / "stages" / ".completed.json"
        content = json.loads(completed_path.read_text())

        # V4.0 最小字段集
        expected_keys = {"session_id", "status", "completed_at", "modules_completed", "architecture_version"}
        assert set(content.keys()) == expected_keys

        # V3.4 的字段不应该存在
        assert "modules_failed" not in content
        assert "pipeline_status" not in content

    def test_state_transitions_linear(self, session_dir, state_mgr):
        """验证: 状态按线性 DAG 转移"""
        # 初始状态：无模块完成
        assert not state_mgr.is_module_completed("planning")
        assert not state_mgr.is_module_completed("research")
        assert not state_mgr.is_module_completed("summary")

        # Planning 完成
        write_run_completed(session_dir, "planning")
        assert state_mgr.is_module_completed("planning")
        assert not state_mgr.is_module_completed("research")

        # Research 完成
        write_run_completed(session_dir, "research")
        assert state_mgr.is_module_completed("research")
        assert not state_mgr.is_module_completed("summary")

        # Summary 完成
        write_run_completed(session_dir, "summary")
        assert state_mgr.is_module_completed("summary")


# ============================================================================
# 3.2 Fail Fast 测试
# ============================================================================

class TestFailFast:
    """Fail Fast 机制测试"""

    def test_fail_fast_planning_missing(self, bb, session_dir, state_mgr):
        """验证: Planning MISSING → .failed，不继续"""
        # Planning 未完成（无 .run.json）
        assert not state_mgr.is_module_completed("planning")

        # 模拟 Fail Fast
        simulate_module_failure(bb, "planning")

        # 验证 .failed 存在
        failed_path = session_dir / "stages" / ".failed.json"
        assert failed_path.exists()

        content = json.loads(failed_path.read_text())
        assert content["failed_module"] == "planning"
        assert content["reason"] == "MISSING"

        # 验证后续模块未启动
        assert not state_mgr.is_module_completed("research")
        assert not state_mgr.is_module_completed("summary")

    def test_fail_fast_research_missing(self, bb, session_dir, state_mgr):
        """验证: Research MISSING → .failed，Summary 不启动"""
        write_run_completed(session_dir, "planning")
        # Research 未完成
        assert not state_mgr.is_module_completed("research")

        simulate_module_failure(bb, "research")

        failed_path = session_dir / "stages" / ".failed.json"
        assert failed_path.exists()
        assert not state_mgr.is_module_completed("summary")

    def test_fail_fast_no_completed_marker(self, bb, session_dir):
        """验证: 失败时不写 .completed"""
        simulate_module_failure(bb, "planning")

        completed_path = session_dir / "stages" / ".completed.json"
        assert not completed_path.exists()


# ============================================================================
# 3.3 断点恢复测试
# ============================================================================

class TestResume:
    """断点恢复测试"""

    def test_resume_from_research(self, session_dir, state_mgr):
        """验证: Planning 已完成 → 从 Research 开始"""
        write_run_completed(session_dir, "planning")

        # 确定起始模块
        modules_order = ["planning", "research", "summary"]
        start_module = None
        for m in modules_order:
            if not state_mgr.is_module_completed(m):
                start_module = m
                break

        assert start_module == "research"

    def test_resume_from_summary(self, session_dir, state_mgr):
        """验证: Planning + Research 完成 → 从 Summary 开始"""
        write_run_completed(session_dir, "planning")
        write_run_completed(session_dir, "research")

        modules_order = ["planning", "research", "summary"]
        start_module = None
        for m in modules_order:
            if not state_mgr.is_module_completed(m):
                start_module = m
                break

        assert start_module == "summary"

    def test_resume_all_completed(self, session_dir, state_mgr):
        """验证: 全部完成 → 直接 PIPELINE_COMPLETED"""
        for m in ["planning", "research", "summary"]:
            write_run_completed(session_dir, m)

        modules_order = ["planning", "research", "summary"]
        start_module = None
        for m in modules_order:
            if not state_mgr.is_module_completed(m):
                start_module = m
                break

        assert start_module is None  # 全部完成，无需继续


# ============================================================================
# 3.4 V4.0 简化验证测试
# ============================================================================

class TestV4Simplification:
    """V4.0 简化正确性验证"""

    def test_no_post_validation_in_orchestrator_prompt(self):
        """验证: orchestrator prompt 的执行算法不含 POST_VALIDATION"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "orchestrator.md"
        content = prompt_path.read_text()

        # 找到执行算法部分（Step 0/1/2），验证不含 Step 4/5 或 POST_VALIDATION
        algo_section = content[content.find("## 执行算法"):]
        assert "POST_VALIDATION" not in algo_section
        assert "Step 4" not in algo_section
        assert "Step 5" not in algo_section
        assert "adversarial" not in algo_section.lower()
        assert "consistency_checker" not in algo_section.lower()

    def test_spawn_count_equals_3_in_prompt(self):
        """验证: orchestrator prompt 只有 3 个模块的 spawn 逻辑"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "orchestrator.md"
        content = prompt_path.read_text()

        # 只应包含 planning, research, summary 三个模块
        assert "planning" in content.lower()
        assert "research" in content.lower()
        assert "summary" in content.lower()

        # 不应包含后置验证模块
        assert "adversarial_quality_reviewer" not in content
        assert "cross_module_consistency_checker" not in content

    def test_completion_marker_is_lightweight(self):
        """验证: 完成标记代码不查询 pipeline_status"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "orchestrator.md"
        content = prompt_path.read_text()

        # 找到完成标记代码段
        marker_pos = content.find("Step 2: 完成标记")
        if marker_pos >= 0:
            # 只检查完成标记的 bash 代码块（到下一个 ``` 结束）
            code_block_start = content.find("```bash", marker_pos)
            code_block_end = content.find("```", code_block_start + 10)
            completion_code = content[marker_pos:code_block_end]
            # 完成标记代码不应包含 pipeline_status 查询
            assert "get_pipeline_status" not in completion_code
            assert "SingleSourceStateManager" not in completion_code

    def test_version_is_v4(self):
        """验证: prompt 版本号为 4.0"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "orchestrator.md"
        content = prompt_path.read_text()

        assert 'version: "4.0' in content or "v4.0" in content.lower()


# ============================================================================
# 3.5 Mock Spawn 集成测试
# ============================================================================

class TestMockSpawn:
    """Mock sessions_spawn 的集成测试"""

    def test_spawn_records_parameters(self, mock_spawn):
        """验证: Mock 能正确记录 spawn 参数"""
        # 模拟 3 次 spawn
        for module in ["planning", "research", "summary"]:
            mock_spawn(
                runtime="subagent",
                mode="run",
                label=f"{module}_module_v4",
                task=f"Run {module} module",
                cwd="/tmp/deepflow",
                lightContext=True,
            )

        assert mock_spawn.call_count == 3
        calls = [c.kwargs["label"] for c in mock_spawn.call_args_list]
        assert calls == ["planning_module_v4", "research_module_v4", "summary_module_v4"]

    def test_spawn_mock_is_independent(self):
        """验证: MagicMock 可以独立使用，不需要 patch"""
        m = MagicMock()
        m(runtime="subagent", mode="run", label="test")
        assert m.call_count == 1

    def test_wait_for_module_mock(self, session_dir):
        """验证: wait_for_module 可以被 Mock"""
        from core.process_manager import ModuleLifecycleManager
        lifecycle = ModuleLifecycleManager(str(session_dir))
        with patch.object(lifecycle, 'wait_for_module') as mock_wait:
            mock_wait.return_value = MagicMock(found=True, reason=None)

            result = lifecycle.wait_for_module(
                "planning",
                expected_files=["stages/planning_convergence.json"],
                timeout=1800,
            )

            assert result.found is True
            mock_wait.assert_called_once()


# ============================================================================
# 执行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
