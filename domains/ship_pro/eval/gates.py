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

    Uses Pydantic contract (ArchitectOutput) for schema validation,
    plus custom checks for acyclic dependencies.

    Checks:
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

    # --- Pydantic schema validation (契约笼子) ---
    pydantic_valid = False
    pydantic_errors = []
    try:
        from domains.ship_pro.contracts.architect import ArchitectOutput
        # Strip _meta before validation (Pydantic treats underscore fields as private)
        bp_for_validation = {k: v for k, v in blueprint.items() if not k.startswith("_")}
        validated = ArchitectOutput(**bp_for_validation)
        pydantic_valid = True
    except Exception as e:
        pydantic_errors = str(e)
        # Fall back to dict-based checks
        validated = None

    # --- Critical checks ---
    # 1. modules_non_empty
    modules = blueprint.get("modules", [])
    critical["modules_non_empty"] = isinstance(modules, list) and len(modules) > 0

    # 2. dependencies_acyclic
    deps = blueprint.get("dependencies", [])
    dep_adj = {}
    module_ids = {m.get("id") for m in modules if isinstance(m, dict)}
    for d in deps:
        if isinstance(d, dict):
            src = d.get("from")
            tgt = d.get("to")
            if src and tgt:
                dep_adj.setdefault(src, []).append(tgt)
    for mid in module_ids:
        dep_adj.setdefault(mid, [])
    critical["dependencies_acyclic"] = _check_acyclic_from_adj(dep_adj)

    # 3. requirements_non_empty
    requirements = blueprint.get("requirements", [])
    # Defensive: handle dict format (e.g. {"items": [...], "total": N}) from LLM
    if isinstance(requirements, dict):
        requirements = requirements.get("items", requirements.get("requirements", []))
    critical["requirements_non_empty"] = isinstance(requirements, list) and len(requirements) > 0

    # --- Major checks (Pydantic contract enforced) ---
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
    minor["wp_file_mapping_exists"] = "wp_file_mapping" in blueprint
    domain_details = blueprint.get("domain_details", {})
    minor["domain_details_non_empty"] = isinstance(domain_details, dict) and len(domain_details) > 0

    # Add Pydantic validation status as informational check
    minor["pydantic_schema_valid"] = pydantic_valid

    # --- NEW: Internal consistency check ---
    # Check: component responsibilities vs principle anti_patterns
    consistency_issues = []
    principles = blueprint.get("architecture_principles", [])
    bp_modules = blueprint.get("modules", [])

    for module in bp_modules:
        if not isinstance(module, dict):
            continue
        module_id = module.get("id", "unknown")
        responsibilities = module.get("responsibilities", [])
        resp_text = " ".join(str(r) for r in responsibilities).lower()

        for principle in principles:
            if not isinstance(principle, dict):
                continue
            anti_patterns = principle.get("anti_patterns", [])
            principle_id = principle.get("id", "unknown")

            for ap in anti_patterns:
                if not isinstance(ap, str):
                    continue
                # Extract key terms from anti_pattern
                ap_lower = ap.lower()
                # Check for "自建 XXX" pattern
                if "自建" in ap_lower:
                    # Extract the thing that should not be self-built
                    parts = ap_lower.split("自建")
                    if len(parts) > 1:
                        thing = parts[1].strip().rstrip("。，,.")
                        # Remove parenthetical explanations
                        thing = thing.split("（")[0].split("(")[0].strip()
                        # Split by "/" to handle "令牌桶限流/优先级队列" style
                        thing_alternatives = [t.strip() for t in thing.split("/") if t.strip()]
                        for thing_alt in thing_alternatives:
                            if len(thing_alt) >= 2 and thing_alt in resp_text:
                                consistency_issues.append({
                                    "module_id": module_id,
                                    "principle_id": principle_id,
                                    "conflict": f"Module responsibility contains '{thing_alt}' which contradicts principle anti_pattern '{ap}'"
                                })
                                break  # one match per anti_pattern per module is enough

    major["internal_consistency"] = len(consistency_issues) == 0
    if consistency_issues:
        major["internal_consistency_details"] = consistency_issues

    # --- NEW: Implementation phase vs principle consistency ---
    # Check: if any principle has anti_pattern containing "分阶段", implementation_hints should not have multiple phases
    phase_split = False
    hints = blueprint.get("implementation_hints", [])
    phases = set()
    for h in hints:
        if isinstance(h, dict):
            phases.add(h.get("phase", ""))
    
    for principle in principles:
        if not isinstance(principle, dict):
            continue
        anti_pats = principle.get("anti_patterns", [])
        for ap in anti_pats:
            if isinstance(ap, str) and "分阶段" in ap:
                # Found a "一步到位" principle (anti-pattern mentions "分阶段")
                if len(phases) > 1:
                    phase_split = True
                    break
        if phase_split:
            break
    
    major["implementation_phase_consistency"] = not phase_split

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
        if not pydantic_valid:
            feedback_parts.append(f"(Pydantic validation warnings: {pydantic_errors[:200]})")
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

    # --- NEW: Obligation-anti_pattern consistency ---
    obligation_conflicts = []
    principles = blueprint.get("architecture_principles", [])
    principle_map = {p.get("id"): p for p in principles if isinstance(p, dict)}

    for wp in work_packages:
        if not isinstance(wp, dict):
            continue
        wp_id = wp.get("id", "unknown")
        serving = wp.get("serving_principles", [])

        for sp in serving:
            if not isinstance(sp, dict):
                continue
            p_id = sp.get("principle_id", "")
            obligation = str(sp.get("obligation", "")).lower()

            # Get the principle's anti_patterns from blueprint
            principle = principle_map.get(p_id, {})
            anti_patterns = principle.get("anti_patterns", [])

            for ap in anti_patterns:
                if not isinstance(ap, str):
                    continue
                ap_lower = ap.lower()
                if "自建" in ap_lower:
                    parts = ap_lower.split("自建")
                    if len(parts) > 1:
                        thing = parts[1].strip().rstrip("。，,.")
                        thing = thing.split("（")[0].split("(")[0].strip()
                        # Split by "/" to handle "令牌桶限流/优先级队列" style
                        thing_alternatives = [t.strip() for t in thing.split("/") if t.strip()]
                        for thing_alt in thing_alternatives:
                            if len(thing_alt) >= 2 and thing_alt in obligation:
                                # Check if obligation says "must implement" this thing
                                if any(kw in obligation for kw in ["必须", "实现", "交付", "包含"]):
                                    obligation_conflicts.append({
                                        "wp_id": wp_id,
                                        "principle_id": p_id,
                                        "obligation_snippet": obligation[:100],
                                        "anti_pattern": ap
                                    })
                                    break  # one match per anti_pattern per WP is enough

    major["obligation_anti_pattern_consistency"] = len(obligation_conflicts) == 0
    if obligation_conflicts:
        major["obligation_anti_pattern_details"] = obligation_conflicts

    # --- NEW: Priority-complexity consistency ---
    priority_complexity_mismatches = []
    for wp in work_packages:
        if not isinstance(wp, dict):
            continue
        wp_id = wp.get("id", "unknown")
        priority = str(wp.get("priority", "")).lower()
        complexity = str(wp.get("complexity", "")).lower()
        
        if complexity == "critical" and priority in ("low", "medium"):
            # Only flag as issue if no rationale explains the mismatch
            rationale = str(wp.get("rationale", "")).lower()
            if not any(kw in rationale for kw in ["independent", "独立", "不依赖", "可并行"]):
                priority_complexity_mismatches.append({
                    "wp_id": wp_id,
                    "priority": priority,
                    "complexity": complexity,
                })

    major["priority_complexity_consistency"] = len(priority_complexity_mismatches) == 0
    if priority_complexity_mismatches:
        major["priority_complexity_details"] = priority_complexity_mismatches

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
# Gate 4: Reviewer (★ 契约笼子)
# ---------------------------------------------------------------------------

