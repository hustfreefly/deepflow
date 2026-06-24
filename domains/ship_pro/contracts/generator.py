"""
契约代码生成器 — 从 Pydantic 模型自动生成:

1. JSON Schema → schemas/ 目录
2. Prompt 中的输出格式段落 (可嵌入 .md 文件)
3. Gate 字段检查清单 (供 gate 代码引用)

用法:
    python3 -m domains.ship_pro.contracts.generator          # 生成所有
    python3 -m domains.ship_pro.contracts.generator --check   # 检查一致性（CI 用）
"""

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel


def _project_root() -> Path:
    """返回 .deepflow 项目根目录。"""
    return Path(__file__).resolve().parents[3]


def generate_json_schema(model_class: type[BaseModel], output_path: str | Path) -> None:
    """从 Pydantic 模型生成 JSON Schema 文件。"""
    schema = model_class.model_json_schema()
    # 添加元信息
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["$id"] = f"https://deepflow.local/schemas/{Path(output_path).name}"
    output_path = Path(output_path)
    output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False))
    print(f"✅ Generated JSON Schema: {output_path}")


def generate_prompt_schema_section(model_class: type[BaseModel], title: str = "输出格式") -> str:
    """
    从 Pydantic 模型生成 Prompt 中的输出格式段落。

    返回 Markdown 文本，可直接嵌入 .md prompt 文件。
    """
    schema = model_class.model_json_schema()

    lines = [
        f"## {title}（由 Pydantic 契约自动生成，禁止手动修改）",
        "",
        "> 此段落由 `contracts/generator.py` 从 Pydantic 模型自动生成。",
        "> 如需修改输出格式，请修改对应的 Pydantic 模型文件。",
        "",
        "```json",
        json.dumps(schema, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    return "\n".join(lines)


def generate_gate_field_checklist(model_class: type[BaseModel]) -> dict:
    """
    从 Pydantic 模型提取 Gate 应检查的字段清单。

    返回:
        {
            "required_fields": [...],
            "all_fields": [...],
            "field_types": {...},
        }
    """
    schema = model_class.model_json_schema()

    # 收集所有 $defs 中的 properties
    all_props = {}
    required = set(schema.get("required", []))

    # Top-level properties
    for name, prop in schema.get("properties", {}).items():
        all_props[name] = {
            "required": name in required,
            "type": prop.get("type", prop.get("anyOf", "unknown")),
        }

    return {
        "required_fields": sorted(required),
        "all_fields": sorted(all_props.keys()),
        "field_types": {k: v["type"] for k, v in all_props.items()},
    }


def check_schema_consistency(model_class: type[BaseModel], schema_path: str | Path) -> list[str]:
    """
    检查 Pydantic 模型生成的 Schema 与存储的 JSON Schema 文件是否一致。

    返回不一致项列表（空列表 = 一致）。
    """
    generated = model_class.model_json_schema()
    schema_path = Path(schema_path)

    if not schema_path.exists():
        return [f"Schema file not found: {schema_path}"]

    stored = json.loads(schema_path.read_text())

    issues = []

    # Compare required fields
    gen_required = set(generated.get("required", []))
    stored_required = set(stored.get("required", []))
    if gen_required != stored_required:
        issues.append(
            f"Required mismatch: generated={gen_required}, stored={stored_required}"
        )

    # Compare top-level properties
    gen_props = set(generated.get("properties", {}).keys())
    stored_props = set(stored.get("properties", {}).keys())
    if gen_props != stored_props:
        only_gen = gen_props - stored_props
        only_stored = stored_props - gen_props
        if only_gen:
            issues.append(f"Properties only in generated: {only_gen}")
        if only_stored:
            issues.append(f"Properties only in stored: {only_stored}")

    return issues


def main() -> None:
    """CLI 入口：生成或检查。"""
    from domains.ship_pro.contracts.architect import ArchitectOutput
    from domains.ship_pro.contracts.packager import ShipPackage
    from domains.ship_pro.contracts.pipeline_state import PipelineState
    from domains.ship_pro.contracts.reviewer import ReviewerOutput

    root = _project_root()
    schemas_dir = root / "domains" / "ship_pro" / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    if "--check" in sys.argv:
        # CI 模式：检查一致性，不写文件
        print("=== Schema Consistency Check ===\n")
        all_ok = True

        # Check Packager
        issues = check_schema_consistency(
            ShipPackage, schemas_dir / "ship_package_v3.schema.json"
        )
        if issues:
            print(f"❌ ShipPackage schema drift detected ({len(issues)} issues):")
            for issue in issues:
                print(f"   - {issue}")
            all_ok = False
        else:
            print("✅ ShipPackage schema is consistent with Pydantic model")

        # Check ReviewerOutput
        issues = check_schema_consistency(
            ReviewerOutput, schemas_dir / "reviewer_output_v3.schema.json"
        )
        if issues:
            print(f"❌ ReviewerOutput schema drift detected ({len(issues)} issues):")
            for issue in issues:
                print(f"   - {issue}")
            all_ok = False
        else:
            print("✅ ReviewerOutput schema is consistent with Pydantic model")

        # Check PipelineState
        issues = check_schema_consistency(
            PipelineState, schemas_dir / "pipeline_state_v3.schema.json"
        )
        if issues:
            print(f"❌ PipelineState schema drift detected ({len(issues)} issues):")
            for issue in issues:
                print(f"   - {issue}")
            all_ok = False
        else:
            print("✅ PipelineState schema is consistent with Pydantic model")

        # Print field checklists
        print("\n=== Gate Field Checklists ===\n")
        arch_fields = generate_gate_field_checklist(ArchitectOutput)
        print(f"ArchitectOutput required: {arch_fields['required_fields']}")
        print(f"ArchitectOutput all: {arch_fields['all_fields']}")

        pkg_fields = generate_gate_field_checklist(ShipPackage)
        print(f"ShipPackage required: {pkg_fields['required_fields']}")
        print(f"ShipPackage all: {pkg_fields['all_fields']}")

        state_fields = generate_gate_field_checklist(PipelineState)
        print(f"PipelineState required: {state_fields['required_fields']}")
        print(f"PipelineState all: {state_fields['all_fields']}")

        reviewer_fields = generate_gate_field_checklist(ReviewerOutput)
        print(f"ReviewerOutput required: {reviewer_fields['required_fields']}")
        print(f"ReviewerOutput all: {reviewer_fields['all_fields']}")

        sys.exit(0 if all_ok else 1)

    else:
        # 生成模式：写文件
        print("=== Generating Schemas from Pydantic Models ===\n")

        generate_json_schema(
            ShipPackage, schemas_dir / "ship_package_v3.schema.json"
        )
        generate_json_schema(
            PipelineState, schemas_dir / "pipeline_state_v3.schema.json"
        )
        generate_json_schema(
            ReviewerOutput, schemas_dir / "reviewer_output_v3.schema.json"
        )

        # Print prompt sections
        print("\n=== Prompt Schema Sections ===\n")
        print("--- ArchitectOutput ---")
        print(generate_prompt_schema_section(ArchitectOutput, "Architect 输出格式")[:500] + "...")
        print("\n--- ShipPackage ---")
        print(generate_prompt_schema_section(ShipPackage, "ShipPackage 输出格式")[:500] + "...")
        print("\n--- PipelineState ---")
        print(generate_prompt_schema_section(PipelineState, "PipelineState 格式")[:500] + "...")
        print("\n--- ReviewerOutput ---")
        print(generate_prompt_schema_section(ReviewerOutput, "Reviewer 输出格式")[:500] + "...")

        # Print gate checklists
        print("\n=== Gate Field Checklists ===\n")
        arch_fields = generate_gate_field_checklist(ArchitectOutput)
        print(f"ArchitectOutput required: {arch_fields['required_fields']}")

        pkg_fields = generate_gate_field_checklist(ShipPackage)
        print(f"ShipPackage required: {pkg_fields['required_fields']}")

        state_fields = generate_gate_field_checklist(PipelineState)
        print(f"PipelineState required: {state_fields['required_fields']}")


if __name__ == "__main__":
    main()
