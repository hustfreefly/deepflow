"""Information Conservation Validator — Phase 2.5

Validates end-to-end information preservation: Planning → Research → ReviewQC.
[R1-B-P1-6] PASS (>=0.8) / WARNING (0.5-0.8) / FAIL (<0.5); req_coverage < 0.5 → forced FAIL.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


# L2: 模块级阈值（per-module transition）
L2_THRESHOLDS = {
    "planning_to_research": {
        "req_coverage_min": 0.9,
        "constraint_propagation_min": 0.85,
    },
    "research_to_review_qc": {
        "req_coverage_min": 0.85,
        "constraint_propagation_min": 0.8,
    },
}

# L3: 全局阈值（end-to-end）
L3_THRESHOLDS = {
    "req_coverage_min": 0.8,
    "constraint_propagation_min": 0.75,
    "source_traceability_min": 0.7,
    "overall_score_min": 0.8,
}


class InformationConservationValidator:
    """信息守恒验证器 — 验证端到端信息不丢失

    检查维度:
    1. 需求覆盖: 所有 P0 REQ ID 在最终输出中被引用
    2. 约束传递: Planning unified_constraints 在下游保留
    3. 来源追溯: 每条约束可追溯到 source_experts
    """

    def validate(
        self,
        planning_output: dict,
        research_output: dict | None = None,
        review_qc_output: dict | None = None,
    ) -> dict:
        """Returns verdict + scores for req_coverage, constraint_propagation, source_traceability."""
        req_cov = self._check_req_coverage(planning_output, research_output, review_qc_output)
        const_prop = self._check_constraint_propagation(planning_output, research_output, review_qc_output)
        src_trace = self._check_source_traceability(planning_output)

        score = req_cov["rate"] * 0.4 + const_prop["rate"] * 0.4 + src_trace["rate"] * 0.2

        if score >= 0.8:
            verdict = "PASS"
        elif score >= 0.5:
            verdict = "WARNING"
        else:
            verdict = "FAIL"

        # 安全底线: 需求覆盖率 < 0.5 → 强制 FAIL
        if req_cov["rate"] < 0.5:
            verdict = "FAIL"

        logger.info("InfoConservation verdict=%s score=%.2f", verdict, score)
        return {
            "verdict": verdict,
            "score": round(score, 4),
            "req_coverage": req_cov,
            "constraint_propagation": const_prop,
            "source_traceability": src_trace,
            "missing_reqs": req_cov.get("missing", []),
            "dropped_constraints": const_prop.get("dropped", []),
        }

    # --- Dimension 1: Requirement coverage ---

    def _check_req_coverage(self, planning_output: dict, research_output: dict | None, review_qc_output: dict | None) -> dict:
        p0_reqs = self._extract_p0_req_ids(planning_output)
        covered = {r for r in p0_reqs if self._id_in(r, research_output, review_qc_output)}
        rate = len(covered) / len(p0_reqs) if p0_reqs else 1.0
        return {"total": len(p0_reqs), "covered": len(covered), "rate": round(rate, 4), "missing": sorted(set(p0_reqs) - covered)}

    # --- Dimension 2: Constraint propagation ---

    def _check_constraint_propagation(self, planning_output: dict, research_output: dict | None, review_qc_output: dict | None) -> dict:
        constraints = planning_output.get("unified_constraints", {}).get("constraints", [])
        cids = [c.get("constraint_id") for c in constraints if c.get("constraint_id")]
        propagated = {c for c in cids if self._id_in(c, research_output, review_qc_output)}
        rate = len(propagated) / len(cids) if cids else 1.0
        return {"total": len(cids), "propagated": len(propagated), "rate": round(rate, 4), "dropped": sorted(set(cids) - propagated)}

    # --- Dimension 3: Source traceability ---

    def _check_source_traceability(self, planning_output: dict) -> dict:
        constraints = planning_output.get("unified_constraints", {}).get("constraints", [])
        traceable = sum(1 for c in constraints if c.get("source_experts"))
        rate = traceable / len(constraints) if constraints else 1.0
        return {"total": len(constraints), "traceable": traceable, "rate": round(rate, 4)}

    # --- Helpers ---

    @staticmethod
    def _extract_p0_req_ids(planning_output: dict) -> list[str]:
        reqs = planning_output.get("structured_requirements", {}).get("requirements", [])
        return [r.get("req_id") for r in reqs if r.get("priority") == "P0" and r.get("req_id")]

    def validate_transition(
        self,
        from_module: str,
        to_module: str,
        upstream_output: dict,
        downstream_output: dict,
    ) -> dict:
        """Validate information conservation at a specific module transition (L2).

        Checks L2 thresholds for the given transition, then also checks L3
        (global) thresholds.  L2 failure → WARNING, L3 failure → FAIL.
        """
        transition_key = f"{from_module}_to_{to_module}"
        l2 = L2_THRESHOLDS.get(transition_key)

        # Compute dimension scores between the two adjacent modules
        req_cov = self._check_req_coverage(upstream_output, downstream_output, None)
        const_prop = self._check_constraint_propagation(upstream_output, downstream_output, None)
        src_trace = self._check_source_traceability(upstream_output)

        overall = req_cov["rate"] * 0.4 + const_prop["rate"] * 0.4 + src_trace["rate"] * 0.2

        # --- L2 check ---
        l2_verdict = "PASS"
        l2_details: dict[str, Any] = {}
        if l2 is not None:
            req_min = l2.get("req_coverage_min", 0)
            const_min = l2.get("constraint_propagation_min", 0)
            if req_cov["rate"] < req_min or const_prop["rate"] < const_min:
                l2_verdict = "WARNING"
            l2_details = {
                "thresholds": l2,
                "req_coverage_met": req_cov["rate"] >= req_min,
                "constraint_propagation_met": const_prop["rate"] >= const_min,
            }
        else:
            l2_details = {"note": f"No L2 thresholds defined for {transition_key}"}

        # --- L3 check ---
        l3_verdict = "PASS"
        if req_cov["rate"] < L3_THRESHOLDS["req_coverage_min"]:
            l3_verdict = "FAIL"
        if const_prop["rate"] < L3_THRESHOLDS["constraint_propagation_min"]:
            l3_verdict = "FAIL"
        if src_trace["rate"] < L3_THRESHOLDS["source_traceability_min"]:
            l3_verdict = "FAIL"
        if overall < L3_THRESHOLDS["overall_score_min"]:
            l3_verdict = "FAIL"

        # Combined verdict: L3 FAIL overrides; L2 WARNING is non-blocking
        if l3_verdict == "FAIL":
            verdict = "FAIL"
        elif l2_verdict == "WARNING":
            verdict = "WARNING"
        else:
            verdict = "PASS"

        logger.info(
            "InfoConservation transition=%s verdict=%s l2=%s l3=%s overall=%.2f",
            transition_key, verdict, l2_verdict, l3_verdict, overall,
        )

        return {
            "verdict": verdict,
            "overall_score": round(overall, 4),
            "l2": {"verdict": l2_verdict, **l2_details},
            "l3": {"verdict": l3_verdict, "thresholds": L3_THRESHOLDS},
            "req_coverage": req_cov,
            "constraint_propagation": const_prop,
            "source_traceability": src_trace,
        }

    @staticmethod
    def _id_in(target_id: str, *outputs: dict | None) -> bool:
        return any(target_id in str(o) for o in outputs if o is not None)
