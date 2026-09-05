#!/usr/bin/env python3
"""
DeepFlow Doctor — Causal Tracer

追踪多 Agent 因果链:
  - 从 session_store（2026.9.1 SQLite 存储）构建 parent-child 关系树
  - 跨 session 追踪: Agent A 的错误输出 → Agent B 消费 → 产生问题
  - 识别"根因 Agent"（谁的错误导致了最多的下游问题）

数据源变更（2026-09-05）：sessions.json 已随 2026.9.1 存储迁移废弃，
改由 session_store.build_tree()（session_nodes + subagent_runs）提供。
"""

from pathlib import Path
from typing import Any

from session_store import build_tree as _store_build_tree


def build_session_tree(sessions_json: str | Path | None = None) -> dict:
    """
    构建 session 关系树（契约与旧版一致，数据源已迁移 SQLite）。

    参数 sessions_json 已废弃（仅为兼容旧调用签名保留），被忽略。

    返回:
        {
            "roots": [root_session_keys],
            "children": {parent_key: [child_keys]},
            "sessions": {key: {id, session_id, label, status, tokens, runtime_ms,
                               started_at, parent, agent_id}},
        }
    """
    return _store_build_tree()


def get_session_family(tree: dict, root_key: str, max_depth: int = 3) -> list[str]:
    """
    获取一个 root session 的所有后代 session keys。
    BFS 遍历，限制深度。
    """
    family = [root_key]
    queue = [(root_key, 0)]
    visited = {root_key}

    while queue:
        key, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        for child in tree["children"].get(key, []):
            if child not in visited:
                visited.add(child)
                family.append(child)
                queue.append((child, depth + 1))

    return family


def trace_causal_chain(issues_by_session: dict[str, list], tree: dict) -> list[dict]:
    """
    跨 session 追踪因果链。

    输入: {session_key: [issues]}
    返回: [{"root_cause_session": ..., "downstream_impact": [...], "total_waste": ...}]

    逻辑:
      - 如果一个 parent session 有 T1/T3 问题
      - 且它的 child session 也有问题
      - 那么 parent 的问题可能是 root cause
    """
    chains = []

    for root_key in tree["roots"]:
        family = get_session_family(tree, root_key)
        if len(family) < 2:
            continue  # 单 session，无链可追

        root_issues = issues_by_session.get(root_key, [])
        child_issues = []
        for child_key in family[1:]:
            child_issues.extend(issues_by_session.get(child_key, []))

        if not root_issues and not child_issues:
            continue

        # 计算总浪费
        total_tokens = sum(i.get("wasted_tokens", 0) for i in root_issues + child_issues)
        total_seconds = sum(i.get("wasted_seconds", 0) for i in root_issues + child_issues)

        # 识别根因
        root_causes = [i for i in root_issues if i["severity"] == "red"]
        if root_causes:
            chains.append({
                "root_session": root_key,
                "root_label": tree["sessions"].get(root_key, {}).get("label", ""),
                "root_causes": root_causes,
                "downstream_sessions": len(family) - 1,
                "downstream_issues": len(child_issues),
                "total_wasted_tokens": total_tokens,
                "total_wasted_seconds": total_seconds,
            })

    # 按总浪费排序
    chains.sort(key=lambda c: c["total_wasted_tokens"], reverse=True)
    return chains


def find_recent_pipeline_sessions(tree: dict, hours: int = 24) -> list[str]:
    """
    找最近的管线 sessions（有子 Agent 的）。
    """
    import time
    cutoff = int((time.time() - hours * 3600) * 1000)
    recent = []

    for key, data in tree["sessions"].items():
        if data["started_at"] < cutoff:
            continue
        if tree["children"].get(key):  # 有子 Agent
            recent.append(key)

    return sorted(recent, key=lambda k: tree["sessions"][k]["started_at"], reverse=True)
