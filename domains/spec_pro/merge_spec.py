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
from datetime import datetime

# Response Normalizer: 将任意格式的 ResponseWorker 输出转换为标准 v2 格式
from domains.spec_pro.response_normalizer import normalize_response, log_format_migration


def _char_bigrams(s: str) -> set:
    """生成字符串的字符 bigram 集合。"""
    s = s.lower().strip()
    if len(s) < 2:
        return {s}
    return {s[i:i+2] for i in range(len(s) - 1)}


def _jaccard_similarity(a: str, b: str) -> float:
    """计算两个字符串的 Jaccard 字符 bigram 相似度。"""
    set_a = _char_bigrams(a)
    set_b = _char_bigrams(b)
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _is_duplicate_by_similarity(item, target: list, threshold: float = 0.45) -> bool:
    """v2.2: 检查 item 是否与 target 中某项相似度超过阈值。
    
    中文文本的 Jaccard bigram 相似度通常较低，阈值设为 0.45。
    - 相同文本: 1.0
    - 相似但扩展的文本: 0.4-0.7
    - 不同语义的文本: < 0.3
    """
    if isinstance(item, str):
        for existing in target:
            if isinstance(existing, str):
                if _jaccard_similarity(item, existing) >= threshold:
                    return True
    return False


def append_unique(target: list, source: list, key: str = None) -> None:
    """Append items from source to target, avoiding duplicates.
    
    v2.2: 无 key 时对字符串做 Jaccard 字符 bigram 相似度去重（阈值 0.45）。
    零外部依赖，确定性算法。
    中文场景说明：
    - "聚合中国各种便宜的token" vs "聚合中国各种便宜的token（DeepSeek）" → ~0.46 → 去重
    - "低成本运营（兼职）" vs "低成本运营（一人公司）" → ~0.21 → 不去重（语义不同）
    - 相同文本 → 1.0 → 去重
    """
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
            if isinstance(item, str):
                if not _is_duplicate_by_similarity(item, target):
                    target.append(item)
            else:
                if item not in target:
                    target.append(item)


