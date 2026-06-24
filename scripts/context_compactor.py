"""
Context Compaction — LLM 驱动的上下文压缩

设计理念:
  - 不是截断历史，是让 LLM 总结"下一个 phase 需要的信息"
  - 每个 Worker 的上下文从 80K → < 10K tokens
  - 触发条件：每 N 轮 或 token 数超过阈值

集成点:
  - loop_runner.py 的 next 命令在返回 task prompt 前调用
  - 或主 Agent 在 spawn Worker 前调用，注入压缩上下文

模型选择:
  - 推荐 qwen3.7-plus（快 + 便宜），压缩任务不需要顶级推理
  - 压缩 prompt 约 500 tokens，输入约 5-10K tokens，输出约 1-2K tokens
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Bootstrap
DEEPFLOW_HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEEPFLOW_HOME))

from contracts.shared.worker_result import WorkerResult

SHANGHAI_TZ = timezone(timedelta(hours=8))


@dataclass
class CompactedContext:
    """压缩后的上下文"""
    completed_phases: list[dict] = field(default_factory=list)
    open_issues: list[str] = field(default_factory=list)
    next_phase_brief: str = ""
    goal_alignment: str = ""
    timestamp: str = ""
    token_estimate: int = 0  # 预估压缩后的 token 数

    def to_prompt_text(self) -> str:
        """生成可注入 Worker prompt 的文本"""
        lines = ["# 📦 已完成 Phase 上下文（压缩摘要）\n"]

        for phase in self.completed_phases:
            status_emoji = {"success": "✅", "partial": "⚠️", "failed": "❌"}.get(
                phase.get("status", ""), "❓"
            )
            lines.append(f"## Phase {phase['phase']}: {phase['name']} {status_emoji}")
            lines.append(f"**决策**: {phase.get('key_decisions', 'N/A')}")
            if phase.get("artifacts"):
                lines.append(f"**产出**: {', '.join(phase['artifacts'])}")
            lines.append("")

        if self.open_issues:
            lines.append("## ⚠️ 未解决问题")
            for issue in self.open_issues:
                lines.append(f"- {issue}")
            lines.append("")

        if self.next_phase_brief:
            lines.append(f"## ➡️ 下一 Phase 简报")
            lines.append(self.next_phase_brief)
            lines.append("")

        if self.goal_alignment:
            lines.append(f"## 🎯 目标对齐度")
            lines.append(self.goal_alignment)
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "completed_phases": self.completed_phases,
            "open_issues": self.open_issues,
            "next_phase_brief": self.next_phase_brief,
            "goal_alignment": self.goal_alignment,
            "timestamp": self.timestamp,
            "token_estimate": self.token_estimate,
        }


class ContextCompactor:
    """上下文压缩器"""

    # Compaction prompt（给 LLM 的指令）
    COMPACT_PROMPT = """你是一个项目进度分析师。

已完成 {completed_count}/{total_count} 个 phase，以下是每个 phase 的产出信息。
请为下一个 phase（Phase {next_phase}: {next_phase_name}）生成一份"工作上下文摘要"。

## 已完成 Phase 信息
{phase_details}

## 要求
1. **completed_phases**: 每个已完成 phase 的关键决策和产出（只保留下一个 phase 需要的）
2. **open_issues**: 当前未解决的问题（跨 phase 的问题）
3. **next_phase_brief**: 下一个 phase 应该做什么，基于已完成上下文
4. **goal_alignment**: 当前产出与原始目标的对齐程度

## 压缩目标
- 原始信息约 {raw_token_estimate} tokens
- 压缩后应 < {target_tokens} tokens（压缩比 {compression_ratio}%）
- 保留关键决策，删除中间过程

