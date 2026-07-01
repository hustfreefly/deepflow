"""Deterministic Checks — Fix 5: Zero-LLM Quality Validation

E2E V3 发现: LLM-as-Judge TPR 仅 30-40%，四层 QA 体系被 Judge 可靠性锁定。
本模块提供 6 个确定性检查，零 LLM 调用，在 Fix Loop 之前运行，过滤明显问题。

设计原则: Code controls flow, LLM generates content (AGENTS.md Zone 4)
"""

from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DeterministicChecks:
    """6 个确定性检查，零 LLM 调用。

    检查结果: PASS / FAIL / WARNING
    在 Fix Loop 之前运行，过滤掉明显问题，减少不必要的 LLM-as-Judge 调用。
    """

    def run_all(self, blackboard_dir: str | Path) -> dict:
        """运行全部 6 个检查，返回汇总结果。"""
        bb = Path(blackboard_dir)
        stages = bb / "stages"

        results = {
            "check_1_file_existence": self.check_file_existence(stages),
            "check_2_json_validity": self.check_json_validity(stages),
            "check_3_cross_reference": self.check_cross_reference(stages),
            "check_4_section_numbering": self.check_section_numbering(stages),
            "check_5_no_tbd_params": self.check_no_tbd_params(stages),
            "check_6_size_progression": self.check_size_progression(stages),
        }

        total = len(results)
        passed = sum(1 for r in results.values() if r["verdict"] == "PASS")
        failed = sum(1 for r in results.values() if r["verdict"] == "FAIL")

        results["summary"] = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "warnings": total - passed - failed,
            "verdict": "PASS" if failed == 0 else "FAIL",
        }

        logger.info(
            "DeterministicChecks: %d/%d passed, %d failed",
            passed, total, failed,
        )
        return results

    # --- Check 1: File existence + non-empty ---

    def check_file_existence(self, stages_dir: Path) -> dict:
        """检查关键 stage 文件是否存在且非空。"""
        required_files = [
            "solution_input.json",
            "planning_convergence.json",
            "research_report.json",
            "base_solution.json",
            "refined_solution.json",
            "solution_document.json",
            "final_solution.json",
            "verification_result.json",
        ]

        missing = []
        empty = []

        for fname in required_files:
            fpath = stages_dir / fname
            if not fpath.exists():
                missing.append(fname)
            elif fpath.stat().st_size == 0:
                empty.append(fname)

        issues = missing + empty
        return {
            "verdict": "FAIL" if missing else ("WARNING" if empty else "PASS"),
            "missing": missing,
            "empty": empty,
            "details": f"{len(required_files) - len(issues)}/{len(required_files)} files present and non-empty",
        }

    # --- Check 2: JSON validity ---

    def check_json_validity(self, stages_dir: Path) -> dict:
        """检查所有 .json 文件是否有效 JSON。"""
        invalid = []
        total = 0

        for fpath in stages_dir.glob("*.json"):
            total += 1
            try:
                content = fpath.read_text(encoding="utf-8")
                json.loads(content)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                invalid.append({"file": fpath.name, "error": str(e)[:100]})

        return {
            "verdict": "FAIL" if invalid else "PASS",
            "total": total,
            "invalid": invalid,
            "details": f"{total - len(invalid)}/{total} valid JSON files",
        }

    # --- Check 3: Cross-file ID reference consistency ---

    def check_cross_reference(self, stages_dir: Path) -> dict:
        """检查跨文件 ID 引用一致性。

        E2E V3 场景: verification_result 中的 constraint_id 是否都存在于 planning_convergence 中。
        """
        issues = []

        # 加载 planning constraints
        planning_path = stages_dir / "planning_convergence.json"
        verification_path = stages_dir / "verification_result.json"

        if not planning_path.exists() or not verification_path.exists():
            return {"verdict": "WARNING", "issues": [], "details": "Required files missing, skipped"}

        try:
            planning_raw = planning_path.read_text(encoding="utf-8")
            verification_raw = verification_path.read_text(encoding="utf-8")
            planning = json.loads(planning_raw)
            verification = json.loads(verification_raw)
            # 某些 stage 文件可能存储为 JSON 字符串（双重编码）
            if isinstance(planning, str):
                planning = json.loads(planning)
            if isinstance(verification, str):
                verification = json.loads(verification)
        except (json.JSONDecodeError, TypeError):
            return {"verdict": "WARNING", "issues": [], "details": "JSON parse error, skipped"}

        if not isinstance(planning, dict) or not isinstance(verification, dict):
            return {"verdict": "WARNING", "issues": [], "details": "Non-dict content, skipped"}

        # 提取 planning 中的 constraint IDs
        planning_cids = set()
        for c in planning.get("unified_constraints", []):
            cid = c.get("id", c.get("constraint_id", ""))
            if cid:
                planning_cids.add(cid)

        # 提取 verification 中引用的 constraint IDs
        verification_cids = set()
        layer1 = verification.get("layer1_checklist", verification)
        if isinstance(layer1, dict):
            for check in layer1.get("results", []):
                cid = check.get("constraint_id", "")
                if cid:
                    verification_cids.add(cid)

        # 检查: verification 引用的 ID 是否都在 planning 中
        orphan_refs = verification_cids - planning_cids
        if orphan_refs:
            issues.append({
                "type": "orphan_constraint_refs",
                "ids": sorted(orphan_refs)[:10],
                "count": len(orphan_refs),
            })

        return {
            "verdict": "FAIL" if issues else "PASS",
            "issues": issues,
            "planning_constraints": len(planning_cids),
            "verification_refs": len(verification_cids),
        }

    # --- Check 4: Section numbering consistency ---

    def check_section_numbering(self, stages_dir: Path) -> dict:
        """检查方案文档中章节编号的一致性。

        E2E V3 发现: verification evidence 使用 "S3.x" 编号但实际文档章节号不同。
        """
        doc_path = stages_dir / "solution_document.json"
        ver_path = stages_dir / "verification_result.json"

        if not doc_path.exists() or not ver_path.exists():
            return {"verdict": "WARNING", "details": "Required files missing, skipped"}

        try:
            doc_content = doc_path.read_text(encoding="utf-8")
            verification_raw = ver_path.read_text(encoding="utf-8")
            verification = json.loads(verification_raw)
            if isinstance(verification, str):
                verification = json.loads(verification)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return {"verdict": "WARNING", "details": "Parse error, skipped"}

        if not isinstance(verification, dict):
            return {"verdict": "WARNING", "details": "Non-dict verification, skipped"}

        # 提取文档中的实际章节号
        actual_sections = set(re.findall(r'(?:Section|S)\s*(\d+(?:\.\d+)*)', doc_content))

        # 提取 verification evidence 中引用的章节号
        cited_sections = set()
        layer1 = verification.get("layer1_checklist", verification)
        if isinstance(layer1, dict):
            for check in layer1.get("results", []):
                evidence = check.get("evidence", "")
                cited = re.findall(r'(?:Section|S)\s*(\d+(?:\.\d+)*)', evidence)
                cited_sections.update(cited)

        # 检查: evidence 引用的章节号是否在文档中存在
        missing_sections = cited_sections - actual_sections

        return {
            "verdict": "WARNING" if missing_sections else "PASS",
            "actual_sections": len(actual_sections),
            "cited_sections": len(cited_sections),
            "missing_refs": sorted(missing_sections)[:10],
            "details": f"{len(missing_sections)} cited sections not found in document",
        }

    # --- Check 5: No TBD parameters ---

    def check_no_tbd_params(self, stages_dir: Path) -> dict:
        """检查关键参数是否仍为 TBD。

        E2E V3 发现: REQ-073 的 max_loop_iterations 参数值仍为 TBD。
        """
        tbd_patterns = [r'TBD', r'TODO', r'FIXME', r'TBA', r'<待定>', r'<待确认>']
        critical_files = ["final_solution.json", "solution_document.json"]

        tbd_found = []

        for fname in critical_files:
            fpath = stages_dir / fname
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
                for pattern in tbd_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        tbd_found.append({
                            "file": fname,
                            "pattern": pattern,
                            "count": len(matches),
                        })
            except UnicodeDecodeError:
                continue

        return {
            "verdict": "WARNING" if tbd_found else "PASS",
            "tbd_items": tbd_found,
            "details": f"{len(tbd_found)} TBD/TODO items found in critical files",
        }

    # --- Check 6: Size progression ---

    def check_size_progression(self, stages_dir: Path) -> dict:
        """检查方案演进的文件大小变化是否合理。

        预期: base < refined <= solution_document >> final (final 是摘要，应更小)
        异常: refined < base (信息丢失) 或 final ≈ solution_document (没做摘要)
        """
        sizes = {}
        for fname in ["base_solution.json", "refined_solution.json", "solution_document.json", "final_solution.json"]:
            fpath = stages_dir / fname
            if fpath.exists():
                sizes[fname] = fpath.stat().st_size

        issues = []

        # base → refined 应该增长
        if "base_solution.json" in sizes and "refined_solution.json" in sizes:
            if sizes["refined_solution.json"] < sizes["base_solution.json"] * 0.8:
                issues.append({
                    "type": "size_regression",
                    "from": "base_solution",
                    "to": "refined_solution",
                    "base_size": sizes["base_solution.json"],
                    "refined_size": sizes["refined_solution.json"],
                    "message": "Refined solution is significantly smaller than base — possible information loss",
                })

        # final 应该比 solution_document 小很多
        if "solution_document.json" in sizes and "final_solution.json" in sizes:
            ratio = sizes["final_solution.json"] / sizes["solution_document.json"]
            if ratio > 0.5:
                issues.append({
                    "type": "incomplete_compression",
                    "ratio": round(ratio, 2),
                    "message": "Final solution is >50% of solution_document — may not be properly summarized",
                })

        return {
            "verdict": "WARNING" if issues else "PASS",
            "sizes": sizes,
            "issues": issues,
        }
