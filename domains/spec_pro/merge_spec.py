#!/usr/bin/env python3
"""
merge_spec.py — Deterministic Living Spec merge (Writer Protocol)

Called by Orchestrator Worker via exec to merge ResponseWorker output into
living_spec.json.  This replaces the error-prone LLM-based merge.

Usage:
    python3 merge_spec.py <response_json_path> <living_spec_path>
    python3 merge_spec.py --revisions <confirmation_path> <living_spec_path>
"""

import json
import os
import sys
import copy
from datetime import datetime


def append_unique(target: list, source: list, key: str = None) -> None:
    """Append items from source to target, avoiding duplicates."""
    if key:
        existing = {item.get(key) for item in target if isinstance(item, dict)}
        for item in source:
            if isinstance(item, dict):
                item_key = item.get(key)
                if item_key not in existing:
                    target.append(item)
                    existing.add(item_key)
            else:
                if item not in target:
                    target.append(item)
    else:
        for item in source:
            if item not in target:
                target.append(item)


def merge_confirmed(spec: dict, updates: dict) -> None:
    """Merge new confirmed data into spec['confirmed'], never deleting existing."""
    confirmed = spec["confirmed"]

    # Simple string fields: only overwrite if new value is non-empty and different
    for field in ["objective"]:
        new_val = updates.get(field)
        if new_val and new_val != confirmed.get(field):
            confirmed[field] = new_val

    # List fields: append unique items
    for field in ["pain_points", "success_metrics", "key_scenarios"]:
        new_items = updates.get(field, [])
        if isinstance(new_items, list):
            append_unique(confirmed.setdefault(field, []), new_items)

    # users: merge by role
    new_users = updates.get("users", [])
    existing_users = confirmed.get("users", [])
    existing_roles = {u.get("role") for u in existing_users if isinstance(u, dict)}
    for u in new_users:
        if isinstance(u, dict) and u.get("role") not in existing_roles:
            existing_users.append(u)
            existing_roles.add(u.get("role"))

    # capabilities: merge sub-lists
    new_caps = updates.get("capabilities", {})
    caps = confirmed.setdefault("capabilities", {"always_do": [], "should_do": [], "never_do": []})
    for sub in ["always_do", "should_do", "never_do"]:
        append_unique(caps.setdefault(sub, []), new_caps.get(sub, []))

    # quality_attributes: append unique
    new_qa = updates.get("quality_attributes", [])
    if isinstance(new_qa, list):
        append_unique(confirmed.setdefault("quality_attributes", []), new_qa)

    # constraints: merge dict
    new_constraints = updates.get("constraints", {})
    constraints = confirmed.setdefault("constraints", {})
    for k, v in new_constraints.items():
        if v and not constraints.get(k):
            constraints[k] = v

    # integration
    new_integration = updates.get("integration", {})
    integration = confirmed.setdefault("integration", {"existing_systems": [], "requirements": []})
    new_systems = new_integration.get("existing_systems", [])
    append_unique(integration.setdefault("existing_systems", []), new_systems, key="name")
    append_unique(integration.setdefault("requirements", []), new_integration.get("requirements", []))

    # risks_and_assumptions
    new_risks = updates.get("risks_and_assumptions", {})
    risks = confirmed.setdefault("risks_and_assumptions", {"risks": [], "assumptions": [], "dependencies": []})
    for sub in ["risks", "assumptions", "dependencies"]:
        append_unique(risks.setdefault(sub, []), new_risks.get(sub, []))


def merge_inferred(spec: dict, response: dict) -> None:
    """Merge inference responses and new inferences into spec['inferred']."""
    inferred = spec.get("inferred", [])

    # Process inference responses
    for ir in response.get("inference_responses", []):
        inf_id = ir.get("id")
        action = ir.get("action")
        for item in inferred:
            if item.get("id") == inf_id:
                if action == "confirm":
                    item["status"] = "confirmed"
                elif action == "reject":
                    item["status"] = "rejected"
                elif action == "modify":
                    modified = ir.get("modified_content", item.get("content", item.get("description", "")))
                    item["content"] = modified
                    item["status"] = "modified"

    # Move confirmed inferences to confirmed layer
    confirmed_inferred = [i for i in inferred if i.get("status") == "confirmed"]
    for inf in confirmed_inferred:
        # Add to appropriate confirmed field based on dimension
        dim = inf.get("dimension", "")
        content = inf.get("content", "")
        if dim == "objective":
            if not spec["confirmed"].get("objective"):
                spec["confirmed"]["objective"] = content
        elif dim == "users":
            spec["confirmed"].setdefault("users", [])
            spec["confirmed"]["users"].append({"role": content, "key_needs": ""})
        elif dim == "quality_attributes":
            spec["confirmed"].setdefault("quality_attributes", [])
            spec["confirmed"]["quality_attributes"].append({"category": "推断", "spec": content, "priority": "P1"})
        elif dim == "constraints":
            spec["confirmed"].setdefault("constraints", {})
            spec["confirmed"]["constraints"]["inferred"] = content
        elif dim == "risks":
            spec["confirmed"].setdefault("risks_and_assumptions", {"risks": [], "assumptions": [], "dependencies": []})
            spec["confirmed"]["risks_and_assumptions"]["risks"].append(content)
        # Mark as moved
        inf["_moved_to_confirmed"] = True

    # Add new inferences
    for ni in response.get("new_inferences", []):
        inferred.append(ni)