def gate_reviewer(review_output: dict) -> dict:
    """
    Quality gate for Reviewer Agent output.

    Uses Pydantic contract (ReviewerOutput) for schema validation,
    plus structural checks.

    Checks:
    - Critical: verdict_valid, issues_is_list, quality_metrics_present, pydantic_valid
    - Major: summary_non_empty, round_present

    Args:
        review_output: The reviewer output dict

    Returns:
        Gate result dict
    """
    critical = {}
    major = {}
    minor = {}

    # --- Pydantic schema validation (契约笼子) ---
    pydantic_valid = False
    pydantic_errors = []
    try:
        from domains.ship_pro.contracts.reviewer import ReviewerOutput
        validated = ReviewerOutput(**review_output)
        pydantic_valid = True
    except Exception as e:
        pydantic_errors = str(e)
        validated = None

    # --- Critical checks ---
    # 1. verdict_valid: must be PASS / PASS_WITH_CONDITIONS / FAIL
    verdict = review_output.get("verdict", "")
    critical["verdict_valid"] = verdict in ("PASS", "PASS_WITH_CONDITIONS", "FAIL")

    # 2. issues_is_list: issues must be a list (can be empty)
    issues = review_output.get("issues")
    critical["issues_is_list"] = isinstance(issues, list)

    # 3. quality_metrics_present: must be a non-empty dict
    metrics = review_output.get("quality_metrics")
    critical["quality_metrics_present"] = isinstance(metrics, dict) and len(metrics) > 0

    # 4. pydantic_valid: Pydantic contract passed
    critical["pydantic_valid"] = pydantic_valid

    # --- Major checks ---
    # 1. summary_non_empty
    summary = review_output.get("summary", "")
    major["summary_non_empty"] = isinstance(summary, str) and len(summary.strip()) > 0

    # 2. round_present
    major["round_present"] = "round" in review_output and isinstance(
        review_output.get("round"), int
    )

    # --- Decision ---
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        details = []
        if not critical["verdict_valid"]:
            details.append(f"verdict='{verdict}' (expected PASS/PASS_WITH_CONDITIONS/FAIL)")
        if not critical["issues_is_list"]:
            details.append("issues is not a list")
        if not critical["quality_metrics_present"]:
            details.append("quality_metrics missing or empty")
        if not critical["pydantic_valid"]:
            details.append(f"Pydantic: {pydantic_errors[:200]}")
        if not critical.get("no_principle_failures", True):
            details.append("原则审计存在 FAIL 项")
        if not critical.get("no_platform_failures", True):
            details.append("平台审计存在 FAIL 项")
        feedback = (
            f"Reviewer Gate FAIL: Critical checks failed: {', '.join(critical_failures)}. "
            f"Details: {'; '.join(details)}. "
            f"Reviewer must output valid verdict, issues list, and quality_metrics."
        )
    elif len(major_failures) > len(major) * 0.5:
        decision = "CONDITIONAL"
        passed = True
        feedback = (
            f"Reviewer Gate CONDITIONAL: Major checks failed: {', '.join(major_failures)}. "
        )
    else:
        decision = "PASS"
        passed = True
        feedback = (
            f"Reviewer output is structurally sound. "
            f"Verdict: {verdict}, Issues: {len(issues) if isinstance(issues, list) else 0}."
        )

    return _make_result(passed, decision, critical, major, minor, feedback)


