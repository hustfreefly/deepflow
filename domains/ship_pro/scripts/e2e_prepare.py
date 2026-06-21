#!/usr/bin/env python3
# ---
# id: ship_pro/e2e_prepare
# version: "3.0.0"
# component: ship_pro
# updated: "2026-06-19"
# status: active
# ---
"""
Ship Pro V3 — E2E Test Prepare Command

Prepares test environments for the 5-Agent pipeline.

Usage:
    python3 e2e_prepare.py <final_result.json> <output_dir>
    python3 e2e_prepare.py prepare-all <cases_dir>
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from e2e_common import (
    AGENTS, AGENT_DEPS, AGENT_MODELS, AGENT_TIMEOUTS, THRESHOLDS,
    STANDARD_CASES, detect_format, count_modules, load_prompt, compute_prompt_sha,
)


# ---------------------------------------------------------------------------
# Task Prompt Generation
# ---------------------------------------------------------------------------

def build_architect_task(input_data: dict, fmt: str, run_id: str, bb_dir: str) -> dict:
    """Build Architect Agent task prompt."""
    prompt = load_prompt("architect")
    prompt_sha = compute_prompt_sha("architect")

    format_hint = f"\n\n**输入格式已预检测为 Format {fmt}**。请按照 Format {fmt} 的提取规则处理。"

    task = f"""## Agent: Architect

{prompt}
{format_hint}

## 输入数据

```json
{json.dumps(input_data, indent=2, ensure_ascii=False)}
```

## 运行信息

- run_id: {run_id}
- blackboard_dir: {bb_dir}
- 请将输出写入: {bb_dir}/blueprint.json
- prompt_sha: {prompt_sha}

## 输出要求

1. 输出必须是合法的 JSON，保存为 blueprint.json
2. 在 _meta 中记录 prompt_sha、model_id、run_id、round
3. 不要编造输入中不存在的信息
"""
    return {
        "agent": "architect",
        "task": task,
        "timeout_seconds": AGENT_TIMEOUTS["architect"],
        "model": AGENT_MODELS["architect"],
        "depends_on": AGENT_DEPS["architect"],
        "output_file": f"{bb_dir}/blueprint.json",
        "prompt_sha": prompt_sha,
    }


def build_decomposer_task(blueprint_path: str, run_id: str, bb_dir: str) -> dict:
    """Build Decomposer Agent task prompt."""
    prompt = load_prompt("decomposer")
    prompt_sha = compute_prompt_sha("decomposer")

    task = f"""## Agent: Decomposer

{prompt}

## 上游输出

### blueprint.json (Architect 输出)

```json
{{BLUEPRINT_PLACEHOLDER}}
```

## 运行信息

- run_id: {run_id}
- blackboard_dir: {bb_dir}
- 请将输出写入: {bb_dir}/wp_structure.json
- prompt_sha: {prompt_sha}

## 输出要求

1. 输出必须是合法的 JSON，保存为 wp_structure.json
2. 在 _meta 中记录 prompt_sha、model_id、run_id、round
3. 每个 WP 必须有 rationale
4. 确保所有模块都被至少一个 WP 覆盖
"""
    return {
        "agent": "decomposer",
        "task": task,
        "timeout_seconds": AGENT_TIMEOUTS["decomposer"],
        "model": AGENT_MODELS["decomposer"],
        "depends_on": AGENT_DEPS["decomposer"],
        "output_file": f"{bb_dir}/wp_structure.json",
        "input_files": [blueprint_path],
        "prompt_sha": prompt_sha,
    }


def build_specifier_task(blueprint_path: str, wp_structure_path: str,
                         run_id: str, bb_dir: str) -> dict:
    """Build Specifier Agent task prompt."""
    prompt = load_prompt("specifier")
    prompt_sha = compute_prompt_sha("specifier")

    task = f"""## Agent: Specifier

{prompt}

## 上游输出

### blueprint.json (Architect 输出)

```json
{{BLUEPRINT_PLACEHOLDER}}
```

### wp_structure.json (Decomposer 输出)

```json
{{WP_STRUCTURE_PLACEHOLDER}}
```

## 运行信息

