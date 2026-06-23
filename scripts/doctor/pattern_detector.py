#!/usr/bin/env python3
"""
DeepFlow Doctor — Pattern Detector

从结构化事件流中自动检测 4 类带病运行模式：
  🔴 T1: 工具调用错误但自动恢复 (最严重 — 浪费 token + 时间)
  🟡 T2: 门控失效 (质量门禁该拦没拦)
  🟡 T3: 静默降级 (输出缩水/步骤跳过但没报错)
  🟡 T4: 范围失控 (Agent 做了超出任务范围的事)
"""

import re
from typing import Any


def detect_issues(events: list[dict], session_label: str = "") -> list[dict]:
    """
    从事件流中检测所有带病模式。

    返回:
        [{"category": "T1"|"T2"|"T3"|"T4",
          "severity": "red"|"yellow",
          "description": "...",
          "evidence": "...",
          "wasted_tokens": int,
          "wasted_seconds": float,
          "ts": int}]
    """
    issues = []
    issues.extend(_detect_tool_error_recovery(events))
    issues.extend(_detect_gate_failures(events))
    issues.extend(_detect_silent_degradation(events))
    issues.extend(_detect_scope_creep(events, session_label))
    return issues


# ---------------------------------------------------------------------------
# T1: 工具调用错误但自动恢复
# ---------------------------------------------------------------------------

def _detect_tool_error_recovery(events: list[dict]) -> list[dict]:
    """
    检测两类工具错误模式:
    T1a: tool_call → tool_result(error) → tool_call(重试/换路径) → tool_result(success)
         隐蔽的带病模式: 最终成功了，但浪费了 token 和时间。
    T1b: tool_call → tool_result(error)
         独立错误: 工具调用失败，无论是否恢复都记录。
    """
    issues = []

    # 匹配 tool_call → tool_result 对
    call_map = {}  # tool_id → call event
    for ev in events:
        if ev["type"] == "tool_call" and ev.get("tool_id"):
            call_map[ev["tool_id"]] = ev

    # 第一遍: 收集所有错误事件
    all_errors = []
    for ev in events:
        if ev["type"] != "tool_result":
            continue
        if not ev.get("success") and ev.get("error"):
            all_errors.append(ev)

    # 第二遍: 分类每个错误是 "恢复型" 还是 "独立型"
    recovered_error_ids = set()
    
    # 找 error → retry(success) 模式
    prev_error = None
    for ev in events:
        if ev["type"] != "tool_result":
            continue

        if not ev.get("success") and ev.get("error"):
            prev_error = ev
            continue

        # 成功了，但之前有错误？
        if prev_error is not None:
            error_call = call_map.get(prev_error.get("tool_id", ""), {})
            success_call = call_map.get(ev.get("tool_id", ""), {})

            time_diff = 0
            try:
                if error_call.get("ts") and success_call.get("ts"):
                    t1, t2 = error_call["ts"], success_call["ts"]
                    if isinstance(t1, (int, float)) and isinstance(t2, (int, float)):
                        time_diff = (t2 - t1) / 1000.0
            except (TypeError, ValueError):
                pass

            error_text = prev_error.get("error", "")
            issues.append({
                "category": "T1",
                "severity": "red",
                "sub_type": "T1a_recovered",
                "description": f"工具调用错误后自动恢复",
                "evidence": f"错误: {error_text[:150]}\n恢复: {success_call.get('input_preview', '')[:150]}",
                "error_type": _classify_error(error_text),
                "tool": error_call.get("tool", "unknown"),
                "wasted_tokens": _estimate_retry_tokens(error_text),
                "wasted_seconds": max(time_diff, 5),
                "ts": prev_error.get("ts", 0),
            })
            recovered_error_ids.add(prev_error.get("tool_id", ""))
            prev_error = None

    # 第三遍: 收集未恢复的独立错误 (T1b)
    for ev in all_errors:
        tool_id = ev.get("tool_id", "")
        if tool_id in recovered_error_ids:
            continue  # 已在 T1a 中报告
        
        error_call = call_map.get(tool_id, {})
        error_text = ev.get("error", ev.get("content_preview", ""))
        
        issues.append({
            "category": "T1",
            "severity": "red",
            "sub_type": "T1b_standalone",
            "description": f"工具调用错误（未恢复）",
            "evidence": f"错误: {error_text[:200]}",
            "error_type": _classify_error(error_text),
            "tool": error_call.get("tool", "unknown"),
            "wasted_tokens": _estimate_retry_tokens(error_text),
            "wasted_seconds": 3,
            "ts": ev.get("ts", 0),
        })

    return issues


