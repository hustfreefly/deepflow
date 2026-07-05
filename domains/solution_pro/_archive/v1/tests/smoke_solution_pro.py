#!/usr/bin/env python3
"""Solution Pro 端到端集成冒烟测试"""

import os
import tempfile
import shutil
import traceback
from pathlib import Path

# Point PYTHONPATH to the deepflow project
DEEPFLOW_BASE = os.path.expanduser("~/.openclaw/workspace/.deepflow")

results = []
test_dir = None

# ============================================================================
# Test 1: Module Import
# ============================================================================
def test_1_module_import():
    """测试所有关键模块导入"""
    try:
        from domains.solution_pro import run_solution_pro
        from domains.solution_pro.orchestrator_agent import _SolutionDispatcher
        from domains.solution_pro.frozen_spec import build_frozen_spec, write_frozen_spec
        from domains.solution_pro.control_contract import build_control_contract
        from domains.solution_pro.task_builder import (
            build_data_collection_task, build_planner_task, build_researcher_task,
            build_reviewer_task, build_consolidator_task, build_auditor_task,
            build_fixer_task, build_fixer_task_with_audit, build_fixer_expert_task,
            build_harness_final_task, build_summarizer_task
        )
        return True, "所有模块导入成功"
    except Exception as e:
        return False, f"导入失败: {e}\n{traceback.format_exc()}"

# ============================================================================
# Test 2: frozen_spec V2.0
# ============================================================================
def test_2_frozen_spec():
    """测试 frozen_spec 生成（场景A + 场景B）"""
    errors = []

    # Scenario A: with living_spec
    try:
        from domains.solution_pro.frozen_spec import build_frozen_spec

        living_spec = {
            "confirmed": {
                "objective": "设计一个高并发电商平台",
                "capabilities": {
                    "always_do": ["支持百万级并发", "99.99%可用性"],
                    "should_do": ["微服务架构"],
                    "never_do": ["使用单体架构"]
                },
                "quality_attributes": [
                    {"spec": "响应时间<100ms", "priority": "P0", "target": "<100ms"},
                    {"spec": "日处理100万订单", "priority": "P1"}
                ],
                "constraints": {
                    "budget": "100万",
                    "timeline": "6个月",
                    "tech_stack": ["React", "Node.js"]
                },
                "integration": {
                    "requirements": ["对接支付宝", "对接微信支付"]
                },
                "pain_points": ["现有系统扩展性差"],
                "success_metrics": [{"metric": "转化率提升20%", "target": "20%"}],
                "users": [{"role": "终端消费者"}, {"role": "运营管理员"}],
                "key_scenarios": ["大促秒杀", "日常购物"],
                "risks_and_assumptions": {
                    "risks": [{"description": "第三方API不稳定"}],
                    "assumptions": [{"description": "云服务资源充足"}]
                },
                "requirement_annotations": []
            },
            "guardrails": {
                "always_do": ["遵循安全最佳实践"],
                "never_do": ["存储明文密码"]
            }
        }

        spec = build_frozen_spec(
            topic="高并发电商平台架构设计",
            constraints=["预算有限"],
            living_spec=living_spec
        )

        # Validate structure
        for key in ["executive_summary", "requirement_groups", "requirements", "guardrails"]:
            if key not in spec:
                errors.append(f"缺少顶层字段: {key}")

        # Validate executive_summary
        es = spec.get("executive_summary", {})
        for key in ["one_liner", "why", "for_whom", "success_criteria"]:
            if key not in es:
                errors.append(f"executive_summary 缺少字段: {key}")

        # Validate requirement_groups has 5 groups
        groups = spec.get("requirement_groups", {})
        expected_groups = {"Core", "Functional", "NonFunctional", "Boundaries", "Context"}
        actual_groups = set(groups.keys()) if isinstance(groups, dict) else set()
        missing_groups = expected_groups - actual_groups
        if missing_groups:
            errors.append(f"requirement_groups 缺少分组: {missing_groups}")

        # Validate requirements have IDs
        reqs = spec.get("requirements", [])
        if len(reqs) == 0:
            errors.append("requirements 为空")
        for req in reqs:
            if "id" not in req or not req["id"].startswith("REQ-"):
                errors.append(f"需求缺少有效ID: {req}")
                break

        # Validate version
        if spec.get("version") != "2.0":
            errors.append(f"version 应为 2.0, 实际: {spec.get('version')}")

    except Exception as e:
        errors.append(f"场景A异常: {e}\n{traceback.format_exc()}")

    # Scenario B: living_spec=None
    try:
        from domains.solution_pro.frozen_spec import build_frozen_spec
        spec_b = build_frozen_spec(
            topic="测试主题-B场景",
            constraints=None,
            living_spec=None
        )
        if "requirements" not in spec_b:
            errors.append("场景B: 缺少 requirements 字段")
        if len(spec_b.get("requirements", [])) == 0:
            errors.append("场景B: requirements 应为非空")
        if "requirement_groups" not in spec_b:
            errors.append("场景B: 缺少 requirement_groups 字段")
    except Exception as e:
        errors.append(f"场景B异常: {e}\n{traceback.format_exc()}")

    if errors:
        return False, "\n".join(errors)
    return True, "场景A/B均通过，包含5个分组、executive_summary字段完整"

