#!/usr/bin/env python3
"""
response_normalizer.py — ResponseWorker 输出格式规范化

用途：将任意版本的 ResponseWorker 输出转换为标准 v2 格式。

Spec Pro 的 ResponseWorker 在不同轮次可能输出不同格式：
- v2（标准）：{"parsed_updates": {...}, "inference_responses": [...], ...}
- v1（旧）：  {"updates": [...], "inferences": [...], ...}

本模块负责自动检测格式版本并转换，确保 merge_spec.py 始终收到标准格式。
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple


# ============================================================================
# 标准 Schema（v2）
# ============================================================================

V2_REQUIRED_KEYS = {"parsed_updates"}


class ResponseFormatError(Exception):
    """响应格式无法识别或转换。"""
    pass


# ============================================================================
# 公共 API
# ============================================================================

def normalize_response(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    将任意格式的 ResponseWorker 输出转换为标准 v2 格式。
    
    Args:
        raw: ResponseWorker 的原始 JSON 输出
    
    Returns:
        (标准化后的 dict, 警告列表)
        
    Raises:
        ResponseFormatError: 无法识别的格式
    """
    warnings: List[str] = []
    version = _detect_version(raw)
    
    if version == "v2":
        # 已是标准格式，直接返回
        return raw, warnings
    
    if version == "v1":
        # 旧格式 → 转换
        normalized, warnings = _convert_v1_to_v2(raw)
        return normalized, warnings
    
    # 未知格式
    raise ResponseFormatError(
        f"Unknown response format. Keys: {sorted(raw.keys())}. "
        f"Expected 'parsed_updates' (v2) or 'updates' (v1)."
    )


def validate_response(response: Dict[str, Any]) -> List[str]:
    """
    验证 response 是否符合标准 v2 schema。
    
    Returns:
        问题列表。空列表 = 通过验证。
    """
    issues = []
    
    for key in V2_REQUIRED_KEYS:
        if key not in response:
            issues.append(f"Missing required key: '{key}'")
    
    # 验证 parsed_updates 的基本结构
    pu = response.get("parsed_updates", {})
    if not isinstance(pu, dict):
        issues.append(f"'parsed_updates' must be a dict, got {type(pu).__name__}")
    
    return issues


# ============================================================================
# 格式检测
# ============================================================================

def _detect_version(raw: Dict[str, Any]) -> str:
    """检测响应格式版本。
    
    Returns:
        "v1" | "v2" | "unknown"
    """
    keys = set(raw.keys())
    
    # v2: 有 parsed_updates
    if "parsed_updates" in keys:
        return "v2"
    
    # v1: 有 updates 数组
    if "updates" in keys:
        updates = raw["updates"]
        if isinstance(updates, list):
            return "v1"
    
    return "unknown"


# ============================================================================
# v1 → v2 转换
# ============================================================================

