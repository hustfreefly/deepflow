#!/usr/bin/env python3
"""
Ship Pro V3 — L2 Code-Based Eval Checks

Deterministic pre-checks (<1s) that run before the Model-Based Reviewer (L3).
Catches hard structural issues in ship_package.json without LLM involvement.

Usage:
    python3 eval_code_checks.py path/to/ship_package.json
    python3 eval_code_checks.py path/to/ship_package.json --threshold 80
"""

import json
import re
import sys
import os
from collections import defaultdict
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 1. JSON Schema Compliance
# ---------------------------------------------------------------------------

# Expected schema definition (manual, no jsonschema dependency required)
SHIP_PACKAGE_SCHEMA = {
    "type": "object",
    "required": ["work_packages"],
    "properties": {
        "work_packages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "id", "title", "objective", "budget", "complexity",
                    "dependencies", "priority", "acceptance_criteria"
                ],
                "properties": {
                    "id": {"type": "string", "pattern": r"^WP-\d{3}$"},
                    "title": {"type": "string", "minLength": 1},
                    "objective": {"type": "string", "minLength": 1},
                    "budget": {"type": ["string", "number"]},
                    "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "dependencies": {"type": "array"},
                    "priority": {"type": ["string", "number"]},
                    "acceptance_criteria": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"}
                    },
                    # Optional fields
                    "model_tier": {"type": "string"},
                    "context_files": {"type": "array"},
                    "outputs": {"type": "array"},
                    "acceptance_tests": {"type": "array"},
                    "retry_policy": {"type": "object"},
                }
            }
        }
    }
}


def _validate_type(value: Any, expected_type: Any) -> bool:
    """Check if value matches expected JSON Schema type."""
    if isinstance(expected_type, list):
        return any(_validate_type(value, t) for t in expected_type)
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "array": list,
        "object": dict,
        "boolean": bool,
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return True
    return isinstance(value, expected)


def _validate_value(value: Any, schema: dict, path: str) -> list:
    """Recursively validate a value against a schema, returning error list."""
    errors = []

    # Type check
    if "type" in schema:
        if not _validate_type(value, schema["type"]):
            errors.append(f"{path}: expected type {schema['type']}, got {type(value).__name__}")
            return errors  # No point continuing if type is wrong

    # Enum check
    if "enum" in schema:
        if value not in schema["enum"]:
            errors.append(f"{path}: value {value!r} not in {schema['enum']}")

    # Pattern check (strings only)
    if "pattern" in schema and isinstance(value, str):
        if not re.match(schema["pattern"], value):
            errors.append(f"{path}: value {value!r} does not match pattern {schema['pattern']}")

    # MinLength check
    if "minLength" in schema and isinstance(value, str):
        if len(value) < schema["minLength"]:
            errors.append(f"{path}: string length {len(value)} < minLength {schema['minLength']}")

    # MinItems check
    if "minItems" in schema and isinstance(value, list):
        if len(value) < schema["minItems"]:
            errors.append(f"{path}: array length {len(value)} < minItems {schema['minItems']}")

    # Required fields (objects)
    if "required" in schema and isinstance(value, dict):
        for field in schema["required"]:
            if field not in value:
                errors.append(f"{path}: missing required field '{field}'")

    # Properties validation (objects)
    if "properties" in schema and isinstance(value, dict):
        for prop, prop_schema in schema["properties"].items():
            if prop in value:
                errors.extend(_validate_value(value[prop], prop_schema, f"{path}.{prop}"))

    # Items validation (arrays)
    if "items" in schema and isinstance(value, list):
        for i, item in enumerate(value):
            errors.extend(_validate_value(item, schema["items"], f"{path}[{i}]"))

    return errors


def check_schema_compliance(data: dict, schema: Optional[dict] = None) -> dict:
    """
    Check if ship_package.json conforms to the expected schema.

    Args:
        data: The parsed ship_package dict
        schema: Optional custom schema; defaults to SHIP_PACKAGE_SCHEMA

    Returns:
        {"passed": bool, "errors": [...], "field_completeness": float}
    """
    schema = schema or SHIP_PACKAGE_SCHEMA
    errors = _validate_value(data, schema, "$")

    # Calculate field completeness across all WPs
    required_wp_fields = [
        "id", "title", "objective", "budget", "complexity",
        "dependencies", "priority", "acceptance_criteria"
    ]
    optional_wp_fields = [
        "model_tier", "context_files", "outputs", "acceptance_tests", "retry_policy"
    ]
    all_fields = required_wp_fields + optional_wp_fields

    work_packages = data.get("work_packages", [])
    if not work_packages:
        return {
            "passed": False,
            "errors": ["No work_packages found"],
            "field_completeness": 0.0
        }

    total_fields = len(work_packages) * len(all_fields)
    present_fields = sum(
        1 for wp in work_packages for f in all_fields if f in wp
    )
    field_completeness = present_fields / total_fields if total_fields > 0 else 0.0

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "field_completeness": round(field_completeness, 3)
    }