# ============================================================================
# Test 3: _SolutionDispatcher init
# ============================================================================
def test_3_dispatcher_init():
    """测试 _SolutionDispatcher 初始化"""
    errors = []
    global test_dir

    try:
        # Create a temp dir for the test
        test_dir = tempfile.mkdtemp(prefix="solution_pro_smoke_")

        from domains.solution_pro.orchestrator_agent import _SolutionDispatcher
        from domains.solution_pro.frozen_spec import build_frozen_spec

        living_spec = {
            "confirmed": {
                "objective": "测试主题目标",
                "capabilities": {"always_do": ["能力1"]},
                "quality_attributes": [{"spec": "高质量", "priority": "P0"}],
                "constraints": {"budget": "50万"},
                "success_metrics": [{"metric": "指标1"}],
                "users": [{"role": "用户1"}],
            }
        }

        dispatcher = _SolutionDispatcher(
            topic="集成测试主题方案",
            solution_type="architecture",
            constraints=["约束1", "约束2"],
            stakeholders=["干系人1", "干系人2"],
            living_spec=living_spec,
            spawn_fn=None
        )

        session_id = dispatcher.init()

        if not session_id:
            errors.append("init() 返回空 session_id")
        if len(session_id) > 50:
            errors.append(f"session_id 超长: {len(session_id)} > 50")
        if not dispatcher.base_path:
            errors.append("base_path 为空")

        # Check blackboard directories
        bp = dispatcher.base_path
        if not os.path.exists(bp):
            errors.append(f"base_path 目录不存在: {bp}")

        # Check frozen_spec.json was written
        frozen_path = os.path.join(bp, "data", "frozen_spec.json")
        if not os.path.exists(frozen_path):
            errors.append(f"frozen_spec.json 未写入: {frozen_path}")
        else:
            import json
            with open(frozen_path) as f:
                fs = json.load(f)
            if "version" not in fs:
                errors.append("frozen_spec.json 缺少 version 字段")

        # Check stages dir
        stages_path = os.path.join(bp, "stages")
        if not os.path.exists(stages_path):
            errors.append(f"stages 目录未创建: {stages_path}")

    except Exception as e:
        errors.append(f"异常: {e}\n{traceback.format_exc()}")

    if errors:
        return False, "\n".join(errors)
    return True, f"session_id={session_id}, blackboard已创建, frozen_spec.json已写入"

# ============================================================================
# Test 4: get_all_tasks
# ============================================================================
def test_4_get_all_tasks():
    """测试 get_all_tasks 返回10个阶段"""
    errors = []
    global test_dir

    try:
        from domains.solution_pro.orchestrator_agent import _SolutionDispatcher

        living_spec = {
            "confirmed": {
                "objective": "测试目标",
                "capabilities": {"always_do": ["测试能力"]},
                "quality_attributes": [],
                "constraints": {},
                "success_metrics": [],
                "users": [],
            }
        }

        dispatcher = _SolutionDispatcher(
            topic="集成测试主题任务",
            solution_type="architecture",
            constraints=["约束1"],
            stakeholders=["干系人1"],
            living_spec=living_spec,
            spawn_fn=None
        )
        dispatcher.init()
        tasks = dispatcher.get_all_tasks()

        # Expected stages
        expected_stages = [
            "data_collection", "planning", "reviewers", "research",
            "consolidator", "audit", "fix", "fixer_expert",
            "harness_final", "summarizer"
        ]

        missing = [s for s in expected_stages if s not in tasks]
        if missing:
            errors.append(f"缺少阶段: {missing}")

        extra = [k for k in tasks if k not in expected_stages]
        if extra:
            errors.append(f"额外阶段: {extra}")

        if len(tasks) != len(expected_stages):
            errors.append(f"阶段数不匹配: 期望{len(expected_stages)}, 实际{len(tasks)}")

        # Check each stage has tasks (strings or dicts of strings)
        for stage, task_val in tasks.items():
            if isinstance(task_val, dict):
                for worker_id, prompt in task_val.items():
                    if not isinstance(prompt, str):
                        errors.append(f"阶段 {stage}.{worker_id} 的 prompt 不是字符串")
            elif isinstance(task_val, str):
                pass  # single string prompt is fine
            else:
                errors.append(f"阶段 {stage} 的值类型异常: {type(task_val)}")

        # Check "全局理解" context in key worker prompts
        key_workers_to_check = []
        for stage, val in tasks.items():
            if isinstance(val, str):
                key_workers_to_check.append((stage, val))
            elif isinstance(val, dict):
                for wid, prompt in val.items():
                    key_workers_to_check.append((f"{stage}.{wid}", prompt))

        workers_with_global = []
        workers_without_global = []
        for worker_name, prompt in key_workers_to_check:
            if "全局理解" in prompt:
                workers_with_global.append(worker_name)
            else:
                workers_without_global.append(worker_name)

        if len(workers_without_global) > 0:
            errors.append(
                f"缺少'全局理解'上下文的worker ({len(workers_without_global)}个): "
                f"{', '.join(workers_without_global[:5])}"
                + (f" ... 等{len(workers_without_global)}个" if len(workers_without_global) > 5 else "")
            )

    except Exception as e:
        errors.append(f"异常: {e}\n{traceback.format_exc()}")

    if errors:
        return False, "\n".join(errors)
    return True, f"10个阶段完整, {len(workers_with_global)}/{len(key_workers_to_check)}个worker含全局理解上下文"

