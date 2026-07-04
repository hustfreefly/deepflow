#!/usr/bin/env python3
"""
Ship Pro V8 - Dry Run (DeepFlowDryRun V5.0 适配)

四层验证：
  L1: 结构验证（Schema + Import + 契约笼子）
  L2: 单角色行为预演（PipelineDesigner + Worker prompt + Consolidator）
  L3: 链条串联（design_pipeline → prepare_runner_spawn → Worker → Consolidator）
  L4: Orchestrator 预演（契约笼子 + 失败级联）
"""
import json
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

issues = []
stats = {"l1": 0, "l2": 0, "l3": 0, "l4": 0}


def check(layer: str, name: str, condition: bool, detail: str = ""):
    """记录检查结果"""
    stats[layer] = stats.get(layer, 0) + 1
    if condition:
        print(f"  {PASS} {name}")
    else:
        msg = f"{name}: {detail}" if detail else name
        print(f"  {FAIL} {msg}")
        issues.append(f"[{layer.upper()}] {msg}")


def check_raise(layer: str, name: str, fn, expected_error=ValueError):
    """验证函数是否 raise 预期异常（契约笼子）"""
    stats[layer] = stats.get(layer, 0) + 1
    try:
        fn()
        msg = f"{name}: 应该 raise {expected_error.__name__} 但没有"
        print(f"  {FAIL} {msg}")
        issues.append(f"[{layer.upper()}] {msg}")
    except expected_error as e:
        print(f"  {PASS} {name} → raise {expected_error.__name__}: {str(e)[:80]}")
    except Exception as e:
        msg = f"{name}: 预期 {expected_error.__name__} 但得到 {type(e).__name__}: {e}"
        print(f"  {FAIL} {msg}")
        issues.append(f"[{layer.upper()}] {msg}")


# ============================================================================
# Mock Data
# ============================================================================

def create_mock_solution_pro_input():
    """V8 格式的 Solution Pro 输入"""
    return {
        "requirements": [
            {"id": f"REQ-{i:03d}", "description": f"需求 {i}: 实现功能模块 {chr(65+i%26)}", "priority": "must_have" if i <= 30 else "should_have"}
            for i in range(1, 41)
        ],
        "key_decisions": [
            {"id": f"D-{i}", "description": f"决策 {i}: 使用 JSON 统一序列化"}
            for i in range(1, 11)
        ],
        "risk_mitigations": [
            {"id": f"R-{i}", "description": f"风险 {i}: API 限流"}
            for i in range(1, 6)
        ],
        "architecture": {
            "overview": "分形三层 Loop 架构",
            "layers": ["project_loop", "domain_loop", "phase_loop"]
        },
        "must_constraints": [
            "所有组件使用 JSON 序列化",
            "原子写入保证崩溃安全"
        ]
    }