# ---------------------------------------------------------------------------
# Gate 5: Packager
# ---------------------------------------------------------------------------

def check_dependency_consistency(packager_output: dict, decomposer_output: dict) -> dict:
    """
    检查 Packager 输出的 dependency_graph 是否与 Decomposer 的 dependencies 一致。

    Packager 不应静默添加新的依赖边。如果发现新依赖，应该标记为 needs_reconciliation。
    """
    # 从 Decomposer 提取声明的依赖
    decomposer_deps = set()
    for wp in decomposer_output.get("work_packages", []):
        wp_id = wp.get("id", "") or wp.get("wp_id", "")
        for dep in wp.get("dependencies", []):
            if isinstance(dep, str):
                decomposer_deps.add((wp_id, dep))
            elif isinstance(dep, dict):
                # Handle object format: {"from": "WP-001", "to": "WP-002"}
                dep_from = dep.get("from", "") or dep.get("id", "")
                if dep_from:
                    decomposer_deps.add((wp_id, dep_from))

    # 从 Packager 提取实际的依赖边
    packager_deps = set()
    dep_graph = packager_output.get("dependency_graph", {})
    for edge in dep_graph.get("edges", []):
        if isinstance(edge, dict):
            from_wp = edge.get("from", "")
            to_wp = edge.get("to", "")
            if from_wp and to_wp:
                packager_deps.add((from_wp, to_wp))

    # 找出 Packager 新增的依赖（Packager 有但 Decomposer 没有）
    new_deps = packager_deps - decomposer_deps
    # 找出 Decomposer 声明但 Packager 遗漏的依赖
    missing_deps = decomposer_deps - packager_deps

    return {
        "consistent": len(new_deps) == 0 and len(missing_deps) == 0,
        "new_dependencies": [{"from": f, "to": t} for f, t in sorted(new_deps)],
        "missing_dependencies": [{"from": f, "to": t} for f, t in sorted(missing_deps)],
    }


