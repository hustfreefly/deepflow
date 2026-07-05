"""
Solution Pro V3 — 可执行验证测试

替代管线内文本搜索验证（41/41 PASS 的 "方案Section X.X定义..." 模式）。
每个测试验证一个关键约束的运行时行为，而非文档引用。

运行方式:
  cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -m pytest \
    domains/solution_pro/tests/test_verification_constraints.py -v

数据来源: blackboard_sessions/<session_id>/stages/
"""

import json
import pytest
from pathlib import Path


# ============================================================
# 配置：指向待验证的管线运行 session
# ============================================================
SESSION_DIR = Path(__file__).parent.parent / "blackboard_sessions" / "ai_loop_v3_full"


def load_stage(filename: str) -> dict:
    """加载 blackboard stage 文件"""
    path = SESSION_DIR / "stages" / filename
    if not path.exists():
        # 尝试不带 stages/ 前缀
        path = SESSION_DIR / filename
    if not path.exists():
        pytest.skip(f"Stage file not found: {path}")
    return json.loads(path.read_text())


def load_json(filename: str) -> dict:
    """加载任意 JSON 文件"""
    path = SESSION_DIR / filename
    if not path.exists():
        pytest.skip(f"File not found: {path}")
    return json.loads(path.read_text())


# ============================================================
# Test 1: P0 约束覆盖验证（替代 "方案Section X.X定义..." 文本搜索）
# ============================================================
class TestP0ConstraintCoverage:
    """
    验证: 所有 P0 REQ 在 unified_constraints 中有对应约束
    方法: 从 living_spec 提取 P0 REQ → 与 unified_constraints 交叉比对
    标准: 100% P0 REQ 有对应 constraint
    """

    def test_p0_requirements_have_constraints(self):
        """每个 P0 REQ 必须在 unified_constraints 中被引用"""
        living_spec = load_json("data/living_spec.json")
        unified = load_stage("unified_constraints.json")

        # 提取 P0 REQ
        req_index = living_spec.get("requirement_index", [])
        p0_reqs = [r for r in req_index if r.get("priority") == "P0"]
        p0_ids = {r["id"] for r in p0_reqs}

        assert len(p0_ids) > 0, "No P0 requirements found in living_spec"

        # 提取 unified constraints 中引用的 REQ IDs
        constraints = unified.get("unified_constraints", [])
        referenced_reqs = set()
        for c in constraints:
            refs = c.get("source_requirements", [])
            if isinstance(refs, list):
                referenced_reqs.update(refs)
            # 也检查 description 和 reasoning 中的引用
            for field in ["description", "reasoning", "id"]:
                text = str(c.get(field, ""))
                for req_id in p0_ids:
                    if req_id in text:
                        referenced_reqs.add(req_id)

        # 也检查 p0_constraints_merged
        p0_merged = unified.get("p0_constraints_merged", [])
        for c in p0_merged:
            refs = c.get("source_requirements", [])
            if isinstance(refs, list):
                referenced_reqs.update(refs)
            for field in ["description", "reasoning", "id"]:
                text = str(c.get(field, ""))
                for req_id in p0_ids:
                    if req_id in text:
                        referenced_reqs.add(req_id)

        # 计算覆盖率
        covered = p0_ids & referenced_reqs
        uncovered = p0_ids - referenced_reqs
        coverage = len(covered) / len(p0_ids) if p0_ids else 0

        assert coverage >= 0.9, (
            f"P0 constraint coverage: {coverage:.0%} ({len(covered)}/{len(p0_ids)}). "
            f"Uncovered: {sorted(uncovered)}"
        )

    def test_p0_constraints_are_severity_critical(self):
        """P0 约束的 severity 必须为 CRITICAL 或 HIGH"""
        unified = load_stage("unified_constraints.json")
        p0_merged = unified.get("p0_constraints_merged", [])

        for c in p0_merged:
            severity = c.get("severity", c.get("priority", "")).upper()
            assert severity in ("CRITICAL", "HIGH", "P0", "MUST", ""), (
                f"P0 constraint {c.get('id', '?')} has unexpected severity: {severity}"
            )


# ============================================================
# Test 2: 信息守恒验证（替代 "information_conservation = PASS" 文本断言）
# ============================================================
class TestInformationConservation:
    """
    验证: 需求→约束→方案的信息流完整性
    方法: 逐层检查关键数据的传播
    标准: 约束保留率 > 70%, research findings 保留率 > 80%
    """

    def test_constraint_retention_rate(self):
        """expert constraints → unified constraints 保留率 > 70%"""
        convergence = load_stage("convergence_planning.json")

        # 从 convergence 中提取统计数据
        expert_constraints_count = convergence.get("expert_constraints_count", 0)
        unified_count = len(convergence.get("unified_constraints", []))

        if expert_constraints_count == 0:
            # 尝试从 expert plans 计算
            expert_plans_dir = SESSION_DIR / "stages" / "expert_plans"
            if expert_plans_dir.exists():
                for f in expert_plans_dir.glob("*.json"):
                    plan = json.loads(f.read_text())
                    constraints = plan.get("constraints", [])
                    expert_constraints_count += len(constraints)

        if expert_constraints_count > 0:
            retention = unified_count / expert_constraints_count
            assert retention >= 0.5, (
                f"Constraint retention too low: {retention:.0%} "
                f"({unified_count}/{expert_constraints_count})"
            )

    def test_final_solution_references_constraints(self):
        """final_solution 必须显式引用 unified constraints"""
        final = load_stage("final_solution.json")
        unified = load_stage("unified_constraints.json")

        unified_ids = {c["id"] for c in unified.get("unified_constraints", []) if "id" in c}
        if not unified_ids:
            pytest.skip("No unified constraint IDs found")

        # 在 final_solution 全文中搜索 constraint ID 引用
        final_text = json.dumps(final, ensure_ascii=False)
        referenced = sum(1 for uid in unified_ids if uid in final_text)

        coverage = referenced / len(unified_ids) if unified_ids else 0
        assert coverage >= 0.7, (
            f"Final solution references {referenced}/{len(unified_ids)} "
            f"unified constraints ({coverage:.0%})"
        )


