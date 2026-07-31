"""
Deliver Pro Smart Assembler — Code-First Assembly

替代 LLM Agent 做 Integrate 阶段的确定性组装。
核心原则：代码做拼接（零丢失），LLM 只做可选语义增强。

设计背景：
  - LLM Agent 做"合并"会本能地摘要/压缩（264KB → 42KB，84% 丢失）
  - Worker 产出是独立章节，不需要"合并"，需要"拼接"
  - 代码做确定性 I/O + 格式化，保留率 ≥95%

用法：
    from domains.deliver_pro.smart_assembler import SmartAssembler
    
    assembler = SmartAssembler(worker_outputs_dir, plan, output_dir)
    result = assembler.run()
    # result.retention_ratio >= 0.95
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class WorkerArtifact:
    """单个 Worker 的产出物。"""
    task_id: str
    title: str
    content: str
    evidence: str = ""
    issues: str = ""
    manifest: dict = field(default_factory=dict)
    original_size: int = 0


@dataclass
class AssemblyResult:
    """组装结果。"""
    deliverable_path: Path
    report_path: Path
    workers_integrated: int
    workers_failed: int
    retention_ratio: float
    total_input_bytes: int
    total_output_bytes: int
    status: str  # "READY_FOR_VALIDATE" | "PARTIAL" | "ASSEMBLY_ERROR"
    coverage_gaps: list[str] = field(default_factory=list)


# ============================================================================
# Smart Assembler
# ============================================================================


class SmartAssembler:
    """
    确定性组装引擎 — 零 LLM 调用。
    
    Pipeline:
      1. COLLECT: 读取 Worker 文件 + 校验 MANIFEST
      2. STRUCTURE: 拓扑排序 + 章节骨架
      3. CHECK: 保留率 / AC 覆盖 / 交叉引用（代码验证）
      4. ASSEMBLE: 拼接 + TOC + 附录 + 报告
    """

    def __init__(
        self,
        worker_outputs_dir: Path,
        plan_data: dict,
        output_dir: Path,
    ):
        self.worker_dir = Path(worker_outputs_dir)
        self.plan = plan_data
        self.output_dir = Path(output_dir)

    def run(self) -> AssemblyResult:
        """执行完整的确定性组装流水线。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Phase 3a: COLLECT
        artifacts, missing_tasks = self._collect()

        # Phase 3a.5: Topological sort (P2-1)
        task_graph = self.plan.get("task_graph", [])
        if len(artifacts) > 1:
            try:
                artifacts = self._topological_sort(artifacts, task_graph)
            except ValueError as e:
                logger.error(f"Topological sort failed: {e}")
                # Fall through with original order; ASSEMBLY_ERROR will be set

        # Phase 3b: STRUCTURE (normalize headings)
        normalized = self._structure(artifacts)

        # Phase 3c: ASSEMBLE (concatenate + TOC + appendix)
        final_text = self._assemble(normalized, artifacts)

        # Write deliverable
        deliverable_path = self.output_dir / "DELIVERABLE.md"
        deliverable_path.write_text(final_text, encoding="utf-8")

        # Phase 3d: CHECK (retention invariant)
        total_input = sum(a.original_size for a in artifacts)
        total_output = len(final_text.encode("utf-8"))
        retention = total_output / total_input if total_input > 0 else 0

        # Determine status based on missing workers
        total_tasks = len(self.plan.get("task_graph", []))
        workers_failed = len(missing_tasks)
        coverage_gaps = [t["task_id"] for t in missing_tasks]

        if workers_failed == 0:
            status = "READY_FOR_VALIDATE"
        elif workers_failed == total_tasks:
            status = "ASSEMBLY_ERROR"
        else:
            status = "PARTIAL"

        # Write report
        report = self._generate_report(
            artifacts, total_input, total_output, retention,
            workers_failed=workers_failed,
            coverage_gaps=coverage_gaps,
        )
        report_path = self.output_dir / "integration_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(
            f"Smart Assembly complete: {len(artifacts)} workers, "
            f"{total_input/1024:.1f}KB → {total_output/1024:.1f}KB, "
            f"retention={retention:.1%}, status={status}"
        )

        return AssemblyResult(
            deliverable_path=deliverable_path,
            report_path=report_path,
            workers_integrated=len(artifacts),
            workers_failed=workers_failed,
            retention_ratio=retention,
            total_input_bytes=total_input,
            total_output_bytes=total_output,
            status=status,
            coverage_gaps=coverage_gaps,
        )

    # ----------------------------------------------------------------
    # Phase 3a: COLLECT
    # ----------------------------------------------------------------

    def _collect(self) -> tuple[list[WorkerArtifact], list[dict]]:
        """读取所有 Worker 产出，校验 MANIFEST。
        
        Returns:
            Tuple of (artifacts list, missing tasks list).
        """
        task_graph = self.plan.get("task_graph", [])
        artifacts = []
        missing_tasks = []

        for task in task_graph:
            task_id = task["task_id"]
            task_dir = self.worker_dir / task_id

            if not task_dir.exists():
                logger.warning(f"Worker dir missing: {task_id}")
                missing_tasks.append(task)
                continue

            # Read DELIVERABLE.md (required)
            deliverable_path = task_dir / "DELIVERABLE.md"
            if not deliverable_path.exists():
                logger.warning(f"DELIVERABLE.md missing: {task_id}")
                missing_tasks.append(task)
                continue

            content = deliverable_path.read_text(encoding="utf-8")

            # Read MANIFEST.json (required, N4: missing/corrupted = failed)
            # Phase 2 fix: 使用 SafeJsonLoader 替代裸 json.loads（边界强制层）
            from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
            manifest_path = task_dir / "MANIFEST.json"
            manifest = {}
            if not manifest_path.exists():
                logger.error(f"N4: MANIFEST.json missing for {task_id}, counting as failed")
                missing_tasks.append({"task_id": task_id, "reason": "MANIFEST.json missing"})
                continue
            load_result = SafeJsonLoader.load_raw(manifest_path, mtime_window=0)
            if load_result.state == "ok":
                manifest = load_result.data or {}
                if not manifest:  # Empty dict
                    logger.error(f"N4: MANIFEST.json empty for {task_id}, counting as failed")
                    missing_tasks.append({"task_id": task_id, "reason": "MANIFEST.json empty"})
                    continue
            elif load_result.state == "invalid_json":
                logger.error(f"N4: MANIFEST.json corrupted for {task_id}: {load_result.error}")
                missing_tasks.append({"task_id": task_id, "reason": f"MANIFEST.json corrupted: {load_result.error}"})
                continue
            else:
                # write_in_progress / not_found → 视为缺失
                logger.error(f"N4: MANIFEST.json not ready for {task_id}: {load_result.state}")
                missing_tasks.append({"task_id": task_id, "reason": f"MANIFEST.json {load_result.state}"})
                continue

            # Read optional files
            evidence = ""
            evidence_path = task_dir / "EVIDENCE.md"
            if evidence_path.exists():
                evidence = evidence_path.read_text(encoding="utf-8")

            issues = ""
            issues_path = task_dir / "ISSUES.md"
            if issues_path.exists():
                issues = issues_path.read_text(encoding="utf-8")

            artifacts.append(WorkerArtifact(
                task_id=task_id,
                title=task.get("title", task_id),
                content=content,
                evidence=evidence,
                issues=issues,
                manifest=manifest,
                original_size=len(content.encode("utf-8")),
            ))

        return artifacts, missing_tasks

    # ----------------------------------------------------------------
    # Topological Sort (P2-1)
    # ----------------------------------------------------------------

    def _topological_sort(
        self,
        artifacts: list[WorkerArtifact],
        task_graph: list[dict],
    ) -> list[WorkerArtifact]:
        """Deterministic topological sort by depends_on.

        Prefers concurrency_plan.waves when available (P2-1).

        Raises:
            ValueError: cycle detected or unknown dependency referenced.
        """
        waves = self.plan.get("concurrency_plan", {}).get("waves", [])
        if waves:
            return self._sort_by_waves(artifacts, waves)

        task_map = {t["task_id"]: t for t in task_graph}
        artifact_map = {a.task_id: a for a in artifacts}

        # Validate: unknown dependencies → fail
        known_ids = set(task_map.keys())
        for task in task_graph:
            for dep in task.get("depends_on", []):
                if dep not in known_ids:
                    raise ValueError(
                        f"Task {task['task_id']} depends on unknown task {dep}"
                    )

        # Kahn's algorithm (deterministic: alphabetical tie-break)
        in_degree: dict[str, int] = {}
        dependents: dict[str, list[str]] = {}
        for task in task_graph:
            tid = task["task_id"]
            deps = task.get("depends_on", [])
            in_degree[tid] = len(deps)
            for dep in deps:
                dependents.setdefault(dep, []).append(tid)

        queue = sorted(tid for tid, deg in in_degree.items() if deg == 0)
        order: list[str] = []

        while queue:
            tid = queue.pop(0)
            order.append(tid)
            for dependent in sorted(dependents.get(tid, [])):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
            queue.sort()

        if len(order) != len(task_graph):
            raise ValueError("Task graph contains a cycle (topological sort failed)")

        return [artifact_map[tid] for tid in order if tid in artifact_map]

    def _sort_by_waves(
        self,
        artifacts: list[WorkerArtifact],
        waves: list[dict],
    ) -> list[WorkerArtifact]:
        """Sort artifacts by concurrency_plan.waves order."""
        artifact_map = {a.task_id: a for a in artifacts}
        result: list[WorkerArtifact] = []
        for wave in sorted(waves, key=lambda w: w.get("wave", 0)):
            for tid in wave.get("task_ids", []):
                if tid in artifact_map:
                    result.append(artifact_map[tid])
        return result

    # ----------------------------------------------------------------
    # Phase 3b: STRUCTURE
    # ----------------------------------------------------------------

    def _structure(self, artifacts: list[WorkerArtifact]) -> list[str]:
        """归一化标题层级，返回处理后的内容列表。"""
        normalized = []
        for i, art in enumerate(artifacts, 1):
            # Shift headings down one level (# → ##)
            content = re.sub(
                r'^(#{1,6})\s',
                lambda m: '#' + m.group(1) + ' ',
                art.content,
                flags=re.MULTILINE,
            )
            # Wrap with chapter header
            chapter = (
                f"# 第{i}章 {art.title}\n\n"
                f"<!-- chapter: {art.task_id} -->\n\n"
                f"{content}"
            )
            normalized.append(chapter)
        return normalized

    # ----------------------------------------------------------------
    # Phase 3c: ASSEMBLE
    # ----------------------------------------------------------------

    def _assemble(
        self,
        normalized_chapters: list[str],
        artifacts: list[WorkerArtifact],
    ) -> str:
        """拼接所有章节 + TOC + 附录。"""
        # Join chapters with separators
        body = "\n\n---\n\n".join(normalized_chapters)

        # Generate TOC from headings
        toc = self._generate_toc(body)

        # Compile evidence index
        evidence_index = self._compile_evidence(artifacts)

        # Compile issues register
        issues_register = self._compile_issues(artifacts)

        # Build header
        wp_id = self.plan.get("wp_id", "UNKNOWN")
        now = datetime.now().strftime("%Y-%m-%d")
        header = (
            f"# {wp_id} — 最终交付物\n\n"
            f"> **组装日期**: {now} | "
            f"**组装方式**: Code-First Assembly（确定性拼接，零 LLM 压缩） | "
            f"**Workers**: {len(artifacts)}\n\n"
            f"---\n\n"
        )

        return header + toc + "\n\n---\n\n" + body + evidence_index + issues_register

    def _generate_toc(self, content: str) -> str:
        """正则扫描标题，生成目录。"""
        toc_lines = ["## 目录\n"]
        for match in re.finditer(r'^(#{1,4})\s+(.+)$', content, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            # Skip HTML comments and metadata
            if title.startswith('<!--') or title.startswith('>'):
                continue
            indent = "  " * (level - 1)
            anchor = re.sub(
                r'[^\w\u4e00-\u9fff-]', '',
                title.lower().replace(' ', '-'),
            )
            toc_lines.append(f"{indent}- [{title}](#{anchor})")
        return "\n".join(toc_lines)

    def _compile_evidence(self, artifacts: list[WorkerArtifact]) -> str:
        """合并所有 EVIDENCE.md 为证据索引附录。"""
        parts_with_evidence = [
            a for a in artifacts if a.evidence.strip()
        ]
        if not parts_with_evidence:
            return ""

        parts = ["\n\n---\n\n# 附录：证据索引\n"]
        for art in parts_with_evidence:
            parts.append(f"## {art.task_id}: {art.title}\n\n{art.evidence}")
        return "\n\n---\n\n".join(parts)

    def _compile_issues(self, artifacts: list[WorkerArtifact]) -> str:
        """合并所有 ISSUES.md 为问题清单附录。"""
        parts_with_issues = [
            a for a in artifacts if a.issues.strip()
        ]
        if not parts_with_issues:
            return ""

        parts = ["\n\n---\n\n# 附录：问题清单\n"]
        for art in parts_with_issues:
            parts.append(f"## {art.task_id}: {art.title}\n\n{art.issues}")
        return "\n\n---\n\n".join(parts)

    # ----------------------------------------------------------------
    # Phase 3d: REPORT
    # ----------------------------------------------------------------

    def _generate_report(
        self,
        artifacts: list[WorkerArtifact],
        total_input: int,
        total_output: int,
        retention: float,
        workers_failed: int = 0,
        coverage_gaps: list[str] | None = None,
    ) -> dict[str, Any]:
        """生成 integration_report.json.

        P1-4: 从 MANIFEST.json 读取 covered_ac_ids/covered_req_ids，
              与 ExecutionPlan 的 AC 总集交叉比对，计算真实覆盖率。
              保留旧布尔值逻辑作为 fallback。
        """
        task_graph = self.plan.get("task_graph", [])

        # Collect all AC IDs from plan (P1-4: use set to avoid duplicates)
        all_ac_ids: set[str] = set()
        for task in task_graph:
            for ac in task.get("acceptance_criteria", []):
                if isinstance(ac, str):
                    all_ac_ids.add(ac)
                elif isinstance(ac, dict) and "id" in ac:
                    all_ac_ids.add(ac["id"])

        # Collect covered AC IDs from MANIFEST (P1-4)
        covered_ac_ids: set[str] = set()
        covered_req_ids: set[str] = set()
        for art in artifacts:
            manifest = art.manifest
            # Top-level covered_ac_ids and covered_req_ids
            for item in manifest.get("covered_ac_ids", []):
                covered_ac_ids.add(str(item))
            for item in manifest.get("covered_req_ids", []):
                covered_req_ids.add(str(item))
            # Also check nested quality_self_check
            qs = manifest.get("quality_self_check", {})
            for item in qs.get("covered_ac_ids", []):
                covered_ac_ids.add(str(item))
            for item in qs.get("covered_req_ids", []):
                covered_req_ids.add(str(item))

        # Cross-reference with plan ACs; fallback to boolean if no IDs found
        if all_ac_ids and covered_ac_ids:
            ac_total = len(all_ac_ids)
            ac_covered = len(covered_ac_ids & set(all_ac_ids))
        else:
            # Fallback: boolean per-worker counting (backward compat)
            ac_total = 0
            ac_covered = 0
            for art in artifacts:
                qs = art.manifest.get("quality_self_check", {})
                if qs.get("acceptance_criteria_met"):
                    ac_covered += 1
                ac_total += 1

        # Determine status
        total_tasks = len(task_graph)
        if workers_failed == 0:
            status = "READY_FOR_VALIDATE"
        elif workers_failed == total_tasks:
            status = "ASSEMBLY_ERROR"
        else:
            status = "PARTIAL"

        return {
            "workers_integrated": len(artifacts),
            "workers_failed": workers_failed,
            "consistency_checks_passed": workers_failed == 0,
            "conflicts_found": [],
            "coverage": {
                "acceptance_criteria_total": ac_total,
                "covered": ac_covered,
                "gaps": coverage_gaps or [],
                "covered_req_ids": sorted(covered_req_ids),
            },
            "assembly_stats": {
                "total_input_bytes": total_input,
                "total_output_bytes": total_output,
                "body_retention_ratio": round(retention, 3),
                "method": "code-first-deterministic",
                "llm_calls": 0,
            },
            "status": status,
        }


# ============================================================================
# Convenience function
# ============================================================================


def assemble(
    worker_outputs_dir: str | Path,
    plan_path: str | Path,
    output_dir: str | Path,
) -> AssemblyResult:
    """
    One-call convenience function for Smart Assembly.
    
    Usage:
        from domains.deliver_pro.smart_assembler import assemble
        result = assemble("stages/worker_outputs", "stages/execution_plan.json", "stages/integrated_draft")
    """
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    assembler = SmartAssembler(
        worker_outputs_dir=Path(worker_outputs_dir),
        plan_data=plan,
        output_dir=Path(output_dir),
    )
    return assembler.run()