def gate_packager(package: dict, decomposer_output: dict = None) -> dict:
    """
    Quality gate for Packager Agent output.

    Checks the final ship_package.json for schema compliance and structural integrity.

    - Critical: schema_compliant, ac_text_not_count, dependency_graph_acyclic
    - Major: all_wps_present, summary_exists, dependency_consistency
    - Minor: (none currently)

    Args:
        package: The packager output dict (ship_package)
        decomposer_output: Optional decomposer output dict for dependency consistency check

    Returns:
        Gate result dict
    """
    critical = {}
    major = {}
    minor = {}

    work_packages = package.get("work_packages", [])

    # --- Critical checks ---

    # 1. schema_compliant: Pydantic contract validation (契约笼子)
    pydantic_errors = []
    try:
        from domains.ship_pro.contracts.packager import ShipPackage
        ShipPackage(**package)
        schema_result = {"passed": True, "errors": []}
    except Exception as e:
        pydantic_errors = str(e)
        schema_result = {"passed": False, "errors": [pydantic_errors[:300]]}
    critical["schema_compliant"] = schema_result["passed"]

    # 1b. json_schema_compliant: validate against generated JSON Schema (契约笼子双重验证)
    json_schema_valid = False
    json_schema_errors = []
    schema_path = (
        Path(__file__).resolve().parents[1] / "schemas" / "ship_package_v3.schema.json"
    )
    if schema_path.exists():
        try:
            schema_data = json.loads(schema_path.read_text())
            result = check_schema_compliance(package, schema_data)
            json_schema_valid = result["passed"]
            json_schema_errors = result.get("errors", [])[:5]
        except Exception as e:
            json_schema_errors = [str(e)[:200]]
    else:
        # Schema file not generated yet — skip, don't fail
        json_schema_valid = True
        json_schema_errors = ["Schema file not found (skipped)"]
    critical["json_schema_compliant"] = json_schema_valid

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

    # 3. dependency_consistency: Packager 不应静默添加/删除依赖边
    if decomposer_output is not None:
        dep_consistency = check_dependency_consistency(package, decomposer_output)
        major["dependency_consistency"] = dep_consistency["consistent"]
        if not dep_consistency["consistent"]:
            major["dependency_consistency_details"] = {
                "new_dependencies": dep_consistency["new_dependencies"],
                "missing_dependencies": dep_consistency["missing_dependencies"],
            }
    # If decomposer_output not provided, skip this check (backward compatible)

    # --- V3 Extras Validation (format + anchoring, not semantic) ---
    wp_ids = {wp.get("id") for wp in work_packages}
    wp_module_ids = set()
    for wp in work_packages:
        mid = wp.get("module_id") or wp.get("id")
        if mid:
            wp_module_ids.add(mid)
    # Merge both sets for component anchoring
    all_ref_ids = wp_ids | wp_module_ids

    # api_conventions: format check
    api_conv = package.get("api_conventions")
    if api_conv is not None:
        from domains.ship_pro.contracts.ship_package_extras import ApiConventions
        try:
            ApiConventions(**api_conv)
            major["api_conventions_valid"] = True
        except Exception:
            major["api_conventions_valid"] = False
        # Confidence check: low → degrade to null
        if isinstance(api_conv, dict) and api_conv.get("confidence") == "low":
            major["api_conventions_valid"] = True  # valid format, but degraded
            # Caller should check confidence and treat as null
    else:
        major["api_conventions_valid"] = True  # optional field

    # integration_tests: format + component anchoring
    int_tests = package.get("integration_tests")
    if int_tests is not None:
        from domains.ship_pro.contracts.ship_package_extras import IntegrationTest
        tests_valid = True
        for test_data in int_tests:
            try:
                t = IntegrationTest(**test_data)
                # Component anchoring: each component must exist in WPs
                for comp in t.components:
                    if comp not in all_ref_ids:
                        tests_valid = False
                        break
            except Exception:
                tests_valid = False
                break
        major["integration_tests_valid"] = tests_valid
    else:
        major["integration_tests_valid"] = True  # optional

    # error_handling_principles: format check
    eh = package.get("error_handling_principles")
    if eh is not None:
        from domains.ship_pro.contracts.ship_package_extras import ErrorHandlingPrinciples
        try:
            ehp = ErrorHandlingPrinciples(**eh)
            # Category count <= WP count * 0.5
            max_cats = max(1, int(len(work_packages) * 0.5))
            major["error_handling_valid"] = len(ehp.exception_categories) <= max_cats
        except Exception:
            major["error_handling_valid"] = False
    else:
        major["error_handling_valid"] = True  # optional

    # environment: format check
    env = package.get("environment")
    if env is not None:
        from domains.ship_pro.contracts.ship_package_extras import EnvironmentSpec
        try:
            EnvironmentSpec(**env)
            major["environment_valid"] = True
        except Exception:
            major["environment_valid"] = False
    else:
        major["environment_valid"] = True  # optional

    # --- Decision ---
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        details = []
        if not critical["schema_compliant"]:
            details.append(f"Pydantic schema errors: {schema_result.get('errors', [])[:3]}")
        if not critical["json_schema_compliant"]:
            details.append(f"JSON Schema errors: {json_schema_errors[:3]}")
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


