#!/usr/bin/env python3
"""
DeepFlow Doctor — Transcript Parser

解析 OpenClaw session .jsonl 为结构化事件流。

输出:
  [
    {"type": "tool_call", "tool": "exec", "input_preview": "...", "ts": 1234567890},
    {"type": "tool_result", "tool": "exec", "success": true/false, "error": "...", "ts": ...},
    {"type": "text", "content": "...", "ts": ...},
    {"type": "thinking", "content": "...", "ts": ...},
  ]
"""

import json
import re
from pathlib import Path
from typing import Any


def parse_transcript(path: str | Path) -> list[dict]:
    """解析 .jsonl transcript 为事件列表。"""
    events = []
    path = Path(path)
    if not path.exists():
        return events

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = record.get("type")
            ts = record.get("timestamp", 0)

            if rtype == "message":
                msg = record.get("message", {})
                role = msg.get("role", "")
                content = msg.get("content", "")
                msg_is_error = msg.get("isError", False)
                tool_name = msg.get("toolName", "")
                tool_call_id = msg.get("toolCallId", "")

                # toolResult 在 message 层级 (role=toolResult)
                if role == "toolResult":
                    result_text = _extract_result_text(content)
                    error_msg = _extract_error(result_text, msg_is_error)
                    events.append({
                        "type": "tool_result",
                        "role": "toolResult",
                        "tool": tool_name,
                        "tool_id": tool_call_id,
                        "success": not msg_is_error and error_msg is None,
                        "error": error_msg,
                        "content_preview": result_text[:500],
                        "ts": ts,
                    })
                else:
                    events.extend(_parse_message(role, content, ts, msg_is_error=msg_is_error))
            elif rtype == "session":
                events.append({"type": "session_start", "id": record.get("id", ""), "ts": ts})

    return events


def _parse_message(role: str, content: Any, ts: int, msg_is_error: bool = False) -> list[dict]:
    """解析 message 内容块。"""
    events = []

    if isinstance(content, str):
        events.append({"type": "text", "role": role, "content": content, "ts": ts})
        return events

    if not isinstance(content, list):
        return events

    for part in content:
        if not isinstance(part, dict):
            continue

        ptype = part.get("type", "")

        if ptype == "thinking":
            events.append({"type": "thinking", "role": role, "content": part.get("thinking", ""), "ts": ts})

        elif ptype == "text":
            events.append({"type": "text", "role": role, "content": part.get("text", ""), "ts": ts})

        elif ptype == "toolCall":
            tool_name = part.get("name", "unknown")
            tool_input = part.get("input", {})
            tool_id = part.get("id", "")
            input_preview = _summarize_input(tool_name, tool_input)
            events.append({
                "type": "tool_call",
                "role": role,
                "tool": tool_name,
                "tool_id": tool_id,
                "input_preview": input_preview,
                "input_raw": tool_input,
                "ts": ts,
            })

        elif ptype == "toolResult":
            tool_id = part.get("toolUseId", "")
            result_content = part.get("content", "")
            is_error = part.get("isError", False) or msg_is_error
            result_text = _extract_result_text(result_content)
            error_msg = _extract_error(result_text, is_error)
            events.append({
                "type": "tool_result",
                "role": "toolResult",
                "tool_id": tool_id,
                "success": not is_error and error_msg is None,
                "error": error_msg,
                "content_preview": result_text[:500],
                "ts": ts,
            })

    return events


def _summarize_input(tool_name: str, tool_input: dict) -> str:
    """提取 tool call 的关键输入信息。"""
    if tool_name == "exec":
        cmd = tool_input.get("command", "")
        return cmd[:200]
    elif tool_name in ("read", "write", "edit"):
        path = tool_input.get("path", "")
        return path
    elif tool_name == "sessions_spawn":
        task = tool_input.get("task", "")
        label = tool_input.get("label", "")
        return f"label={label} task={task[:100]}"
    elif tool_name == "sessions_send":
        target = tool_input.get("sessionKey", tool_input.get("target", ""))
        msg = tool_input.get("message", "")[:100]
        return f"target={target} msg={msg}"
    else:
        # Generic: first 2 keys
        keys = list(tool_input.keys())[:3]
        return ", ".join(f"{k}={str(tool_input[k])[:50]}" for k in keys)


def _extract_result_text(content: Any) -> str:
    """从 tool result content 提取文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif isinstance(part, str):
                texts.append(part)
        return "\n".join(texts)
    return str(content)


def _extract_error(result_text: str, is_error: bool) -> str | None:
    """
    从 tool result 中检测错误。

    原则：只信任 isError 标志（由 OpenClaw 设置），不用正则扫文本。
    原因：正则扫文本会产生 ~90% 误报率（Agent 读文件内容含 "timeout" 等词被误判为错误）。
    """
    if is_error:
        return result_text[:300]

    # 仅检测明确的结构化错误信号（不扫描普通文本）
    # 1. exec 返回非零退出码（stderr 有内容）
    if re.search(r'^---\n\n\(Command exited with code [1-9]\d*\)', result_text, re.MULTILINE):
        return result_text[:300]

    # 2. 工具返回的 JSON 错误包装
    if result_text.startswith('{"status": "error"'):
        return result_text[:300]

    return None
