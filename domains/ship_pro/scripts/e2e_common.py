#!/usr/bin/env python3
# ---
# id: ship_pro/e2e_common
# version: "3.0.0"
# component: ship_pro
# updated: "2026-06-19"
# status: active
# ---
"""
Ship Pro V3 — E2E Test Shared Constants and Helpers

Shared by e2e_prepare, e2e_validate, e2e_report, and e2e_test.
"""

import json
import hashlib
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
DOMAIN_DIR = SCRIPT_DIR.parent
PROMPTS_DIR = DOMAIN_DIR / "prompts"
EVAL_SCRIPT = DOMAIN_DIR / "eval" / "eval_code_checks.py"
SCHEMA_FILE = DOMAIN_DIR / "schemas" / "ship_package_v3.schema.json"

AGENTS: list[str] = ["architect", "decomposer", "specifier", "reviewer", "packager"]

AGENT_DEPS: dict[str, list[str]] = {
    "architect": [],
    "decomposer": ["architect"],
    "specifier": ["architect", "decomposer"],
    "reviewer": ["architect", "decomposer", "specifier"],
    "packager": ["architect", "specifier", "reviewer"],
}

AGENT_MODELS: dict[str, str] = {
    "architect": "strong",
    "decomposer": "strong",
    "specifier": "strong",
    "reviewer": "different",
    "packager": "fast",
}

AGENT_TIMEOUTS: dict[str, int] = {
    "architect": 300,
    "decomposer": 300,
    "specifier": 300,
    "reviewer": 300,
    "packager": 180,
}

# Validation thresholds
THRESHOLDS: dict[str, float] = {
    "architect_module_recall": 0.90,
    "specifier_ac_verifiability": 70,
    "specifier_field_completeness": 0.90,
    "decomposer_module_coverage": 0.90,
}

STANDARD_CASES: list[dict[str, str]] = [
    {
        "name": "case1_ai_customer_service",
        "description": "Format B, 12 components — Enterprise AI customer service system",
        "input": "~/.openclaw/workspace/.deepflow/blackboard/设计一个企业级AI智能客服系统_支持多轮_architecture_87d026ce/final_result.json",
    },
    {
        "name": "case2_smart_resume",
        "description": "Format A, 8 components — Smart resume generation system",
        "input": "~/.openclaw/workspace/.deepflow/blackboard/智能简历生成系统_architecture_d99f733a/final_result.json",
    },
    {
        "name": "case3_single_module",
        "description": "Format A, 1 component — Simple TODO app (boundary case)",
        "input": "~/.openclaw/workspace/.deepflow/blackboard/TC09_单模块TODO应用_architecture_simple/final_result.json",
    },
]


# ---------------------------------------------------------------------------
# Format Detection
# ---------------------------------------------------------------------------

def detect_format(data: dict) -> str:
    """Detect input format type (A/B/C/D)."""
    if "final_solution" in data:
        return "A"
    elif "project" in data and "architecture" in data:
        return "B"
    elif "pipeline_summary" in data or "executive_summary" in data:
        return "C"
    else:
        return "D"


def count_modules(data: dict, fmt: str) -> int:
    """Count modules in the input data."""
    if fmt == "A":
        try:
            comps = data["final_solution"]["detailed_solution"]["architecture"].get("components", [])
            return len(comps)
        except (KeyError, TypeError):
            return 0
    elif fmt == "B":
        arch = data.get("architecture", {})
        if isinstance(arch, dict):
            comps = arch.get("components", arch.get("core_components", arch.get("layers", [])))
            return len(comps) if isinstance(comps, list) else 0
        return 0
    return 0


# ---------------------------------------------------------------------------
# Prompt Loading
# ---------------------------------------------------------------------------

def load_prompt(agent_name: str) -> str:
    """Load Agent prompt template."""
    prompt_file = PROMPTS_DIR / f"{agent_name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_file}")
    return prompt_file.read_text()


def compute_prompt_sha(agent_name: str) -> str:
    """Compute SHA256 of prompt file."""
    prompt_file = PROMPTS_DIR / f"{agent_name}.md"
    return hashlib.sha256(prompt_file.read_bytes()).hexdigest()