# ============================================================================
# Test 5: control_contract
# ============================================================================
def test_5_control_contract():
    """测试 control_contract 生成"""
    errors = []
    global test_dir

    try:
        from domains.solution_pro.orchestrator_agent import _SolutionDispatcher
        from domains.solution_pro.control_contract import build_control_contract
        import json
import core.bootstrap

        living_spec = {
            "confirmed": {
                "objective": "测试目标",
                "capabilities": {"always_do": ["能力1"]},
                "quality_attributes": [{"spec": "质量1", "priority": "P0"}],
                "constraints": {},
                "success_metrics": [],
                "users": [],
            }
        }

        dispatcher = _SolutionDispatcher(
            topic="集成测试主题契约",
            solution_type="architecture",
            constraints=["约束1"],
            stakeholders=["干系人1"],
            living_spec=living_spec,
            spawn_fn=None
        )
        dispatcher.init()

        # Need execution_plan.json for control_contract
        # Call save_execution_plan to create it
        # But save_execution_plan requires planning.json to exist
        # Let's create a minimal planning.json
        planning_path = os.path.join(dispatcher.base_path, "stages", "planning.json")
        minimal_planning = {
            "required_experts": [],
            "audit_strategy": "standard",
            "mode": "standard",
            "layer2_constraints": []
        }
        os.makedirs(os.path.dirname(planning_path), exist_ok=True)
        with open(planning_path, "w") as f:
            json.dump(minimal_planning, f)

        # Also save execution_plan
        dispatcher.save_execution_plan()

        contract = build_control_contract(dispatcher.base_path)

        if "acceptance_criteria" not in contract:
            errors.append("缺少 acceptance_criteria 字段")
        else:
            criteria = contract["acceptance_criteria"]
            if not criteria:
                errors.append("acceptance_criteria 为空")
            else:
                # Check each item has 'group' field (V2.0 feature)
                missing_group = []
                for i, item in enumerate(criteria):
                    if isinstance(item, dict) and "group" not in item:
                        missing_group.append(i)
                if missing_group:
                    errors.append(f"acceptance_criteria 中以下索引缺少 'group' 字段(V2.0): {missing_group}")

    except Exception as e:
        errors.append(f"异常: {e}\n{traceback.format_exc()}")

    if errors:
        return False, "\n".join(errors)
    return True, "control_contract 包含 acceptance_criteria，group字段检查完成"

# ============================================================================
# Test 6: Cleanup
# ============================================================================
def test_6_cleanup():
    """清理测试创建的目录"""
    global test_dir
    try:
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            return True, f"已清理测试目录: {test_dir}"
        elif test_dir:
            return True, f"测试目录已不存在: {test_dir}"
        else:
            return True, "无测试目录需要清理"
    except Exception as e:
        return False, f"清理失败: {e}\n{traceback.format_exc()}"

# ============================================================================
# Run all tests
# ============================================================================
print("=" * 70)
print("Solution Pro 集成冒烟测试")
print("=" * 70)

tests = [
    ("测试1: 模块导入", test_1_module_import),
    ("测试2: frozen_spec V2.0", test_2_frozen_spec),
    ("测试3: _SolutionDispatcher 初始化", test_3_dispatcher_init),
    ("测试4: get_all_tasks", test_4_get_all_tasks),
    ("测试5: control_contract", test_5_control_contract),
    ("测试6: 清理测试", test_6_cleanup),
]

passed = 0
failed = 0

for name, test_fn in tests:
    print(f"\n{'─'*70}")
    print(f"▶ {name}")
    try:
        ok, detail = test_fn()
        status = "✅ PASS" if ok else "❌ FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  {status}: {detail}")
    except Exception as e:
        failed += 1
        print(f"  ❌ FAIL: 未捕获异常: {e}")
        traceback.print_exc()

print(f"\n{'='*70}")
print(f"总体: {passed} 通过, {failed} 失败 (共 {len(tests)} 项)")
print(f"{'='*70}")