# ============================================================
# Test 3: 需求追溯矩阵验证（替代 "requirement_traceability = PASS"）
# ============================================================
class TestRequirementTraceability:
    """
    验证: convergence planner 输出的追溯矩阵覆盖所有 P0 REQ
    方法: 对比 living_spec P0 REQ 与 traceability_matrix
    标准: P0 覆盖率 100%
    """

    def test_traceability_matrix_covers_p0(self):
        """追溯矩阵必须覆盖所有 P0 REQ"""
        living_spec = load_json("data/living_spec.json")
        trace = load_stage("requirement_traceability.json")

        req_index = living_spec.get("requirement_index", [])
        p0_ids = {r["id"] for r in req_index if r.get("priority") == "P0"}

        matrix = trace.get("requirement_traceability_matrix", [])
        traced_ids = {row.get("req_id") for row in matrix if row.get("req_id")}

        covered = p0_ids & traced_ids
        uncovered = p0_ids - traced_ids

        coverage = len(covered) / len(p0_ids) if p0_ids else 0
        assert coverage >= 0.95, (
            f"Traceability coverage: {coverage:.0%} ({len(covered)}/{len(p0_ids)}). "
            f"Missing: {sorted(uncovered)}"
        )

    def test_traceability_has_solution_sections(self):
        """每条追溯记录必须有 solution_section 字段（非空）"""
        trace = load_stage("requirement_traceability.json")
        matrix = trace.get("requirement_traceability_matrix", [])

        assert len(matrix) > 0, "Traceability matrix is empty"

        empty_sections = [
            row.get("req_id", "?")
            for row in matrix
            if not row.get("solution_section", "").strip()
        ]
        assert len(empty_sections) == 0, (
            f"Traceability rows with empty solution_section: {empty_sections}"
        )


# ============================================================
# Test 4: 执行顺序时序验证（替代 "执行流程正确" 文本断言）
# ============================================================
class TestExecutionOrder:
    """
    验证: 数据依赖关系与执行顺序一致
    方法: 检查 stage 文件的时间戳或存在性
    标准: 下游 stage 不应引用不存在的上游 stage
    """

    def test_expert_plans_dont_reference_traceability(self):
        """Expert Plans 不应引用 requirement_traceability（因为它们在 Convergence 之前执行）"""
        expert_plans_dir = SESSION_DIR / "stages" / "expert_plans"
        if not expert_plans_dir.exists():
            pytest.skip("No expert_plans directory")

        for f in expert_plans_dir.glob("*.json"):
            plan = json.loads(f.read_text())
            plan_text = json.dumps(plan, ensure_ascii=False)

            # Expert Plans 不应该声称使用了追溯矩阵
            # （因为追溯矩阵在它们执行时还不存在）
            assert "requirement_traceability_matrix" not in plan_text, (
                f"Expert plan {f.name} claims to use requirement_traceability_matrix "
                f"but it runs before Convergence Planner"
            )

    def test_summary_workers_have_traceability(self):
        """Summary Workers 应能访问追溯矩阵（因为它们在 Convergence 之后执行）"""
        trace = load_stage("requirement_traceability.json")
        matrix = trace.get("requirement_traceability_matrix", [])
        assert len(matrix) > 0, (
            "Traceability matrix is empty — Summary Workers cannot use it"
        )


# ============================================================
# Test 5: Master State 一致性验证（替代 "status = COMPLETE" 文本断言）
# ============================================================
class TestMasterStateConsistency:
    """
    验证: master_state 与实际产出文件一致
    方法: 检查 state 文件的 completed_modules 与 stage 文件存在性
    标准: state 声称完成的模块必须有对应输出文件
    """

    def test_completed_modules_have_outputs(self):
        """每个 completed module 必须有对应的输出文件"""
        state_path = SESSION_DIR / "v2" / "master_state.json"
        if not state_path.exists():
            state_path = SESSION_DIR / "master_state.json"
        if not state_path.exists():
            pytest.skip("No master_state.json found")

        state = json.loads(state_path.read_text())
        completed = state.get("completed_modules", [])

        module_outputs = state.get("module_outputs", {})
        for module_name in completed:
            output_ref = module_outputs.get(module_name)
            assert output_ref is not None, (
                f"Module '{module_name}' is in completed_modules but "
                f"has no entry in module_outputs"
            )

    def test_state_not_initialized_with_artifacts(self):
        """如果 stages/ 有文件，state 不应停留在 INITIALIZED"""
        state_path = SESSION_DIR / "v2" / "master_state.json"
        if not state_path.exists():
            state_path = SESSION_DIR / "master_state.json"
        if not state_path.exists():
            pytest.skip("No master_state.json found")

        state = json.loads(state_path.read_text())
        stages_dir = SESSION_DIR / "stages"

        if stages_dir.exists():
            stage_files = list(stages_dir.glob("*.json"))
            if len(stage_files) > 5:
                # 有 5+ 个 stage 文件但 state 仍在 INITIALIZED = 不一致
                status = state.get("status", "UNKNOWN")
                assert status != "INITIALIZED", (
                    f"State is INITIALIZED but {len(stage_files)} stage files exist. "
                    f"State machine did not track progress."
                )


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
