#!/usr/bin/env python3
"""
DeepFlow Doctor — Session Store（OpenClaw 2026.9.1 存储适配层）

背景：2026.9.1 起 session 存储从文件（sessions.json + .jsonl）迁移到 SQLite：
  - transcript:    ~/.openclaw/agents/<agent>/agent/openclaw-agent.sqlite
                   → transcript_events(session_id, seq, event_json, created_at)
                   event_json 格式与原 .jsonl 行等价（type/message/timestamp），
                   仅 timestamp 为 ISO 字符串（本层统一转 epoch ms int）。
  - session 元数据: 同库 session_nodes（session_key/parent_session_key/label/
                   status/created_at/entry_json）；entry_json 内含 tokens/runtimeMs/startedAt。
  - spawn 关系补充: ~/.openclaw/state/openclaw.sqlite → subagent_runs（跨 agent）。

注意：~/.openclaw/agents/<agent>/openclaw-agent.sqlite（无中间 agent/ 层）是
元数据/配置库，不含 transcript；真正的库在多一层 agent/ 下。

旧 .jsonl 已归档于 agents/<agent>/session-sqlite-import-archive/（.imported-* 后缀），
sessions/ 目录下的 .trajectory-path.json 指针目标已全部失效，勿用。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

AGENTS_ROOT = Path.home() / ".openclaw" / "agents"
STATE_DB = Path.home() / ".openclaw" / "state" / "openclaw.sqlite"


def agent_db_path(agent_id: str) -> Path:
    """真正的 transcript 库路径（中间多一层 agent/）。"""
    return AGENTS_ROOT / agent_id / "agent" / "openclaw-agent.sqlite"


def list_agents() -> list[str]:
    """枚举有 transcript 库的 agent。"""
    if not AGENTS_ROOT.exists():
        return []
    return sorted(
        d.name for d in AGENTS_ROOT.iterdir()
        if d.is_dir() and agent_db_path(d.name).exists()
    )


def _iso_to_ms(ts: Any) -> int:
    """时间戳统一为 epoch ms int。ISO str / int / float / None 均可输入。"""
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, str):
        try:
            return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def iter_transcript_records(session_id: str, agent_id: str | None = None) -> Iterator[dict]:
    """
    从 transcript_events 产出与原 .jsonl 行等价的 record dict 流。
    timestamp 已统一为 epoch ms int（原 ISO 字符串 / 缺失时以 created_at 兜底）。
    """
    agents = [agent_id] if agent_id else list_agents()
    for aid in agents:
        db = agent_db_path(aid)
        if not db.exists():
            continue
        conn = _connect(db)
        try:
            cur = conn.execute(
                "SELECT event_json, created_at FROM transcript_events "
                "WHERE session_id = ? ORDER BY seq",
                (session_id,),
            )
            for event_json, created_at in cur:
                try:
                    record = json.loads(event_json)
                except json.JSONDecodeError:
                    continue
                record["timestamp"] = _iso_to_ms(record.get("timestamp")) or (created_at or 0)
                yield record
            return
        finally:
            conn.close()


def list_sessions(agent_id: str | None = None) -> dict[str, dict]:
    """
    从 session_nodes 列出 session 元数据（合并多 agent）。
    返回 {session_key: {id, session_id, parent, label, status, tokens,
           runtime_ms, started_at, agent_id}}（与旧 sessions.json 契约对齐）。
    """
    sessions: dict[str, dict] = {}
    agents = [agent_id] if agent_id else list_agents()
    for aid in agents:
        db = agent_db_path(aid)
        if not db.exists():
            continue
        conn = _connect(db)
        try:
            cur = conn.execute(
                "SELECT session_key, current_session_id, parent_session_key, "
                "label, display_name, status, created_at, entry_json "
                "FROM session_nodes"
            )
            for key, sid, parent, label, dname, status, created_at, entry_raw in cur:
                entry: dict = {}
                if entry_raw:
                    try:
                        entry = json.loads(entry_raw)
                    except json.JSONDecodeError:
                        pass
                tokens = (entry.get("inputTokens") or 0) + (entry.get("outputTokens") or 0)
                clean_label = (label or dname or "")
                if clean_label:
                    clean_label = clean_label.replace("\n", " ").strip()[:50]
                sessions[key] = {
                    "id": sid or "",
                    "session_id": sid or "",
                    "parent": parent or entry.get("spawnedBy") or "",
                    "label": clean_label,
                    "status": status or entry.get("status", "unknown"),
                    "tokens": tokens,
                    "runtime_ms": entry.get("runtimeMs", 0) or 0,
                    "started_at": _iso_to_ms(entry.get("startedAt")) or (created_at or 0),
                    "agent_id": aid,
                }
        finally:
            conn.close()

    # state 库 subagent_runs 补充跨 agent spawn 关系
    if STATE_DB.exists():
        conn = _connect(STATE_DB)
        try:
            cur = conn.execute(
                "SELECT child_session_key, requester_session_key FROM subagent_runs"
            )
            for child_key, parent_key in cur:
                if child_key in sessions and not sessions[child_key]["parent"] and parent_key:
                    sessions[child_key]["parent"] = parent_key
        finally:
            conn.close()

    return sessions


def build_tree(agent_id: str | None = None) -> dict:
    """
    构建 session 关系树（与旧 build_session_tree 契约一致）。
    返回 {"roots": [...], "children": {parent: [child]}, "sessions": {...}}
    """
    sessions = list_sessions(agent_id)
    children: dict[str, list[str]] = {}
    for key, info in sessions.items():
        parent = info.get("parent")
        if parent:
            children.setdefault(parent, []).append(key)
    roots = [
        k for k in sessions
        if not sessions[k].get("parent") or sessions[k]["parent"] not in sessions
    ]
    return {"roots": roots, "children": children, "sessions": sessions}