def create_mock_pipeline_plan():
    """模拟 PipelineDesigner 输出"""
    return {
        "workers": [
            {
                "role": "CoreInfra",
                "module_purpose": "核心基础设施层，提供 Blackboard、原子写入、锁管理、审计日志、JSON 序列化",
                "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"],
                "depends_on": [],
                "interface_provides": ["BlackboardManager.read()", "BlackboardManager.write()", "AtomicWriter.write()"],
                "interface_requires": [],
                "relevant_decisions": ["D-1: 使用 JSON 统一序列化"],
                "relevant_risks": ["R-1: API 限流"],
                "estimated_wps": 5,
                "estimated_effort_hours": 48
            },
            {
                "role": "LoopEngine",
                "module_purpose": "Loop 引擎层，实现 DAG 调度、任务执行、结果收集、状态推进",
                "covered_req_ids": ["REQ-006", "REQ-007", "REQ-008", "REQ-009", "REQ-010"],
                "depends_on": ["CoreInfra"],
                "interface_provides": ["DAGScheduler.schedule()", "TaskExecutor.run()"],
                "interface_requires": ["BlackboardManager.read()", "BlackboardManager.write()"],
                "relevant_decisions": ["D-2: DAG 拓扑排序"],
                "relevant_risks": [],
                "estimated_wps": 5,
                "estimated_effort_hours": 40
            },
            {
                "role": "QualityGate",
                "module_purpose": "质量门层，实现三层验证（L1 确定性 + L2 LLM Judge + L3 综合）",
                "covered_req_ids": ["REQ-011", "REQ-012", "REQ-013", "REQ-014", "REQ-015"],
                "depends_on": ["CoreInfra", "LoopEngine"],
                "interface_provides": ["GateRunner.run_l1()", "GateRunner.run_l2()"],
                "interface_requires": ["BlackboardManager.read()", "DAGScheduler.schedule()"],
                "relevant_decisions": ["D-3: 三层验证架构"],
                "relevant_risks": ["R-2: Judge 幻觉"],
                "estimated_wps": 4,
                "estimated_effort_hours": 32
            },
            {
                "role": "SafetyShield",
                "module_purpose": "安全盾层，实现熔断、降级、超时控制、安全暂停",
                "covered_req_ids": ["REQ-016", "REQ-017", "REQ-018", "REQ-019", "REQ-020"],
                "depends_on": ["CoreInfra"],
                "interface_provides": ["CircuitBreaker.check()", "SafePause.trigger()"],
                "interface_requires": ["BlackboardManager.read()"],
                "relevant_decisions": [],
                "relevant_risks": ["R-3: 级联失败"],
                "estimated_wps": 4,
                "estimated_effort_hours": 28
            }
        ],
        "execution_order": [
            ["CoreInfra", "SafetyShield"],
            ["LoopEngine"],
            ["QualityGate"]
        ],
        "rationale": "按代码内聚性拆分为 4 个可独立交付的模块：核心基础设施、Loop 引擎、质量门、安全盾。CoreInfra 是基础，其他模块依赖它。SafetyShield 与 CoreInfra 并行开发，LoopEngine 依赖 CoreInfra，QualityGate 依赖前两者。"
    }


def create_mock_worker_output(role: str, prefix: str, wp_count: int = 5):
    """模拟 Worker 输出"""
    return {
        "worker_role": role,
        "wp_id_prefix": prefix,
        "work_packages": [
            {
                "id": f"{prefix}-{i:03d}",
                "title": f"WP {i}: {role} 功能模块 {i}",
                "description": f"实现 {role} 的第 {i} 个功能模块。该模块提供核心能力，包括数据管理、状态同步、并发控制和错误恢复。采用原子写入保证崩溃安全，使用 JSON 统一序列化保证跨层数据一致性。" * 2,
                "acceptance_criteria": [
                    f"AC1: 支持功能 {i} 的 CRUD 操作",
                    f"AC2: 并发测试通过（6 writer 无数据损坏）",
                    f"AC3: 崩溃恢复测试（kill -9 后状态一致）"
                ],
                "deliverables": [f"{role.lower()}_{i}.py", f"test_{role.lower()}_{i}.py"],
                "effort_hours": 8 + i * 2,
                "dependencies": [f"{prefix}-{i-1:03d}"] if i > 1 else []
            }
            for i in range(1, wp_count + 1)
        ]
    }


# ============================================================================
# Layer 1: 结构验证
# ============================================================================

def layer1_structure():
    print("\n" + "=" * 70)
    print("Layer 1: 结构验证")
    print("=" * 70)

    # 1.1 Import 可达性
    try:
        from domains.ship_pro import design_pipeline, prepare_runner_spawn
        from domains.ship_pro.pipeline_designer import (
            PipelineDesigner, PipelinePlan, WorkerSpec, WorkerContext,
            validate_solution_pro_input
        )
        from domains.ship_pro.orchestrator.ship_orchestrator import (
            ShipOrchestrator, extract_json_from_completion
        )
        from domains.ship_pro.contracts.gates import (
            WorkerGate, InformationConservationGate, CompletenessGate, HarnessV3
        )
        from domains.ship_pro.contracts.worker_deliverable import WorkPackage, WorkerDeliverable
        check("l1", "Import 可达性（8 模块）", True)
    except ImportError as e:
        check("l1", "Import 可达性", False, str(e))
        return False

    # 1.2 Schema 完整性
    try:
        schema = PipelinePlan.model_json_schema()
        has_workers = "workers" in schema.get("properties", {})
        has_exec_order = "execution_order" in schema.get("properties", {})
        check("l1", "PipelinePlan Schema 完整性", has_workers and has_exec_order)
    except Exception as e:
        check("l1", "PipelinePlan Schema", False, str(e))

    # 1.3 Gate build_judge_prompt 存在性
    gates_with_judge = [
        ("WorkerGate", WorkerGate),
        ("InformationConservationGate", InformationConservationGate),
        ("HarnessV3", HarnessV3),
    ]
    for name, gate_cls in gates_with_judge:
        has_method = hasattr(gate_cls, "build_judge_prompt")
        check("l1", f"Gate {name}.build_judge_prompt", has_method)

    # 1.4 V8 新方法存在性
    v8_methods = [
        "validate_all_worker_outputs_l1",
        "prepare_judge_spawn_all",
        "merge_gate_results",
        "prepare_consolidator_spawn_v8",
        "validate_ship_package_v8",
    ]
    for method in v8_methods:
        has_method = hasattr(ShipOrchestrator, method)
        check("l1", f"ShipOrchestrator.{method}", has_method)

    # 1.5 Prompt 模板文件存在性
    prompt_files = [
        "prompts/pipeline_runner.md",
        "prompts/worker_template.md",
        "prompts/consolidator.md",
    ]
    base = Path(__file__).parent.parent
    for pf in prompt_files:
        exists = (base / pf).exists()
        check("l1", f"Prompt {pf}", exists)

    # 1.6 V8_DECISIONS.md 存在
    v8_doc = base / "docs" / "V8_DECISIONS.md"
    check("l1", "V8_DECISIONS.md", v8_doc.exists())

    return len([i for i in issues if i.startswith("[L1]")]) == 0