def merge_guardrails(spec: dict, response: dict) -> None:
    """Merge guardrails from response.
    Handles both response['guardrails'] and parsed_updates['meta_signals']['new_guardrails'].
    """
    guardrails = spec.get("guardrails", {"always_do": [], "ask_first": [], "never_do": []})

    # Direct guardrails field
    new_guardrails = response.get("guardrails", {})
    for key in ["always_do", "ask_first", "never_do"]:
        new_items = new_guardrails.get(key, [])
        append_unique(guardrails.setdefault(key, []), new_items)

    # meta_signals.new_guardrails (from ResponseWorker output)
    parsed = response.get("parsed_updates", {})
    meta_signals = parsed.get("meta_signals", {})
    new_from_meta = meta_signals.get("new_guardrails", {})
    for key in ["always_do", "ask_first", "never_do"]:
        new_items = new_from_meta.get(key, [])
        append_unique(guardrails.setdefault(key, []), new_items)


def check_contradictions(spec: dict) -> list:
    """Check for contradictions between new and existing confirmed data."""
    contradictions = []
    # Simple check: if guardrails.always_do conflicts with guardrails.never_do
    always = set(spec.get("guardrails", {}).get("always_do", []))
    never = set(spec.get("guardrails", {}).get("never_do", []))
    conflict = always & never
    if conflict:
        contradictions.append({
            "type": "guardrail_conflict",
            "items": list(conflict),
            "resolution": "保留两者并标注 contradiction",
        })
    return contradictions


def merge_spec(response_path: str, living_spec_path: str) -> dict:
    """Main merge function."""
    with open(response_path, "r", encoding="utf-8") as f:
        response = json.load(f)

    with open(living_spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    parsed_updates = response.get("parsed_updates", {})

    # Step 1: Merge confirmed
    merge_confirmed(spec, parsed_updates)

    # Step 2: Merge inferred
    merge_inferred(spec, response)

    # Step 3: Merge guardrails
    merge_guardrails(spec, response)

    # Step 4: Check contradictions
    contradictions = check_contradictions(spec)

    # Update meta
    spec["meta"]["updated_at"] = datetime.now().isoformat()
    spec["meta"]["conversation_rounds"] = spec["meta"].get("conversation_rounds", 0) + 1

    # Write back
    with open(living_spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    return {"status": "merged", "contradictions": contradictions}


def apply_revisions(confirmation_path: str, living_spec_path: str) -> dict:
    """Apply user revisions from confirmation to living_spec."""
    with open(confirmation_path, "r", encoding="utf-8") as f:
        confirmation = json.load(f)

    with open(living_spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    revisions = confirmation.get("revisions", [])
    for rev in revisions:
        dimension = rev.get("dimension")
        field = rev.get("field")
        new_value = rev.get("new_value")

        if dimension and field:
            if dimension == "confirmed":
                spec["confirmed"][field] = new_value
            elif dimension == "guardrails":
                spec["guardrails"][field] = new_value
            elif dimension == "inferred":
                for item in spec.get("inferred", []):
                    if item.get("id") == field:
                        item["content"] = new_value

    spec["meta"]["updated_at"] = datetime.now().isoformat()

    with open(living_spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    return {"status": "revised", "revisions_applied": len(revisions)}


from datetime import datetime


def main():
    if len(sys.argv) < 3:
        print("Usage: merge_spec.py <response_json> <living_spec_json>")
        print("       merge_spec.py --revisions <confirmation_json> <living_spec_json>")
        sys.exit(1)

    if sys.argv[1] == "--revisions":
        confirmation_path = sys.argv[2]
        living_spec_path = sys.argv[3]
        result = apply_revisions(confirmation_path, living_spec_path)
    else:
        response_path = sys.argv[1]
        living_spec_path = sys.argv[2]
        result = merge_spec(response_path, living_spec_path)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