def _classify_error(error: str) -> str:
    """分类错误类型。"""
    error_lower = error.lower()
    if "module" in error_lower and "not found" in error_lower:
        return "ModuleNotFoundError"
    if "enoent" in error_lower or "no such file" in error_lower:
        return "FileNotFoundError"
    if "file not found" in error_lower or "does not exist" in error_lower:
        return "FileNotFoundError"
    if "not found" in error_lower:
        return "NotFound"
    if "importerror" in error_lower:
        return "ImportError"
    if "syntaxerror" in error_lower:
        return "SyntaxError"
    if "attributeerror" in error_lower:
        return "AttributeError"
    if "keyerror" in error_lower or ("key" in error_lower and "error" in error_lower):
        return "KeyError"
    if "pydantic" in error_lower or "validation" in error_lower:
        return "ValidationError"
    if "traceback" in error_lower:
        return "Traceback"
    if "timeout" in error_lower or "timed out" in error_lower:
        return "Timeout"
    if "could not find" in error_lower or "edit mismatch" in error_lower:
        return "EditMismatch"
    if "cross.app" in error_lower:
        return "FeishuCrossApp"
    if "not a git" in error_lower:
        return "NotGitRepo"
    if "未知命令" in error_lower or "unknown command" in error_lower:
        return "UnknownCommand"
    if "invalid.*param" in error_lower or "invalid param" in error_lower:
        return "InvalidParam"
    if "exit code" in error_lower:
        return "NonZeroExit"
    if "status" in error_lower and "error" in error_lower:
        return "ToolStatusError"
    if "exit code" in error_lower:
        return "NonZeroExit"
    return "OtherError"


def _estimate_retry_tokens(error: str) -> int:
    """估算一次重试浪费的 token 数。"""
    # 基础: 错误信息 + 重试 prompt ≈ 2000 tokens
    base = 2000
    # 如果错误信息很长（比如 traceback），加更多
    if "traceback" in error.lower():
        base += 1500
    return base


# ---------------------------------------------------------------------------
# T2: 门控失效
# ---------------------------------------------------------------------------

def _detect_gate_failures(events: list[dict]) -> list[dict]:
    """
    检测: 质量门禁应该拦住但没拦住的情况。
    信号:
      - gate 相关的 exec 输出包含 "FAIL" 但后续仍继续
      - "auto-pass" / "No code gate" 出现
      - 评分虚高（高分但后续被 reviewer 打回）
    """
    issues = []

    for i, ev in enumerate(events):
        if ev["type"] != "tool_result":
            continue
        content = ev.get("content_preview", "")

        # 信号 1: "No code gate" / "auto-pass"
        if "no code gate" in content.lower() or "auto-pass" in content.lower():
            issues.append({
                "category": "T2",
                "severity": "yellow",
                "description": "Agent 无代码门控，自动放行",
                "evidence": content[:200],
                "wasted_tokens": 0,
                "wasted_seconds": 0,
                "ts": ev.get("ts", 0),
            })

        # 信号 2: Gate FAIL 但后续有 update-status PASS
        if "gate" in content.lower() and "fail" in content.lower():
            # 检查后续事件是否有 update-status PASS
            for j in range(i + 1, min(i + 10, len(events))):
                next_ev = events[j]
                if next_ev["type"] == "tool_call" and "PASS" in next_ev.get("input_preview", ""):
                    issues.append({
                        "category": "T2",
                        "severity": "red",
                        "description": "门控 FAIL 后仍被标记为 PASS",
                        "evidence": f"Gate: {content[:100]}\nOverride: {next_ev.get('input_preview', '')[:100]}",
                        "wasted_tokens": 5000,  # 后续可能需要的修复 token
                        "wasted_seconds": 60,
                        "ts": ev.get("ts", 0),
                    })
                    break

    return issues


# ---------------------------------------------------------------------------
# T3: 静默降级
# ---------------------------------------------------------------------------