# ---------------------------------------------------------------------------
# 2. AC Verifiability Scoring
# ---------------------------------------------------------------------------

# Signal patterns for each level
EXECUTABLE_SIGNALS = [
    r"npm\s+run\s+\S+",
    r"pytest\b",
    r"curl\s+",
    r"assert\b",
    r"cargo\s+test",
    r"go\s+test",
    r"python[3]?\s+\S+\.py",
    r"make\s+\S+",
    r"docker\s+(run|build)",
    r"git\s+(clone|checkout|diff)",
    r"<\s*\d+",        # numeric comparison: < 100
    r">\s*\d+",        # numeric comparison: > 50
    r"==\s*\S+",       # equality check
    r"!=\s*\S+",       # inequality check
    r"https?://\S+",   # specific URL
    r"exit\s+code\s+\d+",
    r"returns?\s+(true|false|\d+)",
    r"responds?\s+with\s+\d{3}",
]

CONDITION_SIGNALS = [
    r"\d+\s*ms\b",
    r"\d+\s*秒",
    r"\d+(\.\d+)?\s*%",
    r"\d+\s*次",
    r"\d+\s*MB\b",
    r"\d+\s*GB\b",
    r"\d+\s*KB\b",
    r"\d+\s*QPS\b",
    r"\d+\s*TPS\b",
    r"\d+\s*条/秒",
    r"响应时间\s*[<≤]\s*\d+",
    r"成功率\s*[>≥]\s*\d+",
    r"延迟\s*[<≤]\s*\d+",
    r"吞吐\s*[>≥]\s*\d+",
    r"覆盖[率率]\s*[>≥]\s*\d+",
    r"accuracy\s*[>≥]\s*\d+",
    r"latency\s*[<≤]\s*\d+",
    r"throughput\s*[>≥]\s*\d+",
]

VAGUE_PATTERNS = [
    r"功能实现完成",
    r"满足设计规格",
    r"集成验证通过",
    r"文档完成",
    r"测试通过",
    r"代码完成",
    r"正常[运工]作",
    r"符合[要期]",
    r"按[时要求]完成",
    r"功能正常",
    r"无[报bug]",
    r"works?\s+as\s+expected",
    r"meets?\s+(the\s+)?requirements?",
    r"functions?\s+correctly",
    r"properly\s+implemented",
    r"fully\s+functional",
    r"completed?\s+successfully",
]

# Pre-compile for performance
_EXEC_RE = [re.compile(p, re.IGNORECASE) for p in EXECUTABLE_SIGNALS]
_COND_RE = [re.compile(p, re.IGNORECASE) for p in CONDITION_SIGNALS]
_VAGUE_RE = [re.compile(p, re.IGNORECASE) for p in VAGUE_PATTERNS]


