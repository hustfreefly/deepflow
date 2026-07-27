"""
Ship Pro - 端到端测试

测试整个 pipeline：
1. Planner 输出验证
2. Worker 输出验证
3. Consolidator 输出验证
4. State Machine 验证
"""
from pathlib import Path
import json
import tempfile
import shutil
import pytest

# 添加路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from domains.ship_pro.contracts import (
    PlannerOutput,
    WorkerSpec,
    WorkerDeliverable,
    WorkPackage,
    ShipPackage,
    DependencyGraph,
    PlannerGate,
    WorkerGate,
    InformationConservationGate,
    CompletenessGate,
    HarnessV3
)
from domains.ship_pro.orchestrator import (
    ShipOrchestrator,
    StateManager,
    StateTransitionError
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_blackboard():
    """创建临时 Blackboard 目录"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_solution_pro_output():
    """Solution Pro 输出示例"""
    return {
        "solution_name": "AI Native Loop Framework",
        "architecture_overview": "分形三层 Loop 架构",
        "key_decisions": [
            {
                "id": "D-001",
                "description": "采用 Python 骨架 + LLM 决策混合架构",
                "priority": "P0"
            }
        ],
        "must_constraints": [
            "必须支持 DAG 并行执行",
            "必须实现信息守恒"
        ],
        "requirements": [
            {"id": "REQ-001", "description": "支持多 Agent 协作", "priority": "P0"},
            {"id": "REQ-002", "description": "实现质量门控", "priority": "P1"}
        ],
        "covered_req_ids": ["REQ-001", "REQ-002"]
    }


@pytest.fixture
def sample_planner_output():
    """Planner 输出示例 — 匹配 PipelinePlan schema (V2)"""
    return {
        "input_type": "engineering",
        "complexity": "high",
        "domain": "AI 工程框架",
        "rationale": "这是一个复杂的 AI 工程框架项目，需要拆解为多个可执行工作包。架构设计先行，工作包拆解跟进，确保信息守恒和平台对齐。",
        "execution_order": [["architecture_designer"], ["wp_decomposer"]],
        "workers": [
            {
                "role": "architecture_designer",
                "module_purpose": "设计整体架构模块，确保 DAG 并行执行和信息守恒原则得到贯彻",
                "required_inputs": ["final_solution"],
                "expected_output_stage": "worker_architecture_designer",
                "output_schema": "WorkerDeliverable",
                "depends_on": [],
                "needs_web_search": False,
                "must_constraints": ["必须支持 DAG 并行执行"],
                "solution_pro_refs": ["architecture_overview"],
                "covered_req_ids": ["REQ-001"],
                "wp_id_prefix": "ARCH",
                "estimated_wps": 4,
                "estimated_effort_hours": 40
            },
            {
                "role": "wp_decomposer",
                "module_purpose": "拆解工作包为可执行的细粒度任务，确保每个工作包有明确的验收标准",
                "required_inputs": ["final_solution", "worker_architecture_designer"],
                "expected_output_stage": "worker_wp_decomposer",
                "output_schema": "WorkerDeliverable",
                "depends_on": ["architecture_designer"],
                "needs_web_search": True,
                "web_search_scope": "工作包拆解最佳实践",
                "must_constraints": ["必须实现信息守恒"],
                "solution_pro_refs": ["key_decisions"],
                "covered_req_ids": ["REQ-002"],
                "wp_id_prefix": "WP",
                "estimated_wps": 6,
                "estimated_effort_hours": 80
            }
        ],
        "integration_strategy": "hierarchical"
    }


@pytest.fixture
def sample_worker_output():
    """Worker 输出示例"""
    return {
        "worker_role": "architecture_designer",
        "wp_id_prefix": "ARCH",
        "work_packages": [
            {
                "id": "ARCH-001",
                "title": "实现 DAG 调度引擎",
                "description": "实现基于拓扑排序的 DAG 调度引擎，支持多 Worker 并行执行、优先级队列调度、超时强制中断机制。引擎需要与 LoopEngine 三层嵌套架构集成，支持动态任务插入和优先级重排。每个任务节点必须有唯一 ID，支持任务依赖的传递性解析和循环检测。",
                "acceptance_criteria": [
                    "支持并行执行",
                    "依赖关系正确解析"
                ],
                "dependencies": [],
                "effort_hours": 40,
                "deliverables": ["dag_engine.py", "test_dag_engine.py"],
                "anchored_to": [],
            }
        ],
        "metadata": {},
        "optional_suggestions": ["建议增加性能测试"],
        "web_search_logs": []
    }


@pytest.fixture
def sample_ship_package():
    """Ship Package 示例"""
    return {
        "solution_name": "AI Native Loop Framework",
        "version": "1.0.0",
        "work_packages": [
            {
                "id": "WP-001",
                "title": "实现 DAG 调度引擎",
                "description": "实现基于拓扑排序的 DAG 调度引擎，支持多 Worker 并行执行、优先级队列调度、超时强制中断机制。引擎需要与 LoopEngine 三层嵌套架构集成，支持动态任务插入和优先级重排。每个任务节点必须有唯一 ID，支持任务依赖的传递性解析和循环检测。",
                "acceptance_criteria": [
                    "支持并行执行",
                    "依赖关系正确解析"
                ],
                "dependencies": [],
                "effort_hours": 40,
                "deliverables": ["dag_engine.py", "test_dag_engine.py"],
                "anchored_to": [],
            }
        ],
        "dependency_graph": {
            "edges": [],
            "execution_layers": [["WP-001"]]
        },
        "metadata": {},
        "optional_suggestions": [],
        "web_search_logs": []
    }


# ============================================================================
# Test Contracts (Schema Validation)
# ============================================================================

class TestContracts:
    """测试 Pydantic Schema 验证"""
    
    def test_planner_output_schema(self, sample_planner_output):
        """PlannerOutput Schema 验证 — PlannerOutput = PipelinePlan (V2)"""
        planner_output = PlannerOutput.model_validate(sample_planner_output)
        assert len(planner_output.workers) == 2
        assert len(planner_output.execution_order) == 2
        assert planner_output.workers[0].role == "architecture_designer"
    
    def test_worker_deliverable_schema(self, sample_worker_output):
        """WorkerDeliverable Schema 验证"""
        worker_output = WorkerDeliverable.model_validate(sample_worker_output)
        assert worker_output.worker_role == "architecture_designer"
        assert len(worker_output.work_packages) == 1
    
    def test_ship_package_schema(self, sample_ship_package):
        """ShipPackage Schema 验证"""
        ship_package = ShipPackage.model_validate(sample_ship_package)
        assert ship_package.solution_name == "AI Native Loop Framework"
        assert len(ship_package.work_packages) == 1


# ============================================================================
# Test Gates
# ============================================================================

class TestGates:
    """测试 Gate 验证逻辑"""
    
    def test_planner_gate_pass(self, sample_planner_output):
        """PlannerGate 通过测试"""
        result = PlannerGate.check(sample_planner_output)
        assert result.passed
        assert result.details["worker_count"] == 2
    
    def test_planner_gate_fail_worker_count(self, sample_planner_output):
        """PlannerGate 失败测试（Worker 数量超限）"""
        # PipelinePlan 限制 max 8 workers，5x 复制 = 10 workers 触发 Pydantic 验证
        sample_planner_output["workers"] = sample_planner_output["workers"] * 5
        sample_planner_output["execution_order"] = [[w["role"]] for w in sample_planner_output["workers"]]
        result = PlannerGate.check(sample_planner_output)
        assert not result.passed
        # V2: Pydantic 先拦截（at most 8），然后 Gate 才检查
        assert len(result.issues) > 0
    
    def test_planner_gate_fail_cycle(self, sample_planner_output):
        """PlannerGate 失败测试（依赖环）"""
        sample_planner_output["workers"][0]["depends_on"] = ["wp_decomposer"]
        sample_planner_output["workers"][1]["depends_on"] = ["architecture_designer"]
        result = PlannerGate.check(sample_planner_output)
        assert not result.passed
        assert "依赖图存在环" in result.issues[0]
    
    def test_worker_gate_pass(self, sample_planner_output, sample_worker_output):
        """WorkerGate 通过测试 — 契约笼子三步模式"""
        worker_spec = sample_planner_output["workers"][0]
        role = worker_spec["role"]
        # 模拟 Agent 层预计算的 Judge 结果
        judge_results = {
            f"worker_must_{role}": {"passed": True, "issues": []}
        }
        result = WorkerGate.check(worker_spec, sample_worker_output, judge_results=judge_results)
        assert result.passed
    
    def test_completeness_gate_pass(self, sample_solution_pro_output, sample_planner_output):
        """CompletenessGate 通过测试 — 契约笼子：需要 Judge Agent 结果"""
        # V2 契约笼子: CompletenessGate 必须有 judge_results
        judge_results = {
            "completeness": {
                "passed": True,
                "coverage_rate": 1.0,
                "covered": ["REQ-001", "REQ-002"],
                "missing": [],
                "issues": []
            }
        }
        result = CompletenessGate.check(
            sample_solution_pro_output, sample_planner_output,
            judge_results=judge_results
        )
        assert result.passed


# ============================================================================
# Test State Manager
# ============================================================================

class TestStateManager:
    """测试 StateManager"""
    
    def test_state_initialization(self, temp_blackboard):
        """状态初始化测试"""
        state_mgr = StateManager(temp_blackboard)
        assert state_mgr.state.run_id.startswith("run_")
        assert state_mgr.state.status == "pending"
    
    def test_state_transition_valid(self, temp_blackboard):
        """合法状态转换测试"""
        state_mgr = StateManager(temp_blackboard)
        state_mgr.update_stage("planner", "running")
        assert state_mgr.state.stages["planner"].status == "running"
        
        state_mgr.update_stage("planner", "completed")
        assert state_mgr.state.stages["planner"].status == "completed"
    
    def test_state_transition_relaxed(self, temp_blackboard):
        """V7: 宽松状态转换 — 不 raise，只 warn"""
        state_mgr = StateManager(temp_blackboard)
        
        # V7: pending -> completed 不再 raise，而是 warn 并执行
        state_mgr.update_stage("planner", "completed")
        assert state_mgr.state.stages["planner"].status == "completed"
    
    def test_state_transition_same_skip(self, temp_blackboard):
        """V7: 同状态转换静默跳过"""
        state_mgr = StateManager(temp_blackboard)
        state_mgr.update_stage("planner", "running")
        # 再次设置 running — 应该静默跳过
        state_mgr.update_stage("planner", "running")
        assert state_mgr.state.stages["planner"].status == "running"
    
    def test_state_auto_create_unknown(self, temp_blackboard):
        """V7: 自动创建未知阶段"""
        state_mgr = StateManager(temp_blackboard)
        state_mgr.update_stage("custom_phase", "running")
        assert "custom_phase" in state_mgr.state.stages
        assert state_mgr.state.stages["custom_phase"].status == "running"
    
    @pytest.mark.skip(reason="P0 FIX: pipeline_state.json 已废弃，.runs/*.run.json 是唯一状态源")
    def test_state_persistence(self, temp_blackboard):
        """状态持久化测试 — 已废弃（pipeline_state.json 不再写入）"""
        state_mgr1 = StateManager(temp_blackboard)
        run_id = state_mgr1.state.run_id
        state_mgr1.update_stage("planner", "running")
        
        # 重新加载
        state_mgr2 = StateManager(temp_blackboard)
        assert state_mgr2.state.run_id == run_id
        assert state_mgr2.state.stages["planner"].status == "running"
    
    def test_write_and_read_stage(self, temp_blackboard):
        """阶段输出读写测试"""
        state_mgr = StateManager(temp_blackboard)
        
        test_data = {"test": "data", "value": 42}
        state_mgr.write_stage("test_stage", test_data)
        
        loaded_data = state_mgr.read_stage("test_stage")
        assert loaded_data == test_data


# ============================================================================
# Test Orchestrator
# ============================================================================

class TestOrchestrator:
    """测试 ShipOrchestrator"""
    
    def test_orchestrator_initialization(self, temp_blackboard):
        """Orchestrator 初始化测试"""
        orchestrator = ShipOrchestrator(temp_blackboard)
        assert orchestrator.blackboard_path == temp_blackboard
        assert orchestrator.state.status == "pending"
    
    def test_prepare_planner_spawn(self, temp_blackboard, sample_solution_pro_output):
        """Planner spawn 参数准备测试"""
        orchestrator = ShipOrchestrator(temp_blackboard)
        spawn_params = orchestrator.prepare_planner_spawn(sample_solution_pro_output)
        
        assert spawn_params["runtime"] == "subagent"
        assert spawn_params["mode"] == "run"
        # Bootstrap pattern: task is a reference, content is in the bootstrap file
        import re
        bootstrap_match = re.search(r'`read` 工具读取: `([^`]+)`', spawn_params["task"])
        assert bootstrap_match, "Expected bootstrap reference in task"
        bootstrap_content = Path(bootstrap_match.group(1)).read_text(encoding='utf-8')
        assert "PlannerOutput" in bootstrap_content
    
    def test_verify_planner_output(self, temp_blackboard, sample_planner_output):
        """Planner 输出验证测试"""
        orchestrator = ShipOrchestrator(temp_blackboard)
        # 模拟真实流程：prepare_planner_spawn 先转 running，再验证
        orchestrator.state_manager.update_stage("planner", "running")
        result = orchestrator.verify_planner_output(sample_planner_output)
        
        assert result.passed
        assert orchestrator.state.stages["planner"].status == "completed"
    
    def test_topological_sort(self, temp_blackboard, sample_planner_output):
        """拓扑排序测试"""
        orchestrator = ShipOrchestrator(temp_blackboard)
        layers = orchestrator._topological_sort(sample_planner_output["workers"])
        
        assert len(layers) == 2
        assert layers[0][0]["role"] == "architecture_designer"
        assert layers[1][0]["role"] == "wp_decomposer"


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
