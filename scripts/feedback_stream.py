"""
Feedback Stream — Worker 完成后的结构化进度报告

设计理念:
  - 不是"数完成事件"，是实时进度感知
  - 每个 Worker 完成后生成健康评估 + 下一步建议
  - 主 Agent 看到结构化报告，不需要"阅读理解"

集成点:
  - loop_runner.py 的 next 命令解析 WorkerResult 后调用此模块
  - 或主 Agent 在 sessions_yield 返回后直接调用
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
class ProgressReport:
    """Worker 完成后的进度报告"""
    event: str = "worker.complete"
    phase: int = 0
    phase_name: str = ""
    status: str = "success"
    progress: str = "0/0"
    progress_bar: str = ""
    health: str = "healthy"
    timestamp: str = ""

    # 给主 Agent 的决策建议
    recommendation_action: str = "continue"
    recommendation_reason: str = ""

    # 摘要信息
    worker_summary: str = ""
    worker_confidence: float = 0.0
    worker_issues: list[str] = field(default_factory=list)
    worker_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "phase": self.phase,
            "phase_name": self.phase_name,
            "status": self.status,
            "progress": self.progress,
            "progress_bar": self.progress_bar,
            "health": self.health,
            "timestamp": self.timestamp,
            "recommendation": {
                "action": self.recommendation_action,
                "reason": self.recommendation_reason,
            },
            "worker_output": {
                "summary": self.worker_summary,
                "confidence": self.worker_confidence,
                "issues": self.worker_issues,
                "warnings": self.worker_warnings,
            },
        }

    def to_markdown(self) -> str:
        """生成飞书可读的 Markdown 进度报告"""
        health_emoji = {"healthy": "🟢", "warning": "🟡", "critical": "🔴"}.get(self.health, "⚪")
        status_emoji = {"success": "✅", "partial": "⚠️", "failed": "❌"}.get(self.status, "❓")

        lines = [
            f"📊 **Pipeline 进度**: {self.progress_bar}",
            f"🏥 健康度: {health_emoji} {self.health}",
            f"{status_emoji} Phase {self.phase} ({self.phase_name}) {self.status}",
        ]

        if self.worker_summary:
            lines.append(f"📋 摘要: {self.worker_summary}")

        if self.worker_confidence > 0:
            lines.append(f"🎯 置信度: {self.worker_confidence:.0%}")

        if self.worker_issues:
            for issue in self.worker_issues:
                lines.append(f"⚠️ 问题: {issue}")

        if self.worker_warnings:
            for warning in self.worker_warnings:
                lines.append(f"💡 注意: {warning}")

        lines.append(f"➡️ 建议: {self.recommendation_action} — {self.recommendation_reason}")

        return "\n".join(lines)


class FeedbackStream:
    """Worker → 主 Agent 的反馈流"""

    def __init__(self, total_phases: int):
        self.total_phases = total_phases

    def on_worker_complete(self, result: WorkerResult) -> ProgressReport:
        """Worker 完成后，生成结构化进度报告"""
        now = datetime.now(SHANGHAI_TZ).isoformat()

        report = ProgressReport(
            event="worker.complete",
            phase=result.phase,
            phase_name=result.phase_name,
            status=result.status,
            progress=f"{result.phase}/{self.total_phases}",
            progress_bar=self._progress_bar(result.phase, self.total_phases),
            health=self._assess_health(result),
            timestamp=now,
            worker_summary=result.summary,
            worker_confidence=result.confidence,
            worker_issues=result.issues,
            worker_warnings=result.warnings,
        )

        # 决策建议
        action, reason = self._recommend_next(result)
        report.recommendation_action = action
        report.recommendation_reason = reason

        return report

    def _progress_bar(self, current: int, total: int) -> str:
        """生成进度条"""
        filled = "█" * current
        empty = "░" * (total - current)
        return f"{filled}{empty} {current}/{total}"

    def _assess_health(self, result: WorkerResult) -> str:
        """
        健康度评估:
        - healthy: 正常推进
        - warning: 有隐患但不阻塞
        - critical: 需要干预
        """
        if result.status == "failed" or result.confidence < 0.5:
            return "critical"
        elif result.status == "partial" or result.confidence < 0.7 or result.issues:
            return "warning"
        return "healthy"

    def _recommend_next(self, result: WorkerResult) -> tuple[str, str]:
        """给主 Agent 的决策建议"""
        if result.status == "failed":
            return ("recover", f"Phase {result.phase} 失败: {'; '.join(result.issues[:2])}")
        elif result.status == "partial":
            return ("continue_with_note", f"Phase {result.phase} 部分完成，继续推进")
        elif result.confidence < 0.5:
            return ("review", f"Phase {result.phase} 置信度过低 ({result.confidence:.0%})，建议检查")
        elif result.warnings:
            return ("continue", f"Phase {result.phase} 完成（有 {len(result.warnings)} 个注意事项）")
        else:
            return ("continue", f"Phase {result.phase} 正常完成，继续下一阶段")

    def on_pipeline_complete(self, results: list[WorkerResult]) -> dict:
        """管线完成后的总结报告"""
        total = len(results)
        success = sum(1 for r in results if r.status == "success")
        partial = sum(1 for r in results if r.status == "partial")
        failed = sum(1 for r in results if r.status == "failed")
        avg_confidence = sum(r.confidence for r in results) / total if total > 0 else 0
        all_issues = []
        for r in results:
            all_issues.extend(r.issues)

        return {
            "event": "pipeline.complete",
            "summary": {
                "total_phases": total,
                "success": success,
                "partial": partial,
                "failed": failed,
                "avg_confidence": round(avg_confidence, 2),
                "total_issues": len(all_issues),
            },
            "issues": all_issues[:10],  # Top 10
            "verdict": "success" if failed == 0 and partial == 0 else ("partial" if failed == 0 else "failed"),
        }


# ── CLI ───────────────────────────────────────────────────────────

def main():
    """CLI: 从 stdin 读取 WorkerResult JSON，输出 ProgressReport"""
    import argparse

    parser = argparse.ArgumentParser(description="Feedback Stream")
    parser.add_argument("--total-phases", type=int, required=True)
    parser.add_argument("--input", help="WorkerResult JSON 文件路径（不指定则从 stdin 读取）")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    result = WorkerResult(**data)
    stream = FeedbackStream(total_phases=args.total_phases)
    report = stream.on_worker_complete(result)

    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_markdown())


if __name__ == "__main__":
    main()