- run_id: {run_id}
- blackboard_dir: {bb_dir}
- 请将输出写入: {bb_dir}/wp_specs.json
- prompt_sha: {prompt_sha}

## 输出要求

1. 输出必须是合法的 JSON，保存为 wp_specs.json
2. 每个 WP 必须有 acceptance_criteria（至少 2 条）
3. AC 必须包含可验证的条件（数值阈值或可执行命令优先）
4. 在 _meta 中记录 prompt_sha、model_id、run_id、round
"""
    return {
        "agent": "specifier",
        "task": task,
        "timeout_seconds": AGENT_TIMEOUTS["specifier"],
        "model": AGENT_MODELS["specifier"],
        "depends_on": AGENT_DEPS["specifier"],
        "output_file": f"{bb_dir}/wp_specs.json",
        "input_files": [blueprint_path, wp_structure_path],
        "prompt_sha": prompt_sha,
    }


def build_reviewer_task(blueprint_path: str, wp_specs_path: str,
                        run_id: str, bb_dir: str) -> dict:
    """Build Reviewer Agent task prompt."""
    prompt = load_prompt("reviewer")
    prompt_sha = compute_prompt_sha("reviewer")

    task = f"""## Agent: Reviewer

{prompt}

## 上游输出

### blueprint.json (Architect 输出)

```json
{{BLUEPRINT_PLACEHOLDER}}
```

### wp_specs.json (Specifier 输出)

```json
{{WP_SPECS_PLACEHOLDER}}
```

## L2 Code-Based 预检结果

运行 `python3 eval/eval_code_checks.py {bb_dir}/ship_package.json` 获取预检结果。
将预检结果作为审核参考，但你的价值在于 L3 语义级审核。

## 运行信息

- run_id: {run_id}
- blackboard_dir: {bb_dir}
- 请将输出写入: {bb_dir}/review_report.json
- prompt_sha: {prompt_sha}

## 输出要求

1. 输出必须是合法的 JSON，保存为 review_report.json
2. verdict 必须是 "PASS" 或 "FAIL"
3. 如果 FAIL，issues 中必须包含 target_agent 字段
4. 在 _meta 中记录 prompt_sha、model_id、run_id、round
"""
    return {
        "agent": "reviewer",
        "task": task,
        "timeout_seconds": AGENT_TIMEOUTS["reviewer"],
        "model": AGENT_MODELS["reviewer"],
        "depends_on": AGENT_DEPS["reviewer"],
        "output_file": f"{bb_dir}/review_report.json",
        "input_files": [blueprint_path, wp_specs_path],
        "prompt_sha": prompt_sha,
    }


def build_packager_task(blueprint_path: str, wp_specs_path: str,
                        review_report_path: str, run_id: str, bb_dir: str) -> dict:
    """Build Packager Agent task prompt."""
    prompt = load_prompt("packager")
    prompt_sha = compute_prompt_sha("packager")

    task = f"""## Agent: Packager

{prompt}

## 上游输出

### blueprint.json (Architect 输出)

```json
{{BLUEPRINT_PLACEHOLDER}}
```

### wp_specs.json (Specifier 输出)

```json
{{WP_SPECS_PLACEHOLDER}}
```

### review_report.json (Reviewer 输出)

```json
{{REVIEW_REPORT_PLACEHOLDER}}
```

## 运行信息

- run_id: {run_id}
- blackboard_dir: {bb_dir}
- 请将输出写入: {bb_dir}/ship_package.json 和 {bb_dir}/summary.md
- prompt_sha: {prompt_sha}

## 输出要求

