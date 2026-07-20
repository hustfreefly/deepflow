"""
Living Spec 数据归一化 + 渲染

设计原则: 最小信息传递损失
- str 和 dict 都是 success_metrics/users 的合法格式，互不强制转换
- 数据层保持原始语义，只在渲染层（format_metric/format_user）统一输出
- normalize_confirmed() 只做 key 归一化（name→metric），不做类型转换

信息流:
  LLM 输出 → merge_spec(保持原样) → living_spec(str|dict) → format_metric(渲染)
                                                              ↑ 唯一的渲染入口
"""

"""
This file is part of pipeline (10-stage architecture).
V3.1 纯 Agent Orchestrator 架构（Python orchestrator 层已删除）。
Do not import this file for new workflows.
"""

from typing import Any, Dict, List, Union


# ---------------------------------------------------------------------------
# Key 归一化（dict → dict，不改类型）
# ---------------------------------------------------------------------------

_METRIC_KEY_ALIASES = {"name", "指标名", "指标", "metric_name"}
_TARGET_KEY_ALIASES = {"目标", "目标值"}
_ROLE_KEY_ALIASES = {"description", "角色"}
_NEEDS_KEY_ALIASES = {"needs", "需求"}


def normalize_metric(m: Any) -> Any:
    """dict 做 key 归一化（name→metric, 目标→target）；str 保持原样。不做类型转换。"""
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        result = {}
        # metric key 归一化（优先 metric，其次别名）
        if "metric" in m:
            result["metric"] = m["metric"]
        else:
            for k in _METRIC_KEY_ALIASES:
                if k in m:
                    result["metric"] = m[k]
                    break
        # target key 归一化
        if "target" in m:
            result["target"] = m["target"]
        else:
            for k in _TARGET_KEY_ALIASES:
                if k in m:
                    result["target"] = m[k]
                    break
        # 保留其余字段（跳过已归一化的 key）
        skip = {"metric", "target"} | _METRIC_KEY_ALIASES | _TARGET_KEY_ALIASES
        for k, v in m.items():
            if k not in skip:
                result[k] = v
        return result
    return str(m)


def normalize_user(u: Any) -> Any:
    """dict 做 key 归一化（description→role, needs→key_needs）；str 保持原样。不做类型转换。"""
    if isinstance(u, str):
        return u
    if isinstance(u, dict):
        result = {}
        if "role" in u:
            result["role"] = u["role"]
        else:
            for k in _ROLE_KEY_ALIASES:
                if k in u:
                    result["role"] = u[k]
                    break
        if "key_needs" in u:
            result["key_needs"] = u["key_needs"]
        else:
            for k in _NEEDS_KEY_ALIASES:
                if k in u:
                    result["key_needs"] = u[k]
                    break
        skip = {"role", "key_needs"} | _ROLE_KEY_ALIASES | _NEEDS_KEY_ALIASES
        for k, v in u.items():
            if k not in skip:
                result[k] = v
        return result
    return str(u)


def normalize_confirmed(confirmed: dict) -> dict:
    """归一化 confirmed 层：只做 key 映射，不做类型转换。幂等。"""
    if not isinstance(confirmed, dict):
        return confirmed
    sm = confirmed.get("success_metrics", [])
    if isinstance(sm, list):
        confirmed["success_metrics"] = [normalize_metric(m) for m in sm]
    users = confirmed.get("users", [])
    if isinstance(users, list):
        confirmed["users"] = [normalize_user(u) for u in users]
    return confirmed


# ---------------------------------------------------------------------------
# 渲染函数（消费端唯一入口）
# ---------------------------------------------------------------------------

def format_metric(m: Any) -> str:
    """将 success_metrics 项渲染为 prompt 文本行。

    - str → 原样返回（保留完整语义，不做虚假拆分）
    - dict with real target → "metric: target"
    - dict with degenerate target (metric==target or empty) → metric only
    """
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        metric = m.get("metric", "")
        target = m.get("target", "")
        if not metric:
            return str(m)
        # 退化检测: target 为空或与 metric 相同 → 只输出 metric
        if not target or target == metric:
            return metric
        return f"{metric}: {target}"
    return str(m)


def format_user(u: Any) -> str:
    """将 users 项渲染为 prompt 文本行。

    - str → 原样返回
    - dict → "role: key_needs" (如果有 key_needs)
    """
    if isinstance(u, str):
        return u
    if isinstance(u, dict):
        role = u.get("role", "")
        key_needs = u.get("key_needs", "")
        count = u.get("count", "")
        parts = []
        if role:
            parts.append(role)
        if count:
            parts.append(f"({count}人)")
        if key_needs:
            parts.append(f": {key_needs}")
        return "".join(parts) if parts else str(u)
    return str(u)


# [TD3 2026-07-13] Deleted dead functions: format_metrics_list, format_users_list (zero callers)
