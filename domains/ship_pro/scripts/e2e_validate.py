#!/usr/bin/env python3
# ---
# id: ship_pro/e2e_validate
# version: "3.0.0"
# component: ship_pro
# updated: "2026-06-19"
# status: active
# ---
"""
Ship Pro V3 — E2E Test Validate Command

Validates all Agent outputs in a test case directory.

Usage:
    python3 e2e_validate.py <output_dir>
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

# Import STAGE_PATH_REGISTRY for path resolution
import core.bootstrap
from domains.ship_pro.blackboard import STAGE_PATH_REGISTRY

from e2e_common import (
    AGENTS, DOMAIN_DIR, THRESHOLDS,
    detect_format, count_modules,
)


# ---------------------------------------------------------------------------
# Validation Functions
# ---------------------------------------------------------------------------

def validate_blueprint(bp: dict, input_data: dict, fmt: str) -> dict:
    """Validate Architect output (blueprint.json)."""
    results: dict[str, Any] = {"agent": "architect", "checks": [], "passed": True}

    has_modules = "modules" in bp or "components" in bp.get("architecture", {})
    has_arch = "architecture" in bp or "modules" in bp
    results["checks"].append({
        "name": "structure_valid", "passed": has_modules or has_arch,
        "detail": f"Has modules: {has_modules}, Has architecture: {has_arch}",
    })

    expected_count = count_modules(input_data, fmt)
    if "modules" in bp:
        actual_count = len(bp["modules"])
    elif "architecture" in bp and isinstance(bp["architecture"], dict):
        arch = bp["architecture"]
        actual_count = len(arch.get("components", arch.get("core_components", arch.get("layers", []))))
    else:
        actual_count = 0
    recall = actual_count / expected_count if expected_count > 0 else 0.0
    results["checks"].append({
        "name": "module_recall", "passed": recall >= THRESHOLDS["architect_module_recall"],
        "detail": f"Expected >={expected_count} modules, found {actual_count}, recall={recall:.2%}", "value": recall,
    })

    modules = bp.get("modules", [])
    if not modules and "architecture" in bp and isinstance(bp["architecture"], dict):
        arch = bp["architecture"]
        modules = arch.get("components", arch.get("core_components", arch.get("layers", [])))
    empty = sum(1 for m in modules if not m.get("name") and not m.get("id"))
    results["checks"].append({
        "name": "no_empty_modules", "passed": empty == 0,
        "detail": f"Empty modules: {empty}/{len(modules)}",
    })

    module_ids = {m.get("id") for m in modules if m.get("id")}
    deps = bp.get("dependencies", [])
    if not deps and "architecture" in bp and isinstance(bp["architecture"], dict):
        deps = bp["architecture"].get("dependencies", [])
    invalid = [d for d in deps if isinstance(d, dict) and (d.get("from") not in module_ids or d.get("to") not in module_ids)]
    results["checks"].append({
        "name": "valid_dependencies", "passed": len(invalid) == 0,
        "detail": f"Invalid dependency refs: {len(invalid)}",
    })

    results["checks"].append({"name": "meta_present", "passed": "_meta" in bp,
                               "detail": "Has _meta field" if "_meta" in bp else "Missing _meta field"})
    results["passed"] = all(c["passed"] for c in results["checks"])
    return results


def validate_wp_structure(ws: dict, blueprint: dict) -> dict:
    """Validate Decomposer output (wp_structure.json)."""
    results: dict[str, Any] = {"agent": "decomposer", "checks": [], "passed": True}
    work_packages = ws.get("work_packages", [])

    results["checks"].append({"name": "wp_count_positive", "passed": len(work_packages) > 0,
                               "detail": f"WP count: {len(work_packages)}"})

    bp_modules = blueprint.get("modules", [])
    if not bp_modules and "architecture" in blueprint:
        arch = blueprint["architecture"]
        if isinstance(arch, dict):
            bp_modules = arch.get("components", arch.get("core_components", arch.get("layers", [])))
    module_ids = {m.get("id") for m in bp_modules if m.get("id")}
    covered: set[str] = set()
    for wp in work_packages:
        covered.update(wp.get("source_modules", []))
    coverage = len(covered & module_ids) / len(module_ids) if module_ids else 1.0
    results["checks"].append({
        "name": "module_coverage", "passed": coverage >= THRESHOLDS["decomposer_module_coverage"],
        "detail": f"Coverage: {coverage:.2%} ({len(covered & module_ids)}/{len(module_ids)}), uncovered: {module_ids - covered}", "value": coverage,
    })

    # Cycle detection
    wp_ids = {wp.get("id") for wp in work_packages}
    adj: dict[str, list] = {wp.get("id"): wp.get("dependencies", []) for wp in work_packages}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {wid: WHITE for wid in wp_ids}
    has_cycle = False

    def dfs(node: str) -> None:
        nonlocal has_cycle
        color[node] = GRAY
        for nb in adj.get(node, []):
            if nb not in color:
                continue
            if color[nb] == GRAY:
                has_cycle = True; return
            if color[nb] == WHITE:
                dfs(nb)
        color[node] = BLACK

    for wid in wp_ids:
        if color[wid] == WHITE:
            dfs(wid)
    results["checks"].append({"name": "no_circular_deps", "passed": not has_cycle,
                               "detail": "No circular dependencies" if not has_cycle else "Circular dependency detected"})

    no_rat = [wp.get("id") for wp in work_packages if not wp.get("rationale")]
    results["checks"].append({"name": "all_wps_have_rationale", "passed": len(no_rat) == 0,
                               "detail": f"WPs without rationale: {no_rat}" if no_rat else "All WPs have rationale"})
    results["checks"].append({"name": "meta_present", "passed": "_meta" in ws,
                               "detail": "Has _meta field" if "_meta" in ws else "Missing _meta field"})
    results["passed"] = all(c["passed"] for c in results["checks"])
    return results


def validate_wp_specs(specs: dict, blueprint: dict, wp_structure: dict) -> dict:
    """Validate Specifier output (wp_specs.json)."""
    results: dict[str, Any] = {"agent": "specifier", "checks": [], "passed": True}
    work_packages = specs.get("work_packages", [])

    expected = len(wp_structure.get("work_packages", []))
    results["checks"].append({"name": "wp_count_matches", "passed": len(work_packages) == expected,
                               "detail": f"Expected {expected} WPs, found {len(work_packages)}"})

    try:
        from domains.ship_pro.eval.eval_code_checks import score_all_acs, check_field_completeness
        ac_result = score_all_acs(work_packages)
        results["checks"].append({
            "name": "ac_verifiability",
            "passed": ac_result["mean_score"] >= THRESHOLDS["specifier_ac_verifiability"],
            "detail": f"Mean AC score: {ac_result['mean_score']:.1f} (threshold: {THRESHOLDS['specifier_ac_verifiability']})",
            "value": ac_result["mean_score"], "distribution": ac_result["distribution"],
        })
        field_result = check_field_completeness(work_packages)
        results["checks"].append({
            "name": "field_completeness",
            "passed": field_result["completeness_rate"] >= THRESHOLDS["specifier_field_completeness"],
            "detail": f"Completeness: {field_result['completeness_rate']:.2%} ({field_result['fully_complete_count']}/{field_result['wp_count']})",
            "value": field_result["completeness_rate"],
        })
    except ImportError as e:
        results["checks"].append({"name": "eval_import", "passed": False, "detail": f"Failed to import eval_code_checks: {e}"})

    no_ac = [wp.get("id") for wp in work_packages if not wp.get("acceptance_criteria")]
    results["checks"].append({"name": "all_wps_have_ac", "passed": len(no_ac) == 0,
                               "detail": f"WPs without AC: {no_ac}" if no_ac else "All WPs have acceptance_criteria"})
    results["checks"].append({"name": "meta_present", "passed": "_meta" in specs,
                               "detail": "Has _meta field" if "_meta" in specs else "Missing _meta field"})
    results["passed"] = all(c["passed"] for c in results["checks"])
    return results


def validate_review_report(rr: dict, specs: dict, blueprint: dict) -> dict:
    """Validate Reviewer output (review_report.json)."""
    results: dict[str, Any] = {"agent": "reviewer", "checks": [], "passed": True}
    verdict = rr.get("verdict", "")
    results["checks"].append({"name": "valid_verdict", "passed": verdict in ("PASS", "FAIL", "PASS_WITH_CONDITIONS"),
                               "detail": f"Verdict: {verdict}"})

    if verdict in ("PASS", "PASS_WITH_CONDITIONS"):
        results["checks"].append({"name": "quality_metrics_present", "passed": "quality_metrics" in rr,
                                   "detail": "Has quality_metrics" if "quality_metrics" in rr else "Missing quality_metrics for PASS verdict"})
    if verdict == "FAIL":
        issues = rr.get("issues", [])
        no_target = [i for i in issues if isinstance(i, dict) and "target_agent" not in i]
        results["checks"].append({"name": "fail_has_target_agent", "passed": len(no_target) == 0,
                                   "detail": f"Issues without target_agent: {len(no_target)}"})

    results["checks"].append({"name": "has_summary", "passed": bool(rr.get("summary")),
                               "detail": "Has summary" if rr.get("summary") else "Missing summary"})
    results["checks"].append({"name": "meta_present", "passed": "_meta" in rr,
                               "detail": "Has _meta field" if "_meta" in rr else "Missing _meta field"})
    results["checks"].append({"name": "round_present", "passed": "round" in rr,
                               "detail": f"Round: {rr.get('round', 'N/A')}"})
    results["passed"] = all(c["passed"] for c in results["checks"])
    return results


def validate_ship_package(sp: dict, specs: dict, review_report: dict) -> dict:
    """Validate Packager output (ship_package.json)."""
    results: dict[str, Any] = {"agent": "packager", "checks": [], "passed": True}

    try:
        from domains.ship_pro.eval.eval_code_checks import run_all_checks
        ev = run_all_checks(sp)
        sc = ev["checks"]["schema_compliance"]
        results["checks"].append({"name": "schema_compliance", "passed": sc["passed"],
                                   "detail": f"Field completeness: {sc['field_completeness']:.2%}, errors: {len(sc['errors'])}",
                                   "errors": sc["errors"][:5]})
        ac = ev["checks"]["ac_verifiability"]
        results["checks"].append({"name": "ac_verifiability", "passed": ac["passed"],
                                   "detail": f"Mean score: {ac['mean_score']:.1f}, distribution: {ac['distribution']}"})
        dg = ev["checks"]["dependency_graph"]
        results["checks"].append({"name": "dependency_graph", "passed": dg["passed"],
                                   "detail": f"Cycles: {dg['has_cycles']}, orphans: {len(dg['orphans'])}, invalid_refs: {len(dg['invalid_refs'])}"})
        results["checks"].append({"name": "eval_overall", "passed": ev["verdict"] == "pass",
                                   "detail": f"Eval verdict: {ev['verdict']}, {ev['summary']}"})
    except ImportError as e:
        results["checks"].append({"name": "eval_import", "passed": False, "detail": f"Failed to import eval_code_checks: {e}"})

    missing = [f for f in ["schema_version", "work_packages", "meta"] if f not in sp]
    results["checks"].append({"name": "required_fields", "passed": len(missing) == 0,
                               "detail": f"Missing fields: {missing}" if missing else "All required fields present"})
    results["checks"].append({"name": "work_packages_non_empty", "passed": len(sp.get("work_packages", [])) > 0,
                               "detail": f"WP count: {len(sp.get('work_packages', []))}"})
    results["passed"] = all(c["passed"] for c in results["checks"])
    return results


# ---------------------------------------------------------------------------
# Validate Command
# ---------------------------------------------------------------------------

def _load_outputs(bb_dir: Path) -> dict:
    """Load all agent outputs from blackboard directory using STAGE_PATH_REGISTRY."""
    outputs: dict[str, Any] = {}
    # Map agent names to STAGE_PATH_REGISTRY keys
    agent_files = {
        "architect": STAGE_PATH_REGISTRY["architect"],
        "decomposer": STAGE_PATH_REGISTRY["decomposer"],
        "specifier": STAGE_PATH_REGISTRY["specifier"],
        "reviewer": STAGE_PATH_REGISTRY["reviewer"],
        "packager": STAGE_PATH_REGISTRY["ship_package"],
    }
    for agent, rel_path in agent_files.items():
        filepath = bb_dir / rel_path
        if filepath.exists():
            try:
                with open(filepath) as f:
                    outputs[agent] = json.load(f)
            except json.JSONDecodeError as e:
                outputs[agent] = {"_error": f"Invalid JSON: {e}"}
        else:
            outputs[agent] = None
    return outputs


def _err_result(agent: str, name: str, detail: str) -> dict:
    """Build a single-check failure result."""
    return {"agent": agent, "passed": False, "checks": [{"name": name, "passed": False, "detail": detail}]}


def validate(output_dir: Path) -> dict:
    """Validate all Agent outputs in a test case directory."""
    # output_dir is now the blackboard directory itself (not parent/blackboard)
    bb_dir = output_dir
    if not bb_dir.exists():
        print(f"❌ Blackboard directory not found: {bb_dir}")
        return {"passed": False, "error": "No blackboard directory"}

    plan_path = output_dir / "run_plan.json"
    run_plan: dict = {}
    if plan_path.exists():
        with open(plan_path) as f:
            run_plan = json.load(f)

    input_path = bb_dir / STAGE_PATH_REGISTRY["input"]
    if input_path.exists():
        with open(input_path) as f:
            input_data = json.load(f)
        fmt = detect_format(input_data)
    else:
        input_data = {}
        fmt = run_plan.get("input_format", "unknown")

    outputs = _load_outputs(bb_dir)
    agent_results: dict[str, dict] = {}

    def _ok(a: str) -> bool:
        return outputs.get(a) is not None and "_error" not in (outputs.get(a) or {})

    # Architect
    if _ok("architect"):
        agent_results["architect"] = validate_blueprint(outputs["architect"], input_data, fmt)
    else:
        detail = outputs["architect"]["_error"] if _ok("architect") is False and outputs.get("architect") and "_error" in outputs["architect"] else "blueprint.json not found"
        agent_results["architect"] = _err_result("architect", "output_exists" if not outputs.get("architect") else "json_valid", detail)

    # Decomposer
    if _ok("decomposer") and _ok("architect"):
        agent_results["decomposer"] = validate_wp_structure(outputs["decomposer"], outputs["architect"])
    else:
        agent_results["decomposer"] = _err_result("decomposer", "prerequisite", "Missing prerequisite outputs")

    # Specifier
    if _ok("specifier") and _ok("decomposer") and _ok("architect"):
        agent_results["specifier"] = validate_wp_specs(outputs["specifier"], outputs["architect"], outputs["decomposer"])
    else:
        agent_results["specifier"] = _err_result("specifier", "prerequisite", "Missing prerequisite outputs")

    # Reviewer
    if _ok("reviewer") and _ok("specifier") and _ok("architect"):
        agent_results["reviewer"] = validate_review_report(outputs["reviewer"], outputs["specifier"], outputs["architect"])
    else:
        agent_results["reviewer"] = _err_result("reviewer", "prerequisite", "Missing prerequisite outputs")

    # Packager
    if _ok("packager") and _ok("specifier") and _ok("reviewer"):
        agent_results["packager"] = validate_ship_package(outputs["packager"], outputs["specifier"], outputs["reviewer"])
    else:
        agent_results["packager"] = _err_result("packager", "prerequisite", "Missing prerequisite outputs")

    passed_agents = sum(1 for r in agent_results.values() if r.get("passed"))
    validation_results: dict[str, Any] = {
        "run_id": run_plan.get("run_id", "unknown"),
        "input_format": fmt,
        "output_dir": str(output_dir),
        "agent_results": agent_results,
        "summary": {
            "passed_agents": passed_agents, "total_agents": len(AGENTS),
            "all_passed": passed_agents == len(AGENTS),
            "timestamp": datetime.now().isoformat(),
        },
    }

    report_path = output_dir / "validation_report.json"
    with open(report_path, "w") as f:
        json.dump(validation_results, f, indent=2, ensure_ascii=False)
    print(f"✅ Validation report written to: {report_path}")
    print(f"📊 Result: {passed_agents}/{len(AGENTS)} agents passed")
    return validation_results


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    command = sys.argv[1]
    if command == "validate":
        if len(sys.argv) < 3:
            print("用法: python3 e2e_validate.py validate <output_dir>")
            sys.exit(1)
        validate(Path(sys.argv[2]))
    else:
        validate(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
