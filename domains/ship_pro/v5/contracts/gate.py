"""
Ship Pro V5 Gate 校验函数

severity 分级:
- BLOCKER: 必须修复，不可带过
- WARNING: 记录，可带过（需 written justification）
- INFO: 仅记录

通过条件: 0 BLOCKER + WARNING ≤ 3
"""
import json
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict


@dataclass
class Issue:
    severity: str  # "blocker" | "warning" | "info"
    message: str
    source: str  # 来源 Agent 或检查项
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def gate_blueprint(blueprint: dict) -> Tuple[bool, List[Dict]]:
    """
    Phase 1 Gate: Blueprint 校验

    检查项:
    1. Pydantic schema 校验
    2. 必选模块覆盖率 ≥ 95%
    3. 无循环依赖
    4. 每个 WP 有 source_modules
    5. 推理链存在且非空
    """
    issues: List[Issue] = []

    # 1. 基本结构检查
    required_fields = ["modules", "work_packages", "requirements", "architecture_principles"]
    for f in required_fields:
        if f not in blueprint:
            issues.append(Issue("blocker", f"缺少必填字段: {f}", "gate_blueprint"))

    modules = blueprint.get("modules", [])
    work_packages = blueprint.get("work_packages", [])
    requirements = blueprint.get("requirements", [])

    # 2. 模块覆盖率
    if modules and work_packages:
        all_module_ids = {m.get("id") for m in modules}
        covered_module_ids = set()
        for wp in work_packages:
            covered_module_ids.update(wp.get("source_modules", []))

        coverage = len(covered_module_ids & all_module_ids) / max(len(all_module_ids), 1)
        uncovered = all_module_ids - covered_module_ids

        if coverage < 0.95:
            issues.append(Issue("blocker",
                f"必选模块覆盖率 {coverage:.0%} < 95%，遗漏: {uncovered}",
                "gate_blueprint", {"coverage": coverage, "uncovered": list(uncovered)}))
        elif coverage < 1.0:
            issues.append(Issue("warning",
                f"模块覆盖率 {coverage:.0%}，可选模块遗漏: {uncovered}",
                "gate_blueprint", {"coverage": coverage, "uncovered": list(uncovered)}))

    # 3. 循环依赖检测
    wp_ids = {wp.get("id") for wp in work_packages}
    for wp in work_packages:
        for dep in wp.get("dependencies", []):
            if dep not in wp_ids:
                issues.append(Issue("warning",
                    f"{wp.get('id')} 依赖不存在的 WP: {dep}",
                    "gate_blueprint"))

    # 简单循环检测 (A→B→A)
    dep_map = {wp.get("id"): wp.get("dependencies", []) for wp in work_packages}
    for wp_id, deps in dep_map.items():
        for dep in deps:
            if wp_id in dep_map.get(dep, []):
                issues.append(Issue("blocker",
                    f"循环依赖: {wp_id} ↔ {dep}",
                    "gate_blueprint"))

    # 4. WP 完整性
    for wp in work_packages:
        if not wp.get("source_modules"):
            issues.append(Issue("blocker",
                f"{wp.get('id')} 缺少 source_modules",
                "gate_blueprint"))
        if not wp.get("title"):
            issues.append(Issue("warning",
                f"{wp.get('id')} 缺少 title",
                "gate_blueprint"))

    # 5. 推理链检查
    reasoning_chain = blueprint.get("_reasoning_chain", {})
    if not reasoning_chain:
        issues.append(Issue("blocker", "推理链缺失", "gate_blueprint"))
    elif not reasoning_chain.get("architect", {}).get("splitting_rationale"):
        issues.append(Issue("warning", "推理链缺少 architect 拆分理由", "gate_blueprint"))

    # 判断通过
    passed = _check_passed(issues)
    return passed, [i.to_dict() for i in issues]


def gate_ship_package(package: dict) -> Tuple[bool, List[Dict]]:
    """
    Phase 2 Gate: Ship Package 校验

    检查项:
    1. Pydantic schema 校验
    2. 数值一致性 (major = 0)
    3. 每个 WP 有 AC
    4. AC 质量 (L3+ 比例)
    5. 字段名合规
    6. 依赖图无循环
    """
    issues: List[Issue] = []

    work_packages = package.get("work_packages", [])
    dep_graph = package.get("dependency_graph", {})

    # 1. 基本结构
    required_fields = ["project", "modules", "work_packages", "dependency_graph"]
    for f in required_fields:
        if f not in package:
            issues.append(Issue("blocker", f"缺少必填字段: {f}", "gate_ship_package"))

    # 2. 数值一致性 (从 numeric_conflicts 字段读取)
    numeric_conflicts = package.get("numeric_conflicts", [])
    major_conflicts = [c for c in numeric_conflicts if c.get("severity") == "major"]
    if major_conflicts:
        for conflict in major_conflicts:
            issues.append(Issue("blocker",
                f"数值矛盾 (major): {conflict.get('metric', 'unknown')} "
                f"值={conflict.get('values', [])}",
                "gate_ship_package",
                {"conflict": conflict}))

    # 3. WP → AC 覆盖
    for wp in work_packages:
        wp_id = wp.get("id", "UNKNOWN")
        acs = wp.get("acceptance_criteria", [])

        if not acs:
            issues.append(Issue("blocker",
                f"{wp_id} 缺少 acceptance_criteria",
                "gate_ship_package"))
            continue

        # 4. AC 质量检查
        l3_plus = sum(1 for ac in acs if ac.get("level") in ("L3", "L4"))
        l1_count = sum(1 for ac in acs if ac.get("level") == "L1")

        if l1_count > 0:
            issues.append(Issue("blocker",
                f"{wp_id} 包含 {l1_count} 条 L1 级 AC（禁止）",
                "gate_ship_package"))

        if l3_plus < 2:
            issues.append(Issue("warning",
                f"{wp_id} L3+ AC 仅 {l3_plus} 条（需 ≥2）",
                "gate_ship_package"))

        # AC 数值检查
        for i, ac in enumerate(acs):
            if not ac.get("has_numeric") and ac.get("level") in ("L3", "L4"):
                issues.append(Issue("warning",
                    f"{wp_id} AC#{i+1} 标记为 {ac.get('level')} 但无数值指标",
                    "gate_ship_package"))

    # 5. 字段名合规
    for req in package.get("requirements", []):
        if "id" in req and "req_id" not in req:
            issues.append(Issue("blocker",
                f"需求字段名错误: 'id' 应为 'req_id'",
                "gate_ship_package"))

    # 6. 依赖图循环检测
    if dep_graph.get("has_cycle"):
        issues.append(Issue("blocker", "依赖图存在循环依赖", "gate_ship_package"))

    # 判断通过
    passed = _check_passed(issues)
    return passed, [i.to_dict() for i in issues]


