#!/usr/bin/env python3
"""
Ship Pro Quality Gate — 数据提取脚本

从 frozen_blueprint.json + ship_package.json 提取关键数据，
生成供 LLM Reviewer 使用的精简 review_data.json。

用法:
    python3 extract_ship_review_data.py --session-id <SESSION_ID>

输出:
    blackboard/{SESSION_ID}/ship_review_data.json
"""

import argparse
import json
import os
import sys
from pathlib import Path


def extract(base_path: str, session_id: str) -> dict:
    """从 Blueprint + Ship Package 提取审查所需的关键数据。"""
    bp_path = os.path.join(base_path, "frozen_blueprint.json")
    sp_path = os.path.join(base_path, "ship_package.json")

    with open(bp_path, "r", encoding="utf-8") as f:
        blueprint = json.load(f)
    with open(sp_path, "r", encoding="utf-8") as f:
        ship_package = json.load(f)

    # === 1. Blueprint 模块 ===
    bp_modules = []
    for m in blueprint.get("architecture", {}).get("modules", []):
        bp_modules.append({
            "id": m.get("id", ""),
            "name": m.get("name", ""),
            "summary": m.get("summary", ""),
            "tier": m.get("tier", ""),
            "dependencies": m.get("dependencies", []),
        })

    # === 2. Blueprint 需求 ===
    bp_requirements = []
    for r in blueprint.get("requirements", {}).get("items", []):
        bp_requirements.append({
            "id": r.get("id", ""),
            "text": r.get("text", ""),
            "priority": r.get("priority", ""),
        })

    # === 3. Blueprint 约束与风险 ===
    bp_constraints = blueprint.get("intent", {}).get("success_criteria", [])
    bp_risks = blueprint.get("risks", {}).get("risk_register", [])
    bp_known_gaps = blueprint.get("risks", {}).get("known_gaps", [])

    # === 4. Ship Package WP ===
    sp_work_packages = []
    for wp in ship_package.get("work_packages", []):
        sp_work_packages.append({
            "id": wp.get("id", ""),
            "title": wp.get("title", ""),
            "phase": wp.get("phase", ""),
            "dependencies": wp.get("dependencies", []),
            "estimated_complexity": wp.get("estimated_complexity", ""),
            "related_modules": wp.get("related_modules", []),
            "requirements": wp.get("requirements", []),
            "acceptance_criteria": wp.get("acceptance_criteria", []),
            "deliverables": wp.get("deliverables", []),
            "constraints": wp.get("constraints", []),
        })

    # === 5. Ship Package 验收契约 ===
    sp_acceptance = ship_package.get("acceptance_contract", [])

    # === 6. Ship Package 风险契约 ===
    sp_risk_register = ship_package.get("risk_contract", {}).get("risk_register", [])

    # === 7. 一致性预检 (确定性) ===
    bp_module_ids = {m["id"] for m in bp_modules}
    wp_related_ids = set()
    for wp in sp_work_packages:
        wp_related_ids.update(wp.get("related_modules", []))

    modules_without_wp = list(bp_module_ids - wp_related_ids)
    wp_without_module = [
        wp["id"] for wp in sp_work_packages
        if not wp.get("related_modules")
    ]

    # === 8. 依赖预检 (确定性) ===
    wp_ids = {wp["id"] for wp in sp_work_packages}
    invalid_deps = []
    for wp in sp_work_packages:
        for dep in wp.get("dependencies", []):
            if dep not in wp_ids:
                invalid_deps.append({"wp_id": wp["id"], "invalid_dep": dep})

    # 循环依赖检测 (简单DFS)
    dep_graph = {wp["id"]: wp.get("dependencies", []) for wp in sp_work_packages}
    cycles = _detect_cycles(dep_graph)

    return {
        "session_id": session_id,
        "blueprint": {
            "modules": bp_modules,
            "requirements": bp_requirements,
            "constraints": bp_constraints,
            "risks": bp_risks,
            "known_gaps": bp_known_gaps,
        },
        "ship_package": {
            "work_packages": sp_work_packages,
            "acceptance_contract": sp_acceptance,
            "risk_register": sp_risk_register,
            "readiness": ship_package.get("readiness", {}),
        },
        "pre_checks": {
            "modules_without_wp": modules_without_wp,
            "wp_without_module": wp_without_module,
            "invalid_dependencies": invalid_deps,
            "dependency_cycles": cycles,
        },
    }


def _detect_cycles(graph: dict) -> list:
    """检测有向图中的循环依赖。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    cycles = []

    def dfs(node, path):
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])
            elif color[neighbor] == WHITE:
                dfs(neighbor, path)
        path.pop()
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            dfs(node, [])

    return cycles


def main():
    parser = argparse.ArgumentParser(description="Ship Pro Quality Gate 数据提取")
    parser.add_argument("--session-id", required=True, help="Session ID")
    args = parser.parse_args()

    session_id = args.session_id
    deepflow_home = os.path.expanduser("~/.openclaw/workspace/.deepflow")
    base_path = os.path.join(deepflow_home, "blackboard", session_id)

    if not os.path.exists(base_path):
        print(f"ERROR: blackboard 目录不存在: {base_path}", file=sys.stderr)
        sys.exit(1)

    result = extract(base_path, session_id)

    output_path = os.path.join(base_path, "ship_review_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Review data extracted to {output_path}")
    print(f"   Modules: {len(result['blueprint']['modules'])}")
    print(f"   Work Packages: {len(result['ship_package']['work_packages'])}")
    print(f"   Pre-check issues: "
          f"{len(result['pre_checks']['modules_without_wp'])} orphan modules, "
          f"{len(result['pre_checks']['invalid_dependencies'])} invalid deps, "
          f"{len(result['pre_checks']['dependency_cycles'])} cycles")


if __name__ == "__main__":
    main()