# ============================================================================
# Layer 2: 单角色行为预演
# ============================================================================

def layer2_roles():
    print("\n" + "=" * 70)
    print("Layer 2: 单角色行为预演")
    print("=" * 70)

    from domains.ship_pro.pipeline_designer import (
        PipelineDesigner, PipelinePlan, WorkerSpec, WorkerContext,
        validate_solution_pro_input
    )
    from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator

    tmp = Path(tempfile.mkdtemp())
    stages = tmp / "stages"
    stages.mkdir()
    input_data = create_mock_solution_pro_input()

    # 2.1 validate_solution_pro_input 契约笼子
    print("\n  --- 2.1 validate_solution_pro_input ---")
    check_raise("l2", "空输入 raise", lambda: validate_solution_pro_input({}))
    check_raise("l2", "空 requirements raise", lambda: validate_solution_pro_input({"requirements": []}))
    check_raise("l2", "缺少 id raise", lambda: validate_solution_pro_input({"requirements": [{"description": "x"}]}))
    
    valid = validate_solution_pro_input(input_data)
    check("l2", "合法输入通过", len(valid["requirements"]) == 40)

    # 2.2 PipelinePlan 契约笼子
    print("\n  --- 2.2 PipelinePlan Schema ---")
    plan_data = create_mock_pipeline_plan()
    plan = PipelinePlan(**plan_data)
    check("l2", "PipelinePlan 构建", len(plan.workers) == 4)
    check("l2", "execution_order 完整", 
          set(r for layer in plan.execution_order for r in layer) == {w.role for w in plan.workers})

    # 2.2b PipelinePlan 违规
    bad_plan = dict(plan_data)
    bad_plan["workers"] = []  # 少于 min_length=2
    check_raise("l2", "workers 空 raise", lambda: PipelinePlan(**bad_plan))

    bad_plan2 = dict(plan_data)
    bad_plan2["execution_order"] = [["NotExist"]]
    check_raise("l2", "execution_order 不匹配 raise", lambda: PipelinePlan(**bad_plan2))

    # 2.3 PipelineDesigner 上下文裁剪
    print("\n  --- 2.3 上下文裁剪 ---")
    designer = PipelineDesigner(blackboard_path=tmp)
    contexts = designer.generate_worker_contexts(plan, input_data)
    check("l2", "生成 4 个 Worker context", len(contexts) == 4)

    for role, ctx in contexts.items():
        serialized = json.dumps(ctx.model_dump(), ensure_ascii=False)
        check("l2", f"Context {role} ≤ 3KB ({len(serialized)} bytes)", len(serialized) <= 3072)

    # 2.3b 裁剪后 REQ-ID 存在性验证
    print("\n  --- 2.3b REQ-ID 存在性 ---")
    bad_plan_req = dict(plan_data)
    bad_plan_req["workers"] = [dict(plan_data["workers"][0]), dict(plan_data["workers"][1])]
    bad_plan_req["workers"][0]["covered_req_ids"] = ["REQ-999"]  # 不存在
    bad_plan_req["execution_order"] = [["CoreInfra", "LoopEngine"]]
    bad_plan_obj = PipelinePlan(**bad_plan_req)
    check_raise("l2", "不存在的 REQ-ID raise",
                lambda: designer.generate_worker_contexts(bad_plan_obj, input_data))

    # 2.4 Worker prompt 生成
    print("\n  --- 2.4 Worker prompt 生成 ---")
    from domains.ship_pro import _build_worker_prompts
    context_paths = designer.save_contexts(contexts)
    
    worker_prompts = _build_worker_prompts(plan, contexts, context_paths, tmp)
    check("l2", "生成 4 个 Worker prompt", len(worker_prompts) == 4)
    
    for role, prompt in worker_prompts.items():
        # 6 段式检查
        has_role = "你是" in prompt or "技术设计师" in prompt
        has_dataflow = "read(" in prompt and "write(" in prompt
        has_forbidden = "禁止" in prompt or "❌" in prompt
        has_example = "CORE-001" in prompt or "Blackboard" in prompt
        has_output_path = "worker_" in prompt
        
        all_ok = has_role and has_dataflow and has_forbidden and has_example and has_output_path
        check("l2", f"Prompt {role} 6段式完整 ({len(prompt)} bytes)", all_ok,
              f"role={has_role} dataflow={has_dataflow} forbidden={has_forbidden} example={has_example} path={has_output_path}")
        check("l2", f"Prompt {role} ≤ 3KB", len(prompt) <= 3072, f"实际 {len(prompt)} bytes")

    # 2.5 Consolidator prompt
    print("\n  --- 2.5 Consolidator ---")
    orch = ShipOrchestrator(tmp)
    
    # 写入 mock worker 输出
    for role, prefix in [("CoreInfra", "CORE"), ("LoopEngine", "LOOP"), ("QualityGate", "QG"), ("SafetyShield", "SAFE")]:
        wo = create_mock_worker_output(role, prefix, wp_count=4)
        (stages / f"worker_{role}.json").write_text(json.dumps(wo), encoding="utf-8")
    
    # 写入 planner output
    (stages / "planner_output.json").write_text(json.dumps(plan_data), encoding="utf-8")
    
    try:
        cons_params = orch.prepare_consolidator_spawn_v8(str(tmp))
        has_task = "task" in cons_params and len(cons_params["task"]) > 100
        has_label = "label" in cons_params
        check("l2", "Consolidator spawn params", has_task and has_label)
        check("l2", "Consolidator prompt 含 6 步法", "Step 1" in cons_params["task"] or "收集" in cons_params["task"])
    except Exception as e:
        check("l2", "Consolidator spawn", False, str(e))

    shutil.rmtree(tmp, ignore_errors=True)
    return len([i for i in issues if i.startswith("[L2]")]) == 0