def gate_judge(judge_output: dict) -> dict:
    """
    Quality gate for Judge Worker output (V4.1).

    **AI Native 职责边界**:
    本函数只做格式/结构检查，不做语义判断。
    - ✅ 检查: verdict 是否存在且为合法枚举值
    - ✅ 检查: risks 是否非空数组
    - ✅ 检查: cross_validation / downstream_consumability 是否存在
    - ❌ 不判断: Judge 找出的 Top-3 风险是否真的最重要
    - ❌ 不判断: Judge 的推理是否合理
    - ❌ 不判断: downstream_consumability 评分是否准确
    
    Judge 的语义质量由 semantic-task (LLM) 评估，本 gate 不替代。

    Checks:
    - Critical: verdict_present, risks_present, cross_validation_present
    - Major: downstream_consumability_present, risks_have_severity
    """
    critical = {}
    major = {}
    minor = {}

    # Critical: verdict
    verdict = judge_output.get("verdict")
    critical["verdict_present"] = verdict in ("pass", "conditional", "fail")

    # Critical: risks array
    risks = judge_output.get("risks", [])
    critical["risks_present"] = isinstance(risks, list) and len(risks) > 0

    # Critical: cross_validation
    cv = judge_output.get("cross_validation", {})
    critical["cross_validation_present"] = isinstance(cv, dict) and len(cv) > 0

    # Major: downstream_consumability
    dc = judge_output.get("downstream_consumability", {})
    major["downstream_consumability_present"] = isinstance(dc, dict) and len(dc) > 0

    # Major: risks have severity
    risks_have_severity = True
    for r in risks:
        if isinstance(r, dict) and r.get("severity") not in ("critical", "major", "minor"):
            risks_have_severity = False
            break
    major["risks_have_severity"] = risks_have_severity and len(risks) > 0

    # Decision
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        feedback = f"Judge Gate FAIL: Critical checks failed: {', '.join(critical_failures)}"
    elif major_failures:
        decision = "CONDITIONAL"
        passed = True
        feedback = f"Judge Gate CONDITIONAL: Major checks failed: {', '.join(major_failures)}"
    else:
        decision = "PASS"
        passed = True
        feedback = "Judge output is structurally sound."

    return _make_result(passed, decision, critical, major, minor, feedback)