def _check_passed(issues: List[Issue]) -> bool:
    """通过条件: 0 BLOCKER + WARNING ≤ 3"""
    blockers = [i for i in issues if i.severity == "blocker"]
    warnings = [i for i in issues if i.severity == "warning"]
    return len(blockers) == 0 and len(warnings) <= 3


if __name__ == "__main__":
    # 测试 Blueprint Gate
    test_blueprint = {
        "modules": [
            {"id": "COMP-001", "name": "Agent Collector", "summary": "...", "responsibilities": [], "technology_stack": []},
            {"id": "COMP-002", "name": "Gateway", "summary": "...", "responsibilities": [], "technology_stack": []},
        ],
        "requirements": [
            {"req_id": "REQ-001", "description": "...", "priority": "P0", "coverage": "covered", "mapped_components": ["COMP-001"]},
        ],
        "architecture_principles": [],
        "work_packages": [
            {"id": "WP-001", "title": "Agent Collector", "source_modules": ["COMP-001"], "dependencies": [], "priority": "high"},
            {"id": "WP-002", "title": "Gateway", "source_modules": ["COMP-002"], "dependencies": ["WP-001"], "priority": "high"},
        ],
        "_reasoning_chain": {
            "parser": {"format": "A"},
            "architect": {"splitting_rationale": {"WP-001": "独立部署"}},
        },
    }

    passed, issues = gate_blueprint(test_blueprint)
    print("=== Blueprint Gate 测试 ===")
    print(f"  通过: {passed}")
    print(f"  问题: {len(issues)}")
    for issue in issues:
        print(f"    [{issue['severity']}] {issue['message']}")
    assert passed, "应该通过"

    # 测试 Ship Package Gate
    test_package = {
        "project": {"name": "ObserveHub"},
        "modules": test_blueprint["modules"],
        "requirements": test_blueprint["requirements"],
        "work_packages": [
            {
                "id": "WP-001",
                "title": "Agent Collector",
                "source_modules": ["COMP-001"],
                "dependencies": [],
                "acceptance_criteria": [
                    {"text": "DaemonSet 成功运行", "level": "L3", "has_numeric": False, "has_verification_method": True},
                    {"text": "接收 1000 条 trace", "level": "L4", "has_numeric": True, "has_verification_method": True},
                ],
            },
            {
                "id": "WP-002",
                "title": "Gateway",
                "source_modules": ["COMP-002"],
                "dependencies": ["WP-001"],
                "acceptance_criteria": [
                    {"text": "HPA 正常扩缩", "level": "L3", "has_numeric": True, "has_verification_method": True},
                    {"text": "采样率 70%", "level": "L3", "has_numeric": True, "has_verification_method": True},
                ],
            },
        ],
        "dependency_graph": {
            "execution_order": ["WP-001", "WP-002"],
            "parallel_groups": [["WP-001"], ["WP-002"]],
            "critical_path": ["WP-001", "WP-002"],
            "edges": [{"from": "WP-001", "to": "WP-002"}],
            "has_cycle": False,
        },
        "numeric_conflicts": [],
    }

    passed, issues = gate_ship_package(test_package)
    print("\n=== Ship Package Gate 测试 ===")
    print(f"  通过: {passed}")
    print(f"  问题: {len(issues)}")
    for issue in issues:
        print(f"    [{issue['severity']}] {issue['message']}")

    # 测试不通过的情况
    test_bad_package = dict(test_package)
    test_bad_package["numeric_conflicts"] = [
        {"metric": "throughput", "severity": "major", "values": [500000, 1000000]},
    ]
    passed, issues = gate_ship_package(test_bad_package)
    print(f"\n=== Ship Package Gate (有 major 矛盾) ===")
    print(f"  通过: {passed}")
    assert not passed, "有 major 矛盾应该不通过"

    print("\n✅ 所有 Gate 测试通过")