# ============================================================================
# Layer 3: 链条串联预演
# ============================================================================

def layer3_chain():
    print("\n" + "=" * 70)
    print("Layer 3: 链条串联预演")
    print("=" * 70)

    from domains.ship_pro.pipeline_designer import PipelineDesigner, PipelinePlan
    from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
    from domains.ship_pro import _build_worker_prompts

    tmp = Path(tempfile.mkdtemp())
    stages = tmp / "stages"
    stages.mkdir()
    input_data = create_mock_solution_pro_input()
    plan_data = create_mock_pipeline_plan()
    plan = PipelinePlan(**plan_data)

    # 3.1 design_pipeline → context trimming → worker prompts
    print("\n  --- 3.1 Designer → Context → Prompts ---")
    designer = PipelineDesigner(blackboard_path=tmp)
    contexts = designer.generate_worker_contexts(plan, input_data)
    context_paths = designer.save_contexts(contexts)
    worker_prompts = _build_worker_prompts(plan, contexts, context_paths, tmp)
    check("l3", "Designer→Context→Prompts 链", len(worker_prompts) == 4)

    # 3.2 模拟 Worker 输出 → L1 验证
    print("\n  --- 3.2 Worker→L1 验证 ---")
    orch = ShipOrchestrator(tmp)
    
    for role, prefix in [("CoreInfra", "CORE"), ("LoopEngine", "LOOP"), ("QualityGate", "QG"), ("SafetyShield", "SAFE")]:
        wo = create_mock_worker_output(role, prefix, wp_count=4)
        (stages / f"worker_{role}.json").write_text(json.dumps(wo), encoding="utf-8")
    
    l1_result = orch.validate_all_worker_outputs_l1(str(tmp))
    check("l3", "L1 全 PASS", l1_result["all_passed"])
    check("l3", "4 Worker 验证通过", len(l1_result["workers"]) == 4)

    # 3.3 L2 Judge spawn
    print("\n  --- 3.3 L2 Judge spawn ---")
    (stages / "planner_output.json").write_text(json.dumps(plan_data), encoding="utf-8")
    judge_params = orch.prepare_judge_spawn_all(str(tmp))
    # 只有 CoreInfra 和 QualityGate 有 must_constraints (mock data 中没设)
    # 但 planner_output mock 中有 must_constraints=[] → 不 spawn
    check("l3", "Judge spawn 参数列表", isinstance(judge_params, list))

    # 3.4 Worker→Consolidator 链
    print("\n  --- 3.4 Worker→Consolidator ---")
    cons_params = orch.prepare_consolidator_spawn_v8(str(tmp))
    check("l3", "Consolidator 可 spawn", "task" in cons_params)

    # 3.5 模拟 Consolidator 输出 → ShipPackage 验证
    print("\n  --- 3.5 Consolidator→ShipPackage ---")
    all_wps = []
    for role, prefix in [("CoreInfra", "CORE"), ("LoopEngine", "LOOP"), ("QualityGate", "QG"), ("SafetyShield", "SAFE")]:
        wo_data = json.loads((stages / f"worker_{role}.json").read_text())
        all_wps.extend(wo_data["work_packages"])
    
    ship_package = {
        "ship_package_version": "v8",
        "solution": "Test Solution",
        "work_packages": all_wps,
        "dependency_graph": {"nodes": [wp["id"] for wp in all_wps], "edges": []},
        "statistics": {
            "total_wps": len(all_wps),
            "total_effort_hours": sum(wp.get("effort_hours", 0) for wp in all_wps),
            "req_coverage_rate": 0.5,
            "dependency_edges": 0
        },
        "issues": [],
        "pending_req_ids": [f"REQ-{i:03d}" for i in range(21, 41)]
    }
    (stages / "ship_package.json").write_text(json.dumps(ship_package), encoding="utf-8")
    
    sp_result = orch.validate_ship_package_v8(str(tmp))
    check("l3", "ShipPackage 验证 PASS", sp_result["valid"])
    check("l3", f"WP 数 {sp_result['wp_count']}", sp_result["wp_count"] == 16)

    # 3.6 信息守恒：WP 不丢失
    print("\n  --- 3.6 信息守恒 ---")
    total_input_wps = sum(4 for _ in range(4))  # 4 workers × 4 WPs
    check("l3", f"WP 保留率 {sp_result['wp_count']}/{total_input_wps}",
          sp_result["wp_count"] == total_input_wps)

    shutil.rmtree(tmp, ignore_errors=True)
    return len([i for i in issues if i.startswith("[L3]")]) == 0