def gate_fixer(fixer_output: dict) -> dict:
    """
    Quality gate for Fixer Worker output (V4.1).

    **AI Native 职责边界**:
    本函数只做格式/结构检查，不做语义判断。
    - ✅ 检查: fixes 是否存在且是数组
    - ✅ 检查: updated_package 是否存在且是 dict
    - ✅ 检查: 每个 fix 都有必要字段
    - ❌ 不判断: 修复方案是否合理
    - ❌ 不判断: remaining_issues 是否应该被修复
    
    Fixer 的语义质量由 Judge 重新评估，本 gate 不替代。

    Checks:
    - Critical: fixes_present, updated_package_present
    - Major: fixes_have_required_fields, remaining_issues_valid
    """
    critical = {}
    major = {}
    minor = {}

    # Critical: fixes array
    fixes = fixer_output.get("fixes", [])
    critical["fixes_present"] = isinstance(fixes, list)

    # Critical: updated_package
    updated_package = fixer_output.get("updated_package", {})
    critical["updated_package_present"] = isinstance(updated_package, dict) and len(updated_package) > 0

    # Major: fixes have required fields
    fixes_have_fields = True
    required_fields = ["issue_id", "category", "fixed", "rationale"]
    for fix in fixes:
        if isinstance(fix, dict):
            if not all(field in fix for field in required_fields):
                fixes_have_fields = False
                break
        else:
            fixes_have_fields = False
            break
    major["fixes_have_required_fields"] = fixes_have_fields

    # Major: remaining_issues format (optional but if present must be valid)
    remaining = fixer_output.get("remaining_issues", [])
    if remaining:
        remaining_valid = isinstance(remaining, list) and all(
            isinstance(r, dict) and "issue_id" in r for r in remaining
        )
        major["remaining_issues_valid"] = remaining_valid
    else:
        major["remaining_issues_valid"] = True

    # Decision
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
        feedback = f"Fixer Gate FAIL: Critical checks failed: {', '.join(critical_failures)}"
    elif major_failures:
        decision = "CONDITIONAL"
        passed = True
        feedback = f"Fixer Gate CONDITIONAL: Major checks failed: {', '.join(major_failures)}"
    else:
        decision = "PASS"
        passed = True
        feedback = "Fixer output is structurally sound."

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
    for agent in ["architect", "decomposer", "specifier", "reviewer", "packager"]:
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

    # Gate 4: Reviewer
    if "reviewer" in data:
        result = gate_reviewer(data["reviewer"])
        icon = "✅" if result["decision"] == "PASS" else ("⚠️" if result["decision"] == "CONDITIONAL" else "❌")
        print(f"  {icon} Reviewer Gate: {result['decision']}")
        print(f"     Critical: {result['critical_results']}")
        print(f"     Major: {result['major_results']}")
        print(f"     Feedback: {result['feedback']}\n")

    # Gate 5: Packager
    if "packager" in data:
        decomposer_data = data.get("decomposer")
        result = gate_packager(data["packager"], decomposer_data)
        icon = "✅" if result["decision"] == "PASS" else ("⚠️" if result["decision"] == "CONDITIONAL" else "❌")
        print(f"  {icon} Packager Gate: {result['decision']}")
        print(f"     Critical: {result['critical_results']}")
        print(f"     Major: {result['major_results']}")
        print(f"     Feedback: {result['feedback']}\n")


if __name__ == "__main__":
    main()
