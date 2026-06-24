#!/usr/bin/env python3
"""
DeepFlow Doctor V2 — LLM Analyzer (L2)

接收 L1 确定性代码产出的候选问题 + 上下文，调用 LLM 进行：
  1. 真实性判定（真问题 vs 误报）
  2. 根因分析
  3. 影响评估
  4. 双轨修复建议（系统性 + 孤立）
  5. 反思自检（confidence + 覆盖度检查）

架构:
  L1 (code) → candidates + context
  L2 (LLM)  → structured diagnosis JSON
  L3 (code) → formatted report
"""

import json
import os
import sys
from pathlib import Path
from typing import Any


def _get_api_config() -> dict:
    """从 openclaw.json 读取 DashScope API 配置。优先用 bailian2 (标准端点)。"""
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        providers = cfg["models"]["providers"]
        # Prefer bailian2 (standard endpoint) over bailian (coding endpoint)
        provider = providers.get("bailian2", providers.get("bailian"))
        return {
            "base_url": provider["baseUrl"],
            "api_key": provider["apiKey"],
            "model": "qwen3.7-plus",
        }
    except Exception as e:
        raise RuntimeError(f"Cannot read DashScope config from openclaw.json: {e}")


def _call_llm(system_prompt: str, user_prompt: str, api_config: dict) -> str:
    """调用 DashScope OpenAI-compatible API (stdlib only, no requests dependency)。"""
    import urllib.request
    import urllib.error

    url = f"{api_config['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": api_config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
        "enable_thinking": False,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


# ──────────────────────────────────────────────────────────────
#  Prompt Templates
# ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是 DeepFlow Doctor — 多 Agent 管线运行诊断专家。

你的职责是分析 L1（确定性代码）筛选出的候选问题，做出最终诊断。

## 你需要做的

### 第一步：真实性判定（每个候选问题）
对每个候选问题判断：
- **true_positive**: 真实的管线问题，需要关注
- **false_positive**: 误报。常见误报模式：
  - Agent 读取文件/日志，文件内容包含 "error"/"timeout"/"Traceback" 等词 → 不是 Agent 自身的错误
  - 自修复 Agent 分析旧 session 日志时，把旧日志的错误当成当前错误
  - Gate FAIL 是正常的契约笼子拦截，不是 bug
  - Agent 运行诊断脚本，脚本输出包含错误关键词 → 诊断工具的正常输出

### 第二步：根因聚类
把 true_positive 问题按根因聚类：
- 如果 ≥3 个 true_positive 共享同一根因 → 标记为 **systemic**（系统性问题）
- 否则标记为 **isolated**（孤立问题）

### 第三步：修复建议
- **系统性修复**: 针对系统性根因的架构级修复（改契约/Prompt/引擎/工具链）
- **孤立修复**: 针对单个问题的具体修复（改代码/配置/路径）

### 第四步：反思自检
- 检查你的分析是否有遗漏或矛盾
- 给出整体置信度（0-100）

## 输出格式

严格输出 JSON（不含 markdown 代码块）：