def score_ac_verifiability(ac_text: str) -> dict:
    """
    Score a single Acceptance Criterion's verifiability on a 4-level scale.

    Level 4 (100): Contains executable commands or specific numeric thresholds
    Level 3 (60):  Has specific conditions with units but no executable context
    Level 2 (30):  Mentions specific modules/tech but no quantification
    Level 1 (0):   Vague, subjective, or contradictory

    Returns:
        {"score": int, "level": int, "reason": str}
    """
    if not ac_text or not ac_text.strip():
        return {"score": 0, "level": 1, "reason": "Empty AC text"}

    text = ac_text.strip()

    # Level 4: executable signals
    for pattern in _EXEC_RE:
        if pattern.search(text):
            return {
                "score": 100,
                "level": 4,
                "reason": f"Contains executable/verifiable signal: {pattern.pattern}"
            }

    # Level 3: condition signals with units
    for pattern in _COND_RE:
        if pattern.search(text):
            return {
                "score": 60,
                "level": 3,
                "reason": f"Contains measurable condition: {pattern.pattern}"
            }

    # Level 1: vague patterns
    for pattern in _VAGUE_RE:
        if pattern.search(text):
            return {
                "score": 0,
                "level": 1,
                "reason": f"Vague/non-verifiable pattern: {pattern.pattern}"
            }

    # Level 2: has some specificity (technical terms, module names) but no numbers
    # Heuristic: contains English words of 4+ chars or Chinese technical terms
    tech_signals = [
        r"[A-Z][a-z]{3,}[A-Z]",     # CamelCase (className)
        r"[a-z_]+_[a-z_]{3,}",       # snake_case (module_name)
        r"\b(API|SDK|CLI|UI|DB|HTTP|REST|GraphQL|JWT|OAuth)\b",
        r"\b(database|server|client|module|component|service|endpoint|cache|queue)\b",
        r"\b(认证|授权|缓存|队列|数据库|服务端|客户端|接口|模块|组件)\b",
    ]
    for pattern in tech_signals:
        if re.search(pattern, text, re.IGNORECASE):
            return {
                "score": 30,
                "level": 2,
                "reason": f"Contains technical reference but no measurable criteria"
            }

    # Default: Level 1 — too generic
    return {
        "score": 0,
        "level": 1,
        "reason": "No verifiable signals detected; AC is too generic"
    }


def score_all_acs(work_packages: list) -> dict:
    """
    Score all ACs across all work packages and produce aggregate stats.

    Returns:
        {
            "mean_score": float,
            "distribution": {"L4": n, "L3": n, "L2": n, "L1": n},
            "weakest_acs": [{"wp_id": str, "ac_idx": int, "score": int, "text": str}],
            "passed": bool,
            "threshold": 80
        }
    """
    THRESHOLD = 80
    all_scores = []
    distribution = {"L4": 0, "L3": 0, "L2": 0, "L1": 0}
    weakest_acs = []

    for wp in work_packages:
        wp_id = wp.get("id", "unknown")
        acs = wp.get("acceptance_criteria", [])
        for idx, ac_text in enumerate(acs):
            result = score_ac_verifiability(ac_text)
            all_scores.append(result["score"])
            distribution[f"L{result['level']}"] += 1

            # Track weak ACs (score < 60)
            if result["score"] < 60:
                weakest_acs.append({
                    "wp_id": wp_id,
                    "ac_idx": idx,
                    "score": result["score"],
                    "text": ac_text[:100] + ("..." if len(ac_text) > 100 else ""),
                    "reason": result["reason"]
                })

    mean_score = sum(all_scores) / len(all_scores) if all_scores else 0.0

    # Sort weakest by score ascending
    weakest_acs.sort(key=lambda x: x["score"])

    return {
        "mean_score": round(mean_score, 1),
        "distribution": distribution,
        "weakest_acs": weakest_acs[:10],  # Top 10 weakest
        "passed": mean_score >= THRESHOLD,
        "threshold": THRESHOLD
    }


# ---------------------------------------------------------------------------
# 3. Dependency Graph Checks
# ---------------------------------------------------------------------------

