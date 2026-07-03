"""
原则对齐回归测试 — 使用 OpenClaw AI Native Loop 案例

测试目标:
1. Spec Pro final_result 包含 architecture_principles 和 platform_capabilities
2. Ship Pro Architect 输出包含 principle_coverage 和 platform_reuse_map
3. gate_principle_alignment 能检测出原则未覆盖
4. gate_platform_coverage 能检测出平台能力未复用
5. Reviewer 输出包含 principle_audit 和 platform_audit
"""

import json
import sys
from pathlib import Path

# Ensure .deepflow is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from domains.ship_pro.contracts.architect import ArchitectOutput
from domains.ship_pro.contracts.reviewer import ReviewerOutput
from domains.ship_pro.contracts.principles import (
    ArchitecturePrinciple,
    PlatformCapability,
    PrincipleCoverage,
    PlatformReuseEntry,
    PrincipleAuditEntry,
    PlatformAuditEntry,
)
from domains.ship_pro.eval.gates import (
    gate_architect,
    gate_reviewer,
    gate_principle_alignment,
    gate_platform_coverage,
)


def test_architect_contract_with_principles():
    """测试 Architect 契约包含原则字段"""

    architect_data = {
        "_meta": {
            "agent": "architect",
            "input_format": "A",
            "overall_confidence": "high",
            "data_sufficiency": {
                "modules": "sufficient",
                "dependencies": "sufficient",
                "requirements": "sufficient",
                "risks": "sufficient",
            },
        },
        "project_type": "multi_agent",
        "project": {
            "name": "Test Project",
            "objective": "Test objective",
            "problem_statement": "Test problem",
        },
        "modules": [
            {
                "id": "COMP-001",
                "name": "Test Module",
                "summary": "Test summary",
                "responsibilities": ["resp1"],
                "technology_stack": ["tech1"],
                "is_infrastructure": True,
            }
        ],
        "dependencies": [],
        "requirements": [
            {
                "req_id": "REQ-001",
                "description": "Test requirement",
                "priority": "P0",
                "coverage": "covered",
                "mapped_components": ["COMP-001"],
            }
        ],
        "architecture_principles": [
            {
                "id": "PRINCIPLE-001",
                "name": "全 LLM 控制",
                "type": "must_do",
                "description": "所有决策模块必须由 LLM 驱动",
                "anti_patterns": ["硬编码 if/else"],
                "verification_method": "代码审查",
                "severity": "BLOCKER",
            }
        ],
        "platform_capabilities": [
            {
                "platform": "OpenClaw",
                "capability": "子 Agent 调度",
                "api": "sessions_spawn",
                "replaces": ["自建 Worker Pool"],
                "must_use": True,
                "rationale": "OpenClaw 已有能力",
            }
        ],
        "principle_coverage": [
            {
                "principle_id": "PRINCIPLE-001",
                "covered_by_modules": ["COMP-001"],
                "coverage_method": "通过 LLM API 实现",
                "gap_analysis": "",
            }
        ],
        "platform_reuse_map": [
            {
                "platform_capability": "子 Agent 调度",
                "reused_by_modules": ["COMP-001"],
                "not_reused_rationale": "",
            }
        ],
    }

    validated = ArchitectOutput(**architect_data)
    assert len(validated.architecture_principles) == 1
    assert validated.architecture_principles[0].id == "PRINCIPLE-001"
    assert len(validated.platform_capabilities) == 1
    assert len(validated.principle_coverage) == 1
    assert len(validated.platform_reuse_map) == 1


def test_gate_principle_alignment_pass():
    """测试 gate_principle_alignment 通过场景"""

    architect_output = {
        "architecture_principles": [
            {
                "id": "PRINCIPLE-001",
                "name": "Test Principle",
                "type": "must_do",
                "description": "Test",
                "anti_patterns": [],
                "verification_method": "Test",
                "severity": "BLOCKER",
            }
        ],
        "platform_capabilities": [
            {
                "platform": "OpenClaw",
                "capability": "Test Capability",
                "api": "test_api",
                "replaces": [],
                "must_use": True,
                "rationale": "Test",
            }
        ],
        "principle_coverage": [
            {
                "principle_id": "PRINCIPLE-001",
                "covered_by_modules": ["COMP-001"],
                "coverage_method": "Test",
                "gap_analysis": "",
            }
        ],
        "platform_reuse_map": [
            {
                "platform_capability": "Test Capability",
                "reused_by_modules": ["COMP-001"],
                "not_reused_rationale": "",
            }
        ],
    }

    result = gate_principle_alignment(architect_output)
    assert result["passed"] is True
    assert result["decision"] == "PASS"


def test_gate_principle_alignment_fail():
    """测试 gate_principle_alignment 失败场景（原则未覆盖）"""

    architect_output = {
        "architecture_principles": [
            {
                "id": "PRINCIPLE-001",
                "name": "Test Principle",
                "type": "must_do",
                "description": "Test",
                "anti_patterns": [],
                "verification_method": "Test",
                "severity": "BLOCKER",
            }
        ],
        "platform_capabilities": [],
        "principle_coverage": [],
        "platform_reuse_map": [],
    }

    result = gate_principle_alignment(architect_output)
    assert result["passed"] is False
    assert result["decision"] == "FAIL"
    assert not result["critical_results"]["all_blockers_covered"]


