"""
Harness 评分器，支持 level 自动推导和显式传入

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
Harness Scorer V2.0
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


def _generate_improvements(c: float, n: float, a: float, g: float) -> list:
    """根据评分生成改进建议"""
    improvements = []
    
    if c < 0.70:
        improvements.append("完善方案覆盖范围，确保关键设计点无遗漏")
    elif c < 0.85:
        improvements.append("可考虑补充更多细节以增强完整性")
    
    if n < 0.70:
        improvements.append("简化方案，去除过度设计，贴合实际需求")
    elif n < 0.85:
        improvements.append("检查是否有可以精简的部分")
    
    if a < 0.70:
        improvements.append("重新审视方案与原始目标的一致性，避免偏离")
    elif a < 0.85:
        improvements.append("确保所有设计决策都服务于原始目标")

    if g < 0.70:
        improvements.append("补充成本、风险、集成、运维和长期演进等全局影响分析")
    elif g < 0.85:
        improvements.append("检查跨阶段依赖和长期影响是否描述充分")
    
    if not improvements:
        improvements.append("当前方案质量良好，无明显改进需求")
    
    return improvements


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


def validate_harness_output(output: dict) -> tuple[bool, str]:
    """
    验证Worker输出的Harness格式是否正确
    
    Returns:
        (是否有效, 错误信息)
    """
    required_fields = ["completeness", "necessity", "alignment", "global_impact", "overall_score", "decision"]
    
    if "harness_check" not in output:
        return False, "缺少harness_check字段"
    
    hc = output["harness_check"]
    
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


if __name__ == "__main__":
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
    
    print("Harness Scorer V2.1 测试")
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
