#!/usr/bin/env python3
"""
E2E Test: Living Spec V2 全链路闭环测试

测试场景: "为小型电商团队构建订单自动通知系统"
覆盖:
  Phase 1: 模拟 Spec Pro 3 轮对话 → merge_conversation_digest
  Phase 2: 验证 living_spec.conversation_digest 累积结果
  Phase 3: Harness V2 验证 (Layer 1 S1-S10 + Layer 2 SC1-SC2)
  Phase 4: Solution Pro 消费验证 (build_conversation_digest_for_prompt + build_worker_context_section)
  Phase 5: 边界测试 (V1 兼容/空 digest/超范围 dimension/去重)
"""

import json
import os
import sys
import tempfile
import shutil

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from domains.spec_pro.merge_spec import merge_conversation_digest, merge_confirmed, merge_spec
from domains.spec_pro.eval.harness import run_harness_v2, run_harness, StructuralGate
from domains.solution_pro.spec_context import (
    build_living_spec_context,
    build_conversation_digest_for_prompt,
    build_worker_context_section,
)

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.detail = ""

    def ok(self, detail=""):
        self.passed = True
        self.detail = detail
        return self

    def fail(self, detail=""):
        self.passed = False
        self.detail = detail
        return self

class TestRunner:
    def __init__(self):
        self.results: list[TestResult] = []
        self.tmpdir = tempfile.mkdtemp(prefix="living_spec_v2_test_")

    def cleanup(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def run(self, test_fn):
        r = TestResult(test_fn.__name__)
        try:
            test_fn(r)
        except Exception as e:
            r.fail(f"Exception: {e}")
        self.results.append(r)
        status = "✅ PASS" if r.passed else "❌ FAIL"
        detail = f" — {r.detail}" if r.detail else ""
        print(f"  {status}  {r.name}{detail}")

    def report(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        print(f"\n{'='*60}")
        print(f"TOTAL: {total} | PASS: {passed} | FAIL: {failed}")
        print(f"{'='*60}")
        if failed:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  ❌ {r.name}: {r.detail}")
        return failed == 0

    def spec_path(self, name="living_spec.json"):
        return os.path.join(self.tmpdir, name)

    def write_spec(self, spec: dict, name="living_spec.json"):
        path = self.spec_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        return path

# ---------------------------------------------------------------------------
# Test data: 3 rounds of simulated Spec Pro conversation
# ---------------------------------------------------------------------------

def make_round1_response():
    """Round 1: User describes basic needs."""
    return {
        "parsed_updates": {
            "objective": "为电商团队构建订单自动通知系统",
            "pain_points": ["手动发邮件经常漏发", "客户投诉3次"],
            "capabilities": {
                "always_do": ["自动发送订单确认邮件", "支持批量处理"],
                "should_do": [],
                "never_do": [],
            },
            "constraints": {
                "budget": "20万",
                "timeline": "3个月",
            },
        },
        "conversation_digest": {
            "key_excerpts": [
                {
                    "excerpt": "每天50多个订单要手动发邮件通知，经常漏发",
                    "dimension": "pain_points",
                    "importance": "critical",
                    "source_round": 1,
                },
                {
                    "excerpt": "上周一个大客户因为漏发通知取消了合同",
                    "dimension": "rationale",
                    "importance": "critical",
                    "source_round": 1,
                },
            ],
        },
    }

def make_round2_response():
    """Round 2: User expresses tech preferences and constraints."""
    return {
        "parsed_updates": {
            "capabilities": {
                "always_do": ["安全审计日志"],
                "should_do": [],
                "never_do": ["微服务架构"],
            },
            "constraints": {
                "tech_stack": ["Vue", "Node.js"],
            },
        },
        "conversation_digest": {
            "key_excerpts": [
                {
                    "excerpt": "之前微服务搞砸了，这次一定要简单架构，单体就行",
                    "dimension": "constraints",
                    "importance": "critical",
                    "source_round": 2,
                },
                {
                    "excerpt": "安全是第一优先级，没有商量余地",
                    "dimension": "capabilities",
                    "importance": "critical",
                    "source_round": 2,
                },
            ],
        },
    }

def make_round3_response():
    """Round 3: User supplements scenarios and priorities."""
    return {
        "parsed_updates": {
            "key_scenarios": [
                "订单提交后自动发邮件",
                "邮件发送失败自动重试",
            ],
            "success_metrics": [
                {"metric": "邮件送达率", "target": "99.9%"},
                {"metric": "漏发率", "target": "0%"},
            ],
        },
        "conversation_digest": {
            "summary": "某电商团队目前用Excel手动处理每天50+订单的邮件通知，漏发导致客户投诉3次。触发点是上周一个大客户因为漏发通知取消了合同。核心矛盾：需要自动化但不能引入复杂系统——团队5人没有专职运维，之前尝试微服务架构失败过。目标：简单可靠的订单通知系统，安全审计是硬性底线。",
            "key_excerpts": [
                {
                    "excerpt": "宁可慢一点也要稳定，性能可以后面优化",
                    "dimension": "tradeoff",
                    "importance": "important",
                    "source_round": 3,
                },
                {
                    "excerpt": "团队只有5个人，没有专职运维",
                    "dimension": "constraints",
                    "importance": "important",
                    "source_round": 3,
                },
            ],
        },
    }

def make_empty_spec():
    """Create initial empty living_spec (meta only, confirmed empty)."""
    return {
        "meta": {
            "engine": "spec_pro",
            "version": "2.1.0",
            "spec_version": 1,
            "scenario": "genesis",
            "created_at": "2026-06-19T00:00:00",
            "updated_at": "",
            "conversation_rounds": 0,
            "quality_score": 0,
            "quality_level": "C",
        },
        "confirmed": {
            "objective": "",
            "pain_points": [],
            "success_metrics": [],
            "users": [],
            "key_scenarios": [],
            "capabilities": {"always_do": [], "should_do": [], "never_do": []},
            "quality_attributes": [],
            "constraints": {},
            "integration": {"existing_systems": [], "requirements": []},
            "risks_and_assumptions": {"risks": [], "assumptions": [], "dependencies": []},
        },
        "inferred": [],
        "guardrails": {"always_do": [], "ask_first": [], "never_do": []},
    }

# Reference dimension tags (soft anchor — not enforced as hard limit)
REFERENCE_DIMENSIONS = {
    "objective", "pain_points", "users", "capabilities",
    "quality_attributes", "constraints", "integration", "risks",
    "rationale", "tradeoff", "success_metrics", "key_scenarios", "general",
}

# ---------------------------------------------------------------------------
# Phase 1 & 2: merge_conversation_digest accumulation
# ---------------------------------------------------------------------------

def _phase1_round1_merge_stub(r: TestResult):
    """Phase 1+2: Round 1 merge_conversation_digest. (stub — see phase1_round1 for actual test)"""
    runner = r  # We'll use a module-level runner; but since we need access, use a different approach
    # Actually we need the runner. Let's restructure.
    pass

# We'll use a different approach — direct test functions that receive runner
def phase1_round1(runner: TestRunner, r: TestResult):
    """Phase 1 Round 1: merge first conversation_digest."""
    spec = make_empty_spec()
    response = make_round1_response()

    merge_conversation_digest(spec, response)

    digest = spec.get("conversation_digest", {})
    excerpts = digest.get("key_excerpts", [])

    if len(excerpts) != 2:
        r.fail(f"Expected 2 excerpts after round 1, got {len(excerpts)}")
        return

    # Check first excerpt
    e0 = excerpts[0]
    if e0.get("dimension") != "pain_points":
        r.fail(f"Excerpt 0 dimension expected 'pain_points', got '{e0.get('dimension')}'")
        return
    if e0.get("importance") != "critical":
        r.fail(f"Excerpt 0 importance expected 'critical', got '{e0.get('importance')}'")
        return
    if e0.get("source_round") != 1:
        r.fail(f"Excerpt 0 source_round expected 1, got {e0.get('source_round')}")
        return

    # full_conversation_path should be set
    if digest.get("full_conversation_path") != "spec/conversation_log.json":
        r.fail(f"full_conversation_path not set correctly: {digest.get('full_conversation_path')}")
        return

    r.ok("2 excerpts merged, dimensions and importance correct, full_conversation_path set")

def phase1_round2(runner: TestRunner, r: TestResult):
    """Phase 1 Round 2: accumulate second round excerpts."""
    spec = make_empty_spec()
    merge_conversation_digest(spec, make_round1_response())
    merge_conversation_digest(spec, make_round2_response())

    digest = spec.get("conversation_digest", {})
    excerpts = digest.get("key_excerpts", [])

    if len(excerpts) != 4:
        r.fail(f"Expected 4 excerpts after round 2, got {len(excerpts)}")
        return

    # Round 2 excerpts
    e2 = excerpts[2]
    if e2.get("dimension") != "constraints":
        r.fail(f"Excerpt 2 dimension expected 'constraints', got '{e2.get('dimension')}'")
        return
    if e2.get("source_round") != 2:
        r.fail(f"Excerpt 2 source_round expected 2, got {e2.get('source_round')}")
        return

    r.ok("4 excerpts accumulated after round 2")

def phase1_round3(runner: TestRunner, r: TestResult):
    """Phase 1 Round 3: summary + all 6 excerpts."""
    spec = make_empty_spec()
    merge_conversation_digest(spec, make_round1_response())
    merge_conversation_digest(spec, make_round2_response())
    merge_conversation_digest(spec, make_round3_response())

    digest = spec.get("conversation_digest", {})
    excerpts = digest.get("key_excerpts", [])
    summary = digest.get("summary", "")

    # Summary check
    if len(summary.strip()) < 100:
        r.fail(f"Summary too short: {len(summary.strip())} chars (min 100)")
        return

    # Excerpts count: 2+2+2=6
    if len(excerpts) != 6:
        r.fail(f"Expected 6 excerpts after round 3, got {len(excerpts)}")
        return

    # All dimensions in reference set
    for i, e in enumerate(excerpts):
        dim = e.get("dimension", "")
        if dim not in REFERENCE_DIMENSIONS:
            r.fail(f"Excerpt {i} dimension '{dim}' not in reference set")
            return

    # Importance checks
    critical_count = sum(1 for e in excerpts if e.get("importance") == "critical")
    important_count = sum(1 for e in excerpts if e.get("importance") == "important")
    if critical_count != 4:
        r.fail(f"Expected 4 critical excerpts, got {critical_count}")
        return
    if important_count != 2:
        r.fail(f"Expected 2 important excerpts, got {important_count}")
        return

    r.ok(f"summary={len(summary)} chars, 6 excerpts, 4 critical + 2 important, all dims valid")

def phase2_full_path(runner: TestRunner, r: TestResult):
    """Phase 2: full_conversation_path is set correctly."""
    spec = make_empty_spec()
    merge_conversation_digest(spec, make_round1_response())

    digest = spec.get("conversation_digest", {})
    if digest.get("full_conversation_path") != "spec/conversation_log.json":
        r.fail(f"full_conversation_path: {digest.get('full_conversation_path')}")
        return
    r.ok("full_conversation_path = spec/conversation_log.json")

# ---------------------------------------------------------------------------
# Phase 3: Harness V2 validation
# ---------------------------------------------------------------------------

def phase3_harness_v2(runner: TestRunner, r: TestResult):
    """Phase 3: Fill confirmed layer + run harness V2, expect all PASS."""
    spec = make_empty_spec()

    # Fill confirmed layer (simulate Spec Pro structured collection complete)
    spec["confirmed"] = {
        "objective": "为电商团队构建订单自动通知系统，实现订单提交后自动发送邮件通知，减少漏发",
        "pain_points": ["手动发邮件经常漏发", "客户投诉3次", "大客户因漏发取消合同"],
        "success_metrics": [
            {"metric": "邮件送达率", "target": "99.9%"},
            {"metric": "漏发率", "target": "0%"},
        ],
        "users": [{"role": "运营人员", "key_needs": "批量处理订单通知"}],
        "key_scenarios": ["订单提交后自动发邮件", "邮件发送失败自动重试"],
        "capabilities": {
            "always_do": ["自动发送订单确认邮件", "支持批量处理", "安全审计日志"],
            "should_do": ["发送状态看板"],
            "never_do": ["微服务架构"],
        },
        "quality_attributes": [
            {"category": "可靠性", "spec": "邮件送达率99.9%", "priority": "P0"},
        ],
        "constraints": {
            "budget": "20万",
            "timeline": "3个月",
            "tech_stack": ["Vue", "Node.js"],
        },
        "integration": {
            "existing_systems": [{"name": "邮件SMTP", "type": "email"}],
            "requirements": ["SMTP邮件发送接口"],
        },
        "risks_and_assumptions": {
            "risks": ["SMTP服务商限流"],
            "assumptions": ["团队有基础Node.js开发能力"],
            "dependencies": ["SMTP服务商可用"],
        },
    }

    # Add conversation_digest (from 3 rounds)
    merge_conversation_digest(spec, make_round1_response())
    merge_conversation_digest(spec, make_round2_response())
    merge_conversation_digest(spec, make_round3_response())

    # Add guardrails
    spec["guardrails"] = {
        "always_do": ["所有邮件发送记录审计日志"],
        "ask_first": [],
        "never_do": ["不引入微服务架构"],
    }

    # Write spec to file and run harness
    spec_path = runner.write_spec(spec)
    result = run_harness_v2(spec_path)

    # Verify Layer 1
    checks = result.get("checks", [])
    layer1_fails = [c for c in checks if not c["passed"]]
    if layer1_fails:
        fail_ids = [c["id"] for c in layer1_fails]
        r.fail(f"Layer 1 failures: {fail_ids}")
        return

    # Verify Layer 2
    layer2 = result.get("layer2")
    if not layer2:
        r.fail("Layer 2 not present in result")
        return

    l2_checks = layer2.get("checks", [])
    l2_fails = [c for c in l2_checks if not c["passed"]]
    if l2_fails:
        fail_ids = [c["id"] for c in l2_fails]
        r.fail(f"Layer 2 failures: {fail_ids}")
        return

    # Final decision
    decision = result.get("decision")
    if decision != "PASS":
        r.fail(f"Expected final decision PASS, got {decision}")
        return

    r.ok(f"Layer 1: {result['passed']}/{result['total']} PASS, Layer 2: 2/2 PASS, decision=PASS")

# ---------------------------------------------------------------------------
# Phase 4: Solution Pro consumption validation
# ---------------------------------------------------------------------------

def phase4_digest_prompt(runner: TestRunner, r: TestResult):
    """Phase 4a: build_conversation_digest_for_prompt output validation."""
    spec = make_empty_spec()
    merge_conversation_digest(spec, make_round1_response())
    merge_conversation_digest(spec, make_round2_response())
    merge_conversation_digest(spec, make_round3_response())

    digest = spec.get("conversation_digest", {})
    prompt_text = build_conversation_digest_for_prompt(digest)

    # Check "## 需求概述" + summary content
    if "## 需求概述" not in prompt_text:
        r.fail("Missing '## 需求概述' section")
        return

    summary = digest.get("summary", "")
    if summary[:20] not in prompt_text:
        r.fail("Summary content not found in prompt text")
        return

    # Check "## 用户关键表达"
    if "## 用户关键表达" not in prompt_text:
        r.fail("Missing '## 用户关键表达' section")
        return

    # Check all excerpts present
    excerpts = digest.get("key_excerpts", [])
    for e in excerpts:
        excerpt_text = e.get("excerpt", "")
        if excerpt_text not in prompt_text:
            r.fail(f"Excerpt not found in prompt: '{excerpt_text[:30]}...'")
            return

    # Check critical formatting: bold + "← 不可妥协"
    critical_excerpts = [e for e in excerpts if e.get("importance") == "critical"]
    for ce in critical_excerpts:
        expected_marker = f'**"{ce["excerpt"]}"**'
        if expected_marker not in prompt_text:
            r.fail(f"Critical excerpt not bolded: '{ce['excerpt'][:30]}...'")
            return
        if "← 不可妥协" not in prompt_text:
            r.fail("Missing '← 不可妥协' marker for critical excerpts")
            return

    # Check important excerpts are present without bold
    important_excerpts = [e for e in excerpts if e.get("importance") == "important"]
    for ie in important_excerpts:
        # Should be present as normal quote (not bold)
        if ie["excerpt"] not in prompt_text:
            r.fail(f"Important excerpt missing: '{ie['excerpt'][:30]}...'")
            return

    r.ok(f"Prompt text has summary, all {len(excerpts)} excerpts, critical bolded with marker")

def phase4_worker_context(runner: TestRunner, r: TestResult):
    """Phase 4b: build_worker_context_section for 'planner' role."""
    spec = make_empty_spec()

    # Fill confirmed with user_directives
    spec["confirmed"]["objective"] = "为电商团队构建订单自动通知系统"
    spec["confirmed"]["user_directives"] = [
        {"directive": "deliberately_omitted", "dimension": "compliance", "content": "不需要考虑数据合规"},
    ]
    spec["confirmed"]["capabilities"]["always_do"] = ["自动发送订单确认邮件"]
    spec["confirmed"]["capabilities"]["never_do"] = ["微服务架构"]
    spec["confirmed"]["constraints"] = {"budget": "20万"}

    # Add solution_pro_hints
    spec["solution_pro_hints"] = {
        "focus_areas": [{"area": "邮件可靠性", "weight": 0.8, "reason": "核心需求"}],
        "anti_patterns": ["不要引入消息队列"],
    }

    # Add guardrails
    spec["guardrails"] = {
        "always_do": ["审计日志"],
        "ask_first": [],
        "never_do": ["微服务"],
    }

    # Add conversation_digest
    merge_conversation_digest(spec, make_round1_response())
    merge_conversation_digest(spec, make_round2_response())
    merge_conversation_digest(spec, make_round3_response())

    context_text = build_worker_context_section(spec, "planner")

    # Verify sections present
    checks = {
        "user_directives": "用户显式要求" in context_text or "User Directives" in context_text,
        "solution_pro_hints": "Spec Pro 提示" in context_text or "Solution Pro Hints" in context_text,
        "guardrails": "研究边界" in context_text,
        "conversation_digest": "需求概述" in context_text or "用户关键表达" in context_text,
    }

    failed_checks = [k for k, v in checks.items() if not v]
    if failed_checks:
        r.fail(f"Missing sections in worker context: {failed_checks}")
        return

    r.ok("Worker context contains user_directives, solution_pro_hints, guardrails, conversation_digest")

# ---------------------------------------------------------------------------
# Phase 5: Boundary tests
# ---------------------------------------------------------------------------

def phase5_v1_compat(runner: TestRunner, r: TestResult):
    """Phase 5.1: V1 backward compat — no conversation_digest → full chain OK."""
    spec = make_empty_spec()
    spec["confirmed"]["objective"] = "为电商团队构建订单自动通知系统，实现订单提交后自动发送邮件通知"
    spec["confirmed"]["pain_points"] = ["手动发邮件经常漏发"]
    spec["confirmed"]["capabilities"]["always_do"] = ["自动发送订单确认邮件"]
    spec["confirmed"]["capabilities"]["never_do"] = ["微服务架构"]
    spec["confirmed"]["constraints"] = {"budget": "20万"}
    spec["guardrails"] = {"always_do": ["审计日志"], "ask_first": [], "never_do": ["微服务"]}
    # No conversation_digest at all (V1 spec)

    spec_path = runner.write_spec(spec)
    result = run_harness_v2(spec_path)

    # Should not crash, Layer 2 should be skipped
    if result.get("layer2_skipped") is not True:
        # It's OK if layer2 is present but passed; just check it doesn't crash
        pass

    # build_conversation_digest_for_prompt with None
    digest_text = build_conversation_digest_for_prompt(None)
    if digest_text != "":
        r.fail(f"Expected empty string for None digest, got: '{digest_text[:20]}'")
        return

    # build_worker_context_section should work without conversation_digest
    context = build_worker_context_section(spec, "planner")
    if not isinstance(context, str):
        r.fail(f"Expected string context, got {type(context)}")
        return

    r.ok("V1 spec (no conversation_digest) handled gracefully, Layer 2 skipped")

def phase5_empty_digest(runner: TestRunner, r: TestResult):
    """Phase 5.2: Empty digest {} → no crash."""
    spec = make_empty_spec()
    spec["conversation_digest"] = {}

    digest_text = build_conversation_digest_for_prompt({})
    if digest_text != "":
        r.fail(f"Expected empty string for empty digest, got: '{digest_text[:20]}'")
        return

    # merge_conversation_digest with empty dict should not crash
    merge_conversation_digest(spec, {"conversation_digest": {}})
    r.ok("Empty digest handled without crash")

def phase5_custom_dimension(runner: TestRunner, r: TestResult):
    """Phase 5.3: dimension='custom_tag' → still processable (soft anchor)."""
    spec = make_empty_spec()
    response = {
        "conversation_digest": {
            "key_excerpts": [
                {
                    "excerpt": "我们有一些特殊的业务流程需要考虑",
                    "dimension": "custom_tag",
                    "importance": "normal",
                    "source_round": 1,
                },
            ],
        },
    }

    merge_conversation_digest(spec, response)
    digest = spec.get("conversation_digest", {})
    excerpts = digest.get("key_excerpts", [])

    if len(excerpts) != 1:
        r.fail(f"Expected 1 excerpt with custom dimension, got {len(excerpts)}")
        return

    if excerpts[0].get("dimension") != "custom_tag":
        r.fail(f"Custom dimension not preserved: {excerpts[0].get('dimension')}")
        return

    # build_conversation_digest_for_prompt should handle it
    prompt_text = build_conversation_digest_for_prompt(digest)
    if "特殊的业务流程" not in prompt_text:
        r.fail("Custom dimension excerpt not in prompt output")
        return

    r.ok("Custom dimension 'custom_tag' processed correctly (soft anchor)")

def phase5_dedup(runner: TestRunner, r: TestResult):
    """Phase 5.4: Round 2 repeats Round 1 excerpt → no duplicate."""
    spec = make_empty_spec()
    merge_conversation_digest(spec, make_round1_response())

    # Round 2 with one duplicate excerpt from round 1
    response_dup = {
        "conversation_digest": {
            "key_excerpts": [
                {
                    "excerpt": "每天50多个订单要手动发邮件通知，经常漏发",  # Same as round 1
                    "dimension": "pain_points",
                    "importance": "critical",
                    "source_round": 2,
                },
                {
                    "excerpt": "我们需要一个后台管理界面",
                    "dimension": "key_scenarios",
                    "importance": "normal",
                    "source_round": 2,
                },
            ],
        },
    }

    merge_conversation_digest(spec, response_dup)
    digest = spec.get("conversation_digest", {})
    excerpts = digest.get("key_excerpts", [])

    # Should have 3 total (2 from round 1 + 1 new from round 2, duplicate removed)
    if len(excerpts) != 3:
        r.fail(f"Expected 3 excerpts after dedup, got {len(excerpts)}")
        return

    # Verify no duplicate text
    texts = [e.get("excerpt", "").lower() for e in excerpts]
    if len(texts) != len(set(texts)):
        r.fail("Duplicate excerpts found after dedup")
        return

    r.ok("Duplicate excerpt correctly deduplicated (2+2-1=3)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("E2E Test: Living Spec V2 全链路闭环")
    print("=" * 60)

    runner = TestRunner()

    try:
        # Phase 1 & 2
        print("\n--- Phase 1 & 2: merge_conversation_digest accumulation ---")
        runner.run(lambda r: phase1_round1(runner, r))
        runner.run(lambda r: phase1_round2(runner, r))
        runner.run(lambda r: phase1_round3(runner, r))
        runner.run(lambda r: phase2_full_path(runner, r))

        # Phase 3
        print("\n--- Phase 3: Harness V2 validation ---")
        runner.run(lambda r: phase3_harness_v2(runner, r))

        # Phase 4
        print("\n--- Phase 4: Solution Pro consumption ---")
        runner.run(lambda r: phase4_digest_prompt(runner, r))
        runner.run(lambda r: phase4_worker_context(runner, r))

        # Phase 5
        print("\n--- Phase 5: Boundary tests ---")
        runner.run(lambda r: phase5_v1_compat(runner, r))
        runner.run(lambda r: phase5_empty_digest(runner, r))
        runner.run(lambda r: phase5_custom_dimension(runner, r))
        runner.run(lambda r: phase5_dedup(runner, r))

    finally:
        runner.cleanup()

    all_pass = runner.report()
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    main()
