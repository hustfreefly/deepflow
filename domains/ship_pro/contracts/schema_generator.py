"""
Ship Pro V4.1 — Schema Auto-Generator

Generates prompt-friendly schema descriptions from Pydantic models.
Solves the "Packager retries 2x due to schema mismatch" problem.

Usage:
    from contracts.schema_generator import generate_prompt_schema
    schema_str = generate_prompt_schema(PackagerOutput, "packager")
    # → inject schema_str into Worker prompt
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def generate_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Generate JSON Schema from Pydantic model."""
    return model.model_json_schema()


def generate_prompt_schema(
    model: type[BaseModel],
    capability_name: str,
    include_example: bool = True,
) -> str:
    """
    Generate a prompt-friendly schema description from a Pydantic model.

    Returns markdown text ready to inject into Worker prompts.
    """
    schema = generate_json_schema(model)
    lines = [
        f"## Output Schema ({capability_name})",
        "",
        "Your output MUST conform to this exact JSON structure:",
        "",
        "```json",
        json.dumps(schema, indent=2, ensure_ascii=False),
        "```",
        "",
    ]

    if include_example:
        # Generate a minimal example from the schema
        example = _generate_example(schema)
        lines.extend([
            "### Example Output",
            "",
            "```json",
            json.dumps(example, indent=2, ensure_ascii=False),
            "```",
            "",
        ])

    lines.extend([
        "### Validation Rules",
        "",
        f"- Top-level keys must match the schema above",
        f"- All `required` fields must be present",
        f"- Field types must match (string, number, array, object, boolean)",
        f"- If a field is optional, you may omit it",
        "",
    ])

    return "\n".join(lines)


def _generate_example(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate a minimal example from JSON Schema."""
    result: dict[str, Any] = {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for key, prop in properties.items():
        if key.startswith("_"):
            continue  # Skip private fields
        if key not in required:
            continue  # Only show required fields in example

        prop_type = prop.get("type", "string")
        if prop_type == "string":
            enum_vals = prop.get("enum", [])
            result[key] = enum_vals[0] if enum_vals else f"<{key}>"
        elif prop_type == "integer":
            result[key] = 0
        elif prop_type == "number":
            result[key] = 0.0
        elif prop_type == "boolean":
            result[key] = True
        elif prop_type == "array":
            result[key] = []
        elif prop_type == "object":
            result[key] = {}
        else:
            result[key] = None

    return result


def get_output_schema_json(
    model: type[BaseModel],
) -> str:
    """Return compact JSON schema string for gate validation."""
    return json.dumps(generate_json_schema(model), ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI: Generate schemas for all Ship Pro output contracts
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from contracts.capability_registry import build_default_registry
    from contracts.architect import ArchitectOutput
    from contracts.packager import PackagerOutput
    from contracts.reviewer import ReviewerOutput
    from contracts.specifier_ac import SpecifierOutput

    registry = build_default_registry()

    contract_map = {
        "architect": ArchitectOutput,
        "specifier": SpecifierOutput,
        "reviewer": ReviewerOutput,
        "packager": PackagerOutput,
    }

    for cap_id, model in contract_map.items():
        cap = registry.capabilities.get(cap_id)
        if not cap:
            continue
        print(f"\n{'='*60}")
        print(f"Capability: {cap_id}")
        print(f"{'='*60}")
        print(generate_prompt_schema(model, cap_id))