1. ship_package.json 必须严格遵循 ship_package_v3.schema.json
2. summary.md 必须人类可读
3. 在 meta 中记录 prompt_sha、model_id、run_id
"""
    return {
        "agent": "packager",
        "task": task,
        "timeout_seconds": AGENT_TIMEOUTS["packager"],
        "model": AGENT_MODELS["packager"],
        "depends_on": AGENT_DEPS["packager"],
        "output_files": [f"{bb_dir}/ship_package.json", f"{bb_dir}/summary.md"],
        "input_files": [blueprint_path, wp_specs_path, review_report_path],
        "prompt_sha": prompt_sha,
    }


# ---------------------------------------------------------------------------
# Prepare Command
# ---------------------------------------------------------------------------

def prepare(input_path: Path, output_dir: Path) -> dict:
    """
    Prepare test environment for a single test case.

    Creates:
    - output_dir/blackboard/ — with input copied
    - output_dir/run_plan.json — complete task prompts for all agents
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load input
    with open(input_path) as f:
        input_data = json.load(f)

    fmt = detect_format(input_data)
    module_count = count_modules(input_data, fmt)
    run_id = f"e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fmt.lower()}"

    print(f"📋 Format: {fmt}, Modules: {module_count}, Run ID: {run_id}")

    # Create blackboard
    bb_dir = output_dir / "blackboard"
    bb_dir.mkdir(exist_ok=True)

    # Copy input to blackboard
    with open(bb_dir / "final_result.json", "w") as f:
        json.dump(input_data, f, indent=2, ensure_ascii=False)

    # Build paths
    blueprint_path = str(bb_dir / "blueprint.json")
    wp_structure_path = str(bb_dir / "wp_structure.json")
    wp_specs_path = str(bb_dir / "wp_specs.json")
    review_report_path = str(bb_dir / "review_report.json")

    # Build task prompts for each agent
    tasks: dict[str, dict] = {}
    tasks["architect"] = build_architect_task(input_data, fmt, run_id, str(bb_dir))
    tasks["decomposer"] = build_decomposer_task(blueprint_path, run_id, str(bb_dir))
    tasks["specifier"] = build_specifier_task(
        blueprint_path, wp_structure_path, run_id, str(bb_dir)
    )
    tasks["reviewer"] = build_reviewer_task(
        blueprint_path, wp_specs_path, run_id, str(bb_dir)
    )
    tasks["packager"] = build_packager_task(
        blueprint_path, wp_specs_path, review_report_path, run_id, str(bb_dir)
    )

    # Build run_plan
    run_plan = {
        "run_id": run_id,
        "input_format": fmt,
        "input_file": str(input_path),
        "module_count": module_count,
        "blackboard_dir": str(bb_dir),
        "agents": tasks,
        "execution_order": AGENTS,
        "generated_at": datetime.now().isoformat(),
        "validation_thresholds": THRESHOLDS,
    }

    # Write run_plan
    plan_path = output_dir / "run_plan.json"
    with open(plan_path, "w") as f:
        json.dump(run_plan, f, indent=2, ensure_ascii=False)

    print(f"✅ Run plan written to: {plan_path}")
    print(f"📁 Blackboard: {bb_dir}")
    print(f"📋 Execution order: {' → '.join(AGENTS)}")

    return run_plan


# ---------------------------------------------------------------------------
# Prepare All Standard Cases
# ---------------------------------------------------------------------------

def prepare_all_cases(base_output_dir: Path) -> list:
    """Prepare all 3 standard test cases."""
    base_output_dir.mkdir(parents=True, exist_ok=True)
    plans: list[dict] = []

    for case in STANDARD_CASES:
        print(f"\n{'='*50}")
        print(f"📦 Preparing: {case['name']}")
        print(f"   {case['description']}")
        print(f"{'='*50}")

        input_path = Path(os.path.expanduser(case["input"]))
        if not input_path.exists():
            print(f"❌ Input not found: {input_path}")
            continue

        output_dir = base_output_dir / case["name"]
        plan = prepare(input_path, output_dir)
        plans.append({
            "case": case["name"],
            "description": case["description"],
            "run_plan": plan,
        })

    # Write summary
    summary_path = base_output_dir / "test_cases_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "cases": plans,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Summary written to: {summary_path}")
    return plans


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "prepare":
        if len(sys.argv) < 4:
            print("用法: python3 e2e_prepare.py prepare <final_result.json> <output_dir>")
            sys.exit(1)
        input_path = Path(sys.argv[2])
        output_dir = Path(sys.argv[3])
        prepare(input_path, output_dir)

    elif command == "prepare-all":
        base_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("test_runs")
        prepare_all_cases(base_dir)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
