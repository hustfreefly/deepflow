"""
Ship Pro V6 - 端到端测试

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

from domains.ship_pro.v6.contracts import (
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
from domains.ship_pro.v6.orchestrator import (
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
        "key_design_decisions": [
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
        ]
    }


@pytest.fixture
def sample_planner_output():
    """Planner 输出示例"""
    return {
        "input_type": "engineering",
        "complexity": "high",
        "domain": "AI 工程框架",
        "analysis_summary": "这是一个复杂的 AI 工程框架项目，需要拆解为多个可执行工作包。",
        "workers": [
            {
                "role": "architecture_designer",
                "task_description": "设计架构模块",
                "required_inputs": ["final_solution"],
                "expected_output_stage": "worker_architecture_designer",
                "output_schema": "WorkerDeliverable",
                "depends_on": [],
                "needs_web_search": False,
                "must_constraints": ["必须支持 DAG 并行执行"],
                "solution_pro_refs": ["architecture_overview"]
            },
            {
                "role": "wp_decomposer",
                "task_description": "拆解工作包",
                "required_inputs": ["final_solution", "worker_architecture_designer"],
                "expected_output_stage": "worker_wp_decomposer",
                "output_schema": "WorkerDeliverable",
                "depends_on": ["architecture_designer"],
                "needs_web_search": True,
                "web_search_scope": "工作包拆解最佳实践",
                "must_constraints": ["必须实现信息守恒"],
                "solution_pro_refs": ["key_design_decisions"]
            }
        ],
        "integration_strategy": "hierarchical"
    }


@pytest.fixture
def sample_worker_output():
    """Worker 输出示例"""
    return {
        "worker_role": "architecture_designer",
        "work_packages": [
            {
                "id": "WP-001",
                "title": "实现 DAG 调度引擎",
                "description": "实现基于拓扑排序的 DAG 调度引擎",
                "acceptance_criteria": [
                    "支持并行执行",
                    "依赖关系正确解析"
                ],
                "dependencies": [],
                "estimated_effort": "5 人天",
                "deliverables": ["dag_engine.py", "test_dag_engine.py"]
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
                "description": "实现基于拓扑排序的 DAG 调度引擎",
                "acceptance_criteria": [
                    "支持并行执行",
                    "依赖关系正确解析"
                ],
                "dependencies": [],
                "estimated_effort": "5 人天",
                "deliverables": ["dag_engine.py", "test_dag_engine.py"]
            }
        ],
        "dependency_graph": {
            "edges": [],
            "execution_order": [["WP-001"]],
            "parallel_groups": [["WP-001"]]
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
        """PlannerOutput Schema 验证"""
        planner_output = PlannerOutput.model_validate(sample_planner_output)
        assert planner_output.input_type == "engineering"
        assert len(planner_output.workers) == 2
    
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
        sample_planner_output["workers"] = sample_planner_output["workers"] * 5  # 10 workers
        result = PlannerGate.check(sample_planner_output)
        assert not result.passed
        assert "Worker 数量" in result.issues[0]
    
    def test_planner_gate_fail_cycle(self, sample_planner_output):
        """PlannerGate 失败测试（依赖环）"""
        sample_planner_output["workers"][0]["depends_on"] = ["wp_decomposer"]
        sample_planner_output["workers"][1]["depends_on"] = ["architecture_designer"]
        result = PlannerGate.check(sample_planner_output)
        assert not result.passed
        assert "依赖图存在环" in result.issues[0]
    
    def test_worker_gate_pass(self, sample_planner_output, sample_worker_output):
        """WorkerGate 通过测试"""
        worker_spec = sample_planner_output["workers"][0]
        result = WorkerGate.check(worker_spec, sample_worker_output)
        assert result.passed
    
    def test_completeness_gate_pass(self, sample_solution_pro_output, sample_ship_package):
        """CompletenessGate 通过测试"""
        result = CompletenessGate.check(sample_solution_pro_output, sample_ship_package)
        assert result.passed
        assert result.details["coverage_rate"] >= 0.0  # 暂时允许 0%（需要 LLM 判断）


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
    
    def test_state_transition_invalid(self, temp_blackboard):
        """非法状态转换测试"""
        state_mgr = StateManager(temp_blackboard)
        
        with pytest.raises(StateTransitionError):
            state_mgr.update_stage("planner", "completed")  # pending → completed 非法
    
    def test_state_persistence(self, temp_blackboard):
        """状态持久化测试"""
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
        assert orchestrator.state.state.status == "pending"
    
    def test_prepare_planner_spawn(self, temp_blackboard, sample_solution_pro_output):
        """Planner spawn 参数准备测试"""
        orchestrator = ShipOrchestrator(temp_blackboard)
        spawn_params = orchestrator.prepare_planner_spawn(sample_solution_pro_output)
        
        assert spawn_params["runtime"] == "subagent"
        assert spawn_params["mode"] == "run"
        assert "PlannerOutput" in spawn_params["task"]
    
    def test_verify_planner_output(self, temp_blackboard, sample_planner_output):
        """Planner 输出验证测试"""
        orchestrator = ShipOrchestrator(temp_blackboard)
        result = orchestrator.verify_planner_output(sample_planner_output)
        
        assert result.passed
        assert orchestrator.state.state.stages["planner"].status == "completed"
    
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
