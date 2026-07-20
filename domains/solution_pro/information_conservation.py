"""Information Conservation Validator — Phase 2.5

Validates end-to-end information preservation: Planning → Research → Summary.
[R1-B-P1-6] PASS (>=0.8) / WARNING (0.5-0.8) / FAIL (<0.5); req_coverage < 0.5 → forced FAIL.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


# 默认权重: 需求 35% + 约束 30% + 追溯 15% + 研究利用 20%
# 注意: 完整实现需要从 domain_profile 加载，当前先参数化
DEFAULT_WEIGHTS = {
    "req_coverage": 0.35,
    "constraint_propagation": 0.30,
    "source_traceability": 0.15,
    "research_utilization": 0.20,
}

DEFAULT_THRESHOLDS = {
    "pass_min": 0.8,
    "warn_min": 0.5,
    "req_coverage_floor": 0.5,  # 低于此值强制 FAIL
    "research_util_floor": 0.3,  # 低于此值降级
}

# L2: 模块级阈值（per-module transition）
L2_THRESHOLDS = {
    "planning_to_research": {
        "req_coverage_min": 0.9,
        "constraint_propagation_min": 0.85,
    },
    "research_to_summary": {
        "req_coverage_min": 0.85,
        "constraint_propagation_min": 0.8,
        "research_utilization_min": 0.6,  # Fix 1: Expert finding 利用率下限
    },
}

# L3: 全局阈值（end-to-end）
L3_THRESHOLDS = {
    "req_coverage_min": 0.8,
    "constraint_propagation_min": 0.75,
    "source_traceability_min": 0.7,
    "research_utilization_min": 0.5,  # Fix 1: 研究利用率下限
    "overall_score_min": 0.8,
}


class InformationConservationValidator:
    """信息守恒验证器 — 验证端到端信息不丢失

    检查维度:
    1. 需求覆盖: 所有 P0 REQ ID 在最终输出中被引用
    2. 约束传递: Planning unified_constraints 在下游保留
    3. 来源追溯: 每条约束可追溯到 source_experts
    """

    def __init__(self, weights=None, thresholds=None):
        """初始化验证器，支持自定义权重和阈值。

        Args:
            weights: 维度权重 dict，key 为 req_coverage/constraint_propagation/
                     source_traceability/research_utilization。默认使用 DEFAULT_WEIGHTS。
            thresholds: 判定阈值 dict，key 为 pass_min/warn_min/req_coverage_floor/
                        research_util_floor。默认使用 DEFAULT_THRESHOLDS。
        """
        self.weights = weights or DEFAULT_WEIGHTS
        self.thresholds = thresholds or DEFAULT_THRESHOLDS

    def validate(
        self,
        planning_output: dict,
        research_output: dict | None = None,
        summary_output: dict | None = None,
        living_spec: dict | None = None,
    ) -> dict:
        """Returns verdict + scores for req_coverage, constraint_propagation, source_traceability, research_utilization.

        P1-11-FIX: living_spec is the authoritative P0 source. If provided,
        P0 REQ IDs are extracted from living_spec.requirement_index instead of
        planning_output self-report.
        """
        req_cov = self._check_req_coverage(planning_output, research_output, summary_output, living_spec)
        const_prop = self._check_constraint_propagation(planning_output, research_output, summary_output)
        src_trace = self._check_source_traceability(planning_output)
        # Fix 1: 研究利用率检查 — 防止 Expert findings 被静默忽略
        research_util = self._check_research_utilization(research_output, summary_output)

        # 权重分配（从 self.weights 读取）
        score = (
            req_cov["rate"] * self.weights.get("req_coverage", 0.35)
            + const_prop["rate"] * self.weights.get("constraint_propagation", 0.30)
            + src_trace["rate"] * self.weights.get("source_traceability", 0.15)
            + research_util["rate"] * self.weights.get("research_utilization", 0.20)
        )

        pass_min = self.thresholds.get("pass_min", 0.8)
        warn_min = self.thresholds.get("warn_min", 0.5)

        if score >= pass_min:
            verdict = "PASS"
        elif score >= warn_min:
            verdict = "WARNING"
        else:
            verdict = "FAIL"

        # 安全底线: 需求覆盖率 < floor → 强制 FAIL
        req_floor = self.thresholds.get("req_coverage_floor", 0.5)
        if req_cov["rate"] < req_floor:
            verdict = "FAIL"
        # Fix 1: 研究利用率 < floor → 降级为 WARNING
        util_floor = self.thresholds.get("research_util_floor", 0.3)
        if research_util["rate"] < util_floor:
            verdict = "WARNING" if verdict == "PASS" else verdict

        logger.info("InfoConservation verdict=%s score=%.2f research_util=%.2f", verdict, score, research_util["rate"])
        return {
            "verdict": verdict,
            "score": round(score, 4),
            "req_coverage": req_cov,
            "constraint_propagation": const_prop,
            "source_traceability": src_trace,
            "research_utilization": research_util,
            "missing_reqs": req_cov.get("missing", []),
            "dropped_constraints": const_prop.get("dropped", []),
            "uncited_experts": research_util.get("uncited_experts", []),
        }

    # --- Dimension 1: Requirement coverage ---

    def _check_req_coverage(self, planning_output: dict, research_output: dict | None, summary_output: dict | None = None, living_spec: dict | None = None) -> dict:
        # P1-11-FIX: Use living_spec as authoritative P0 source if available
        # This prevents Planning self-report from shrinking the P0 denominator
        if living_spec and isinstance(living_spec, dict):
            p0_reqs = self._extract_p0_from_living_spec(living_spec)
            if not p0_reqs:
                # Fallback to planning if living_spec has no P0 REQs
                p0_reqs = self._extract_p0_req_ids(planning_output)
        else:
            p0_reqs = self._extract_p0_req_ids(planning_output)
        covered = {r for r in p0_reqs if self._id_in(r, research_output, summary_output)}
        # B4-FIX + R1-FIX: 空源集合处理 — 区分「有结构的 planning」vs「非结构化上游」
        # - planning 有 structured_requirements key（即使 requirements 为空）→ FAIL（数据存在但无 P0）
        # - 上游无结构化 REQ 数据（key 不存在）→ N/A (rate=1.0)
        if not p0_reqs:
            # R1: "data exists" = structured_requirements key is present as a dict
            # 即使 requirements 列表为空，只要 key 存在就说明上游尝试了结构化，但没有 P0 REQ
            has_structured_reqs = (
                isinstance(planning_output, dict) and
                isinstance(planning_output.get("structured_requirements"), dict)
            )
            rate = 0.0 if has_structured_reqs else 1.0
            empty_source = not has_structured_reqs  # N/A marker
        else:
            rate = len(covered) / len(p0_reqs)
            empty_source = False
        return {"total": len(p0_reqs), "covered": len(covered), "rate": round(rate, 4), "missing": sorted(set(p0_reqs) - covered), "empty_source": empty_source}

    # --- Dimension 2: Constraint propagation ---

    def _check_constraint_propagation(self, planning_output: dict, research_output: dict | None, summary_output: dict | None = None) -> dict:
        # Fix: unified_constraints 可能是 list 或 dict
        # R1-FIX: 区分「key 存在但为空」(FAIL) vs「key 不存在」(N/A)
        has_constraints_key = "unified_constraints" in (planning_output if isinstance(planning_output, dict) else {})
        raw = planning_output.get("unified_constraints", []) if isinstance(planning_output, dict) else []
        if isinstance(raw, dict):
            constraints = raw.get("constraints", [])
        elif isinstance(raw, list):
            constraints = raw
        else:
            constraints = []
        # 兼容 id / constraint_id 两种字段名
        cids = [c.get("id", c.get("constraint_id", "")) for c in constraints if isinstance(c, dict)]
        cids = [c for c in cids if c]
        propagated = {c for c in cids if self._id_in(c, research_output, summary_output)}
        if cids:
            rate = len(propagated) / len(cids)
            empty_source = False
        else:
            # R1: key present but empty → FAIL; key absent → N/A
            rate = 0.0 if has_constraints_key else 1.0
            empty_source = not has_constraints_key
        return {"total": len(cids), "propagated": len(propagated), "rate": round(rate, 4), "dropped": sorted(set(cids) - propagated), "empty_source": empty_source}

    # --- Dimension 3: Source traceability ---

    def _check_source_traceability(self, planning_output: dict) -> dict:
        # R1-FIX: 区分「key 存在但为空」(FAIL) vs「key 不存在」(N/A)
        has_constraints_key = "unified_constraints" in (planning_output if isinstance(planning_output, dict) else {})
        raw = planning_output.get("unified_constraints", []) if isinstance(planning_output, dict) else []
        if isinstance(raw, dict):
            constraints = raw.get("constraints", [])
        elif isinstance(raw, list):
            constraints = raw
        else:
            constraints = []
        traceable = sum(1 for c in constraints if isinstance(c, dict) and c.get("source_experts"))
        if constraints:
            rate = traceable / len(constraints)
            empty_source = False
        else:
            # R1: key present but empty → FAIL; key absent → N/A
            rate = 0.0 if has_constraints_key else 1.0
            empty_source = not has_constraints_key
        return {"total": len(constraints), "traceable": traceable, "rate": round(rate, 4), "empty_source": empty_source}

    # --- Helpers ---

    # --- Dimension 4: Research utilization (Fix 1) ---

    def _check_research_utilization(self, research_output: dict | None, summary_output: dict | None = None) -> dict:
        """Check whether expert findings were utilized in the solution.

        E2E 发现: 56% Expert 零引用，360KB research → 45KB solution 压缩后仅 1 处引用标记。
        本方法检测 expert findings 是否被下游方案引用（粗粒度：expert name/ID 出现在方案文本中）。
        """
        if research_output is None:
            return {"total": 0, "utilized": 0, "rate": 1.0, "uncited_experts": [], "empty_source": True}

        # 兼容: research_output 可能是字符串（双重编码）
        if isinstance(research_output, str):
            import json as _json
            try:
                research_output = _json.loads(research_output)
            except (ValueError, TypeError):
                return {"total": 0, "utilized": 0, "rate": 1.0, "uncited_experts": [], "empty_source": True}

        if not isinstance(research_output, dict):
            return {"total": 0, "utilized": 0, "rate": 1.0, "uncited_experts": [], "empty_source": True}

        # 提取 expert IDs 和关键 finding 标题
        experts = research_output.get("expert_to_findings_map", {})
        if not experts:
            # Fallback: 从 research_metadata 或 expert 文件中提取
            experts = self._extract_experts_from_metadata(research_output)

        if not experts:
            return {"total": 0, "utilized": 0, "rate": 1.0, "uncited_experts": [], "empty_source": True}

        # 检查每个 expert 的 findings 是否在 summary_output 中被引用
        solution_text = str(summary_output) if summary_output else ""
        cited = []
        uncited = []

        for expert_id, findings in experts.items():
            # 结构化引用标记检查（确定性）：检查 [REF-expert_id] 标记是否存在
            ref_tag = f"[REF-{expert_id}"
            expert_cited = ref_tag.lower() in solution_text.lower()

            if expert_cited:
                cited.append(expert_id)
            else:
                uncited.append(expert_id)

        total = len(experts)
        utilized = len(cited)
        rate = utilized / total if total > 0 else 1.0

        return {
            "total": total,
            "utilized": utilized,
            "uncited": len(uncited),
            "rate": round(rate, 4),
            "uncited_experts": sorted(uncited),
            "empty_source": False,
        }

    @staticmethod
    def _extract_experts_from_metadata(research_output: dict) -> dict:
        """Fallback: extract expert map from research output structure."""
        experts = {}
        # 尝试从 research_metadata 提取
        metadata = research_output.get("metadata", research_output.get("research_metadata", {}))
        if isinstance(metadata, dict):
            expert_map = metadata.get("expert_to_findings_map", {})
            if expert_map:
                return expert_map
        # 尝试从 experts 列表提取
        expert_list = research_output.get("experts", [])
        if isinstance(expert_list, list):
            for exp in expert_list:
                if isinstance(exp, dict):
                    eid = exp.get("expert_id", exp.get("id", ""))
                    findings = exp.get("findings", exp.get("key_findings", []))
                    if eid:
                        experts[eid] = findings
        return experts

    @staticmethod
    def _extract_p0_from_living_spec(living_spec: dict) -> list[str]:
        """P1-11-FIX: Extract P0 REQ IDs from living_spec (authoritative source).

        Reads requirement_index from top-level (promoted by B5-FIX in spec_living_md.py)
        or from confirmed.requirement_index.
        """
        if not isinstance(living_spec, dict):
            return []

        # Top-level requirement_index (promoted by B5-FIX)
        req_index = living_spec.get("requirement_index", [])
        if not req_index:
            # Fallback: confirmed.requirement_index
            confirmed = living_spec.get("confirmed", {})
            if isinstance(confirmed, dict):
                req_index = confirmed.get("requirement_index", [])

        if req_index and isinstance(req_index, list):
            p0_ids = []
            for r in req_index:
                if isinstance(r, dict):
                    rid = r.get("id") or r.get("req_id") or ""
                    priority = r.get("priority", "P0")
                    if rid and priority == "P0":
                        p0_ids.append(rid)
                    elif rid:
                        # Include all REQs if no priority field (treat as P0)
                        p0_ids.append(rid)
            if p0_ids:
                return p0_ids

        return []

    @staticmethod
    def _extract_p0_req_ids(output: dict) -> list[str]:
        # B4-FIX: 多路径提取 P0 REQ，增强健壮性
        # 支持 planning_output 和 research_output 两种结构
        if not isinstance(output, dict):
            return []

        # 路径 1: structured_requirements.requirements（planning 原始路径）
        sr = output.get("structured_requirements", {})
        if isinstance(sr, dict):
            reqs = sr.get("requirements", [])
            if reqs and isinstance(reqs, list):
                p0_ids = [r.get("req_id") for r in reqs if isinstance(r, dict) and r.get("priority") == "P0" and r.get("req_id")]
                if p0_ids:
                    return p0_ids

        # 路径 2: covered_req_ids（planning_convergence / research_convergence 标准字段）
        covered = output.get("covered_req_ids", [])
        if covered and isinstance(covered, list):
            return [r for r in covered if isinstance(r, str) and r.strip()]

        # 路径 3: coverage.covered_req_ids（research digest 结构）
        coverage = output.get("coverage", {})
        if isinstance(coverage, dict):
            cov_reqs = coverage.get("covered_req_ids", [])
            if cov_reqs and isinstance(cov_reqs, list):
                return [r for r in cov_reqs if isinstance(r, str) and r.strip()]

        # 路径 4: requirement_index（living_spec 透传字段）
        req_index = output.get("requirement_index", [])
        if req_index and isinstance(req_index, list):
            return [r.get("id") for r in req_index if isinstance(r, dict) and r.get("id")]

        # 路径 5: 从 key_findings/design_decisions 中提取 REQ- 前缀（最后手段）
        import re
        text = str(output)
        req_ids = list(set(re.findall(r"REQ-[A-Z0-9]+-\d+", text)))
        if req_ids:
            return sorted(req_ids)

        return []

    def validate_transition(
        self,
        from_module: str,
        to_module: str,
        upstream_output: dict,
        downstream_output: dict,
        living_spec: dict | None = None,
    ) -> dict:
        """Validate information conservation at a specific module transition (L2).

        Checks L2 thresholds for the given transition, then also checks L3
        (global) thresholds.  L2 failure → WARNING, L3 failure → FAIL.

        P1-11-FIX: living_spec is the authoritative P0 source.
        """
        transition_key = f"{from_module}_to_{to_module}"
        l2 = L2_THRESHOLDS.get(transition_key)

        # Compute dimension scores between the two adjacent modules
        req_cov = self._check_req_coverage(upstream_output, downstream_output, None, living_spec)
        const_prop = self._check_constraint_propagation(upstream_output, downstream_output, None)
        src_trace = self._check_source_traceability(upstream_output)
        # R2-FIX: research_utilization must be checked for research→summary transition
        research_util = self._check_research_utilization(
            upstream_output if transition_key == "research_to_summary" else None,
            downstream_output if transition_key == "research_to_summary" else None,
        )

        overall = req_cov["rate"] * 0.35 + const_prop["rate"] * 0.30 + src_trace["rate"] * 0.15 + research_util["rate"] * 0.20

        # --- L2 check ---
        l2_verdict = "PASS"
        l2_details: dict[str, Any] = {}
        if l2 is not None:
            req_min = l2.get("req_coverage_min", 0)
            const_min = l2.get("constraint_propagation_min", 0)
            util_min = l2.get("research_utilization_min", 0)
            l2_fail = req_cov["rate"] < req_min or const_prop["rate"] < const_min
            # R2-FIX: research_utilization L2 threshold check
            if research_util["rate"] < util_min and not research_util.get("empty_source", False):
                l2_fail = True
            if l2_fail:
                l2_verdict = "WARNING"
            l2_details = {
                "thresholds": l2,
                "req_coverage_met": req_cov["rate"] >= req_min,
                "constraint_propagation_met": const_prop["rate"] >= const_min,
                "research_utilization_met": research_util["rate"] >= util_min or research_util.get("empty_source", False),
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
        # R2-FIX: research_utilization L3 threshold check
        if research_util["rate"] < L3_THRESHOLDS.get("research_utilization_min", 0.5) and not research_util.get("empty_source", False):
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
            "InfoConservation transition=%s verdict=%s l2=%s l3=%s overall=%.2f research_util=%.2f",
            transition_key, verdict, l2_verdict, l3_verdict, overall, research_util["rate"],
        )

        result = {
            "verdict": verdict,
            "overall_score": round(overall, 4),
            "l2": {"verdict": l2_verdict, **l2_details},
            "l3": {"verdict": l3_verdict, "thresholds": L3_THRESHOLDS},
            "req_coverage": req_cov,
            "constraint_propagation": const_prop,
            "source_traceability": src_trace,
            "research_utilization": research_util,
        }

        # CRITICAL #3: 信息守恒验证失败时 raise，由调用方 try/except 捕获（soft gate）
        if verdict == "FAIL":
            raise ValueError(
                f"Information conservation FAIL at {transition_key}: "
                f"overall_score={overall:.2f}, "
                f"req_coverage={req_cov['rate']:.2f}, "
                f"constraint_propagation={const_prop['rate']:.2f}, "
                f"source_traceability={src_trace['rate']:.2f}, "
                f"research_utilization={research_util['rate']:.2f}"
            )

        return result

    @staticmethod
    def _id_in(target_id: str, *outputs: dict | None) -> bool:
        return any(target_id in str(o) for o in outputs if o is not None)