def check_dependency_graph(work_packages: list) -> dict:
    """
    Check the dependency graph for structural issues.

    Checks:
    - Circular dependencies (DFS-based cycle detection)
    - Orphan nodes (no deps and not depended upon, when WP count > 1)
    - Invalid references (dependency IDs that don't exist)
    - Topological ordering (Kahn's algorithm)

    Returns:
        {
            "has_cycles": bool,
            "cycles": [...],
            "orphans": [...],
            "invalid_refs": [...],
            "topological_order": [...],
            "passed": bool
        }
    """
    wp_ids = {wp.get("id") for wp in work_packages}
    # Build adjacency list: edge from dependency -> dependent
    # i.e., if WP-002 depends on WP-001, edge is WP-001 -> WP-002
    adj = defaultdict(list)       # forward edges (dep -> dependents)
    reverse_adj = defaultdict(list)  # reverse edges (dependent -> deps)
    in_degree = defaultdict(int)

    # Initialize all nodes
    for wp_id in wp_ids:
        in_degree[wp_id] = in_degree.get(wp_id, 0)

    invalid_refs = []
    for wp in work_packages:
        wp_id = wp.get("id")
        deps = wp.get("dependencies", [])
        if not isinstance(deps, list):
            deps = []
        for dep_id in deps:
            if dep_id not in wp_ids:
                invalid_refs.append({"wp_id": wp_id, "invalid_dep": dep_id})
            else:
                adj[dep_id].append(wp_id)
                reverse_adj[wp_id].append(dep_id)
                in_degree[wp_id] = in_degree.get(wp_id, 0) + 1
                in_degree[dep_id] = in_degree.get(dep_id, 0)

    # --- Cycle detection using DFS ---
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {wp_id: WHITE for wp_id in wp_ids}
    parent = {wp_id: None for wp_id in wp_ids}
    cycles = []

    def dfs_cycle(node, path):
        color[node] = GRAY
        path.append(node)
        for neighbor in reverse_adj.get(node, []):  # follow dependency edges
            if color[neighbor] == GRAY:
                # Found a cycle — extract it
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                dfs_cycle(neighbor, path)
        path.pop()
        color[node] = BLACK

    for wp_id in sorted(wp_ids):
        if color[wp_id] == WHITE:
            dfs_cycle(wp_id, [])

    # --- Orphan detection ---
    orphans = []
    if len(wp_ids) > 1:
        for wp_id in wp_ids:
            has_deps = len(reverse_adj.get(wp_id, [])) > 0
            is_depended_on = len(adj.get(wp_id, [])) > 0
            if not has_deps and not is_depended_on:
                orphans.append(wp_id)

    # --- Topological sort (Kahn's algorithm) ---
    topo_order = []
    queue = sorted([n for n in wp_ids if in_degree.get(n, 0) == 0])
    temp_in_degree = dict(in_degree)

    while queue:
        node = queue.pop(0)
        topo_order.append(node)
        for neighbor in sorted(adj.get(node, [])):
            temp_in_degree[neighbor] -= 1
            if temp_in_degree[neighbor] == 0:
                queue.append(neighbor)
        queue.sort()  # Keep deterministic order

    # If topo_order doesn't include all nodes, there's a cycle
    if len(topo_order) < len(wp_ids):
        missing = wp_ids - set(topo_order)
        topo_order.extend(sorted(missing))  # Append remaining (in cycle)

    passed = (
        len(cycles) == 0
        and len(invalid_refs) == 0
        and len(orphans) == 0
    )

    return {
        "has_cycles": len(cycles) > 0,
        "cycles": cycles,
        "orphans": sorted(orphans),
        "invalid_refs": invalid_refs,
        "topological_order": topo_order,
        "passed": passed
    }


# ---------------------------------------------------------------------------
# 4. AC Deduplication Detection
# ---------------------------------------------------------------------------

def _char_ngrams(text: str, n: int = 3) -> set:
    """Extract character n-grams from text."""
    text = text.lower().strip()
    if len(text) < n:
        return {text}
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def check_ac_dedup(work_packages: list, threshold: float = 0.7) -> dict:
    """
    Detect duplicate or highly similar Acceptance Criteria across WPs.

    Uses Jaccard similarity on character trigrams.
    Pairs with similarity > threshold are flagged as duplicates.

    Returns:
        {
            "duplicate_pairs": [{"ac_a": {...}, "ac_b": {...}, "similarity": float}],
            "duplicate_rate": float,
            "passed": bool
        }
    """
    # Collect all ACs with their source location
    ac_list = []
    for wp in work_packages:
        wp_id = wp.get("id", "unknown")
        for idx, ac_text in enumerate(wp.get("acceptance_criteria", [])):
            if ac_text and ac_text.strip():
                ngrams = _char_ngrams(ac_text)
                ac_list.append({
                    "wp_id": wp_id,
                    "ac_idx": idx,
                    "text": ac_text.strip(),
                    "ngrams": ngrams
                })

    duplicate_pairs = []
    total_pairs = 0

    for i in range(len(ac_list)):
        for j in range(i + 1, len(ac_list)):
            total_pairs += 1
            sim = _jaccard_similarity(ac_list[i]["ngrams"], ac_list[j]["ngrams"])
            if sim > threshold:
                duplicate_pairs.append({
                    "ac_a": {
                        "wp_id": ac_list[i]["wp_id"],
                        "ac_idx": ac_list[i]["ac_idx"],
                        "text": ac_list[i]["text"][:80]
                    },
                    "ac_b": {
                        "wp_id": ac_list[j]["wp_id"],
                        "ac_idx": ac_list[j]["ac_idx"],
                        "text": ac_list[j]["text"][:80]
                    },
                    "similarity": round(sim, 3)
                })

    duplicate_rate = len(duplicate_pairs) / total_pairs if total_pairs > 0 else 0.0

    return {
        "duplicate_pairs": duplicate_pairs,
        "duplicate_rate": round(duplicate_rate, 4),
        "passed": len(duplicate_pairs) == 0
    }