def _detect_silent_degradation(events: list[dict]) -> list[dict]:
    """
    检测: 输出缩水/步骤跳过但没报错。
    信号:
      - Agent 输出文件大小异常小
      - "skipping" / "degraded" / "fallback" 关键词
      - 应该有 N 个输出但只看到 M 个 (M < N)
      - exec 返回 ENOENT 但 Agent 说 "I have all the data"
    """
    issues = []

    for i, ev in enumerate(events):
        content = ""
        if ev["type"] == "tool_result":
            content = ev.get("content_preview", "")
        elif ev["type"] == "text":
            content = ev.get("content", "")

        if not content:
            continue

        content_lower = content.lower()

        # 信号 1: ENOENT/missing 但 Agent 声称有数据
        # 只匹配 exec/read 的 tool_result，不匹配普通 JSON 输出
        if ev["type"] == "tool_result" and any(kw in content_lower for kw in ["enoent", "no such file", "file not found"]):
            # 检查后续 agent 文本是否声称成功
            for j in range(i + 1, min(i + 5, len(events))):
                next_ev = events[j]
                if next_ev["type"] == "text" and next_ev.get("role") == "assistant":
                    next_text = next_ev.get("content", "").lower()
                    if any(kw in next_text for kw in ["i have all", "all the data", "proceeding", "let me analyze", "let me perform"]):
                        issues.append({
                            "category": "T3",
                            "severity": "yellow",
                            "description": "文件缺失但 Agent 声称有完整数据",
                            "evidence": f"缺失: {content[:100]}\n声称: {next_ev.get('content', '')[:100]}",
                            "wasted_tokens": 3000,
                            "wasted_seconds": 30,
                            "ts": ev.get("ts", 0),
                        })
                        break

        # 信号 2: 降级关键词（只匹配 tool_result，不匹配普通文本）
        if ev["type"] == "tool_result":
            if any(kw in content_lower for kw in ["fallback mode", "degraded - no", "degraded mode", "skipping step", "no api key"]):
                issues.append({
                    "category": "T3",
                    "severity": "yellow",
                    "description": "静默降级: 使用了 fallback/degraded 模式",
                    "evidence": content[:200],
                    "wasted_tokens": 1000,
                    "wasted_seconds": 10,
                    "ts": ev.get("ts", 0),
                })

    return issues


# ---------------------------------------------------------------------------
# T4: 范围失控
# ---------------------------------------------------------------------------

def _detect_scope_creep(events: list[dict], session_label: str = "") -> list[dict]:
    """
    检测: Agent 做了超出任务范围的事。
    信号:
      - session label 说 "Reviewer" 但 Agent 做了 write/exec 到非预期路径
      - 大量 write 操作（输出膨胀）
      - Agent 修改了非自己负责的文件
    """
    issues = []
    write_targets = []

    for ev in events:
        if ev["type"] != "tool_call":
            continue

        # 收集所有 write 操作
        if ev.get("tool") in ("write", "edit"):
            target = ev.get("input_preview", "")
            write_targets.append(target)

        # 收集所有 exec 操作中的 write 行为
        if ev.get("tool") == "exec":
            cmd = ev.get("input_preview", "")
            if any(kw in cmd for kw in ["cp ", "mv ", "mkdir ", "tee ", "> "]):
                write_targets.append(f"exec:{cmd[:100]}")

    # 过滤预期的写操作（stages/, blackboard/, .json 输出等）
    unexpected_writes = [
        t for t in write_targets
        if not any(kw in t.lower() for kw in [
            "stages/", "blackboard/", "_output.json", "_result.json", ".completed",
            "ship_output/", "ship_package", "summary.md", "pipeline_state", "pipeline_config",
            ".notified_stages", ".cron_run_count", ".stage_progress", ".auto_chain",
            "architect", "decomposer", "specifier", "reviewer", "packager"
        ])
    ]

    # 信号: 非预期的写操作过多（>8 个）
    if len(unexpected_writes) > 8:
        issues.append({
            "category": "T4",
            "severity": "yellow",
            "description": f"范围失控: {len(unexpected_writes)} 个非预期写操作（总 {len(write_targets)} 个）",
            "evidence": "\n".join(unexpected_writes[:5]) + (f"\n... 还有 {len(unexpected_writes)-5} 个" if len(unexpected_writes) > 5 else ""),
            "wasted_tokens": len(unexpected_writes) * 500,
            "wasted_seconds": len(unexpected_writes) * 3,
            "ts": events[-1].get("ts", 0) if events else 0,
        })

    return issues
