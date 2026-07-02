#!/usr/bin/env python3
"""
E2E V3 Harness Check V2 验证跑

用下午的 AI Loop frozen_spec，验证：
1. 契约笼子 (H1-H8) 能否拦截不合规输出
2. V2 验证链路 (harness_scorer + task_builder) 是否正常工作
3. verdict→score 映射是否正确
4. 分层聚合规则是否生效
"""

import sys
import json
import os
from pathlib import Path

# Setup path
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from domains.solution_pro.schemas.v2_schemas import (
    HarnessCheckV2, validate_harness_check_v2, verdict_to_score
)
from domains.solution_pro.harness_scorer import (
    validate_harness_output, validate_harness_output_v2, harness_v2_to_scores
)
from domains.solution_pro.task_builder import validate_stage_output

# ============================================================
# Test Data: AI Loop frozen_spec context
# ============================================================

FROZEN_SPEC_PATH = _root / "domains/solution_pro/blackboard_sessions/ai_loop_v3_full/frozen_spec.json"

def load_frozen_spec():
    with open(FROZEN_SPEC_PATH) as f:
        return json.load(f)

# ============================================================
# V2 Compliant Outputs (模拟 Worker 正确输出)
# ============================================================

def make_v2_harness_check(
    c_verdict="STRONG", n_verdict="ADEQUATE", a_verdict="STRONG", g_verdict="STRONG",
    overall_verdict="PASS", layer1_verdict="PASS",
    unverified_assumptions=None, beyond_spec_items=None,
):
    """生成 V2 格式的 harness_check"""
    return {
        "layer1_system_guardrails": {
            "completeness": {
                "verdict": c_verdict,
                "evidence": {"structural": "REQ-001~REQ-031 全部映射", "semantic": "P0 需求 100% 覆盖"},
                "unhandled_requirements": [],
                "deferred_requirements": [],
            },
            "necessity": {
                "verdict": n_verdict,
                "evidence": {"structural": "3 项建议已标注为 suggestion", "semantic": "超出 spec 的内容已标注"},
                "beyond_spec_items": beyond_spec_items or [{"item": "rate limiting", "type": "suggestion"}],
            },
            "alignment": {
                "verdict": a_verdict,
                "evidence": {"structural": "spec: AI Native Loop Framework", "semantic": "输出与 spec 核心目标一致"},
            },
            "global_impact": {
                "verdict": g_verdict,
                "evidence": {"structural": "JSON schema 验证通过", "semantic": "下游可直接消费"},
                "downstream_consumers": ["Researcher", "Reviewer"],
            },
        },
        "layer2_role_quality": {
            "expert_selection_quality": {
                "verdict": "STRONG",
                "sub_checks": {"覆盖所有关键领域": {"pass": True, "note": "5 个专家覆盖 AI loop 全维度"}},
                "evidence": {"structural": "required_experts: 5 entries", "semantic": "专家面板完整"},
            },
        },
        "reflection": {
            "unverified_assumptions": unverified_assumptions or [
                {
                    "assumption": "假设 5 个专家足够覆盖 AI Native Loop 的复杂度",
                    "location": "planning.json → required_experts",
                    "risk_if_wrong": "HIGH: 可能遗漏 loop 持久化和恢复的跨域交互",
                }
            ],
            "downstream_risk": {
                "risk_point": "Researcher 可能不知道 AI loop 的状态持久化聚焦什么",
                "location": "planning.json → dimensions.state_persistence 无 targets",
                "mitigation": "dispatch 前补充 state_persistence target",
            },
            "skipped_requirements": [
                {"req_id": "REQ-078", "reason": "P2 优先级，延迟到 detailed_design"},
            ],
        },
        "overall_verdict": overall_verdict,
        "layer1_verdict": layer1_verdict,
        "layer2_verdict": "PASS",
        "weakest_dimension": "necessity" if n_verdict == "ADEQUATE" else None,
        "improvement_priority": ["补充 state_persistence target"],
    }


def make_stage_output(harness_check, stage_name="planner"):
    """包装成完整 stage output"""
    return {
        "status": "completed",
        "stage": stage_name,
        "session_id": "e2e_v3_harness_v2_test",
        "timestamp": "2026-07-02T19:45:00",
        "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003"],
        "requirement_evidence": [
            {"req_id": "REQ-001", "status": "covered"},
            {"req_id": "REQ-002", "status": "covered"},
            {"req_id": "REQ-003", "status": "covered"},
        ],
        "harness_check": harness_check,
    }


# ============================================================
# Test Cases
# ============================================================