## 输出格式（严格 JSON）
```json
{{
    "completed_phases": [
        {{
            "phase": N,
            "name": "phase_name",
            "status": "success|partial|failed",
            "key_decisions": "一句话总结关键决策",
            "artifacts": ["产出文件列表"]
        }}
    ],
    "open_issues": ["未解决问题"],
    "next_phase_brief": "下一个 phase 应该做什么",
    "goal_alignment": "当前产出与目标的对齐程度"
}}
```"""

    def __init__(
        self,
        compact_every_n: int = 3,
        token_threshold: int = 60_000,
        target_tokens: int = 2_000,
    ):
        self.compact_every_n = compact_every_n
        self.token_threshold = token_threshold
        self.target_tokens = target_tokens
        self.last_compaction: Optional[CompactedContext] = None

    def should_compact(self, completed_count: int, estimated_tokens: int = 0) -> bool:
        """判断是否需要压缩"""
        if completed_count == 0:
            return False
        if completed_count % self.compact_every_n == 0:
            return True
        if estimated_tokens > self.token_threshold:
            return True
        return False

    def build_compaction_prompt(
        self,
        results: list[WorkerResult],
        next_phase: int,
        next_phase_name: str,
        total_phases: int,
    ) -> str:
        """构建压缩 prompt"""
        phase_details = []
        for r in results:
            artifacts_list = list(r.artifacts.values()) if r.artifacts else []
            phase_details.append(
                f"Phase {r.phase} ({r.phase_name}): status={r.status}, "
                f"summary={r.summary}, confidence={r.confidence}, "
                f"artifacts={artifacts_list}, issues={r.issues}"
            )

        raw_estimate = sum(len(r.summary) + len(json.dumps(r.artifacts)) for r in results) // 4  # 粗略估算
        compression_ratio = int(self.target_tokens / max(raw_estimate, 1) * 100)

        return self.COMPACT_PROMPT.format(
            completed_count=len(results),
            total_count=total_phases,
            next_phase=next_phase,
            next_phase_name=next_phase_name,
            phase_details="\n".join(phase_details),
            raw_token_estimate=raw_estimate,
            target_tokens=self.target_tokens,
            compression_ratio=min(compression_ratio, 100),
        )

    def compact_from_results(
        self,
        results: list[WorkerResult],
        next_phase: int,
        next_phase_name: str,
        total_phases: int,
        llm_response: Optional[str] = None,
    ) -> CompactedContext:
        """
        从 WorkerResult 列表生成压缩上下文。

        两种模式：
        1. llm_response 不为空：解析 LLM 的压缩结果
        2. llm_response 为空：确定性压缩（不调 LLM，从 WorkerResult 直接提取）

        模式 2 用于测试和 fallback。
        """
        now = datetime.now(SHANGHAI_TZ).isoformat()

        if llm_response:
            return self._parse_llm_response(llm_response, now)

        # 确定性压缩：直接从 WorkerResult 提取关键信息
        completed_phases = []
        all_issues = []
        summaries = []

        for r in results:
            completed_phases.append({
                "phase": r.phase,
                "name": r.phase_name,
                "status": r.status,
                "key_decisions": r.summary,
                "artifacts": list(r.artifacts.values()) if r.artifacts else [],
            })
            all_issues.extend(r.issues)
            if r.summary:
                summaries.append(f"Phase {r.phase}: {r.summary}")

        return CompactedContext(
            completed_phases=completed_phases,
            open_issues=all_issues[:10],  # Top 10
            next_phase_brief=f"基于已完成的 {len(results)} 个 phase，继续执行 Phase {next_phase} ({next_phase_name})",
            goal_alignment=f"已完成 {len(results)}/{total_phases} phases",
            timestamp=now,
            token_estimate=len(json.dumps(completed_phases, ensure_ascii=False)) // 4,
        )

    def _parse_llm_response(self, response: str, timestamp: str) -> CompactedContext:
        """解析 LLM 压缩结果"""
        import re

        pattern = r'```json\s*\n(.*?)\n\s*```'
        match = re.search(pattern, response, re.DOTALL)

        if match:
            try:
                data = json.loads(match.group(1).strip())
                return CompactedContext(
                    completed_phases=data.get("completed_phases", []),
                    open_issues=data.get("open_issues", []),
                    next_phase_brief=data.get("next_phase_brief", ""),
                    goal_alignment=data.get("goal_alignment", ""),
                    timestamp=timestamp,
                    token_estimate=len(match.group(1)) // 4,
                )
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: 空上下文
        return CompactedContext(timestamp=timestamp)


# ── CLI ───────────────────────────────────────────────────────────

def main():
    """
    CLI: 读取 WorkerResult 列表，输出压缩上下文。

    用法:
      python3 scripts/context_compactor.py \
        --input results.json \
        --next-phase 5 \
        --next-phase-name "consolidator" \
        --total-phases 10 \
        --format json|prompt
    """
    import argparse

    parser = argparse.ArgumentParser(description="Context Compactor")
    parser.add_argument("--input", required=True, help="WorkerResult JSON 数组文件路径")
    parser.add_argument("--next-phase", type=int, required=True)
    parser.add_argument("--next-phase-name", required=True)
    parser.add_argument("--total-phases", type=int, required=True)
    parser.add_argument("--format", choices=["json", "prompt"], default="json")
    parser.add_argument("--deterministic", action="store_true",
                        help="使用确定性压缩（不调 LLM）")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    results = [WorkerResult(**d) for d in data]
    compactor = ContextCompactor()

    context = compactor.compact_from_results(
        results=results,
        next_phase=args.next_phase,
        next_phase_name=args.next_phase_name,
        total_phases=args.total_phases,
    )

    if args.format == "json":
        print(json.dumps(context.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(context.to_prompt_text())


if __name__ == "__main__":
    main()