# ---------------------------------------------------------------------------
# 5. Field Completeness Check
# ---------------------------------------------------------------------------

def check_field_completeness(work_packages: list) -> dict:
    """
    Check that each WP has all required and optional fields populated.

    Returns:
        {
            "completeness_rate": float,
            "missing_fields": {"WP-001": ["field1", ...], ...},
            "passed": bool,
            "wp_count": int,
            "fully_complete_count": int
        }
    """
    required_fields = [
        "id", "title", "objective", "budget", "complexity",
        "dependencies", "priority", "acceptance_criteria"
    ]
    optional_fields = [
        "model_tier", "context_files", "outputs",
        "acceptance_tests", "retry_policy"
    ]
    all_fields = required_fields + optional_fields

    missing_fields = {}
    fully_complete_count = 0

    for wp in work_packages:
        wp_id = wp.get("id", "unknown")
        missing = []
        for field in required_fields:
            if field not in wp:
                missing.append(field)
            elif wp[field] is None:
                missing.append(field)
            elif isinstance(wp[field], str) and wp[field].strip() == "":
                missing.append(field)
            elif isinstance(wp[field], list) and len(wp[field]) == 0:
                # Empty list for required field (except dependencies which can be empty)
                if field != "dependencies":
                    missing.append(field)

        if missing:
            missing_fields[wp_id] = missing
        else:
            fully_complete_count += 1

    wp_count = len(work_packages)
    completeness_rate = fully_complete_count / wp_count if wp_count > 0 else 0.0

    return {
        "completeness_rate": round(completeness_rate, 3),
        "missing_fields": missing_fields,
        "passed": len(missing_fields) == 0,
        "wp_count": wp_count,
        "fully_complete_count": fully_complete_count
    }


# ---------------------------------------------------------------------------
# 6. Comprehensive Check Entry Point
# ---------------------------------------------------------------------------