def _convert_v1_to_v2(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    将 v1 updates 格式转换为 v2 parsed_updates 格式。
    
    v1 结构:
    {
        "updates": [
            {"dimension": "quality_attributes", "changes": [
                {"action": "add", "content": {...}},
                {"action": "modify", "content": {...}}
            ]},
            {"dimension": "pain_points", "changes": [...]},
            ...
        ],
        "inferences": [
            {"id": "INF-001", "status": "confirmed", ...},
            {"id": "INF-004", "status": "modified", ...}
        ],
        "new_inferences": [...],
        "input_guards": {...},
        "meta": {"signals": [...]}
    }
    
    v2 结构:
    {
        "input_guard": {...},
        "parsed_updates": {
            "quality_attributes": [...],
            "pain_points": [...],
            ...
        },
        "inference_responses": [
            {"id": "INF-001", "action": "confirm"},
            {"id": "INF-004", "action": "modify", "modified_content": "..."}
        ],
        "new_inferences": [...],
        "meta_signals": {...}
    }
    """
    warnings: List[str] = []
    parsed_updates: Dict[str, Any] = {}
    
    # 转换 updates → parsed_updates
    updates = raw.get("updates", [])
    for update in updates:
        dim = update.get("dimension")
        if not dim:
            continue
        
        changes = update.get("changes", [])
        for change in changes:
            action = change.get("action")
            content = change.get("content")
            
            if action == "add":
                _append_to_dimension(parsed_updates, dim, content)
            elif action == "modify":
                _overwrite_dimension(parsed_updates, dim, content)
    
    # 转换 inferences → inference_responses
    inference_responses = []
    for inf in raw.get("inferences", []):
        inf_id = inf.get("id")
        status = inf.get("status", "pending")
        
        # status → action 映射
        action_map = {
            "confirmed": "confirm",
            "rejected": "reject",
            "modified": "modify",
            "pending": "pending",
        }
        action = action_map.get(status, "pending")
        
        resp = {"id": inf_id, "action": action}
        if action == "modify":
            resp["modified_content"] = inf.get("content", "")
        inference_responses.append(resp)
    
    # 构建 v2 输出
    normalized = {
        "input_guard": raw.get("input_guards", raw.get("input_guard", {})),
        "parsed_updates": parsed_updates,
        "inference_responses": inference_responses,
        "meta_signals": raw.get("meta", {}).get("signals", raw.get("meta_signals", {})),
        "new_inferences": raw.get("new_inferences", []),
    }
    
    warnings.append(
        f"Auto-migrated: v1 format ({len(updates)} updates) → v2 format"
    )
    
    return normalized, warnings


# ============================================================================
# 维度追加工具
# ============================================================================

def _append_to_dimension(parsed_updates: Dict[str, Any], dim: str, content: Any) -> None:
    """将内容追加到 parsed_updates 的对应维度。"""
    if content is None:
        return
    
    if dim == "objective":
        # objective 是字符串，只取第一个非空值
        if not parsed_updates.get("objective") and isinstance(content, str) and content.strip():
            parsed_updates["objective"] = content.strip()
    
    elif dim == "capabilities":
        # capabilities 是子字典
        if isinstance(content, dict):
            caps = parsed_updates.setdefault("capabilities", {
                "always_do": [], "should_do": [], "never_do": []
            })
            # content 可能有 action=modify，这里只处理 add
            # v1 capabilities 的 modify action 需要特殊处理
            pass  # modify 在 _overwrite_dimension 中处理
    
    elif dim == "constraints":
        # constraints 是字典
        if isinstance(content, dict):
            existing = parsed_updates.setdefault("constraints", {})
            for k, v in content.items():
                if v:
                    existing[k] = v
    
    elif dim == "integration":
        # integration 是字典
        if isinstance(content, dict):
            existing = parsed_updates.setdefault("integration", {
                "existing_systems": [], "requirements": []
            })
            for key in ["existing_systems", "requirements"]:
                if key in content:
                    _extend_unique(existing.setdefault(key, []), content[key])
    
    elif dim == "risks_and_assumptions":
        # risks_and_assumptions 是字典
        if isinstance(content, dict):
            existing = parsed_updates.setdefault("risks_and_assumptions", {
                "risks": [], "assumptions": [], "dependencies": []
            })
            for key in ["risks", "assumptions", "dependencies"]:
                if key in content:
                    _extend_unique(existing.setdefault(key, []), content[key])
    
    else:
        # 其他维度（pain_points, success_metrics, quality_attributes, users, key_scenarios）
        # 都是列表
        existing = parsed_updates.setdefault(dim, [])
        if isinstance(existing, list):
            _append_unique(existing, content)


def _overwrite_dimension(parsed_updates: Dict[str, Any], dim: str, content: Any) -> None:
    """覆盖维度的值（用于 modify action）。"""
    if content is None:
        return
    
    if dim == "capabilities":
        # capabilities modify: 可能是修改 always_do 中的某一项
        if isinstance(content, dict):
            caps = parsed_updates.setdefault("capabilities", {
                "always_do": [], "should_do": [], "never_do": []
            })
            # 如果 content 有 target 和 new_value，执行替换
            if "target" in content and "new_value" in content:
                target = content["target"]
                new_value = content["new_value"]
                # 查找并替换
                for sub_key in ["always_do", "should_do", "never_do"]:
                    for i, item in enumerate(caps.get(sub_key, [])):
                        if target in str(item):
                            caps[sub_key][i] = new_value
                            return
            # 否则合并
            for sub_key in ["always_do", "should_do", "never_do"]:
                if sub_key in content:
                    _extend_unique(caps.setdefault(sub_key, []), content[sub_key])
    else:
        _append_to_dimension(parsed_updates, dim, content)


def _append_unique(target: list, item: Any) -> None:
    """追加不重复的项。"""
    if isinstance(item, dict):
        # 用 JSON 字符串做去重比较
        existing = {json.dumps(x, sort_keys=True, ensure_ascii=False) for x in target if isinstance(x, dict)}
        item_json = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if item_json not in existing:
            target.append(item)
    else:
        if item not in target:
            target.append(item)


def _extend_unique(target: list, source: Any) -> None:
    """将 source 中的项追加到 target，去重。"""
    if isinstance(source, list):
        for item in source:
            _append_unique(target, item)
    elif source is not None:
        _append_unique(target, source)


# ============================================================================
# Audit log
# ============================================================================

def log_format_migration(response_path: str, warnings: List[str], base_path: str = None) -> None:
    """记录格式迁移事件到 audit log。"""
    if not base_path:
        base_path = os.path.dirname(os.path.dirname(response_path))
    
    audit_path = os.path.join(base_path, "spec", "format_migration_audit.log")
    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": response_path,
        "warnings": warnings,
    }
    
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ============================================================================
# CLI 入口
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: response_normalizer.py <response_json_path>")
        print("       response_normalizer.py --validate <response_json_path>")
        sys.exit(1)
    
    mode = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if mode == "--validate" and path:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        issues = validate_response(raw)
        if issues:
            print(f"VALIDATION FAILED: {json.dumps(issues, ensure_ascii=False)}")
            sys.exit(1)
        else:
            print("VALIDATION PASSED")
            sys.exit(0)
    
    # 默认: normalize
    path = sys.argv[1] if not path else path
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    
    try:
        normalized, warnings = normalize_response(raw)
        print(json.dumps({
            "status": "ok",
            "version": _detect_version(raw),
            "warnings": warnings,
            "normalized_keys": list(normalized.keys()),
        }, ensure_ascii=False, indent=2))
        sys.exit(0)
    except ResponseFormatError as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