# ============================================================================
# Layer 4: Orchestrator 预演（契约笼子 + 失败级联）
# ============================================================================

def layer4_orchestrator():
    print("\n" + "=" * 70)
    print("Layer 4: Orchestrator 预演")
    print("=" * 70)

    from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator

    tmp = Path(tempfile.mkdtemp())
    stages = tmp / "stages"
    stages.mkdir()
    orch = ShipOrchestrator(tmp)

    # 4.1 L1 契约笼子：无文件 → raise
    print("\n  --- 4.1 L1 契约笼子 ---")
    check_raise("l4", "无 worker 文件 raise",
                lambda: orch.validate_all_worker_outputs_l1(str(tmp)))

    # 4.2 L1：坏 WP（desc 太短）→ raise
    print("\n  --- 4.2 L1 坏 WP ---")
    bad_wp = {
        "worker_role": "BadWorker",
        "wp_id_prefix": "BAD",
        "work_packages": [{
            "id": "BAD-001", "title": "Bad", "description": "短",
            "acceptance_criteria": ["AC1"],
            "deliverables": ["f.py"]
        }]
    }
    (stages / "worker_BadWorker.json").write_text(json.dumps(bad_wp), encoding="utf-8")
    check_raise("l4", "AC<2 + desc<100 raise",
                lambda: orch.validate_all_worker_outputs_l1(str(tmp)))
    (stages / "worker_BadWorker.json").unlink()

    # 4.3 L2 契约笼子：无 planner → raise
    print("\n  --- 4.3 L2 契约笼子 ---")
    good_wp = create_mock_worker_output("CoreInfra", "CORE", 3)
    (stages / "worker_CoreInfra.json").write_text(json.dumps(good_wp), encoding="utf-8")
    check_raise("l4", "无 planner_output.json raise",
                lambda: orch.prepare_judge_spawn_all(str(tmp)))

    # 4.4 L3 契约笼子：Judge 缺失 → raise
    print("\n  --- 4.4 L3 契约笼子 ---")
    plan_data = create_mock_pipeline_plan()
    # 给 CoreInfra 加 must_constraints，让 "Judge 缺失" 场景触发
    plan_data["workers"][0]["must_constraints"] = ["必须使用 JSON 序列化"]
    (stages / "planner_output.json").write_text(json.dumps(plan_data), encoding="utf-8")
    check_raise("l4", "Judge 缺失 raise (CoreInfra has must_constraints)",
                lambda: orch.merge_gate_results(str(tmp), {"all_passed": True}, {}))

    # 4.5 ShipPackage 契约笼子
    print("\n  --- 4.5 ShipPackage 契约笼子 ---")
    check_raise("l4", "无 ship_package.json raise",
                lambda: orch.validate_ship_package_v8(str(tmp)))

    (stages / "ship_package.json").write_text(json.dumps({"work_packages": []}), encoding="utf-8")
    check_raise("l4", "空 work_packages raise",
                lambda: orch.validate_ship_package_v8(str(tmp)))

    # 4.6 缺失字段
    print("\n  --- 4.6 WP 缺字段 ---")
    incomplete_sp = {"work_packages": [{"id": "X-001", "title": "T"}]}
    (stages / "ship_package.json").write_text(json.dumps(incomplete_sp), encoding="utf-8")
    check_raise("l4", "WP 缺 description/AC/deliverables raise",
                lambda: orch.validate_ship_package_v8(str(tmp)))

    # 4.7 正常流程
    print("\n  --- 4.7 正常流程 ---")
    good_sp = {
        "work_packages": [{
            "id": "CORE-001", "title": "T", "description": "D",
            "acceptance_criteria": ["AC1"], "deliverables": ["f.py"], "effort_hours": 8
        }]
    }
    (stages / "ship_package.json").write_text(json.dumps(good_sp), encoding="utf-8")
    result = orch.validate_ship_package_v8(str(tmp))
    check("l4", "合法 ShipPackage PASS", result["valid"])

    shutil.rmtree(tmp, ignore_errors=True)
    return len([i for i in issues if i.startswith("[L4]")]) == 0


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 70)
    print("Ship Pro V8 - DryRun V5.0 行为预演")
    print("=" * 70)

    l1_ok = layer1_structure()
    l2_ok = layer2_roles()
    l3_ok = layer3_chain()
    l4_ok = layer4_orchestrator()

    # 综合报告
    print("\n" + "=" * 70)
    print("DryRun V5.0 综合报告")
    print("=" * 70)
    
    for layer, ok in [("L1 结构验证", l1_ok), ("L2 单角色预演", l2_ok), 
                       ("L3 链条串联", l3_ok), ("L4 Orchestrator", l4_ok)]:
        count = stats.get(layer[:2].lower(), 0)
        layer_issues = [i for i in issues if i.startswith(f"[{layer[:2]}]")]
        status = PASS if ok else FAIL
        print(f"  {status} {layer}: {count} 项检查, {len(layer_issues)} 问题")

    total_checks = sum(stats.values())
    total_issues = len(issues)
    
    print(f"\n  总检查: {total_checks} 项")
    print(f"  总问题: {total_issues} 个")
    
    if issues:
        print(f"\n  问题清单:")
        for issue in issues:
            print(f"    {FAIL} {issue}")
    
    # 判定
    blocker_count = len([i for i in issues if "raise" in i.lower() or "import" in i.lower()])
    
    if total_issues == 0:
        verdict = "🟢 GO"
    elif blocker_count == 0:
        verdict = "🟡 CONDITIONAL"
    else:
        verdict = "🔴 NO_GO"
    
    print(f"\n  判定: {verdict}")
    print(f"  BLOCKER: {blocker_count} | 重要: {total_issues - blocker_count} | 建议: 0")
    print("=" * 70)

    return total_issues == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
