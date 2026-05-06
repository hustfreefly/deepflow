"""
Harness Scorer V2.0
===================

3维度评分器（权重：完整性35% / 必要性25% / 目标一致性40%）

决策层级：
- PASS (≥0.85): 质量达标
- WARNING (0.70-0.84): 咨询意见
- CRITICAL_WARNING (0.60-0.69): 强烈建议修改
- BLOCK_RECOMMENDATION (<0.60): 建议重新规划（仍不阻断）

特殊规则：目标一致性<0.6 → 至少CRITICAL_WARNING
"""

from typing import Dict, Literal
from dataclasses import dataclass

# 评分权重（已确认）
WEIGHT_COMPLETENESS = 0.35
WEIGHT_NECESSITY = 0.25
WEIGHT_ALIGNMENT = 0.40

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
    level: LevelType
    reasoning: str
    
    def __post_init__(self):
        # 自动根据分数确定level
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
    overall_score: float
    decision: DecisionType
    improvements: list


def calculate_harness_score(
    completeness: float,
    necessity: float,
    alignment: float,
    completeness_reasoning: str = "",
    necessity_reasoning: str = "",
    alignment_reasoning: str = ""
) -> HarnessScore:
    """
    计算Harness总分和决策
    
    公式：总分 = 完整性×0.35 + 必要性×0.25 + 目标一致性×0.40
    
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
        alignment * WEIGHT_ALIGNMENT
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
    improvements = _generate_improvements(completeness, necessity, alignment)
    
    return HarnessScore(
        completeness=DimensionScore(completeness, "medium", completeness_reasoning),
        necessity=DimensionScore(necessity, "medium", necessity_reasoning),
        alignment=DimensionScore(alignment, "medium", alignment_reasoning),
        overall_score=round(overall, 2),
        decision=decision,
        improvements=improvements
    )


def _generate_improvements(c: float, n: float, a: float) -> list:
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
    required_fields = ["completeness", "necessity", "alignment", "overall_score", "decision"]
    
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
    for dim in ["completeness", "necessity", "alignment"]:
        score = hc[dim]["score"] if isinstance(hc[dim], dict) else hc[dim]
        if not (0.0 <= score <= 1.0):
            return False, f"{dim}分数超出范围: {score}"
    
    return True, ""


# 便捷函数：从等级快速计算
def calculate_from_levels(
    completeness_level: LevelType,
    necessity_level: LevelType,
    alignment_level: LevelType,
    **reasonings
) -> HarnessScore:
    """从等级（high/medium/low）快速计算总分"""
    return calculate_harness_score(
        completeness=level_to_score(completeness_level),
        necessity=level_to_score(necessity_level),
        alignment=level_to_score(alignment_level),
        **reasonings
    )


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        # 完美方案
        (0.90, 0.88, 0.92, "全部覆盖", "恰到好处", "完全对齐"),
        # 完整性不足
        (0.65, 0.85, 0.88, "遗漏关键点", "适度", "对齐"),
        # 目标偏离（触发特殊规则）
        (0.88, 0.85, 0.55, "完整", "适度", "明显偏离目标"),
        # 全面不足
        (0.55, 0.60, 0.58, "严重遗漏", "过度设计", "偏离目标"),
    ]
    
    print("Harness Scorer V2.0 测试")
    print("=" * 60)
    print(f"权重: 完整性{WEIGHT_COMPLETENESS} / 必要性{WEIGHT_NECESSITY} / 目标一致性{WEIGHT_ALIGNMENT}")
    print(f"阈值: PASS≥{THRESHOLD_PASS} / WARNING≥{THRESHOLD_WARNING} / CRITICAL≥{THRESHOLD_CRITICAL}")
    print("=" * 60)
    
    for c, n, a, cr, nr, ar in test_cases:
        score = calculate_harness_score(c, n, a, cr, nr, ar)
        print(f"\n完整性:{c:.2f} 必要性:{n:.2f} 目标一致:{a:.2f}")
        print(f"  → 总分: {score.overall_score:.2f} | 决策: {score.decision}")
        print(f"  → 改进建议: {score.improvements[0] if score.improvements else '无'}")
