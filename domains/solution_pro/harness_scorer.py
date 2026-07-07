"""
Harness 评分器，支持 level 自动推导和显式传入

Version: 2.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
Harness Scorer 2.0.0
===================

4维度评分器（权重：完整性30% / 必要性20% / 目标一致性30% / 全局影响20%）

决策层级：
- PASS (≥0.85): 质量达标
- WARNING (0.70-0.84): 咨询意见
- CRITICAL_WARNING (0.60-0.69): 强烈建议修改
- BLOCK_RECOMMENDATION (<0.60): 建议重新规划（仍不阻断）

特殊规则：目标一致性<0.6 → 至少CRITICAL_WARNING
"""

from typing import Dict, Literal, Optional
from dataclasses import dataclass
import json

# P0-2: Import GateAConfig for dynamic scoring (lazy import for standalone compatibility)
try:
    from .schemas.schemas import GateAConfig
except ImportError:  # pragma: no cover - standalone execution
    GateAConfig = None  # type: ignore

# 统一 4 维评分权重
WEIGHT_COMPLETENESS = 0.30
WEIGHT_NECESSITY = 0.20
WEIGHT_ALIGNMENT = 0.30
WEIGHT_GLOBAL_IMPACT = 0.20

# 阈值（已确认）
THRESHOLD_PASS = 0.85
THRESHOLD_WARNING = 0.70
THRESHOLD_CRITICAL = 0.60

# 特殊规则阈值
THRESHOLD_ALIGNMENT_CRITICAL = 0.60

