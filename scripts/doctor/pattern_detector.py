#!/usr/bin/env python3
"""
DeepFlow Doctor — Pattern Detector

从结构化事件流中自动检测 5 类带病运行模式：
  🔴 T1: 工具调用错误但自动恢复 (最严重 — 浪费 token + 时间)
  🟡 T2: 门控失效 (质量门禁该拦没拦)
  🟡 T3: 静默降级 (输出缩水/步骤跳过但没报错)
  🟡 T4: 范围失控 (Agent 做了超出任务范围的事)
  🟡 T5: LLM 困惑 (Agent 误解 Prompt 指令，做出与预期相反的行为)
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
    issues.extend(_detect_llm_confusion(events))
    return issues


def detect_pipeline_issues(events: list[dict], run_info: dict | None = None) -> list[dict]:
    """
    管线专用检测：聚焦 gate 门控和 Agent 阶段，过滤探索/调试噪音。

    与 detect_issues 的区别:
      - T1: 只检测管线执行相关的工具错误（gate_fn、run_pipeline、schema 验证）
      - T2: 门控检测增强（检查 gate_pass 但 retry_count > 0 的隐性成本）
      - T3: 静默降级检测（输出文件异常小、字段缺失）
      - T4: 跳过（管线范围内不存在范围失控）

    参数:
        events: 已经过 pipeline_scope 时间窗口过滤的事件列表
        run_info: discover_pipeline_runs() 返回的 run dict（用于交叉验证）
    """
    issues = []
    issues.extend(_detect_pipeline_tool_errors(events))
    issues.extend(_detect_gate_health(events, run_info))
    issues.extend(_detect_silent_degradation(events))  # 复用，事件已过滤
    issues.extend(_detect_llm_confusion(events))
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


# ---------------------------------------------------------------------------
# Pipeline-specific detection (used by --scope pipeline)
# ---------------------------------------------------------------------------

# Doctor 自身输出关键词（过滤自引用）
_DOCTOR_SELF_KEYWORDS = [
    "DeepFlow Doctor", "📋 发现", "scope=pipeline", "🩺 DeepFlow Doctor",
    "L1 候选", "L2 LLM 分析", "doctor_main.py",
]

# 管线核心执行关键词（匹配到这些 = 管线行为，否则 = 探索/调试）
_PIPELINE_KEYWORDS = [
    "run_pipeline", "gate_arch", "gate_decomp", "gate_spec", "gate_review", "gate_pack",
    "gate_fn", "pydantic", "schema", "validation", "ShipPackage", "ArchitectOutput",
    "DecomposerOutput", "SpecifierOutput", "ReviewerOutput",
    "spawn", "sessions_spawn", "sessions_yield",
    "pipeline_state", "blackboard", "stages/",
    "PASS", "FAIL", "gate_pass", "gate_fail",
    "retry", "max_retries",
]


def _is_pipeline_event(ev: dict) -> bool:
    """判断事件是否属于管线核心执行（排除 Doctor 自身输出）。"""
    searchable = ""
    if ev["type"] == "tool_call":
        searchable = (ev.get("input_preview") or "") + (ev.get("tool") or "")
    elif ev["type"] == "tool_result":
        searchable = (ev.get("content_preview") or "") + (ev.get("error") or "")
    elif ev["type"] == "text":
        searchable = ev.get("content") or ""

    # 排除 Doctor 自身的输出
    for doc_kw in _DOCTOR_SELF_KEYWORDS:
        if doc_kw in searchable:
            return False

    searchable_lower = searchable.lower()
    return any(kw.lower() in searchable_lower for kw in _PIPELINE_KEYWORDS)


def _detect_pipeline_tool_errors(events: list[dict]) -> list[dict]:
    """管线专用 T1: 只检测管线执行中的工具错误，忽略探索/调试。"""
    issues = []

    # 只分析管线相关事件
    pipeline_events = [ev for ev in events if _is_pipeline_event(ev)]

    # 匹配 tool_call → tool_result 对（仅管线事件）
    call_map = {}
    for ev in pipeline_events:
        if ev["type"] == "tool_call" and ev.get("tool_id"):
            call_map[ev["tool_id"]] = ev

    # 收集管线事件中的错误
    recovered_ids = set()
    prev_error = None

    for ev in pipeline_events:
        if ev["type"] != "tool_result":
            continue

        if not ev.get("success") and ev.get("error"):
            prev_error = ev
            continue

        if prev_error is not None:
            error_call = call_map.get(prev_error.get("tool_id", ""), {})
            error_text = prev_error.get("error", "")

            # 分类错误，判断是否真正影响管线
            error_type = _classify_error(error_text)
            is_gate_error = any(kw in error_text.lower() for kw in [
                "gate", "schema", "pydantic", "validation", "spawn", "pipeline"
            ])

            if is_gate_error:
                issues.append({
                    "category": "T1",
                    "severity": "red",
                    "sub_type": "T1a_pipeline_recovered",
                    "description": "管线门控错误后自动恢复",
                    "evidence": f"错误: {error_text[:200]}",
                    "error_type": error_type,
                    "tool": error_call.get("tool", "unknown"),
                    "wasted_tokens": _estimate_retry_tokens(error_text),
                    "wasted_seconds": 10,
                    "ts": prev_error.get("ts", 0),
                })

            recovered_ids.add(prev_error.get("tool_id", ""))
            prev_error = None

    # 未恢复的管线错误
    for ev in pipeline_events:
        if ev["type"] != "tool_result":
            continue
        if ev.get("success") or not ev.get("error"):
            continue
        tool_id = ev.get("tool_id", "")
        if tool_id in recovered_ids:
            continue

        error_text = ev.get("error", ev.get("content_preview", ""))
        error_call = call_map.get(tool_id, {})

        issues.append({
            "category": "T1",
            "severity": "red",
            "sub_type": "T1b_pipeline_standalone",
            "description": "管线执行错误（未恢复）",
            "evidence": f"错误: {error_text[:200]}",
            "error_type": _classify_error(error_text),
            "tool": error_call.get("tool", "unknown"),
            "wasted_tokens": _estimate_retry_tokens(error_text),
            "wasted_seconds": 5,
            "ts": ev.get("ts", 0),
        })

    return issues


def _detect_gate_health(events: list[dict], run_info: dict | None = None) -> list[dict]:
    """
    门控健康度检测（管线专用 T2 增强）:
      - gate_pass 但 retry_count > 0 → 隐性成本（Agent 首次输出不合格）
      - gate_fail → 严重问题
      - retry_count == max_retries → 达到重试上限（可能质量妥协）
    """
    issues = []
    if not run_info:
        return issues

    agents = run_info.get("agents", {})
    for agent_name, agent_info in agents.items():
        state = agent_info.get("state", "")
        retry_count = agent_info.get("retry_count", 0)
        max_retries = agent_info.get("max_retries", 0)
        decision = agent_info.get("gate_decision", "")
        feedback = agent_info.get("last_gate_feedback", "")

        # gate_fail → 严重
        if state == "gate_fail":
            issues.append({
                "category": "T2",
                "severity": "red",
                "description": f"门控失败: {agent_name} → {decision}",
                "evidence": f"feedback: {feedback[:200]}",
                "wasted_tokens": retry_count * 5000,
                "wasted_seconds": retry_count * 60,
                "ts": 0,
            })

        # gate_pass 但多次重试 → 隐性成本（≥2 次才算，1 次是正常门控行为）
        elif state == "gate_pass" and retry_count >= 2:
            hit_max = retry_count >= max_retries and max_retries > 0
            desc_suffix = "，达到重试上限（质量可能妥协）" if hit_max else ""
            issues.append({
                "category": "T2",
                "severity": "yellow",
                "description": f"门控通过但多次重试: {agent_name} ({retry_count}/{max_retries}){desc_suffix}",
                "evidence": f"feedback: {feedback[:200]}",
                "wasted_tokens": retry_count * 5000,
                "wasted_seconds": retry_count * 60,
                "ts": 0,
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


# ---------------------------------------------------------------------------
# T5: LLM 困惑 (Prompt 理解偏差)
# ---------------------------------------------------------------------------

def _detect_llm_confusion(events: list[dict]) -> list[dict]:
    """
    检测 LLM 因 Prompt 理解偏差而做出错误决策的模式。

    信号:
      T5a: 能力自限 — LLM 说"我不能"但实际可以 (e.g. "I cannot spawn" when it can)
      T5b: 语义反转 — LLM 做了与指令相反的事 (e.g. "摘要" when task says "拼接")
      T5c: 角色误解 — LLM 误解自己的角色/深度 (e.g. "depth-1 cannot spawn")
      T5d: 提前退出 — LLM 说"完成"但实际还有未完成任务
      T5e: 重复尝试同一操作 — LLM 困惑后反复尝试同一方法
    """
    issues = []

    for i, ev in enumerate(events):
        if ev["type"] != "text":
            continue

        content = ev.get("content", "")
        content_lower = content.lower()

        # ----- T5a: 能力自限 -----
        # LLM 声称不能做某事，但实际上有权限
        capability_denial = [
            "i cannot", "i can't", "not allowed to", "don't have permission",
            "unable to spawn", "cannot spawn", "cannot call", "not able to",
            "i am not able", "i'm not allowed", "我没有权限", "我不能",
            "不允许我", "无法调用",
        ]
        if any(denial in content_lower for denial in capability_denial):
            # 排除误报: 如果前一个 tool_result 是错误，LLM 可能在正确描述失败
            prev_result = None
            for j in range(i - 1, max(0, i - 3), -1):
                if events[j]["type"] == "tool_result" and not events[j].get("success"):
                    prev_result = events[j]
                    break
            # 排除误报: 排除 OpenClaw 内部上下文和引用用户原话
            is_internal = content.strip().startswith("<<<BEGIN_OPENCLAW")
            is_quoting_user = (
                content_lower.strip().startswith("the user said")
                or content_lower.strip().startswith("user said")
                or "用户说" in content_lower[:30]
            )
            if prev_result is None and not is_internal and not is_quoting_user:
                issues.append({
                    "category": "T5",
                    "severity": "yellow",
                    "sub_type": "T5a",
                    "description": "LLM 困惑: 能力自限 — 声称不能做某事但实际可能有权限",
                    "evidence": content[:300],
                    "wasted_tokens": 5000,
                    "wasted_seconds": 30,
                    "ts": ev.get("ts", 0),
                })

        # ----- T5b: 语义反转 -----
        # 任务说"拼接/组装"但 LLM 做了"摘要/合并/压缩"
        # 关键优化: 只在同一段文本中，"拼接"类词和"摘要"类词出现在相近位置时才触发
        # 排除: 文档内容、OpenClaw 内部上下文、长文本（>500字符的可能是文档输出）
        if len(content) < 500 and not content.startswith("<<<BEGIN_OPENCLAW"):
            task_hints = ["must assemble", "must concatenate", "必须拼接", "必须组装", "全部保留"]
            reversal_hints = ["summarize it", "create a summary", "摘要如下", "压缩为", "精简为"]

            has_task_hint = any(h in content_lower for h in task_hints)
            has_reversal = any(h in content_lower for h in reversal_hints)

            if has_task_hint and has_reversal:
                issues.append({
                    "category": "T5",
                    "severity": "yellow",
                    "sub_type": "T5b",
                    "description": "LLM 困惑: 语义反转 — 可能将\"拼接\"误解为\"摘要\"",
                    "evidence": content[:300],
                    "wasted_tokens": 20000,
                    "wasted_seconds": 60,
                    "ts": ev.get("ts", 0),
                })

        # ----- T5c: 角色误解 -----
        # LLM 误解自己的角色或 depth
        role_confusion = [
            "as a depth-1", "as a depth-2", "i am only a", "my role is only",
            "i am just a", "not my responsibility", "超出我的职责",
            "as the main agent, i", "as a sub-agent, i cannot",
        ]
        if any(rc in content_lower for rc in role_confusion):
            issues.append({
                "category": "T5",
                "severity": "yellow",
                "sub_type": "T5c",
                "description": "LLM 困惑: 角色误解 — 可能误解了自己的角色或 depth",
                "evidence": content[:300],
                "wasted_tokens": 3000,
                "wasted_seconds": 20,
                "ts": ev.get("ts", 0),
            })

        # ----- T5d: 提前退出 -----
        # LLM 说"完成"但后续事件显示还有未完成的工作
        premature_exit = [
            "all tasks completed", "all workers completed", "pipeline complete",
            "all phases done", "全部完成", "所有任务已完成",
            "no remaining", "no pending", "没有剩余",
        ]
        # 排除 OpenClaw 内部上下文（不是 LLM 自己说的话）
        is_internal = content.strip().startswith("<<<BEGIN_OPENCLAW")
        if not is_internal and any(pe in content_lower for pe in premature_exit):
            # 检查后续是否有更多 tool_call（说明 LLM 过早宣布完成）
            subsequent_tool_calls = sum(
                1 for e in events[i+1:i+10]
                if e["type"] == "tool_call"
            )
            if subsequent_tool_calls > 2:
                issues.append({
                    "category": "T5",
                    "severity": "yellow",
                    "sub_type": "T5d",
                    "description": "LLM 困惑: 提前退出 — 声称完成但后续仍有操作",
                    "evidence": content[:300],
                    "wasted_tokens": 5000,
                    "wasted_seconds": 30,
                    "ts": ev.get("ts", 0),
                })

    # ----- T5e: 重复尝试同一操作 -----
    # LLM 困惑后反复尝试同一方法（不是换路径重试）
    # V3 优化: 只标记真正困惑的重复
    # 排除: 所有常见的正常操作循环
    EXCLUDE_TOOLS = {
        "read", "sessions_yield", "sessions_list", "sessions_send",
        "subagents", "cron", "message", "session_status",
        "sessions_history", "sessions_spawn", "process",
        "memory_search", "memory_get", "lcm_grep", "lcm_describe",
    }
    EXCLUDE_INPUT_PATTERNS = [
        "pytest", "python3 -m pytest", "git ", "grep ", "find ",
        "wc -l", "cat ", "head ", "tail ", "ls ", "echo ",
        "python3 -c", "diff ", "stat ",
    ]

    prev_tool_call = None
    repeat_count = 0
    for ev in events:
        if ev["type"] != "tool_call":
            continue

        tool = ev.get("tool", "")
        input_preview = ev.get("input_preview", "")[:100]

        # 跳过常见的正常操作
        if tool in EXCLUDE_TOOLS:
            prev_tool_call = None
            repeat_count = 0
            continue
        if any(p in input_preview.lower() for p in EXCLUDE_INPUT_PATTERNS):
            prev_tool_call = None
            repeat_count = 0
            continue

        if prev_tool_call and tool == prev_tool_call.get("tool") and \
           input_preview == prev_tool_call.get("input_preview", "")[:100]:
            repeat_count += 1
            # 只有连续 4+ 次完全相同操作才报告（提高阈值）
            if repeat_count >= 3:
                issues.append({
                    "category": "T5",
                    "severity": "yellow",
                    "sub_type": "T5e",
                    "description": f"LLM 困惑: 重复尝试 — 同一 {tool} 操作无变化重复 {repeat_count + 1} 次",
                    "evidence": f"tool: {tool}, input: {input_preview}",
                    "wasted_tokens": repeat_count * 3000,
                    "wasted_seconds": repeat_count * 15,
                    "ts": ev.get("ts", 0),
                })
                repeat_count = 0  # 重置，避免重复报告
        else:
            repeat_count = 0

        prev_tool_call = ev

    return issues