def run_tests():
    spec = load_frozen_spec()
    print(f"📋 Frozen Spec: {spec.get('topic', 'N/A')}")
    print(f"   Requirements: {len(spec.get('requirements', []))}")
    p0_count = len([r for r in spec.get('requirements', []) if r.get('priority') == 'P0'])
    print(f"   P0: {p0_count}")
    print()

    results = {"pass": 0, "fail": 0, "total": 0}

    def test(name, expected_pass, test_fn):
        results["total"] += 1
        try:
            ok, err = test_fn()
            if ok == expected_pass:
                results["pass"] += 1
                status = "✅"
            else:
                results["fail"] += 1
                status = "❌"
            detail = "" if ok else f": {err[:80]}"
            print(f"  {status} {name} (expected={'PASS' if expected_pass else 'FAIL'}, got={'PASS' if ok else 'FAIL'}{detail})")
        except Exception as e:
            results["fail"] += 1
            print(f"  ❌ {name}: EXCEPTION: {str(e)[:80]}")

    # === Test Group 1: V2 Schema Validation ===
    print("=" * 60)
    print("Test Group 1: V2 Schema Validation (HarnessCheckV2)")
    print("=" * 60)

    # 1.1: Compliant output should pass
    test("V2 合规输出通过", True, lambda: validate_harness_check_v2(make_v2_harness_check()))

    # 1.2: H1 - Missing dimension
    def test_h1_missing():
        hc = make_v2_harness_check()
        del hc["layer1_system_guardrails"]["alignment"]
        return validate_harness_check_v2(hc)
    test("H1: 缺少维度 → FAIL", False, test_h1_missing)

    # 1.3: H3 - FAIL verdict but overall PASS
    def test_h3_fail():
        hc = make_v2_harness_check(c_verdict="FAIL", overall_verdict="PASS", layer1_verdict="FAIL")
        return validate_harness_check_v2(hc)
    test("H3: FAIL + overall=PASS → FAIL", False, test_h3_fail)

    # 1.4: H3 - 2 WEAK but overall CONDITIONAL
    def test_h3_2weak():
        hc = make_v2_harness_check(
            c_verdict="WEAK", n_verdict="WEAK",
            overall_verdict="CONDITIONAL", layer1_verdict="FAIL"
        )
        return validate_harness_check_v2(hc)
    test("H3: 2×WEAK + overall=CONDITIONAL → FAIL", False, test_h3_2weak)

    # 1.5: H3 - 1 WEAK but overall PASS
    def test_h3_1weak():
        hc = make_v2_harness_check(
            c_verdict="WEAK", overall_verdict="PASS", layer1_verdict="CONDITIONAL"
        )
        return validate_harness_check_v2(hc)
    test("H3: 1×WEAK + overall=PASS → FAIL", False, test_h3_1weak)

    # 1.6: H3 - All ADEQUATE+ → PASS
    test("H3: 全 ADEQUATE+ → PASS", True, lambda: validate_harness_check_v2(
        make_v2_harness_check(c_verdict="ADEQUATE", n_verdict="ADEQUATE")
    ))

    # 1.7: H5 - All STRONG without justification
    def test_h5_all_strong():
        hc = make_v2_harness_check(
            c_verdict="STRONG", n_verdict="STRONG", a_verdict="STRONG", g_verdict="STRONG",
            overall_verdict="STRONG_PASS", layer1_verdict="PASS",
            unverified_assumptions=[
                {"assumption": "假设 X", "location": "x", "risk_if_wrong": "LOW: 低风险"}
            ]
        )
        return validate_harness_check_v2(hc)
    test("H5: 全 STRONG + STRONG_PASS 无 justification → FAIL", False, test_h5_all_strong)

    # 1.8: H6 - Evasive reflection
    def test_h6_evasive():
        hc = make_v2_harness_check(
            unverified_assumptions=[
                {"assumption": "没有问题，一切完备", "location": "x", "risk_if_wrong": "HIGH: ..."}
            ]
        )
        return validate_harness_check_v2(hc)
    test("H6: 敷衍反思 → FAIL", False, test_h6_evasive)

    # 1.9: H7 - Empty reflection
    def test_h7_empty():
        hc = make_v2_harness_check()
        hc["reflection"]["unverified_assumptions"] = []
        return validate_harness_check_v2(hc)
    test("H7: 空反思 → FAIL", False, test_h7_empty)

    # 1.10: H8 - beyond_spec without suggestion label
    def test_h8_beyond():
        hc = make_v2_harness_check(
            n_verdict="STRONG",
            beyond_spec_items=[{"item": "rate limiting", "type": "new_requirement"}]
        )
        return validate_harness_check_v2(hc)
    test("H8: beyond_spec 未标注 suggestion → FAIL", False, test_h8_beyond)

    print()

    # === Test Group 2: harness_scorer.py V2 Integration ===
    print("=" * 60)
    print("Test Group 2: harness_scorer.py V2 Integration")
    print("=" * 60)

    # 2.1: V2 output via validate_harness_output()
    def test_scorer_v2():
        output = make_stage_output(make_v2_harness_check())
        return validate_harness_output(output)
    test("scorer: V2 格式通过 validate_harness_output()", True, test_scorer_v2)

    # 2.2: V1 output backward compatibility
    def test_scorer_v1():
        output = {
            "status": "completed", "stage": "test", "covered_req_ids": ["REQ-001"],
            "harness_check": {
                "completeness": {"score": 0.85, "level": "high", "reasoning": "..."},
                "necessity": {"score": 0.90, "level": "high", "reasoning": "..."},
                "alignment": {"score": 0.88, "level": "high", "reasoning": "..."},
                "global_impact": {"score": 0.82, "level": "high", "reasoning": "..."},
                "overall_score": 0.86, "decision": "PASS", "improvements": [],
            }
        }
        return validate_harness_output(output)
    test("scorer: V1 格式向后兼容", True, test_scorer_v1)

    # 2.3: verdict→score mapping
    def test_verdict_mapping():
        hc = make_v2_harness_check(c_verdict="STRONG", n_verdict="ADEQUATE")
        scores = harness_v2_to_scores(hc)
        assert scores["completeness"] == 0.95, f"Expected 0.95, got {scores['completeness']}"
        assert scores["necessity"] == 0.80, f"Expected 0.80, got {scores['necessity']}"
        assert scores["decision"] == "PASS", f"Expected PASS, got {scores['decision']}"
        return True, ""
    test("scorer: verdict→score 映射正确", True, test_verdict_mapping)

    # 2.4: V2 dedicated validation
    def test_scorer_v2_dedicated():
        hc = make_v2_harness_check()
        return validate_harness_output_v2(hc)
    test("scorer: validate_harness_output_v2() 通过", True, test_scorer_v2_dedicated)

    print()

    # === Test Group 3: task_builder.py V2 Integration ===
    print("=" * 60)
    print("Test Group 3: task_builder.py V2 Integration")
    print("=" * 60)

    # 3.1: V2 stage output via validate_stage_output()
    def test_builder_v2():
        output = make_stage_output(make_v2_harness_check(), stage_name="researcher")
        return validate_stage_output(output, "researcher")
    test("builder: V2 stage output 通过", True, test_builder_v2)

    # 3.2: V2 with FAIL verdict (should still pass validation - it's valid V2 format)
    def test_builder_v2_fail():
        hc = make_v2_harness_check(
            c_verdict="FAIL", overall_verdict="FAIL", layer1_verdict="FAIL",
            unverified_assumptions=[
                {"assumption": "假设 X 可能不成立", "location": "planning.json → section 3", "risk_if_wrong": "HIGH: 导致下游全部错误"}
            ]
        )
        output = make_stage_output(hc, stage_name="researcher")
        return validate_stage_output(output, "researcher")
    test("builder: V2 FAIL verdict 格式仍有效", True, test_builder_v2_fail)

    # 3.3: V2 with invalid format (missing layer1)
    def test_builder_v2_invalid():
        output = make_stage_output({"invalid": True}, stage_name="researcher")
        return validate_stage_output(output, "researcher")
    test("builder: 无效 V2 格式 → FAIL", False, test_builder_v2_invalid)

    # 3.4: Exempt stage (planning) doesn't need harness_check
    def test_builder_exempt():
        output = {"status": "completed", "stage": "planning", "covered_req_ids": ["REQ-001"]}
        return validate_stage_output(output, "planning")
    test("builder: 豁免阶段 (planning) 不需要 harness_check", True, test_builder_exempt)

    print()

    # === Test Group 4: Cross-Worker Consistency ===
    print("=" * 60)
    print("Test Group 4: Cross-Worker V2 Consistency")
    print("=" * 60)

    workers = ["planner", "researcher", "reviewer", "auditor", "consolidator", "fixer", "fixer_expert"]
    for worker in workers:
        def test_worker(w=worker):
            hc = make_v2_harness_check()
            output = make_stage_output(hc, stage_name=w)
            ok, err = validate_stage_output(output, w)
            return ok, err
        test(f"Worker {worker}: V2 格式有效", True, test_worker)

    print()

    # === Summary ===
    print("=" * 60)
    passed = results["pass"]
    total = results["total"]
    failed = results["fail"]
    print(f"📊 Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("🎉 ALL TESTS PASSED — Harness Check V2 E2E 验证通过")
    else:
        print(f"⚠️  {failed} tests failed — 需要修复")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