DecisionType = Literal["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]
LevelType = Literal["high", "medium", "low"]


@dataclass
class DimensionScore:
    """单维度评分"""
    score: float  # 0.0-1.0
    reasoning: str
    level: Optional[LevelType] = None  # 不传入时自动推导
    
    def __post_init__(self):
        # 仅在未显式传入 level 时自动推导
        if self.level is None:
            if self.score >= 0.85:
                self.level = "high"
            elif self.score >= 0.70:
                self.level = "medium"
            else:
                self.level = "low"


@dataclass
class HarnessScore:
    """Harness完整评分结果"""
    completeness: DimensionScore
    necessity: DimensionScore
    alignment: DimensionScore
    global_impact: DimensionScore
    overall_score: float
    decision: DecisionType
    improvements: list


def calculate_harness_score(
    completeness: float,
    necessity: float,
    alignment: float,
    global_impact: float,
    completeness_reasoning: str = "",
    necessity_reasoning: str = "",
    alignment_reasoning: str = "",
    global_impact_reasoning: str = "",
) -> HarnessScore:
    """
    计算Harness总分和决策
    
    公式：总分 = 完整性×0.30 + 必要性×0.20 + 目标一致性×0.30 + 全局影响×0.20
    
    Args:
        completeness: 完整性评分 (0.0-1.0)
        necessity: 必要性评分 (0.0-1.0)
        alignment: 目标一致性评分 (0.0-1.0)
        completeness_reasoning: 完整性理由
        necessity_reasoning: 必要性理由
        alignment_reasoning: 目标一致性理由
    
    Returns:
        HarnessScore对象
    """
    # 计算总分
    overall = (
        completeness * WEIGHT_COMPLETENESS +
        necessity * WEIGHT_NECESSITY +
        alignment * WEIGHT_ALIGNMENT +
        global_impact * WEIGHT_GLOBAL_IMPACT
    )
    
    # 基础决策
    if overall >= THRESHOLD_PASS:
        decision: DecisionType = "PASS"
    elif overall >= THRESHOLD_WARNING:
        decision = "WARNING"
    elif overall >= THRESHOLD_CRITICAL:
        decision = "CRITICAL_WARNING"
    else:
        decision = "BLOCK_RECOMMENDATION"
    
    # 特殊规则：目标一致性<0.6 → 至少CRITICAL_WARNING
    if alignment < THRESHOLD_ALIGNMENT_CRITICAL:
        if decision == "PASS" or decision == "WARNING":
            decision = "CRITICAL_WARNING"
    
    # 生成改进建议
    improvements = _generate_improvements(completeness, necessity, alignment, global_impact)
    
    return HarnessScore(
        completeness=DimensionScore(completeness, completeness_reasoning),
        necessity=DimensionScore(necessity, necessity_reasoning),
        alignment=DimensionScore(alignment, alignment_reasoning),
        global_impact=DimensionScore(global_impact, global_impact_reasoning),
        overall_score=round(overall, 2),
        decision=decision,
        improvements=improvements
    )


def calculate_harness_score_dynamic(
    completeness: float,
    necessity: float,
    alignment: float,
    global_impact: float,
    gate_a_config: "GateAConfig",
    completeness_reasoning: str = "",
    necessity_reasoning: str = "",
    alignment_reasoning: str = "",
    global_impact_reasoning: str = "",
) -> HarnessScore:
    """
    P0-2: Dynamic Harness scoring using GateAConfig weights/thresholds.

    Unlike calculate_harness_score() which uses hardcoded constants,
    this function reads weights and thresholds from the GateAConfig
    produced by the Meta-Planner, enabling per-task customization.

    Args:
        completeness: 完整性评分 (0.0-1.0)
        necessity: 必要性评分 (0.0-1.0)
        alignment: 目标一致性评分 (0.0-1.0)
        global_impact: 全局影响评分 (0.0-1.0)
        gate_a_config: GateAConfig instance with dynamic weights/thresholds
        completeness_reasoning: 完整性理由
        necessity_reasoning: 必要性理由
        alignment_reasoning: 目标一致性理由
        global_impact_reasoning: 全局影响理由

    Returns:
        HarnessScore对象 (same dataclass as calculate_harness_score)
    """
    # Dynamic weights from config
    w_c = gate_a_config.weights.completeness
    w_n = gate_a_config.weights.necessity
    w_a = gate_a_config.weights.alignment
    w_g = gate_a_config.weights.global_impact

    # Dynamic thresholds from config
    threshold_pass = gate_a_config.thresholds.PASS
    threshold_warning = gate_a_config.thresholds.WARNING
    threshold_critical = gate_a_config.thresholds.CRITICAL_WARNING

    # Calculate weighted score
    overall = (
        completeness * w_c
        + necessity * w_n
        + alignment * w_a
        + global_impact * w_g
    )

    # Decision based on dynamic thresholds
    if overall >= threshold_pass:
        decision: DecisionType = "PASS"
    elif overall >= threshold_warning:
        decision = "WARNING"
    elif overall >= threshold_critical:
        decision = "CRITICAL_WARNING"
    else:
        decision = "BLOCK_RECOMMENDATION"

    # Special rule: alignment < critical threshold → at least CRITICAL_WARNING
    if alignment < threshold_critical:
        if decision in ("PASS", "WARNING"):
            decision = "CRITICAL_WARNING"

    improvements = _generate_improvements(completeness, necessity, alignment, global_impact)

    return HarnessScore(
        completeness=DimensionScore(completeness, completeness_reasoning),
        necessity=DimensionScore(necessity, necessity_reasoning),
        alignment=DimensionScore(alignment, alignment_reasoning),
        global_impact=DimensionScore(global_impact, global_impact_reasoning),
        overall_score=round(overall, 2),
        decision=decision,
        improvements=improvements,
    )


def _generate_improvements(c: float, n: float, a: float, g: float) -> list:
    """识别弱维度，交给 LLM Judge 生成针对性改进建议。
    代码不生成固定字符串建议（那是语义内容）。
    """
    scores = {
        "completeness": c,
        "necessity": n,
        "alignment": a,
        "global_impact": g,
    }
    weak_dimensions = []
    for dim, score in scores.items():
        if isinstance(score, (int, float)) and score < 0.70:
            weak_dimensions.append({"dimension": dim, "score": score})

    if not weak_dimensions:
        return []

    return [{
        "type": "llm_improvement_needed",
        "weak_dimensions": weak_dimensions,
        "instruction": "Generate specific improvement suggestions based on the weak dimensions above",
    }]


def level_to_score(level: LevelType) -> float:
    """等级转分数（用于简化输入）"""
    mapping = {
        "high": 0.90,
        "medium": 0.75,
        "low": 0.60
    }
    return mapping.get(level, 0.75)


def score_to_dict(score: HarnessScore) -> dict:
    """将HarnessScore转为JSON可序列化的字典"""
    return {
        "completeness": {
            "score": score.completeness.score,
            "level": score.completeness.level,
            "reasoning": score.completeness.reasoning
        },
        "necessity": {
            "score": score.necessity.score,
            "level": score.necessity.level,
            "reasoning": score.necessity.reasoning
        },
        "alignment": {
            "score": score.alignment.score,
            "level": score.alignment.level,
            "reasoning": score.alignment.reasoning
        },
        "global_impact": {
            "score": score.global_impact.score,
            "level": score.global_impact.level,
            "reasoning": score.global_impact.reasoning
        },
        "overall_score": score.overall_score,
        "decision": score.decision,
        "improvements": score.improvements
    }


def _validate_harness_output_legacy(output: dict) -> tuple[bool, str]:
    """
    验证Worker输出的Harness格式是否正确
    
    优先使用 HarnessCheck Pydantic schema（含契约笼子）
    如果 验证失败，尝试 格式（向后兼容）
    
    Returns:
        (是否有效, 错误信息)
    """
    if "harness_check" not in output:
        return False, "缺少harness_check字段"
    
    hc = output["harness_check"]
    
    # 格式检测: 有 layer1_system_guardrails
    if "layer1_system_guardrails" in hc:
        try:
            from .schemas.schemas import HarnessCheckV2
            HarnessCheckV2(**hc)
            return True, ""
        except ImportError:
            pass
        except Exception as e:
            raise ValueError(f"[HarnessCheckV2] 验证失败 — 契约笼子触发: {e}")
    
    # 格式（向后兼容）
    required_fields = ["completeness", "necessity", "alignment", "global_impact", "overall_score", "decision"]
    
    for field in required_fields:
        if field not in hc:
            return False, f"harness_check缺少{field}字段"
    
    # 验证decision值
    valid_decisions = ["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]
    if hc["decision"] not in valid_decisions:
        return False, f"decision值无效: {hc['decision']}"
    
    # 验证分数范围
    for dim in ["completeness", "necessity", "alignment", "global_impact"]:
        score = hc[dim]["score"] if isinstance(hc[dim], dict) else hc[dim]
        if not (0.0 <= score <= 1.0):
            return False, f"{dim}分数超出范围: {score}"
    
    return True, ""


def validate_harness_output(harness_check: dict) -> tuple[bool, str]:
    """
    专用验证函数
    
    Args:
        harness_check: harness_check 字段的内容（不是整个 stage output）
    
    Returns:
        (是否有效, 错误信息)
    """
    try:
        from .schemas.schemas import HarnessCheckV2
        HarnessCheckV2(**harness_check)
        return True, ""
    except ImportError:
        return False, "HarnessCheck schema 未安装"
    except Exception as e:
        raise ValueError(f"[HarnessCheckV2] 验证失败 — 契约笼子触发: {e}")


def harness_to_scores(harness_check: dict) -> dict:
    """
    verdict → 数值映射（供 Gate A Layer 2 使用）
    
    Args:
        harness_check: HarnessCheck格式的 dict
    
    Returns:
        {"completeness": 0.95, "necessity": 0.80, "alignment": 0.95, "global_impact": 0.95,
         "overall_score": 0.91, "decision": "PASS"}
    """
    from .schemas.schemas import VERDICT_SCORE_MAP
    
    layer1 = harness_check.get("layer1_system_guardrails", {})
    scores = {}
    for dim in ["completeness", "necessity", "alignment", "global_impact"]:
        dim_data = layer1.get(dim, {})
        # Prefer LLM-provided numeric score; fallback to VERDICT_SCORE_MAP
        llm_score = dim_data.get("score")
        if isinstance(llm_score, (int, float)) and 0.0 <= llm_score <= 1.0:
            scores[dim] = llm_score
        else:
            verdict = dim_data.get("verdict", "WEAK")
            scores[dim] = VERDICT_SCORE_MAP.get(verdict, 0.50)
    
    # overall_score = weighted average
    overall = (
        scores["completeness"] * 0.30 +
        scores["necessity"] * 0.20 +
        scores["alignment"] * 0.30 +
        scores["global_impact"] * 0.20
    )
    
    # decision from overall_verdict
    overall_verdict = harness_check.get("overall_verdict", "CONDITIONAL")
    verdict_to_decision = {
        "STRONG_PASS": "PASS",
        "PASS": "PASS",
        "CONDITIONAL": "WARNING",
        "WARNING": "CRITICAL_WARNING",
        "FAIL": "BLOCK_RECOMMENDATION",
    }
    decision = verdict_to_decision.get(overall_verdict, "WARNING")
    
    return {
        "completeness": scores["completeness"],
        "necessity": scores["necessity"],
        "alignment": scores["alignment"],
        "global_impact": scores["global_impact"],
        "overall_score": round(overall, 2),
        "decision": decision,
    }


# 便捷函数：从等级快速计算
def calculate_from_levels(
    completeness_level: LevelType,
    necessity_level: LevelType,
    alignment_level: LevelType,
    global_impact_level: LevelType,
    **reasonings
) -> HarnessScore:
    """从等级（high/medium/low）快速计算总分"""
    return calculate_harness_score(
        completeness=level_to_score(completeness_level),
        necessity=level_to_score(necessity_level),
        alignment=level_to_score(alignment_level),
        global_impact=level_to_score(global_impact_level),
        **reasonings
    )


def calculate_harness_score_dynamic(
    weights: Dict[str, float],
    thresholds: Dict[str, float],
    scores: Dict[str, float],
    reasonings: Optional[Dict[str, str]] = None,
) -> HarnessScore:
    """
    动态权重/阈值的 Harness 评分

    Args:
        weights: 四维度权重 dict，key 为 completeness/necessity/alignment/global_impact，值之和应为 1.0
        thresholds: 阈值 dict，至少包含 PASS/WARNING/CRITICAL/BLOCK_RECOMMENDATION
        scores: 评分 dict，key 为 completeness/necessity/alignment/global_impact，值 0.0-1.0
        reasonings: 可选，各维度理由 dict

    Returns:
        HarnessScore 对象（复用现有 dataclass）
    """
    # 校验权重 key
    required_dims = {"completeness", "necessity", "alignment", "global_impact"}
    missing_dims = required_dims - set(weights.keys())
    if missing_dims:
        raise ValueError(f"weights 缺少维度: {missing_dims}")
    missing_score_dims = required_dims - set(scores.keys())
    if missing_score_dims:
        raise ValueError(f"scores 缺少维度: {missing_score_dims}")

    # 归一化权重（防御性：即使和不为 1 也能工作）
    w_sum = sum(weights.values())
    if w_sum <= 0:
        raise ValueError("weights 总和必须 > 0")
    norm_weights = {k: v / w_sum for k, v in weights.items()}

    # 计算加权总分
    overall = sum(scores[d] * norm_weights[d] for d in required_dims)

    # 从 thresholds 读取阈值（提供默认值兜底）
    t_pass = thresholds.get("PASS", THRESHOLD_PASS)
    t_warn = thresholds.get("WARNING", THRESHOLD_WARNING)
    t_crit = thresholds.get("CRITICAL", thresholds.get("CRITICAL_WARNING", THRESHOLD_CRITICAL))
    t_block = thresholds.get("BLOCK_RECOMMENDATION", 0.0)

    # 基础决策
    if overall >= t_pass:
        decision: DecisionType = "PASS"
    elif overall >= t_warn:
        decision = "WARNING"
    elif overall >= t_crit:
        decision = "CRITICAL_WARNING"
    else:
        decision = "BLOCK_RECOMMENDATION"

    # 特殊规则：alignment < 阈值 → 至少 CRITICAL_WARNING
    alignment_critical_threshold = thresholds.get("ALIGNMENT_CRITICAL", THRESHOLD_ALIGNMENT_CRITICAL)
    if scores.get("alignment", 1.0) < alignment_critical_threshold:
        if decision in ("PASS", "WARNING"):
            decision = "CRITICAL_WARNING"

    # 生成改进建议
    r = reasonings or {}
    improvements = _generate_improvements(
        scores.get("completeness", 0),
        scores.get("necessity", 0),
        scores.get("alignment", 0),
        scores.get("global_impact", 0),
    )

    return HarnessScore(
        completeness=DimensionScore(scores.get("completeness", 0), r.get("completeness", "")),
        necessity=DimensionScore(scores.get("necessity", 0), r.get("necessity", "")),
        alignment=DimensionScore(scores.get("alignment", 0), r.get("alignment", "")),
        global_impact=DimensionScore(scores.get("global_impact", 0), r.get("global_impact", "")),
        overall_score=round(overall, 2),
        decision=decision,
        improvements=improvements,
    )


# =============================================================================
# [Phase 1.4] Gate A Layer 2 语义校准 + Gate B CRITICAL 保底检查
# =============================================================================


class GateALayer2Calibration:
    """
    Gate A Layer 2: LLM 语义校准层

    对 Gate A Layer 1（代码打分）的结果进行 LLM 语义验证。
    使用 3-run majority vote 确保一致性。

    向后兼容：当 llm_judge_fn 为 None 时，自动 fallback 到规则判定。
    """

    TEMPERATURE = 0.2

    FEW_SHOT_EXAMPLES = [
        {
            "input": {"completeness": 0.9, "necessity": 0.85, "alignment": 0.95, "global_impact": 0.90},
            "output": {
                "semantic_verdict": "PASS",
                "reasoning": "completeness 0.9 是因为跳过了一个 P2 低优先级需求，核心功能 100% 覆盖。alignment 0.95 表明方案与需求高度对齐。"
            }
        },
        {
            "input": {"completeness": 0.9, "necessity": 0.60, "alignment": 0.55, "global_impact": 0.70},
            "output": {
                "semantic_verdict": "FAIL",
                "reasoning": "alignment 0.55 表明方案偏离了原始意图。necessity 0.60 表明约束质量不足。"
            }
        },
    ]

    def __init__(self, llm_judge_fn=None):
        """
        Args:
            llm_judge_fn: Callable[[stage_output, frozen_spec, harness_reasoning, scores, prompt, temperature], dict]
                          返回 {"semantic_verdict": "PASS"|"FAIL", "reasoning": "..."}
                          当为 None 时，自动 fallback 到规则判定。
            注意: HarnessScorer 的 llm_judge_fn 签名与 LLMJudgeAdapter 不兼容，
                  需要调用方自行适配。不要在这里自动创建 Adapter。
        """
        self.llm_judge_fn = llm_judge_fn

    def run_majority_vote(
        self,
        stage_output: dict,
        frozen_spec: dict,
        harness_reasoning: str,
        scores: dict,
        n_runs: int = 3,
        living_spec: dict = None,
    ) -> dict:
        """
        运行 3 次 LLM Judge，取多数投票结果。

        Args:
            living_spec: Living Spec(Spec Pro 产出,可选)。存在时优先使用 narrative 替代 frozen_spec。

        Returns:
            {
                "semantic_verdict": "PASS" | "FAIL",
                "votes": ["PASS", "PASS", "FAIL"],
                "consistency": 0.67,  # max(pass_count, fail_count) / n_runs
            }
        """
        if self.llm_judge_fn is None:
            # Fallback: 基于规则的判定
            return self._rule_based_verdict(scores)

        votes = []
        for i in range(n_runs):
            prompt = self._build_calibration_prompt(stage_output, frozen_spec, harness_reasoning, scores, living_spec=living_spec)
            result = self.llm_judge_fn(
                stage_output=stage_output,
                frozen_spec=frozen_spec,
                harness_reasoning=harness_reasoning,
                scores=scores,
                prompt=prompt,
                temperature=self.TEMPERATURE,
            )
            # fix: handle None return from adapter (triggers rule fallback)
            if result is None:
                logger.warning("LLM judge returned None, falling back to rule-based verdict")
                return self._rule_based_verdict(scores)
            votes.append(result.get("semantic_verdict", "FAIL"))

        pass_count = votes.count("PASS")
        fail_count = votes.count("FAIL")

        # Majority vote; tie goes to FAIL (conservative)
        if pass_count >= 2:
            verdict = "PASS"
        else:
            verdict = "FAIL"

        return {
            "semantic_verdict": verdict,
            "votes": votes,
            "consistency": max(pass_count, fail_count) / n_runs,
        }

    def _build_calibration_prompt(self, stage_output, frozen_spec, harness_reasoning, scores, living_spec=None):
        """构建 Layer 2 校准 prompt"""
        examples_text = "\n".join([
            f"示例 {i+1}:\n输入: {ex['input']}\n输出: {ex['output']}"
            for i, ex in enumerate(self.FEW_SHOT_EXAMPLES)
        ])

        # Living Spec 优先
        if living_spec:
            spec_for_prompt = living_spec.get("narrative", "")[:3000]
        else:
            spec_for_prompt = str(json.dumps(frozen_spec, ensure_ascii=False))[:3000] if frozen_spec else ""

        return f"""## Gate A Layer 2 语义校准

你是一个独立的质量评审员。基于以下信息判断 Harness Agent 的打分是否合理。

### Harness Agent 打分
- completeness: {scores.get('completeness', 0)}
- necessity: {scores.get('necessity', 0)}
- alignment: {scores.get('alignment', 0)}
- global_impact: {scores.get('global_impact', 0)}

### Harness Agent 推理
{harness_reasoning}

### 原始需求（Spec Context）
{spec_for_prompt}

### Stage 输出摘要
{json.dumps(stage_output, ensure_ascii=False)[:1000]}

## 参考示例
{examples_text}

## 你的判断
请判断 Harness Agent 的打分是否合理，输出：
{{"semantic_verdict": "PASS"|"FAIL", "reasoning": "..."}}

判断标准：
- 如果打分与推理一致且合理 → PASS
- 如果打分与推理矛盾，或遗漏了关键问题 → FAIL
"""

    def _rule_based_verdict(self, scores: dict) -> dict:
        """基于规则的 fallback 判定"""
        completeness = scores.get("completeness", 0)
        necessity = scores.get("necessity", 0)
        alignment = scores.get("alignment", 0)
        global_impact = scores.get("global_impact", 0)

        # 加权平均
        weighted_avg = (
            completeness * 0.3 +
            necessity * 0.2 +
            alignment * 0.3 +
            global_impact * 0.2
        )

        verdict = "PASS" if weighted_avg >= 0.7 else "FAIL"

        return {
            "semantic_verdict": verdict,
            "votes": [verdict],
            "consistency": 1.0,
            "note": "rule_based_fallback",
        }


def evaluate_gate_b_critical(
    gate_b_results: list,
    critical_checks: list,
) -> dict:
    """
    Gate B CRITICAL 保底检查。

    确保所有 CRITICAL 级别的检查全部通过，且整体通过率 >= 80%。

    Args:
        gate_b_results: [{"check_id": "CHK-001", "verdict": "PASS"|"FAIL", "reasoning": "..."}]
        critical_checks: [{"id": "CHK-001", "criticality": "CRITICAL", "description": "..."}]

    Returns:
        {
            "verdict": "PASS" | "FAIL",
            "critical_pass_rate": 1.0,   # CRITICAL 检查通过率
            "overall_pass_rate": 0.9,    # 所有检查通过率
            "failed_critical": [],        # 失败的 CRITICAL 检查 ID
        }
    """
    # 构建 check_id -> verdict 映射
    verdict_map = {r["check_id"]: r["verdict"] for r in gate_b_results}

    # 检查 CRITICAL 项
    failed_critical = []
    for check in critical_checks:
        if check.get("criticality") == "CRITICAL":
            check_id = check["id"]
            if verdict_map.get(check_id) != "PASS":
                failed_critical.append(check_id)

    # 计算通过率
    total_checks = len(gate_b_results)
    passed_checks = sum(1 for r in gate_b_results if r["verdict"] == "PASS")
    overall_pass_rate = passed_checks / total_checks if total_checks > 0 else 0.0

    critical_total = len([c for c in critical_checks if c.get("criticality") == "CRITICAL"])
    critical_passed = critical_total - len(failed_critical)
    critical_pass_rate = critical_passed / critical_total if critical_total > 0 else 1.0

    # 判定：CRITICAL 全部通过 + 整体通过率 >= 80%
    verdict = "PASS" if (len(failed_critical) == 0 and overall_pass_rate >= 0.8) else "FAIL"

    return {
        "verdict": verdict,
        "critical_pass_rate": critical_pass_rate,
        "overall_pass_rate": overall_pass_rate,
        "failed_critical": failed_critical,
    }


if __name__ == "__main__":
    # [Phase 0a] P0-2: 新增 calculate_harness_score_dynamic() 支持动态权重/阈值
    # 测试用例
    test_cases = [
        # 完美方案
        (0.90, 0.88, 0.92, 0.86, "全部覆盖", "恰到好处", "完全对齐", "全局影响充分"),
        # 完整性不足
        (0.65, 0.85, 0.88, 0.82, "遗漏关键点", "适度", "对齐", "影响可控"),
        # 目标偏离（触发特殊规则）
        (0.88, 0.85, 0.55, 0.78, "完整", "适度", "明显偏离目标", "影响一般"),
        # 全面不足
        (0.55, 0.60, 0.58, 0.52, "严重遗漏", "过度设计", "偏离目标", "缺少全局影响分析"),
    ]
    
    print
    print("=" * 60)
    print(
        f"权重: 完整性{WEIGHT_COMPLETENESS} / 必要性{WEIGHT_NECESSITY} / "
        f"目标一致性{WEIGHT_ALIGNMENT} / 全局影响{WEIGHT_GLOBAL_IMPACT}"
    )
    print(f"阈值: PASS≥{THRESHOLD_PASS} / WARNING≥{THRESHOLD_WARNING} / CRITICAL≥{THRESHOLD_CRITICAL}")
    print("=" * 60)
    
    for c, n, a, g, cr, nr, ar, gr in test_cases:
        score = calculate_harness_score(c, n, a, g, cr, nr, ar, gr)
        print(f"\n完整性:{c:.2f} 必要性:{n:.2f} 目标一致:{a:.2f} 全局影响:{g:.2f}")
        print(f"  → 总分: {score.overall_score:.2f} | 决策: {score.decision}")
        print(f"  → 改进建议: {score.improvements[0] if score.improvements else '无'}")
