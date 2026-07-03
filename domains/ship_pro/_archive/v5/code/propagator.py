"""
P2-2 Constraint Propagator - 约束传播器（纯代码，不用 LLM）

从 blueprint 的原则/SLA/平台能力推导到 WP 级约束。
确定性规则映射，100% 可预测。
"""
from typing import Dict, List, Any


def propagate_constraints(blueprint: dict) -> Dict[str, Dict[str, Any]]:
    """
    输入: blueprint.json (Phase 1 输出)
    输出: {wp_id: {serving_principles, sla_thresholds, platform_requirements}}
    """
    wp_constraints: Dict[str, Dict[str, Any]] = {}

    work_packages = blueprint.get("work_packages", [])
    principles = blueprint.get("architecture_principles", [])
    sla_constraints = blueprint.get("sla_constraints", [])
    platform_capabilities = blueprint.get("platform_capabilities", [])

    for wp in work_packages:
        wp_id = wp.get("id", "UNKNOWN")
        source_modules = set(wp.get("source_modules", []))

        constraints: Dict[str, Any] = {
            "serving_principles": [],
            "sla_thresholds": [],
            "platform_requirements": [],
        }

        # 原则 → WP serving_principles
        for principle in principles:
            covered_by = set(principle.get("covered_by_modules", []))
            # 也检查 principle_coverage 格式
            if not covered_by:
                for cov in blueprint.get("principle_coverage", []):
                    if cov.get("principle_id") == principle.get("id"):
                        covered_by = set(cov.get("covered_by_modules", []))

            if source_modules & covered_by:
                constraints["serving_principles"].append({
                    "principle_id": principle.get("id", ""),
                    "name": principle.get("name", ""),
                    "type": principle.get("type", ""),
                    "severity": principle.get("severity", ""),
                    "obligation": f"本 WP 必须遵守: {principle.get('description', '')}",
                    "anti_patterns": principle.get("anti_patterns", []),
                })

        # SLA → AC 数值阈值
        for sla in sla_constraints:
            affected = set(sla.get("affected_modules", []))
            if not affected:
                # 如果没有 affected_modules，检查 mapped_components
                affected = set(sla.get("mapped_components", []))
            if not affected:
                # 如果仍然为空，检查是否全局约束
                if sla.get("scope") == "global":
                    affected = source_modules

            if source_modules & affected or not affected:
                constraints["sla_thresholds"].append({
                    "metric": sla.get("metric", ""),
                    "threshold": sla.get("threshold", ""),
                    "operator": sla.get("operator", ">="),
                    "unit": sla.get("unit", ""),
                    "description": sla.get("description", ""),
                })

        # 平台能力 → WP constraints
        for cap in platform_capabilities:
            reused_by = set(cap.get("reused_by_modules", []))
            if not reused_by:
                for reuse in blueprint.get("platform_reuse_map", []):
                    if reuse.get("platform_capability") == cap.get("capability"):
                        reused_by = set(reuse.get("reused_by_modules", []))

            if source_modules & reused_by:
                constraints["platform_requirements"].append({
                    "platform": cap.get("platform", ""),
                    "capability": cap.get("capability", ""),
                    "api": cap.get("api", ""),
                    "replaces": cap.get("replaces", []),
                    "must_use": cap.get("must_use", False),
                })

        wp_constraints[wp_id] = constraints

    return wp_constraints


if __name__ == "__main__":
    # 测试用例
    test_blueprint = {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "OTel Agent Collector",
                "source_modules": ["COMP-001", "COMP-002"],
                "dependencies": [],
                "priority": "high",
            },
            {
                "id": "WP-002",
                "title": "Kafka Cluster",
                "source_modules": ["COMP-003"],
                "dependencies": ["WP-001"],
                "priority": "high",
            },
        ],
        "architecture_principles": [
            {
                "id": "PRINCIPLE-001",
                "name": "OTel Compliance",
                "type": "must_do",
                "severity": "BLOCKER",
                "description": "100% 通过 OTel 官方 compliance check",
                "anti_patterns": ["自定义 trace format", "非标准 span 属性"],
                "covered_by_modules": ["COMP-001", "COMP-002"],
            },
        ],
        "sla_constraints": [
            {
                "metric": "throughput",
                "threshold": 500000,
                "operator": ">=",
                "unit": "TPS",
                "affected_modules": ["COMP-003"],
                "description": "Kafka 突发写入吞吐 ≥ 500k TPS",
            },
        ],
        "platform_capabilities": [
            {
                "platform": "AWS",
                "capability": "MSK",
                "api": "aws msk create-cluster",
                "replaces": ["自建 Kafka"],
                "must_use": True,
                "reused_by_modules": ["COMP-003"],
            },
        ],
        "principle_coverage": [],
        "platform_reuse_map": [],
    }

    result = propagate_constraints(test_blueprint)

    print("=== Propagator 测试 ===")
    for wp_id, constraints in result.items():
        print(f"\n{wp_id}:")
        print(f"  原则: {len(constraints['serving_principles'])} 条")
        for p in constraints["serving_principles"]:
            print(f"    - {p['principle_id']}: {p['obligation'][:50]}...")
        print(f"  SLA: {len(constraints['sla_thresholds'])} 条")
        for s in constraints["sla_thresholds"]:
            print(f"    - {s['metric']} {s['operator']} {s['threshold']} {s['unit']}")
        print(f"  平台: {len(constraints['platform_requirements'])} 条")
        for p in constraints["platform_requirements"]:
            print(f"    - {p['platform']}/{p['capability']} (must_use={p['must_use']})")

    # 验证
    assert len(result["WP-001"]["serving_principles"]) == 1, "WP-001 应有 1 条原则"
    assert len(result["WP-002"]["sla_thresholds"]) == 1, "WP-002 应有 1 条 SLA"
    assert len(result["WP-002"]["platform_requirements"]) == 1, "WP-002 应有 1 条平台约束"
    assert result["WP-001"]["platform_requirements"] == [], "WP-001 不应有平台约束"
    print("\n✅ 所有测试通过")