{
  "diagnoses": [
    {
      "candidate_id": 0,
      "verdict": "true_positive" | "false_positive",
      "confidence": 0.0-1.0,
      "reason": "判定理由（一句话）",
      "root_cause": "根因（仅 true_positive）",
      "impact": "high" | "medium" | "low",
      "impact_detail": "影响描述（仅 true_positive）",
      "fix_suggestion": "具体修复建议（仅 true_positive）",
      "cluster_id": "cluster-1" | null
    }
  ],
  "systemic_issues": [
    {
      "cluster_id": "cluster-1",
      "root_cause": "系统性根因描述",
      "affected_count": 3,
      "affected_candidates": [0, 1, 5],
      "systemic_fix": "架构级修复建议（改什么文件、怎么改）",
      "priority": "P0" | "P1" | "P2"
    }
  ],
  "reflection": {
    "missed_anything": "是否有遗漏？描述可能遗漏的点",
    "contradictions": "是否有矛盾？",
    "overall_confidence": 0-100,
    "coverage_check": "是否覆盖了所有 candidate？true_positive + false_positive = total?"
  },
  "summary": {
    "total_candidates": 10,
    "true_positives": 5,
    "false_positives": 5,
    "systemic_count": 1,
    "isolated_count": 2,
    "top_priority_fix": "最应该先修什么（一句话）"
  }
}
"""


def _build_user_prompt(
    candidates: list[dict],
    events: list[dict],
    session_label: str,
    pipeline_meta: dict,
) -> str:
    """构建 user prompt：候选问题 + 上下文 + 管线元数据。"""

    parts = []

    # 1. Pipeline metadata
    parts.append(f"## 管线信息\n- Session: {session_label}")
    parts.append(f"- Agent 数: {pipeline_meta.get('agent_count', '?')}")
    parts.append(f"- 运行时长: {pipeline_meta.get('runtime_seconds', '?')}s")
    parts.append(f"- Token 消耗: {pipeline_meta.get('tokens', '?')}")
    parts.append("")

    # 2. Candidates with context (cap at 15 to keep prompt manageable)
    capped = candidates[:15]
    parts.append(f"## 候选问题（共 {len(candidates)} 个，以下展示前 {len(capped)} 个代表性候选，剩余 {len(candidates)-len(capped)} 个模式类似）")
    parts.append("")

    for i, c in enumerate(capped):
        parts.append(f"### 候选 #{i}")
        parts.append(f"- 类别: {c.get('category', '?')} ({c.get('sub_type', '?')})")
        parts.append(f"- 严重度: {c.get('severity', '?')}")
        parts.append(f"- 错误类型: {c.get('error_type', '?')}")
        parts.append(f"- 工具: {c.get('tool', '?')}")
        parts.append(f"- 证据: {c.get('evidence', '')[:300]}")

        # Context: find events near this candidate's timestamp
        ts = c.get("ts", 0)
        if isinstance(ts, str):
            try:
                ts = int(ts)
            except (ValueError, TypeError):
                ts = 0
        if ts > 0 and events:
            context_events = _get_context_events(events, ts, window=5)
            if context_events:
                parts.append(f"- 上下文事件:")
                for ce in context_events:
                    ce_type = ce.get("type", "?")
                    if ce_type == "tool_call":
                        parts.append(f"    [{ce_type}] {ce.get('tool', '?')}: {ce.get('input_preview', '')[:120]}")
                    elif ce_type == "tool_result":
                        success = "✅" if ce.get("success") else "❌"
                        parts.append(f"    [{ce_type}] {success} {ce.get('tool', '?')}: {ce.get('content_preview', '')[:120]}")
                    elif ce_type == "text":
                        parts.append(f"    [{ce_type}] {ce.get('content', '')[:120]}")
        parts.append("")

    return "\n".join(parts)


def _get_context_events(events: list[dict], target_ts: int, window: int = 5) -> list[dict]:
    """获取目标时间戳前后的事件（跳过 thinking/text 类型，只保留 tool_call/tool_result）。"""
    # Find the index closest to target_ts
    best_idx = 0
    first_ts = events[0].get("ts", 0)
    if isinstance(first_ts, str):
        try:
            first_ts = int(first_ts)
        except (ValueError, TypeError):
            first_ts = 0
    best_diff = abs(first_ts - target_ts)
    for i, ev in enumerate(events):
        ev_ts = ev.get("ts", 0)
        if isinstance(ev_ts, str):
            try:
                ev_ts = int(ev_ts)
            except (ValueError, TypeError):
                ev_ts = 0
        diff = abs(ev_ts - target_ts)
        if diff < best_diff:
            best_diff = diff
            best_idx = i

    # Get surrounding tool events
    context = []
    start = max(0, best_idx - window)
    end = min(len(events), best_idx + window + 1)
    for ev in events[start:end]:
        if ev.get("type") in ("tool_call", "tool_result"):
            context.append(ev)
    return context[:8]  # Cap at 8 context events


def analyze_candidates(
    candidates: list[dict],
    events: list[dict],
    session_label: str = "",
    pipeline_meta: dict | None = None,
) -> dict:
    """
    L2: 调用 LLM 分析候选问题。

    Args:
        candidates: L1 检测到的候选问题列表
        events: 完整事件流（用于上下文提取）
        session_label: session 标签
        pipeline_meta: 管线元数据

    Returns:
        LLM 结构化诊断 dict
    """
    if not candidates:
        return {
            "diagnoses": [],
            "systemic_issues": [],
            "reflection": {
                "missed_anything": "无候选问题，无需分析",
                "contradictions": "无",
                "overall_confidence": 100,
                "coverage_check": "0 candidates, 0 diagnoses — consistent",
            },
            "summary": {
                "total_candidates": 0,
                "true_positives": 0,
                "false_positives": 0,
                "systemic_count": 0,
                "isolated_count": 0,
                "top_priority_fix": "无问题",
            },
        }

    api_config = _get_api_config()
    user_prompt = _build_user_prompt(candidates, events, session_label, pipeline_meta or {})

    raw_response = _call_llm(SYSTEM_PROMPT, user_prompt, api_config)

    # Parse JSON response
    # Handle potential markdown code block wrapping
    text = raw_response.strip()
    if text.startswith("```"):
        # Remove markdown fences
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: try to extract JSON from the response
        import re
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {
                "diagnoses": [],
                "systemic_issues": [],
                "reflection": {
                    "missed_anything": f"LLM response not parseable as JSON: {text[:200]}",
                    "contradictions": "unknown",
                    "overall_confidence": 0,
                    "coverage_check": "parse failure",
                },
                "summary": {
                    "total_candidates": len(candidates),
                    "true_positives": 0,
                    "false_positives": 0,
                    "systemic_count": 0,
                    "isolated_count": 0,
                    "top_priority_fix": "LLM 分析失败，需要手动检查",
                },
            }

    return result