def test_gate_platform_coverage_fail():
    """测试 gate_platform_coverage 失败场景（平台能力未在 AC 中体现）"""

    specifier_output = {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "Test WP",
                "acceptance_criteria": [
                    "Given X, When Y, Then Z"
                ],
            }
        ]
    }

    architect_output = {
        "platform_capabilities": [
            {
                "platform": "OpenClaw",
                "capability": "子 Agent 调度",
                "api": "sessions_spawn",
                "replaces": [],
                "must_use": True,
                "rationale": "Test",
            }
        ],
        "platform_reuse_map": [],
    }

    result = gate_platform_coverage(specifier_output, architect_output)
    assert result["passed"] is False
    assert result["decision"] == "FAIL"
    assert not result["critical_results"]["must_use_in_ac"]


def test_reviewer_contract_with_audit():
    """测试 Reviewer 契约包含审计字段"""

    reviewer_data = {
        "verdict": "PASS_WITH_CONDITIONS",
        "issues": [],
        "quality_metrics": {
            "ac_verifiability_score": 85.0,
            "coverage_rate": 0.9,
            "dependency_sanity": "ok",
        },
        "summary": "Test summary",
        "round": 1,
        "principle_audit": [
            {
                "principle_id": "PRINCIPLE-001",
                "principle_name": "Test Principle",
                "wp_coverage": {"WP-001": "✅ PASS"},
                "overall_status": "PASS",
                "action_required": "",
            }
        ],
        "platform_audit": [
            {
                "platform_capability": "Test Capability",
                "api": "test_api",
                "wp_status": {"WP-001": "✅ PASS"},
                "overall_status": "PASS",
                "violation_description": "",
            }
        ],
    }

    validated = ReviewerOutput(**reviewer_data)
    assert len(validated.principle_audit) == 1
    assert validated.principle_audit[0].overall_status == "PASS"
    assert len(validated.platform_audit) == 1


def test_backward_compatibility():
    """测试向后兼容：旧数据（无新字段）仍能通过验证"""

    old_architect_data = {
        "_meta": {
            "agent": "architect",
            "input_format": "A",
            "overall_confidence": "high",
            "data_sufficiency": {
                "modules": "sufficient",
                "dependencies": "sufficient",
                "requirements": "sufficient",
                "risks": "sufficient",
            },
        },
        "project_type": "web_app",
        "project": {
            "name": "Old Project",
            "objective": "Old objective",
            "problem_statement": "Old problem",
        },
        "modules": [
            {
                "id": "COMP-001",
                "name": "Old Module",
                "summary": "Old summary",
            }
        ],
        "requirements": [
            {
                "req_id": "REQ-001",
                "description": "Old requirement",
                "priority": "P0",
                "coverage": "covered",
                "mapped_components": ["COMP-001"],
            }
        ],
    }

    validated = ArchitectOutput(**old_architect_data)
    assert validated.architecture_principles == []
    assert validated.platform_capabilities == []
    assert validated.principle_coverage == []
    assert validated.platform_reuse_map == []

    old_reviewer_data = {
        "verdict": "PASS",
        "issues": [],
        "quality_metrics": {
            "ac_verifiability_score": 90.0,
            "coverage_rate": 0.95,
            "dependency_sanity": "ok",
        },
        "summary": "Old summary",
    }

    validated_r = ReviewerOutput(**old_reviewer_data)
    assert validated_r.principle_audit == []
    assert validated_r.platform_audit == []


def test_regression_old_case_still_passes_gate():
    """
    回归测试：用原始 OpenClaw AI Native Loop 的 Architect 数据
    （不含新字段），gate_architect 应该仍然 PASS（向后兼容）。
    """
    old_blueprint = {
        "_meta": {
            "agent": "architect",
            "input_format": "A",
            "overall_confidence": "high",
            "data_sufficiency": {
                "modules": "sufficient",
                "dependencies": "sufficient",
                "requirements": "sufficient",
                "risks": "sufficient",
            },
        },
        "project_type": "multi_agent",
        "project": {
            "name": "OpenClaw AI Native Loop",
            "objective": "Build AI Native Loop",
            "problem_statement": "Long-running agent",
        },
        "modules": [
            {"id": "COMP-001", "name": "LLMScheduler", "summary": "LLM scheduling"},
        ],
        "dependencies": [],
        "requirements": [
            {
                "req_id": "REQ-001",
                "description": "Core requirement",
                "priority": "P0",
                "coverage": "covered",
                "mapped_components": ["COMP-001"],
            }
        ],
    }

    result = gate_architect(old_blueprint)
    assert result["passed"] is True, "Old data without new fields should still pass"


if __name__ == "__main__":
    tests = [
        ("test_architect_contract_with_principles", test_architect_contract_with_principles),
        ("test_gate_principle_alignment_pass", test_gate_principle_alignment_pass),
        ("test_gate_principle_alignment_fail", test_gate_principle_alignment_fail),
        ("test_gate_platform_coverage_fail", test_gate_platform_coverage_fail),
        ("test_reviewer_contract_with_audit", test_reviewer_contract_with_audit),
        ("test_backward_compatibility", test_backward_compatibility),
        ("test_regression_old_case_still_passes_gate", test_regression_old_case_still_passes_gate),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"✅ {name}")
            passed += 1
        except Exception as e:
            print(f"❌ {name}: {e}")
            failed += 1

    print(f"\n{'🎉 All tests passed!' if failed == 0 else f'💥 {failed} test(s) failed'}")
    print(f"Results: {passed}/{passed + failed} passed")
    sys.exit(0 if failed == 0 else 1)
