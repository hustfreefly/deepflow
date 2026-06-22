#!/usr/bin/env python3
# ---
# id: ship_pro/eval/gates
# version: "1.0.0"
# component: ship_pro
# updated: "2026-06-19"
# status: active
# ---
"""
Ship Pro V3.1 — Harness Gate Functions

Code-Based quality gates that run after each Agent's output.
Each gate returns a structured result with Critical/Major/Minor tiers.

Decision logic:
- Any Critical failure → FAIL
- >threshold Major failures → CONDITIONAL
- Minor failures → recorded but still PASS

Usage:
    from gates import gate_architect, gate_decomposer, gate_specifier, gate_packager
    result = gate_architect(blueprint)
    if result["decision"] == "FAIL":
        print(result["feedback"])
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Import BlackboardManager for V6 API
import core.bootstrap
from domains.ship_pro.blackboard import BlackboardManager

from domains.ship_pro.eval.eval_code_checks import (
    check_schema_compliance,
    check_dependency_graph,
    score_all_acs,
    score_ac_verifiability,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _normalize_deps_to_adj(wps: list, dep_key: str = "dependencies") -> dict:
    """
    Normalize various dependency formats to adjacency list {wp_id: [dep_ids]}.

    Handles:
    - Simple string list: ["WP-001"]
    - Object list: [{"from": "WP-001", "to": "WP-002"}]
    - Missing deps key
    """
    adj = {}
    for wp in wps:
        wp_id = wp.get("id") or wp.get("wp_id", "unknown")
        deps_raw = wp.get(dep_key, [])
        dep_ids = []
        if isinstance(deps_raw, list):
            for d in deps_raw:
                if isinstance(d, str):
                    dep_ids.append(d)
                elif isinstance(d, dict):
                    # Object format: {"from": "WP-001", "to": "WP-002"}
                    # The dependency OF this WP is the "from" field
                    if "from" in d:
                        dep_ids.append(d["from"])
                    elif "id" in d:
                        dep_ids.append(d["id"])
        adj[wp_id] = dep_ids
    return adj


def _check_acyclic_from_adj(adj: dict) -> bool:
    """Check if a dependency adjacency list is acyclic using DFS."""
    WHITE, GRAY, BLACK = 0, 1, 2
    all_nodes = set(adj.keys())
    for deps in adj.values():
        all_nodes.update(deps)
    color = {node: WHITE for node in all_nodes}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor in adj.get(node, []):
            if color.get(neighbor, WHITE) == GRAY:
                return False  # cycle
            if color.get(neighbor, WHITE) == WHITE:
                if not dfs(neighbor):
                    return False
        color[node] = BLACK
        return True

    for node in all_nodes:
        if color[node] == WHITE:
            if not dfs(node):
                return False
    return True


def _make_result(
    passed: bool,
    decision: str,
    critical_results: dict,
    major_results: dict,
    minor_results: dict,
    feedback: str,
) -> dict:
    """Create a standardized gate result dict."""
    return {
        "passed": passed,
        "decision": decision,
        "critical_results": critical_results,
        "major_results": major_results,
        "minor_results": minor_results,
        "feedback": feedback,
    }


# ---------------------------------------------------------------------------
# Gate 1: Architect
# ---------------------------------------------------------------------------

def gate_architect(blueprint: dict) -> dict:
    """
    Quality gate for Architect Agent output.

    Checks the architectural blueprint for structural completeness:
    - Critical: modules non-empty, dependencies acyclic, requirements non-empty
    - Major: requirements mapped, project_type exists
    - Minor: wp_file_mapping exists, domain_details non-empty

    Args:
        blueprint: The architect output dict (modules, dependencies, requirements, etc.)

    Returns:
        Gate result dict with passed/decision/critical_results/major_results/minor_results/feedback
    """
    critical = {}
    major = {}
    minor = {}

    # --- Critical checks ---
    # 1. modules_non_empty
    modules = blueprint.get("modules", [])
    critical["modules_non_empty"] = isinstance(modules, list) and len(modules) > 0

    # 2. dependencies_acyclic
    deps = blueprint.get("dependencies", [])
    # Build adjacency for cycle check: edge from → to means "from depends on to"
    dep_adj = {}
    module_ids = {m.get("id") for m in modules if isinstance(m, dict)}
    for d in deps:
        if isinstance(d, dict):
            src = d.get("from")
            tgt = d.get("to")
            if src and tgt:
                dep_adj.setdefault(src, []).append(tgt)
    # Ensure all module IDs are in adj
    for mid in module_ids:
        dep_adj.setdefault(mid, [])
    critical["dependencies_acyclic"] = _check_acyclic_from_adj(dep_adj)

    # 3. requirements_non_empty
    requirements = blueprint.get("requirements", [])
    critical["requirements_non_empty"] = isinstance(requirements, list) and len(requirements) > 0

    # --- Major checks ---
    # 1. requirements_mapped: each requirement has mapped_components
    if requirements:
        mapped_count = sum(
            1 for r in requirements
            if isinstance(r, dict) and "mapped_components" in r
        )
        major["requirements_mapped"] = mapped_count == len(requirements)
    else:
        major["requirements_mapped"] = False

    # 2. project_type_exists
    major["project_type_exists"] = bool(blueprint.get("project_type"))

    # --- Minor checks ---
    # 1. wp_file_mapping_exists
    minor["wp_file_mapping_exists"] = "wp_file_mapping" in blueprint

    # 2. domain_details_non_empty
    domain_details = blueprint.get("domain_details", {})
    minor["domain_details_non_empty"] = isinstance(domain_details, dict) and len(domain_details) > 0

    # --- Decision ---
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]
    minor_failures = [k for k, v in minor.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        feedback = (
            f"Architect Gate FAIL: Critical checks failed: {', '.join(critical_failures)}. "
            f"Blueprint must have non-empty modules, acyclic dependencies, and non-empty requirements."
        )
    elif len(major_failures) > len(major) * 0.5:
        decision = "CONDITIONAL"
        passed = True
        feedback = (
            f"Architect Gate CONDITIONAL: Major checks failed: {', '.join(major_failures)}. "
            f"Consider adding project_type and mapped_components to requirements."
        )
    else:
        decision = "PASS"
        passed = True
        feedback_parts = []
        if minor_failures:
            feedback_parts.append(f"Minor notes: {', '.join(minor_failures)}")
        feedback_parts.append("Architect output is structurally sound.")
        feedback = " ".join(feedback_parts)

    return _make_result(passed, decision, critical, major, minor, feedback)


# ---------------------------------------------------------------------------
# Gate 2: Decomposer
# ---------------------------------------------------------------------------

def gate_decomposer(wp_structure: dict, blueprint: dict) -> dict:
    """
    Quality gate for Decomposer Agent output.

    Checks work package decomposition against the blueprint:
    - Critical: WPs non-empty, 100% module coverage, dependencies acyclic
    - Major: all WPs have source_modules, all WPs have rationale

    Args:
        wp_structure: The decomposer output dict (work_packages, dependency_edges, etc.)
        blueprint: The architect blueprint (for module coverage check)

    Returns:
        Gate result dict
    """
    critical = {}
    major = {}
    minor = {}

    work_packages = wp_structure.get("work_packages", [])

    # --- Critical checks ---
    # 1. wps_non_empty
    critical["wps_non_empty"] = isinstance(work_packages, list) and len(work_packages) > 0

    # 2. module_coverage_100: every module in blueprint covered by at least one WP
    blueprint_modules = {
        m.get("id") for m in blueprint.get("modules", []) if isinstance(m, dict)
    }
    covered_modules = set()
    for wp in work_packages:
        source_mods = wp.get("source_modules", [])
        if isinstance(source_mods, list):
            covered_modules.update(source_mods)
    if blueprint_modules:
        critical["module_coverage_100"] = blueprint_modules.issubset(covered_modules)
    else:
        critical["module_coverage_100"] = True  # No modules to cover

    # 3. dependencies_acyclic
    dep_adj = _normalize_deps_to_adj(work_packages)
    critical["dependencies_acyclic"] = _check_acyclic_from_adj(dep_adj)

    # --- Major checks ---
    # 1. all_wps_have_source_modules
    if work_packages:
        with_source = sum(
            1 for wp in work_packages
            if wp.get("source_modules") and len(wp["source_modules"]) > 0
        )
        major["all_wps_have_source_modules"] = with_source == len(work_packages)
    else:
        major["all_wps_have_source_modules"] = False

    # 2. all_wps_have_rationale
    if work_packages:
        with_rationale = sum(
            1 for wp in work_packages
            if wp.get("rationale") and str(wp["rationale"]).strip()
        )
        major["all_wps_have_rationale"] = with_rationale == len(work_packages)
    else:
        major["all_wps_have_rationale"] = False

    # --- Decision ---
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        feedback = (
            f"Decomposer Gate FAIL: Critical checks failed: {', '.join(critical_failures)}. "
        )
        if "module_coverage_100" in critical_failures:
            uncovered = blueprint_modules - covered_modules
            feedback += f"Uncovered modules: {uncovered}. "
        if "dependencies_acyclic" in critical_failures:
            feedback += "WP dependency graph has cycles. "
    elif len(major_failures) > len(major) * 0.5:
        decision = "CONDITIONAL"
        passed = True
        feedback = (
            f"Decomposer Gate CONDITIONAL: Major checks failed: {', '.join(major_failures)}. "
        )
    else:
        decision = "PASS"
        passed = True
        feedback = "Decomposer output is structurally sound."

    return _make_result(passed, decision, critical, major, minor, feedback)


# ---------------------------------------------------------------------------
# Gate 3: Specifier (★ most critical)
# ---------------------------------------------------------------------------

def gate_specifier(specs: dict) -> dict:
    """
    Quality gate for Specifier Agent output.

    Zero-tolerance for critical field emptiness. If budget/complexity/outputs/AC
    are empty/null across WPs, the gate FAILs immediately.

    Checks:
    - Critical: budget_filled, complexity_filled, outputs_non_empty,
                ac_non_empty (≥2), schema_field_names
    - Major (>30% fail = CONDITIONAL): requirements_non_empty, ac_score_70
    - Minor (record only): context_files_filled, acceptance_tests_filled,
                          model_tier_filled

    Args:
        specs: The specifier output dict (work_package_specs or similar)

    Returns:
        Gate result dict
    """
    critical = {}
    major = {}
    minor = {}

    # Normalize: accept both "work_package_specs" and "work_packages"
    wps = specs.get("work_package_specs", specs.get("work_packages", []))
    if not wps:
        return _make_result(
            False, "FAIL",
            {"wps_exist": False}, {}, {},
            "Specifier Gate FAIL: No work packages found in specifier output."
        )

    wp_count = len(wps)

    # --- Critical checks ---

    # 1. budget_filled: each WP's budget is not null
    budget_filled_count = sum(
        1 for wp in wps
        if wp.get("budget") is not None and isinstance(wp.get("budget"), dict)
        and wp["budget"].get("tokens") is not None
    )
    critical["budget_filled"] = budget_filled_count == wp_count

    # 2. complexity_filled: each WP's complexity is not null
    complexity_filled_count = sum(
        1 for wp in wps
        if wp.get("complexity") is not None and str(wp.get("complexity", "")).strip()
    )
    critical["complexity_filled"] = complexity_filled_count == wp_count

    # 3. outputs_non_empty: each WP has at least 1 output
    outputs_ok_count = sum(
        1 for wp in wps
        if isinstance(wp.get("outputs"), list) and len(wp["outputs"]) >= 1
    )
    critical["outputs_non_empty"] = outputs_ok_count == wp_count

    # 4. ac_non_empty: each WP has at least 2 acceptance_criteria
    ac_ok_count = sum(
        1 for wp in wps
        if isinstance(wp.get("acceptance_criteria"), list) and len(wp["acceptance_criteria"]) >= 2
    )
    critical["ac_non_empty"] = ac_ok_count == wp_count

    # 5. schema_field_names: uses "id" not "wp_id"
    uses_wp_id = any("wp_id" in wp and "id" not in wp for wp in wps)
    critical["schema_field_names"] = not uses_wp_id

    # --- Major checks ---

    # 1. requirements_non_empty: each WP has at least 1 REQ-ID
    reqs_ok_count = sum(
        1 for wp in wps
        if isinstance(wp.get("requirements"), list) and len(wp["requirements"]) >= 1
    )
    major_threshold = 0.3
    major["requirements_non_empty"] = (reqs_ok_count / wp_count) >= (1 - major_threshold)

    # 2. ac_score_70: AC verifiability mean score >= 70
    # Build a fake work_packages list for score_all_acs
    fake_wps = []
    for wp in wps:
        wp_id = wp.get("id") or wp.get("wp_id", "unknown")
        acs = wp.get("acceptance_criteria", [])
        # Normalize AC objects to text strings
        ac_texts = []
        for ac in acs:
            if isinstance(ac, str):
                ac_texts.append(ac)
            elif isinstance(ac, dict):
                # Use description + verification as the AC text
                text = ac.get("description", "") + " " + ac.get("verification", "")
                ac_texts.append(text.strip())
        fake_wps.append({"id": wp_id, "acceptance_criteria": ac_texts})

    ac_score_result = score_all_acs(fake_wps)
    major["ac_score_70"] = ac_score_result["mean_score"] >= 70

    # --- Minor checks ---

    # 1. context_files_filled
    context_ok_count = sum(
        1 for wp in wps
        if isinstance(wp.get("context_files"), list) and len(wp["context_files"]) > 0
    )
    minor["context_files_filled"] = context_ok_count == wp_count

    # 2. acceptance_tests_filled
    tests_ok_count = sum(
        1 for wp in wps
        if isinstance(wp.get("acceptance_tests"), list) and len(wp["acceptance_tests"]) > 0
    )
    minor["acceptance_tests_filled"] = tests_ok_count == wp_count

    # 3. model_tier_filled
    tier_ok_count = sum(
        1 for wp in wps
        if wp.get("model_tier") is not None and str(wp.get("model_tier", "")).strip()
    )
    minor["model_tier_filled"] = tier_ok_count == wp_count

    # --- Decision ---
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]
    minor_failures = [k for k, v in minor.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        details = []
        if not critical["budget_filled"]:
            details.append(f"budget null in {wp_count - budget_filled_count}/{wp_count} WPs")
        if not critical["complexity_filled"]:
            details.append(f"complexity null in {wp_count - complexity_filled_count}/{wp_count} WPs")
        if not critical["outputs_non_empty"]:
            details.append(f"outputs empty in {wp_count - outputs_ok_count}/{wp_count} WPs")
        if not critical["ac_non_empty"]:
            details.append(f"AC <2 items in {wp_count - ac_ok_count}/{wp_count} WPs")
        if not critical["schema_field_names"]:
            details.append("uses 'wp_id' instead of 'id'")
        feedback = (
            f"Specifier Gate FAIL: Critical checks failed: {', '.join(critical_failures)}. "
            f"Details: {'; '.join(details)}. "
            f"Specifier must fill budget, complexity, outputs, and AC for every WP."
        )
    elif len(major_failures) > len(major) * 0.3:
        decision = "CONDITIONAL"
        passed = True
        feedback = (
            f"Specifier Gate CONDITIONAL: Major checks failed: {', '.join(major_failures)}. "
            f"AC mean score: {ac_score_result['mean_score']:.1f}. "
        )
    else:
        decision = "PASS"
        passed = True
        feedback_parts = [f"AC mean score: {ac_score_result['mean_score']:.1f}."]
        if minor_failures:
            feedback_parts.append(f"Minor notes: {', '.join(minor_failures)}.")
        feedback_parts.append("Specifier output meets quality standards.")
        feedback = " ".join(feedback_parts)

    return _make_result(passed, decision, critical, major, minor, feedback)


# ---------------------------------------------------------------------------
# Gate 4: Packager
# ---------------------------------------------------------------------------

def gate_packager(package: dict) -> dict:
    """
    Quality gate for Packager Agent output.

    Checks the final ship_package.json for schema compliance and structural integrity.

    - Critical: schema_compliant, ac_text_not_count, dependency_graph_acyclic
    - Major: all_wps_present, summary_exists
    - Minor: (none currently)

    Args:
        package: The packager output dict (ship_package)

    Returns:
        Gate result dict
    """
    critical = {}
    major = {}
    minor = {}

    work_packages = package.get("work_packages", [])

    # --- Critical checks ---

    # 1. schema_compliant: passes JSON Schema validation
    schema_result = check_schema_compliance(package)
    critical["schema_compliant"] = schema_result["passed"]

    # 2. ac_text_not_count: AC should be text arrays, not count numbers
    ac_is_text = True
    for wp in work_packages:
        acs = wp.get("acceptance_criteria", [])
        for ac in acs:
            if isinstance(ac, (int, float)) and not isinstance(ac, str):
                ac_is_text = False
                break
            if isinstance(ac, dict) and "description" in ac:
                # AC as object is not schema-compliant (should be string)
                ac_is_text = False
                break
        if not ac_is_text:
            break
    critical["ac_text_not_count"] = ac_is_text

    # 3. dependency_graph_acyclic
    dep_graph = package.get("dependency_graph", {})
    # Check execution_order and edges for cycles
    edges = dep_graph.get("edges", [])
    dep_adj = {}
    wp_ids = {wp.get("id") for wp in work_packages}
    for edge in edges:
        if isinstance(edge, dict):
            src = edge.get("from")
            tgt = edge.get("to")
            if src and tgt:
                # "from" depends on "to" → edge from src to tgt in dependency direction
                dep_adj.setdefault(src, []).append(tgt)
    for wid in wp_ids:
        dep_adj.setdefault(wid, [])
    critical["dependency_graph_acyclic"] = _check_acyclic_from_adj(dep_adj)

    # --- Major checks ---

    # 1. all_wps_present: all WP IDs referenced in dependency_graph exist
    exec_order = dep_graph.get("execution_order", [])
    if exec_order:
        exec_wp_ids = set(exec_order)
        actual_wp_ids = {wp.get("id") for wp in work_packages}
        major["all_wps_present"] = exec_wp_ids == actual_wp_ids
    else:
        major["all_wps_present"] = len(work_packages) > 0

    # 2. summary_exists: summary field exists and is non-empty
    summary = package.get("summary", {})
    major["summary_exists"] = isinstance(summary, dict) and len(summary) > 0

    # --- Decision ---
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        details = []
        if not critical["schema_compliant"]:
            details.append(f"schema errors: {schema_result.get('errors', [])[:3]}")
        if not critical["ac_text_not_count"]:
            details.append("AC contains objects/numbers instead of text strings")
        if not critical["dependency_graph_acyclic"]:
            details.append("dependency graph has cycles")
        feedback = (
            f"Packager Gate FAIL: Critical checks failed: {', '.join(critical_failures)}. "
            f"Details: {'; '.join(details)}"
        )
    elif len(major_failures) > len(major) * 0.5:
        decision = "CONDITIONAL"
        passed = True
        feedback = (
            f"Packager Gate CONDITIONAL: Major checks failed: {', '.join(major_failures)}. "
        )
    else:
        decision = "PASS"
        passed = True
        feedback = "Packager output is structurally sound."

    return _make_result(passed, decision, critical, major, minor, feedback)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all gates against real pipeline data for debugging."""
    import argparse

    parser = argparse.ArgumentParser(description="Ship Pro V3.1 Harness Gates")
    parser.add_argument("test_data_dir", help="Path to blackboard directory with agent outputs")
    args = parser.parse_args()

    base = args.test_data_dir

    # Use BlackboardManager V6 API for stage I/O
    bm = BlackboardManager(session_id="gate_debug", base_dir=base)

    data = {}
    for agent in ["architect", "decomposer", "specifier", "packager"]:
        result = bm.read_stage(agent)
        if result is not None:
            data[agent] = result
            print(f"✅ Loaded {agent}")
        else:
            print(f"❌ Missing {agent}")

    print("\n" + "=" * 60)
    print("  Ship Pro V3.1 — Harness Gate Results")
    print("=" * 60 + "\n")

    # Gate 1: Architect
    if "architect" in data:
        result = gate_architect(data["architect"])
        icon = "✅" if result["decision"] == "PASS" else ("⚠️" if result["decision"] == "CONDITIONAL" else "❌")
        print(f"  {icon} Architect Gate: {result['decision']}")
        print(f"     Critical: {result['critical_results']}")
        print(f"     Major: {result['major_results']}")
        print(f"     Feedback: {result['feedback']}\n")

    # Gate 2: Decomposer
    if "decomposer" in data and "architect" in data:
        result = gate_decomposer(data["decomposer"], data["architect"])
        icon = "✅" if result["decision"] == "PASS" else ("⚠️" if result["decision"] == "CONDITIONAL" else "❌")
        print(f"  {icon} Decomposer Gate: {result['decision']}")
        print(f"     Critical: {result['critical_results']}")
        print(f"     Major: {result['major_results']}")
        print(f"     Feedback: {result['feedback']}\n")

    # Gate 3: Specifier
    if "specifier" in data:
        result = gate_specifier(data["specifier"])
        icon = "✅" if result["decision"] == "PASS" else ("⚠️" if result["decision"] == "CONDITIONAL" else "❌")
        print(f"  {icon} Specifier Gate: {result['decision']}")
        print(f"     Critical: {result['critical_results']}")
        print(f"     Major: {result['major_results']}")
        print(f"     Feedback: {result['feedback']}\n")

    # Gate 4: Packager
    if "packager" in data:
        result = gate_packager(data["packager"])
        icon = "✅" if result["decision"] == "PASS" else ("⚠️" if result["decision"] == "CONDITIONAL" else "❌")
        print(f"  {icon} Packager Gate: {result['decision']}")
        print(f"     Critical: {result['critical_results']}")
        print(f"     Major: {result['major_results']}")
        print(f"     Feedback: {result['feedback']}\n")


if __name__ == "__main__":
    main()