def run_all_checks(ship_package: dict) -> dict:
    """
    Run all L2 code-based checks on a ship_package.

    Returns:
        {
            "verdict": "pass" | "fail",
            "checks": {
                "schema_compliance": {...},
                "ac_verifiability": {...},
                "dependency_graph": {...},
                "ac_dedup": {...},
                "field_completeness": {...}
            },
            "summary": "human-readable summary string"
        }
    """
    work_packages = ship_package.get("work_packages", [])

    # Run all checks
    schema_result = check_schema_compliance(ship_package)
    ac_result = score_all_acs(work_packages)
    dep_result = check_dependency_graph(work_packages)
    dedup_result = check_ac_dedup(work_packages)
    field_result = check_field_completeness(work_packages)

    checks = {
        "schema_compliance": schema_result,
        "ac_verifiability": ac_result,
        "dependency_graph": dep_result,
        "ac_dedup": dedup_result,
        "field_completeness": field_result,
    }

    # Count passes
    passed_checks = sum(1 for c in checks.values() if c.get("passed", False))
    total_checks = len(checks)

    # Build issue list
    issues = []
    if not schema_result["passed"]:
        error_count = len(schema_result["errors"])
        issues.append(f"Schema violations ({error_count} errors)")
    if not ac_result["passed"]:
        issues.append(f"AC verifiability ({ac_result['mean_score']:.0f} < {ac_result['threshold']})")
    if not dep_result["passed"]:
        if dep_result["has_cycles"]:
            issues.append(f"Dependency cycles ({len(dep_result['cycles'])} found)")
        if dep_result["invalid_refs"]:
            issues.append(f"Invalid dependency refs ({len(dep_result['invalid_refs'])})")
        if dep_result["orphans"]:
            issues.append(f"Orphan WPs ({len(dep_result['orphans'])})")
    if not dedup_result["passed"]:
        issues.append(f"Duplicate ACs ({len(dedup_result['duplicate_pairs'])} pairs)")
    if not field_result["passed"]:
        issues.append(f"Incomplete fields ({field_result['wp_count'] - field_result['fully_complete_count']} WPs)")

    verdict = "pass" if passed_checks == total_checks else "fail"
    summary = f"{passed_checks}/{total_checks} passed"
    if issues:
        summary += f", {len(issues)} issue{'s' if len(issues) > 1 else ''}: " + "; ".join(issues)

    return {
        "verdict": verdict,
        "checks": checks,
        "summary": summary
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def format_report(result: dict) -> str:
    """Format check results into a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("  Ship Pro V3 — L2 Code-Based Eval Report")
    lines.append("=" * 60)
    lines.append("")

    verdict = result["verdict"].upper()
    verdict_icon = "✅" if verdict == "PASS" else "❌"
    lines.append(f"  Verdict: {verdict_icon}  {verdict}")
    lines.append(f"  Summary: {result['summary']}")
    lines.append("")

    checks = result["checks"]

    # Schema Compliance
    sc = checks["schema_compliance"]
    icon = "✅" if sc["passed"] else "❌"
    lines.append(f"  {icon} Schema Compliance")
    lines.append(f"     Field completeness: {sc['field_completeness']:.1%}")
    if sc["errors"]:
        for err in sc["errors"][:5]:
            lines.append(f"     ⚠  {err}")
        if len(sc["errors"]) > 5:
            lines.append(f"     ... and {len(sc['errors']) - 5} more errors")
    lines.append("")

    # AC Verifiability
    ac = checks["ac_verifiability"]
    icon = "✅" if ac["passed"] else "❌"
    lines.append(f"  {icon} AC Verifiability")
    lines.append(f"     Mean score: {ac['mean_score']:.1f} (threshold: {ac['threshold']})")
    dist = ac["distribution"]
    lines.append(f"     Distribution: L4={dist['L4']} L3={dist['L3']} L2={dist['L2']} L1={dist['L1']}")
    if ac["weakest_acs"]:
        lines.append(f"     Weakest ACs:")
        for weak in ac["weakest_acs"][:3]:
            lines.append(f"       [{weak['wp_id']} AC#{weak['ac_idx']}] score={weak['score']} — {weak['text'][:60]}")
    lines.append("")

    # Dependency Graph
    dg = checks["dependency_graph"]
    icon = "✅" if dg["passed"] else "❌"
    lines.append(f"  {icon} Dependency Graph")
    if dg["topological_order"]:
        lines.append(f"     Execution order: {' → '.join(dg['topological_order'])}")
    if dg["has_cycles"]:
        for cycle in dg["cycles"]:
            lines.append(f"     🔄 Cycle: {' → '.join(cycle)}")
    if dg["invalid_refs"]:
        for ref in dg["invalid_refs"]:
            lines.append(f"     ⚠  Invalid ref: {ref['wp_id']} → {ref['invalid_dep']}")
    if dg["orphans"]:
        lines.append(f"     👻 Orphans: {', '.join(dg['orphans'])}")
    lines.append("")

    # AC Dedup
    dd = checks["ac_dedup"]
    icon = "✅" if dd["passed"] else "❌"
    lines.append(f"  {icon} AC Deduplication")
    lines.append(f"     Duplicate pairs: {len(dd['duplicate_pairs'])}")
    lines.append(f"     Duplicate rate: {dd['duplicate_rate']:.2%}")
    if dd["duplicate_pairs"]:
        for pair in dd["duplicate_pairs"][:3]:
            lines.append(f"     📋 {pair['ac_a']['wp_id']}#{pair['ac_a']['ac_idx']} ↔ "
                        f"{pair['ac_b']['wp_id']}#{pair['ac_b']['ac_idx']} "
                        f"(sim={pair['similarity']:.2f})")
    lines.append("")

    # Field Completeness
    fc = checks["field_completeness"]
    icon = "✅" if fc["passed"] else "❌"
    lines.append(f"  {icon} Field Completeness")
    lines.append(f"     Complete WPs: {fc['fully_complete_count']}/{fc['wp_count']}")
    lines.append(f"     Completeness rate: {fc['completeness_rate']:.1%}")
    if fc["missing_fields"]:
        for wp_id, fields in list(fc["missing_fields"].items())[:5]:
            lines.append(f"     {wp_id}: missing {', '.join(fields)}")
    lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ship Pro V3 — L2 Code-Based Eval Checks"
    )
    parser.add_argument(
        "package_path",
        help="Path to ship_package.json"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted report"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=80,
        help="AC verifiability threshold (default: 80)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.package_path):
        print(f"Error: File not found: {args.package_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.package_path, "r", encoding="utf-8") as f:
            ship_package = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    result = run_all_checks(ship_package)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_report(result))

    # Exit code: 0 = pass, 1 = fail
    sys.exit(0 if result["verdict"] == "pass" else 1)


if __name__ == "__main__":
    main()