def merge_confirmed(spec: dict, updates: dict) -> None:
    """Merge new confirmed data into spec['confirmed'], never deleting existing.
    
    Defensive checks at entry:
    - Ensure spec and updates are dicts
    - Ensure spec['confirmed'] exists and is a dict
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be dict, got {type(spec).__name__}")
    if not isinstance(updates, dict):
        raise ValueError(f"updates must be dict, got {type(updates).__name__}")
    
    spec.setdefault("confirmed", {})
    confirmed = spec["confirmed"]
    
    if not isinstance(confirmed, dict):
        raise ValueError(f"spec['confirmed'] must be dict, got {type(confirmed).__name__}")

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
    existing_users = confirmed.setdefault("users", [])  # F1: setdefault 确保字段存在
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

    # quality_attributes: semantic dedup by category + spec[:15] (F6)
    new_qa = updates.get("quality_attributes", [])
    if isinstance(new_qa, list):
        qa_list = confirmed.setdefault("quality_attributes", [])
        existing_keys = {
            (item.get("category", ""), str(item.get("spec", ""))[:15])
            for item in qa_list if isinstance(item, dict)
        }
        for qa in new_qa:
            if isinstance(qa, dict):
                key = (qa.get("category", ""), str(qa.get("spec", ""))[:15])
                if key not in existing_keys:
                    qa_list.append(qa)
                    existing_keys.add(key)
            else:
                # 非 dict 类型，按普通去重
                if qa not in qa_list:
                    qa_list.append(qa)

    # constraints: merge dict (F2: allow overwrite when new value is non-empty)
    new_constraints = updates.get("constraints", {})
    constraints = confirmed.setdefault("constraints", {})
    for k, v in new_constraints.items():
        if v:
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
    inferred = spec.setdefault("inferred", [])  # F2: setdefault 确保字段存在

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

    # Move confirmed inferences to confirmed layer (F1: all 10 dimensions)
    confirmed_inferred = [i for i in inferred if i.get("status") == "confirmed"]
    for inf in confirmed_inferred:
        dim = inf.get("dimension", "")
        content = inf.get("content", "")
        c = spec["confirmed"]
        if dim == "objective":
            if not c.get("objective"):
                c["objective"] = content
        elif dim == "pain_points":
            append_unique(c.setdefault("pain_points", []), [content])
        elif dim == "success_metrics":
            append_unique(c.setdefault("success_metrics", []), [content])
        elif dim == "users":
            c.setdefault("users", []).append({"role": content, "key_needs": ""})
        elif dim == "key_scenarios":
            append_unique(c.setdefault("key_scenarios", []), [content])
        elif dim == "capabilities":
            caps = c.setdefault("capabilities", {"always_do": [], "should_do": [], "never_do": []})
            append_unique(caps.setdefault("should_do", []), [content])
        elif dim == "quality_attributes":
            c.setdefault("quality_attributes", []).append({"category": "推断", "spec": content, "priority": "P1"})
        elif dim == "constraints":
            c.setdefault("constraints", {})["inferred"] = content
        elif dim == "integration":
            integ = c.setdefault("integration", {"existing_systems": [], "requirements": []})
            append_unique(integ.setdefault("requirements", []), [content])
        elif dim == "risks":
            ra = c.setdefault("risks_and_assumptions", {"risks": [], "assumptions": [], "dependencies": []})
            append_unique(ra.setdefault("risks", []), [content])
        # P1-3 修复: 迁移后从 inferred 活跃列表中移除，归档到 archived
        inf["_moved_to_confirmed"] = True
        inf["_archived"] = True

    # P1-3 修复: 将已归档的 inference 从 inferred 列表中移除
    inferred[:] = [i for i in inferred if not i.get("_archived")]

    # Add new inferences
    for ni in response.get("new_inferences", []):
        inferred.append(ni)


def merge_guardrails(spec: dict, response: dict) -> None:
    """Merge guardrails from response.
    Handles both response['guardrails'] and parsed_updates['meta_signals']['new_guardrails'].
    """
    guardrails = spec.setdefault("guardrails", {"always_do": [], "ask_first": [], "never_do": []})  # F2: setdefault

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
    
    # Check 1: guardrails.always_do conflicts with guardrails.never_do
    always = set(spec.get("guardrails", {}).get("always_do", []))
    never = set(spec.get("guardrails", {}).get("never_do", []))
    conflict = always & never
    if conflict:
        contradictions.append({
            "type": "guardrail_conflict",
            "items": list(conflict),
            "resolution": "保留两者并标注 contradiction",
        })
    
    # Check 2: capabilities.always_do conflicts with capabilities.never_do
    caps = spec.get("confirmed", {}).get("capabilities", {})
    caps_always = set(caps.get("always_do", []))
    caps_never = set(caps.get("never_do", []))
    caps_conflict = caps_always & caps_never
    if caps_conflict:
        contradictions.append({
            "type": "capability_conflict",
            "items": list(caps_conflict),
            "resolution": "always_do 与 never_do 存在冲突，需要澄清",
        })
    
    # Check 3: constraints.conflicts (e.g., platform vs tech_stack)
    constraints = spec.get("confirmed", {}).get("constraints", {})
    platform = constraints.get("platform")
    tech_stack = constraints.get("tech_stack", [])
    # Simple heuristic: if platform constraints conflict with tech_stack choices, flag it
    # (This is a placeholder for more sophisticated checks)
    
    return contradictions


def merge_conversation_digest(spec: dict, response: dict) -> None:
    """V2: Merge conversation_digest from ResponseWorker output.

    - summary: overwritten each round by StructureWorker (not here)
    - key_excerpts: incrementally appended from ResponseWorker, with dedup
    """
    new_digest = response.get("conversation_digest")
    if not new_digest or not isinstance(new_digest, dict):
        return

    existing = spec.get("conversation_digest") or {}

    # summary: StructureWorker 产出时覆盖更新
    if new_digest.get("summary"):
        existing["summary"] = new_digest["summary"]

    # key_excerpts: ResponseWorker 增量追加，代码负责去重
    new_excerpts = new_digest.get("key_excerpts", [])
    existing_excerpts = existing.setdefault("key_excerpts", [])
    existing_texts = {e.get("excerpt", "").lower() for e in existing_excerpts if isinstance(e, dict)}
    for e in new_excerpts:
        if isinstance(e, dict) and e.get("excerpt"):
            if e["excerpt"].lower() not in existing_texts:
                existing_excerpts.append(e)
                existing_texts.add(e["excerpt"].lower())

    # 上限 20 条，超出按 source_round 保留最新
    if len(existing_excerpts) > 20:
        existing_excerpts.sort(key=lambda x: x.get("source_round", 0), reverse=True)
        existing["key_excerpts"] = existing_excerpts[:20]

    existing["full_conversation_path"] = "spec/conversation_log.json"
    spec["conversation_digest"] = existing


def merge_user_directives(spec: dict, response: dict) -> None:
    """Merge user_directives from parse_response output into confirmed layer."""
    parsed_updates = response.get("parsed_updates", {})
    user_directives = parsed_updates.get("user_directives") or response.get("user_directives", [])
    if not user_directives:
        return
    
    confirmed = spec.setdefault("confirmed", {})
    directives = confirmed.setdefault("user_directives", [])
    
    # Append unique directives by dimension + directive/type + content/reason.
    existing = {
        (
            d.get("dimension"),
            d.get("directive") or d.get("type"),
            d.get("content") or d.get("reason"),
        )
        for d in directives
        if isinstance(d, dict)
    }
    for directive in user_directives:
        if isinstance(directive, dict):
            key = (
                directive.get("dimension"),
                directive.get("directive") or directive.get("type"),
                directive.get("content") or directive.get("reason"),
            )
            if key not in existing:
                directives.append(directive)
                existing.add(key)
        elif isinstance(directive, str):
            key = (None, directive, None)
            if key not in existing:
                directives.append({"directive": directive, "source": "user"})
                existing.add(key)


def merge_spec(response_path: str, living_spec_path: str) -> dict:
    """Main merge function with robust error handling."""
    # P0-5: 文件不存在/JSON 格式错误异常处理
    if not os.path.exists(response_path):
        return {"status": "error", "message": f"Response file not found: {response_path}"}
    if not os.path.exists(living_spec_path):
        return {"status": "error", "message": f"Living spec file not found: {living_spec_path}"}
    
    try:
        with open(response_path, "r", encoding="utf-8") as f:
            response = json.load(f)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON in response file: {e}"}
    
    try:
        with open(living_spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON in living spec file: {e}"}

    # 🔧 P0 修复: 通过 ResponseNormalizer 规范化输入
    # 不再假设 response 有 parsed_updates 字段，normalizer 会自动适配格式版本
    try:
        response, migration_warnings = normalize_response(response)
    except Exception as e:
        return {"status": "error", "message": f"Response format error: {e}"}

    # 记录格式迁移事件（如果有）
    if migration_warnings:
        try:
            log_format_migration(response_path, migration_warnings, os.path.dirname(os.path.dirname(living_spec_path)))
        except Exception:
            pass  # audit log 失败不阻塞合并

    parsed_updates = response.get("parsed_updates", {})

    # Step 0: Validate structure (F3: 确保 confirmed 层存在)
    if "confirmed" not in spec:
        spec["confirmed"] = {
            "objective": "", "pain_points": [], "success_metrics": [],
            "users": [], "key_scenarios": [],
            "capabilities": {"always_do": [], "should_do": [], "never_do": []},
            "quality_attributes": [], "constraints": {},
            "integration": {"existing_systems": [], "requirements": []},
            "risks_and_assumptions": {"risks": [], "assumptions": [], "dependencies": []},
        }

    # Step 1: Merge confirmed
    merge_confirmed(spec, parsed_updates)

    # Step 2: Merge inferred
    merge_inferred(spec, response)

    # Step 3: Merge guardrails
    merge_guardrails(spec, response)

    # Step 4: Check contradictions
    contradictions = check_contradictions(spec)
    
    # Step 5: Merge user_directives (parse_response.md 输出)
    merge_user_directives(spec, response)

    # Step 6: Merge conversation_digest (V2 对话摘要累积)
    merge_conversation_digest(spec, response)

    # Update meta
    meta = spec.setdefault("meta", {})
    meta["updated_at"] = datetime.now().isoformat()
    meta["conversation_rounds"] = meta.get("conversation_rounds", 0) + 1

    # Write back
    with open(living_spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    return {"status": "merged", "contradictions": contradictions}


def apply_revisions(confirmation_path: str, living_spec_path: str) -> dict:
    """Apply user revisions from confirmation to living_spec."""
    if not os.path.exists(confirmation_path):
        return {"status": "error", "message": f"Confirmation file not found: {confirmation_path}"}
    if not os.path.exists(living_spec_path):
        return {"status": "error", "message": f"Living spec file not found: {living_spec_path}"}

    try:
        with open(confirmation_path, "r", encoding="utf-8") as f:
            confirmation = json.load(f)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON in confirmation file: {e}"}

    try:
        with open(living_spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON in living spec file: {e}"}

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

    meta = spec.setdefault("meta", {})
    meta["updated_at"] = datetime.now().isoformat()

    with open(living_spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    return {"status": "revised", "revisions_applied": len(revisions)}


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
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
