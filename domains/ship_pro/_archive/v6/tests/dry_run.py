#!/usr/bin/env python3
"""
Ship Pro V6 - Dry Run Script

模拟完整的 Ship Pro V6 流程，验证所有组件集成正确。
"""
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ship_pro_v6.orchestrator.state_manager import StateManager
from ship_pro_v6.contracts.planner_output import PlannerOutput
from ship_pro_v6.contracts.worker_deliverable import WorkerDeliverable
from ship_pro_v6.contracts.ship_package import ShipPackage
from ship_pro_v6.orchestrator.ship_orchestrator import ShipOrchestrator


def create_mock_solution_pro_output():
    """创建模拟的 Solution Pro 输出"""
    return {
        "project_name": "AI Native Loop Engineering Framework",
        "requirements": [
            {"req_id": "REQ-001", "description": "实现动态 Agent 调度"},
            {"req_id": "REQ-002", "description": "实现动态 Prompt 生成"},
            {"req_id": "REQ-003", "description": "实现动态结果生成"},
            {"req_id": "REQ-004", "description": "实现信息守恒检查"}
        ],
        "must_constraints": [
            "所有 Agent 必须使用 OpenClaw sessions_spawn",
            "所有 Prompt 必须包含约束笼子"
        ]
    }


def create_mock_planner_output():
    """创建模拟的 Planner 输出"""
    return {
        "analysis": {
            "project_type": "engineering_framework",
            "complexity": "high",
            "domain": "ai_agent_orchestration"
        },
        "worker_specs": [
            {
                "role": "architecture_designer",
                "task_description": "设计系统架构和组件关系",
                "required_inputs": ["solution_pro_output"],
                "expected_output_stage": "architecture_design",
                "output_schema": "WorkerDeliverable",
                "depends_on": [],
                "needs_web_search": False,
                "must_constraints": ["所有 Agent 必须使用 OpenClaw sessions_spawn"],
                "solution_pro_refs": ["REQ-001", "REQ-002"]
            },
            {
                "role": "implementation_planner",
                "task_description": "制定实现计划和里程碑",
                "required_inputs": ["solution_pro_output", "architecture_design"],
                "expected_output_stage": "implementation_plan",
                "output_schema": "WorkerDeliverable",
                "depends_on": ["architecture_designer"],
                "needs_web_search": False,
                "must_constraints": [],
                "solution_pro_refs": ["REQ-003"]
            },
            {
                "role": "risk_analyst",
                "task_description": "分析技术风险和缓解策略",
                "required_inputs": ["solution_pro_output", "architecture_design"],
                "expected_output_stage": "risk_analysis",
                "output_schema": "WorkerDeliverable",
                "depends_on": ["architecture_designer"],
                "needs_web_search": False,
                "must_constraints": ["所有 Prompt 必须包含约束笼子"],
                "solution_pro_refs": ["REQ-004"]
            }
        ]
    }


def create_mock_worker_outputs():
    """创建模拟的 Worker 输出"""
    return {
        "architecture_designer": {
            "work_packages": [
                {
                    "wp_id": "WP-001",
                    "title": "核心调度引擎",
                    "description": "实现基于 DAG 的 Agent 调度引擎",
                    "acceptance_criteria": [
                        "支持拓扑排序",
                        "支持并行执行",
                        "支持依赖关系验证"
                    ],
                    "covered_req_ids": ["REQ-001", "REQ-002"],
                    "estimated_hours": 80
                },
                {
                    "wp_id": "WP-002",
                    "title": "Blackboard 状态管理",
                    "description": "实现 Blackboard 状态持久化和管理",
                    "acceptance_criteria": [
                        "支持原子写入",
                        "支持状态机转换",
                        "支持并发访问"
                    ],
                    "covered_req_ids": ["REQ-003"],
                    "estimated_hours": 40
                }
            ],
            "dependency_graph": {
                "edges": [
                    {"from": "WP-001", "to": "WP-002"}
                ],
                "execution_layers": [["WP-001"], ["WP-002"]]
            }
        },
        "implementation_planner": {
            "work_packages": [
                {
                    "wp_id": "WP-003",
                    "title": "Phase 1 实现",
                    "description": "实现核心功能",
                    "acceptance_criteria": [
                        "完成调度引擎",
                        "完成状态管理",
                        "通过单元测试"
                    ],
                    "covered_req_ids": ["REQ-003"],
                    "estimated_hours": 120
                }
            ],
            "dependency_graph": {
                "edges": [
                    {"from": "WP-001", "to": "WP-003"},
                    {"from": "WP-002", "to": "WP-003"}
                ],
                "execution_layers": [["WP-001", "WP-002"], ["WP-003"]]
            }
        },
        "risk_analyst": {
            "work_packages": [
                {
                    "wp_id": "WP-004",
                    "title": "风险评估报告",
                    "description": "生成技术风险评估和缓解策略",
                    "acceptance_criteria": [
                        "识别所有关键风险",
                        "提供缓解策略",
                        "评估影响程度"
                    ],
                    "covered_req_ids": ["REQ-004"],
                    "estimated_hours": 20
                }
            ],
            "dependency_graph": {
                "edges": [
                    {"from": "WP-001", "to": "WP-004"}
                ],
                "execution_layers": [["WP-001"], ["WP-004"]]
            }
        }
    }


