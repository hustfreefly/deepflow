#!/usr/bin/env python3
"""
Packager Output Normalizer — Deterministic format fixes.
Fixes known LLM format deviations without changing semantics.
"""
import json
import sys
from pathlib import Path


def normalize_packager(packager_path: str) -> dict:
    """Apply deterministic format fixes to packager output."""
    with open(packager_path) as f:
        pkg = json.load(f)

    fixes = []

    # Fix 1: meta fields
    meta = pkg.get("meta", {})
    if "package_id" not in meta:
        meta["package_id"] = "SP-001"
        fixes.append("meta.package_id: added SP-001")
    if "generator" not in meta:
        meta["generator"] = {
            "agent": "ship-pro",
            "model": meta.get("model", "unknown"),
            "version": "3.1.0",
        }
        fixes.append("meta.generator: added default")
    if "input_format" not in meta:
        meta["input_format"] = "A_final_solution"
        fixes.append("meta.input_format: defaulted to A_final_solution")
    pkg["meta"] = meta

    # Fix 2: project_context
    if "project_context" not in pkg or not isinstance(pkg.get("project_context"), dict):
        pkg["project_context"] = {
            "problem_statement": "See architect output",
            "solution_overview": "See architect output",
            "architecture": {"style": "unknown", "components": []},
            "requirements_coverage": {"total": 0, "covered": 0, "coverage_rate": 0},
            "constraints": [],
            "known_gaps": [],
        }
        fixes.append("project_context: added default structure")

    # Fix 3: summary
    if not isinstance(pkg.get("summary"), dict):
        wps = pkg.get("work_packages", [])
        pkg["summary"] = {
            "total_wps": len(wps),
            "estimated_effort": "unknown",
            "total_token_budget": sum(
                wp.get("budget", {}).get("tokens", 0)
                if isinstance(wp.get("budget"), dict) else 0
                for wp in wps
            ),
            "total_time_minutes": sum(
                wp.get("budget", {}).get("time_minutes", 0)
                if isinstance(wp.get("budget"), dict) else 0
                for wp in wps
            ),
            "parallel_time_minutes": 0,
            "complexity_distribution": {
                "trivial": 0, "low": 0, "medium": 0, "high": 0, "critical": 0
            },
            "narrative": "See work_packages for details",
            "immediate_next_steps": [],
        }
        fixes.append("summary: rebuilt from work_packages")

    # Fix 4: dependency_graph list → dict
    dg = pkg.get("dependency_graph", {})
    if isinstance(dg, list):
        pkg["dependency_graph"] = {
            "edges": dg,
            "execution_order": _topo_sort(dg),
            "parallel_groups": [],
            "critical_path": [],
        }
        fixes.append("dependency_graph: list → dict with edges + execution_order")
    elif isinstance(dg, dict):
        if "edges" not in dg:
            dg["edges"] = []
            fixes.append("dependency_graph.edges: added empty list")
        if "execution_order" not in dg:
            dg["execution_order"] = _topo_sort(dg.get("edges", []))
            fixes.append("dependency_graph.execution_order: computed from edges")
        if "parallel_groups" not in dg:
            dg["parallel_groups"] = []
        if "critical_path" not in dg:
            dg["critical_path"] = []

    # Fix 5: work_packages model_tier normalization
    TIER_MAP = {
        "bailian/qwen3.7-max": "qwen-max",
        "bailian/qwen3.7-plus": "qwen-plus",
        "bailian/kimi-k2.5": "auto",
        "bailian/kimi-k2.6": "auto",
        "gpt-4": "gpt-4o",
        "gpt-4-turbo": "gpt-4o",
        "claude-3-opus": "claude-opus",
        "claude-3-sonnet": "claude-sonnet",
        "claude-3-haiku": "claude-haiku",
    }
    VALID_TIERS = {"claude-opus", "claude-sonnet", "claude-haiku",
                    "gpt-4o", "gpt-4o-mini", "qwen-max", "qwen-plus", "auto"}
    for wp in pkg.get("work_packages", []):
        tier = wp.get("model_tier", "auto")
        if tier not in VALID_TIERS:
            new_tier = TIER_MAP.get(tier, "auto")
            wp["model_tier"] = new_tier
            fixes.append(f"model_tier {wp.get('id')}: {tier} → {new_tier}")

    # Fix 6: budget normalization
    for wp in pkg.get("work_packages", []):
        budget = wp.get("budget")
        if isinstance(budget, (int, float)):
            wp["budget"] = {"tokens": int(budget), "time_minutes": 30, "max_retries": 3}
            fixes.append(f"budget {wp.get('id')}: number → object")
        elif isinstance(budget, dict):
            if "tokens" not in budget:
                budget["tokens"] = 50000
            if "time_minutes" not in budget:
                budget["time_minutes"] = 30
            if "max_retries" not in budget:
                budget["max_retries"] = 3

    # Fix 7: outputs normalization
    for wp in pkg.get("work_packages", []):
        outputs = wp.get("outputs", [])
        if outputs and isinstance(outputs[0], str):
            wp["outputs"] = [
                {"type": "file", "path": o, "description": ""}
                for o in outputs
            ]
            fixes.append(f"outputs {wp.get('id')}: string[] → object[]")

    # Fix 8: api_conventions normalization
    api = pkg.get("api_conventions")
    if api and isinstance(api, dict):
        # If naming_style is missing, add default
        if "naming_style" not in api:
            api["naming_style"] = "snake_case"
            fixes.append("api_conventions.naming_style: defaulted to snake_case")
        if "parameter_style" not in api:
            api["parameter_style"] = "dict"
            fixes.append("api_conventions.parameter_style: defaulted to dict")
        if "method_prefixes" not in api:
            api["method_prefixes"] = {}
        if "rules" not in api:
            api["rules"] = []
        if "examples" not in api:
            api["examples"] = []
        if "confidence" not in api:
            api["confidence"] = "high"

        # Fix rules: objects → strings
        rules = api.get("rules", [])
        if rules and isinstance(rules[0], dict):
            api["rules"] = [
                r.get("description", r.get("rule", r.get("text", str(r))))
                for r in rules
            ]
            fixes.append("api_conventions.rules: objects → strings")

        # Fix example field names: good→correct, bad→incorrect
        for ex in api.get("examples", []):
            if isinstance(ex, dict):
                if "good" in ex and "correct" not in ex:
                    ex["correct"] = ex.pop("good")
                if "bad" in ex and "incorrect" not in ex:
                    ex["incorrect"] = ex.pop("bad")
                if "explanation" not in ex:
                    ex["explanation"] = ""

        # Ensure rules is 5-8 items, examples is 3-5 items
        # If too few, pad with placeholders (confidence → low)
        if len(api.get("rules", [])) < 5:
            api["confidence"] = "low"
            fixes.append("api_conventions: too few rules → confidence=low")
        if len(api.get("examples", [])) < 3:
            # Pad with generic examples
            while len(api["examples"]) < 3:
                api["examples"].append({
                    "correct": f"module.method(param_dict={{...}})",
                    "incorrect": f"module.method('string_param')",
                    "explanation": "Use dict parameters",
                })
            fixes.append("api_conventions.examples: padded to 3")

    # Fix 9: integration_tests normalization
    tests = pkg.get("integration_tests")
    if isinstance(tests, dict):
        # Extract tests list from dict
        tests = tests.get("tests", [])
        pkg["integration_tests"] = tests
        fixes.append("integration_tests: dict → list")

    if isinstance(tests, list):
        for t in tests:
            if isinstance(t, dict):
                if "scenario" not in t:
                    t["scenario"] = t.get("description", "N/A")
                if "confidence" not in t:
                    t["confidence"] = "high"
                # Rename involves_wps → components
                if "involves_wps" in t and "components" not in t:
                    t["components"] = t.pop("involves_wps")

    # Fix 10: error_handling_principles normalization
    eh = pkg.get("error_handling_principles")
    if eh and isinstance(eh, dict):
        principles = eh.get("principles", [])
        if principles and isinstance(principles[0], dict):
            # Convert objects to strings
            eh["principles"] = [
                p.get("description", p.get("name", str(p)))
                for p in principles
            ]
            fixes.append("error_handling_principles.principles: objects → strings")

        cats = eh.get("exception_categories", [])
        if cats and isinstance(cats[0], dict):
            eh["exception_categories"] = [
                c.get("category", c.get("name", str(c)))
                for c in cats
            ]
            fixes.append("error_handling_principles.exception_categories: objects → strings")

        if "max_retry_limit" not in eh:
            eh["max_retry_limit"] = 5
        if "confidence" not in eh:
            eh["confidence"] = "high"

    # Fix 11: risk_register items must have title and likelihood
    for risk in pkg.get("risk_register", []):
        if isinstance(risk, dict):
            if "title" not in risk and "id" in risk:
                risk["title"] = risk.get("description", risk["id"])
            if "likelihood" not in risk:
                risk["likelihood"] = "possible"

    # Write normalized output
    with open(packager_path, "w") as f:
        json.dump(pkg, f, indent=2, ensure_ascii=False)

    return {"fixes_applied": len(fixes), "fixes": fixes, "output_path": packager_path}


def _topo_sort(edges: list) -> list:
    """Topological sort from edge list."""
    adj = {}
    in_deg = {}
    all_ids = set()
    for e in edges:
        if not isinstance(e, dict):
            continue
        src, tgt = e.get("from", ""), e.get("to", "")
        if not src or not tgt:
            continue
        # "from" depends on "to" → to must come before from
        adj.setdefault(tgt, []).append(src)
        in_deg[src] = in_deg.get(src, 0) + 1
        in_deg.setdefault(tgt, 0)
        all_ids.add(src)
        all_ids.add(tgt)

    order = []
    queue = sorted([n for n in all_ids if in_deg.get(n, 0) == 0])
    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in sorted(adj.get(node, [])):
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)
        queue.sort()
    return order


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: normalize_packager.py <packager_output_path>")
        sys.exit(1)

    result = normalize_packager(sys.argv[1])
    print(json.dumps(result, indent=2))
