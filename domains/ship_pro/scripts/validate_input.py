#!/usr/bin/env python3
"""
Validate and classify Ship Pro input format.

Analyzes a final_result.json file to:
1. Detect format variant (A/B/C)
2. Assess information sufficiency for each Ship Pro agent
3. Generate validation report with recommendations

Usage:
    python validate_input.py <input_path> [--output report.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# --- Format Detection ---

def detect_format(data: dict[str, Any]) -> str:
    """
    Detect Solution Pro output format variant.

    Format A (final_solution nested):
      - Architecture in final_solution.detailed_solution.architecture
      - Common in: Serenity Skills, smart resume, AI customer service

    Format B (top-level flat):
      - Architecture in top-level architecture field
      - Common in: cross-border AI, enterprise customer service

    Format C (minimal):
      - No architecture info, only metadata
      - Common in: dryrun, test cases
    """
    # Check Format A
    fs = data.get("final_solution", {})
    if isinstance(fs, dict):
        ds = fs.get("detailed_solution", {})
        if isinstance(ds, dict) and "architecture" in ds:
            return "A"

    # Check Format B
    if "architecture" in data and isinstance(data["architecture"], dict):
        return "B"

    # Default to Format C
    return "C"


def extract_architecture(data: dict[str, Any], fmt: str) -> dict[str, Any] | None:
    """Extract architecture information based on format."""
    if fmt == "A":
        fs = data.get("final_solution", {})
        ds = fs.get("detailed_solution", {})
        return ds.get("architecture")
    elif fmt == "B":
        return data.get("architecture")
    else:
        return None


# --- Sufficiency Assessment ---

AGENT_REQUIREMENTS = {
    "architect": {
        "required_fields": ["executive_summary", "final_solution"],
        "optional_fields": ["architecture", "requirements_traceability_matrix"],
        "min_content_length": 500,
        "description": "Needs executive summary and solution overview to extract architecture"
    },
    "decomposer": {
        "required_fields": ["executive_summary"],
        "optional_fields": ["architecture", "modules"],
        "min_content_length": 1000,
        "description": "Needs architecture with modules/components to create work packages"
    },
    "specifier": {
        "required_fields": ["executive_summary"],
        "optional_fields": ["requirements", "constraints"],
        "min_content_length": 1500,
        "description": "Needs requirements and constraints to write acceptance tests"
    },
    "reviewer": {
        "required_fields": ["executive_summary"],
        "optional_fields": ["quality_assurance"],
        "min_content_length": 800,
        "description": "Needs solution details to perform quality review"
    },
    "packager": {
        "required_fields": ["executive_summary"],
        "optional_fields": [],
        "min_content_length": 300,
        "description": "Needs minimal info, assembles outputs from previous agents"
    },
}


def assess_sufficiency(data: dict[str, Any], fmt: str) -> dict[str, Any]:
    """
    Assess information sufficiency for each Ship Pro agent.

    Returns a dict with:
      - agent_name: {
          "sufficient": bool,
          "missing_required": list[str],
          "missing_optional": list[str],
          "content_length": int,
          "recommendation": str
        }
    """
    results = {}
    content_str = json.dumps(data)
    content_length = len(content_str)

    for agent, reqs in AGENT_REQUIREMENTS.items():
        missing_required = []
        missing_optional = []

        # Check required fields
        for field in reqs["required_fields"]:
            if field not in data:
                missing_required.append(field)

        # Check optional fields
        for field in reqs["optional_fields"]:
            if field not in data:
                missing_optional.append(field)

        # Check content length
        length_ok = content_length >= reqs["min_content_length"]

        # Determine sufficiency
        sufficient = len(missing_required) == 0 and length_ok

        # Generate recommendation
        if sufficient:
            recommendation = "✅ Sufficient information available"
        elif missing_required:
            recommendation = f"❌ Missing required fields: {', '.join(missing_required)}"
        elif not length_ok:
            recommendation = f"⚠️ Content too short ({content_length} chars, need {reqs['min_content_length']})"
        else:
            recommendation = "⚠️ Some optional fields missing, but can proceed"

        results[agent] = {
            "sufficient": sufficient,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "content_length": content_length,
            "min_required": reqs["min_content_length"],
            "recommendation": recommendation,
            "description": reqs["description"],
        }

    return results


# --- Validation Report ---

def generate_report(
    input_path: str,
    data: dict[str, Any],
    fmt: str,
    sufficiency: dict[str, Any]
) -> dict[str, Any]:
    """Generate comprehensive validation report."""
    # Count overall sufficiency
    sufficient_count = sum(1 for v in sufficiency.values() if v["sufficient"])
    total_agents = len(sufficiency)

    # Overall assessment
    if sufficient_count == total_agents:
        overall = "✅ All agents have sufficient information"
        status = "PASS"
    elif sufficient_count >= total_agents * 0.6:
        overall = f"⚠️ {sufficient_count}/{total_agents} agents ready, others may need manual input"
        status = "PARTIAL"
    else:
        overall = f"❌ Only {sufficient_count}/{total_agents} agents ready, input too sparse"
        status = "FAIL"

    return {
        "input_path": input_path,
        "format": fmt,
        "format_description": {
            "A": "Final solution nested (architecture in final_solution.detailed_solution.architecture)",
            "B": "Top-level flat (architecture at top level)",
            "C": "Minimal (no architecture info)",
        }.get(fmt, "Unknown"),
        "status": status,
        "overall_assessment": overall,
        "agent_sufficiency": sufficiency,
        "summary": {
            "sufficient_agents": sufficient_count,
            "total_agents": total_agents,
            "missing_architecture": fmt == "C",
        },
    }


# --- Main ---

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python validate_input.py <input_path> [--output report.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = None

    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    # Load input
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading {input_path}: {e}")
        sys.exit(1)

    # Detect format
    fmt = detect_format(data)

    # Assess sufficiency
    sufficiency = assess_sufficiency(data, fmt)

    # Generate report
    report = generate_report(input_path, data, fmt, sufficiency)

    # Output
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Report saved to {output_path}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