def create_mock_ship_package(worker_outputs):
    """创建模拟的 ShipPackage"""
    all_work_packages = []
    all_edges = []
    
    for role, output in worker_outputs.items():
        all_work_packages.extend(output["work_packages"])
        all_edges.extend(output["dependency_graph"]["edges"])
    
    return {
        "solution_name": "AI Native Loop Engineering Framework",
        "work_packages": all_work_packages,
        "dependency_graph": {
            "edges": all_edges,
            "execution_layers": [["WP-001", "WP-002"], ["WP-003", "WP-004"]]
        },
        "metadata": {
            "total_work_packages": len(all_work_packages),
            "total_dependencies": len(all_edges)
        }
    }


def main():
    """主函数"""
    print("=" * 80)
    print("Ship Pro V6 - Dry Run")
    print("=" * 80)
    
    # Setup
    blackboard_path = Path("blackboard/OpenClaw AI Native Loop Engineering Framework")
    blackboard_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize StateManager
    print("\n1. Initializing StateManager...")
    state_mgr = StateManager(blackboard_path)
    print(f"   ✅ StateManager initialized (run_id: {state_mgr.state.run_id})")
    
    # Create mock data
    print("\n2. Creating mock data...")
    solution_pro_output = create_mock_solution_pro_output()
    planner_output = create_mock_planner_output()
    worker_outputs = create_mock_worker_outputs()
    ship_package = create_mock_ship_package(worker_outputs)
    print("   ✅ Mock data created")
    
    # Initialize Orchestrator
    print("\n3. Initializing ShipOrchestrator...")
    orchestrator = ShipOrchestrator(state_mgr)
    print("   ✅ Orchestrator initialized")
    
    # Phase 1: Planner
    print("\n4. Phase 1: Planner")
    print("   4.1 Updating state: pending → running")
    state_mgr.update_stage("planner", "running")
    
    print("   4.2 Validating PlannerOutput...")
    planner_output_obj = PlannerOutput(**planner_output)
    print(f"   ✅ PlannerOutput valid ({len(planner_output_obj.worker_specs)} workers)")
    
    print("   4.3 Running PlannerGate...")
    orchestrator.run_planner_gate(planner_output)
    print("   ✅ PlannerGate passed")
    
    print("   4.4 Updating state: running → completed")
    state_mgr.update_stage("planner", "completed")
    
    # Phase 2: Build
    print("\n5. Phase 2: Build")
    print("   5.1 Updating state: pending → running")
    state_mgr.update_stage("build", "running")
    
    print("   5.2 Computing topological order...")
    topo_order = orchestrator.compute_topological_order(planner_output["worker_specs"])
    print(f"   ✅ Topological order: {topo_order}")
    
    print("   5.3 Validating WorkerDeliverables...")
    for role in topo_order:
        worker_output = worker_outputs[role]
        worker_deliverable = WorkerDeliverable(**worker_output)
        print(f"   ✅ {role}: {len(worker_deliverable.work_packages)} work packages")
    
    print("   5.4 Running WorkerGates...")
    orchestrator.run_worker_gates(planner_output["worker_specs"], worker_outputs)
    print("   ✅ All WorkerGates passed")
    
    print("   5.5 Updating state: running → completed")
    state_mgr.update_stage("build", "completed")
    
    # Phase 3: Shipper
    print("\n6. Phase 3: Shipper")
    print("   6.1 Updating state: pending → running")
    state_mgr.update_stage("shipper", "running")
    
    print("   6.2 Validating ShipPackage...")
    ship_package_obj = ShipPackage(**ship_package)
    print(f"   ✅ ShipPackage valid ({len(ship_package_obj.work_packages)} work packages)")
    
    print("   6.3 Running Gates (InformationConservation, Completeness, HarnessV3)...")
    orchestrator.run_shipper_gates(solution_pro_output, ship_package)
    print("   ✅ All Gates passed")
    
    print("   6.4 Updating state: running → completed")
    state_mgr.update_stage("shipper", "completed")
    
    # Final summary
    print("\n" + "=" * 80)
    print("Dry Run Summary")
    print("=" * 80)
    print(f"✅ All phases completed successfully")
    print(f"✅ Total work packages: {len(ship_package_obj.work_packages)}")
    print(f"✅ Total dependencies: {len(ship_package_obj.dependency_graph.edges)}")
    print(f"✅ Execution layers: {len(ship_package_obj.dependency_graph.execution_layers)}")
    print(f"✅ State transitions: pending → running → completed (all phases)")
    print("=" * 80)


if __name__ == "__main__":
    main()
