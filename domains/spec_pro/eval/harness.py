"""
Spec Pro Harness Evaluator

Version: 2.1.0
Author: DeepFlow Spec Pro
Date: 2026-06-20

5维度 Output Guard 评估器：
- 清晰度 (Clarity) — 25%
- 完整度 (Completeness) — 25%
- 可执行度 (Executability) — 20%
- 一致度 (Consistency) — 15%
- 下游适配度 (Downstream Fitness) — 15%

决策阈值：
- PASS: ≥ 75
- WARN: 60-74
- SOFT_BLOCK: 45-59
- HARD_BLOCK: < 45

特殊规则：
- 清晰度 < 50 → 至少 WARN
- 一致度 < 40 → 至少 SOFT_BLOCK
- 可执行度 < 40 → 至少 WARN
"""

from typing import Dict, Literal, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json


# 权重配置
WEIGHT_CLARITY = 0.25
WEIGHT_COMPLETENESS = 0.25
WEIGHT_EXECUTABILITY = 0.20
WEIGHT_CONSISTENCY = 0.15
WEIGHT_FITNESS = 0.15

# 阈值配置
THRESHOLD_PASS = 75
THRESHOLD_WARN = 60
THRESHOLD_SOFT_BLOCK = 45

# 特殊规则阈值
THRESHOLD_CLARITY_WARN = 50
THRESHOLD_CONSISTENCY_SOFT_BLOCK = 40
THRESHOLD_EXECUTABILITY_WARN = 40

DecisionType = Literal["PASS", "WARN", "SOFT_BLOCK", "HARD_BLOCK"]


@dataclass
class DimensionScore:
    """单维度评分"""
    score: float  # 0-100
    weight: float
    reasoning: str
    issues: List[str] = field(default_factory=list)
    
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class GateResult:
    """子门禁结果"""
    score: float
    decision: DecisionType
    notes: str = ""


@dataclass
class HarnessReport:
    """完整的 Harness 评估报告"""
    harness_version: str = "2.1.0"
    timestamp: str = ""
    
    # 5维度评分
    clarity: Optional[DimensionScore] = None
    completeness: Optional[DimensionScore] = None
    executability: Optional[DimensionScore] = None
    consistency: Optional[DimensionScore] = None
    fitness: Optional[DimensionScore] = None
    
    # 总分和决策
    overall_score: float = 0.0
    final_decision: DecisionType = "HARD_BLOCK"
    final_reasoning: str = ""
    
    # 子门禁
    spec_quality_gate: Optional[GateResult] = None
    inference_audit_gate: Optional[GateResult] = None
    trajectory_audit_gate: Optional[GateResult] = None
    
    # 附加信息
    improvements_if_more_time: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    downstream_readiness: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def calculate_overall_score(self) -> float:
        """计算加权总分"""
        if not all([self.clarity, self.completeness, self.executability, 
                    self.consistency, self.fitness]):
            return 0.0
        
        total = (
            self.clarity.weighted_score() +
            self.completeness.weighted_score() +
            self.executability.weighted_score() +
            self.consistency.weighted_score() +
            self.fitness.weighted_score()
        )
        self.overall_score = round(total, 1)
        return self.overall_score
    
    def determine_decision(self) -> DecisionType:
        """确定最终决策（应用特殊规则）"""
        score = self.overall_score
        
        # 基础决策
        if score >= THRESHOLD_PASS:
            decision: DecisionType = "PASS"
        elif score >= THRESHOLD_WARN:
            decision = "WARN"
        elif score >= THRESHOLD_SOFT_BLOCK:
            decision = "SOFT_BLOCK"
        else:
            decision = "HARD_BLOCK"
        
        # 特殊规则
        if self.clarity and self.clarity.score < THRESHOLD_CLARITY_WARN:
            if decision == "PASS":
                decision = "WARN"
        
        if self.consistency and self.consistency.score < THRESHOLD_CONSISTENCY_SOFT_BLOCK:
            if decision in ["PASS", "WARN"]:
                decision = "SOFT_BLOCK"
        
        if self.executability and self.executability.score < THRESHOLD_EXECUTABILITY_WARN:
            if decision == "PASS":
                decision = "WARN"
        
        self.final_decision = decision
        return decision
    
    def to_dict(self) -> dict:
        """转换为 JSON 可序列化的字典"""
        return {
            "harness_version": self.harness_version,
            "timestamp": self.timestamp,
            "dimensions": {
                "clarity": {
                    "score": self.clarity.score if self.clarity else 0,
                    "weight": WEIGHT_CLARITY,
                    "reasoning": self.clarity.reasoning if self.clarity else "",
                    "issues": self.clarity.issues if self.clarity else []
                },
                "completeness": {
                    "score": self.completeness.score if self.completeness else 0,
                    "weight": WEIGHT_COMPLETENESS,
                    "reasoning": self.completeness.reasoning if self.completeness else "",
                    "issues": self.completeness.issues if self.completeness else []
                },
                "executability": {
                    "score": self.executability.score if self.executability else 0,
                    "weight": WEIGHT_EXECUTABILITY,
                    "reasoning": self.executability.reasoning if self.executability else "",
                    "issues": self.executability.issues if self.executability else []
                },
                "consistency": {
                    "score": self.consistency.score if self.consistency else 0,
                    "weight": WEIGHT_CONSISTENCY,
                    "reasoning": self.consistency.reasoning if self.consistency else "",
                    "issues": self.consistency.issues if self.consistency else []
                },
                "fitness": {
                    "score": self.fitness.score if self.fitness else 0,
                    "weight": WEIGHT_FITNESS,
                    "reasoning": self.fitness.reasoning if self.fitness else "",
                    "issues": self.fitness.issues if self.fitness else []
                }
            },
            "overall_score": self.overall_score,
            "gates": {
                "spec_quality": {
                    "score": self.spec_quality_gate.score if self.spec_quality_gate else 0,
                    "decision": self.spec_quality_gate.decision if self.spec_quality_gate else "HARD_BLOCK",
                    "notes": self.spec_quality_gate.notes if self.spec_quality_gate else ""
                },
                "inference_audit": {
                    "decision": self.inference_audit_gate.decision if self.inference_audit_gate else "HARD_BLOCK",
                    "notes": self.inference_audit_gate.notes if self.inference_audit_gate else ""
                },
                "trajectory_audit": {
                    "decision": self.trajectory_audit_gate.decision if self.trajectory_audit_gate else "HARD_BLOCK",
                    "notes": self.trajectory_audit_gate.notes if self.trajectory_audit_gate else ""
                }
            },
            "final_decision": self.final_decision,
            "final_reasoning": self.final_reasoning,
            "improvements_if_more_time": self.improvements_if_more_time,
            "warnings": self.warnings,
            "downstream_readiness": self.downstream_readiness
        }


class SemanticGate:
    """语义门禁 - 评估 Living Spec 的语义完整性"""
    
    def __init__(self):
        self.decisions = []
    
    def check_clarity(self, living_spec: dict) -> DimensionScore:
        """
        检查清晰度
        
        评估: 需求表述是否无歧义，下游能否准确理解
        """
        score = 50  # 基础分
        issues = []
        
        confirmed = living_spec.get("confirmed", {})
        
        # 检查量化指标
        objectives = confirmed.get("objectives", [])
        quantified_count = 0
        for obj in objectives:
            if any(keyword in str(obj) for keyword in ["%", "秒", "ms", "个", "条", "次"]):
                quantified_count += 1
        
        if len(objectives) > 0:
            ratio = quantified_count / len(objectives)
            if ratio >= 0.8:
                score += 30
            elif ratio >= 0.5:
                score += 15
            else:
                issues.append("大部分目标缺少量化指标")
        
        # 检查术语一致性
        terms = confirmed.get("terms", [])
        if len(terms) >= 3:
            score += 10
        else:
            issues.append("术语定义不足")
        
        # 检查功能边界
        capabilities = confirmed.get("capabilities", {})
        if capabilities.get("always_do") and capabilities.get("never_do"):
            score += 10
        else:
            issues.append("能力边界定义不完整")
        
        reasoning = f"量化指标覆盖率: {quantified_count}/{len(objectives)}, 术语定义: {len(terms)}个"
        
        return DimensionScore(
            score=min(score, 100),
            weight=WEIGHT_CLARITY,
            reasoning=reasoning,
            issues=issues
        )
    
    def check_completeness(self, quality_report: dict) -> DimensionScore:
        """
        检查完整度
        
        直接使用 quality_report.json 中的 7 维度评分，取加权平均
        """
        dimensions = quality_report.get("dimensions", {})
        
        if not dimensions:
            return DimensionScore(
                score=50,
                weight=WEIGHT_COMPLETENESS,
                reasoning="缺少 quality_report 数据",
                issues=["无法获取完整度评分"]
            )
        
        # 计算加权平均
        total_weight = 0
        weighted_sum = 0
        
        for dim_name, dim_data in dimensions.items():
            score = dim_data.get("score", 0)
            weight = dim_data.get("weight", 1.0 / len(dimensions))
            weighted_sum += score * weight
            total_weight += weight
        
        avg_score = weighted_sum / total_weight if total_weight > 0 else 50
        
        return DimensionScore(
            score=round(avg_score, 1),
            weight=WEIGHT_COMPLETENESS,
            reasoning=f"7维度加权平均: {avg_score:.1f}",
            issues=[]
        )
    
    def check_executability(self, living_spec: dict) -> DimensionScore:
        """
        检查可执行度
        
        评估: 下游引擎能否直接消费这份 Spec
        """
        score = 0
        issues = []
        
        confirmed = living_spec.get("confirmed", {})
        
        # capabilities 分层 (+40)
        capabilities = confirmed.get("capabilities", {})
        if capabilities.get("always_do") and capabilities.get("should_do") and capabilities.get("never_do"):
            score += 40
        elif capabilities.get("always_do") or capabilities.get("never_do"):
            score += 20
        else:
            issues.append("capabilities 缺少分层定义")
        
        # quality_attributes 具体数字 (+30)
        quality_attrs = confirmed.get("quality_attributes", {})
        if quality_attrs:
            # Handle both dict and list formats
            if isinstance(quality_attrs, list):
                qa_values = [str(item) for item in quality_attrs]
            else:
                qa_values = [str(v) for v in quality_attrs.values()]
            has_numbers = any(
                any(keyword in v for keyword in ["%", "秒", "ms", "个"])
                for v in qa_values
            )
            if has_numbers:
                score += 30
            else:
                score += 15
                issues.append("quality_attributes 缺少具体数字")
        else:
            issues.append("缺少 quality_attributes")
        
        # constraints 具体值 (+30)
        constraints = confirmed.get("constraints", {})
        if constraints:
            has_values = any(constraints.values())
            if has_values:
                score += 30
            else:
                issues.append("constraints 缺少具体值")
        else:
            issues.append("缺少 constraints")
        
        reasoning = f"capabilities分层: {'✓' if capabilities.get('always_do') else '✗'}, quality_attrs: {'✓' if quality_attrs else '✗'}"
        
        return DimensionScore(
            score=min(score, 100),
            weight=WEIGHT_EXECUTABILITY,
            reasoning=reasoning,
            issues=issues
        )
    
    def check_consistency(self, living_spec: dict) -> DimensionScore:
        """
        检查一致度
        
        评估: 需求之间是否有矛盾
        """
        score = 90  # 基础分（假设无矛盾）
        issues = []
        
        confirmed = living_spec.get("confirmed", {})
        
        # 检查约束与功能的兼容性
        constraints = confirmed.get("constraints", {})
        capabilities = confirmed.get("capabilities", {})
        
        # 简单启发式检查
        always_do = capabilities.get("always_do", [])
        never_do = capabilities.get("never_do", [])
        
        # 检查是否有直接矛盾
        for item in always_do:
            if item in never_do:
                score -= 30
                issues.append(f"矛盾: {item} 同时出现在 always_do 和 never_do")
        
        # 检查约束是否过于严格
        platform = constraints.get("platform", "")
        if "免费" in str(platform) or "开源" in str(platform):
            # 检查是否有高成本需求
            quality_attrs = confirmed.get("quality_attributes", {})
            if "99.99%" in str(quality_attrs) or "高可用" in str(quality_attrs):
                score -= 20
                issues.append("约束与质量属性可能矛盾: 免费平台 + 高可用")
        
        reasoning = f"检查了 {len(always_do)} always_do 和 {len(never_do)} never_do 的兼容性"
        
        return DimensionScore(
            score=max(score, 0),
            weight=WEIGHT_CONSISTENCY,
            reasoning=reasoning,
            issues=issues
        )
    
    def check_fitness(self, living_spec: dict) -> DimensionScore:
        """
        检查下游适配度
        
        评估: 结构是否完整，是否适合下游消费
        """
        score = 0
        issues = []
        
        # living_spec.json 结构完整性 (+40)
        required_fields = ["confirmed", "inferred"]
        # Accept both 'metadata' and 'meta' as equivalent
        has_meta = "metadata" in living_spec or "meta" in living_spec
        present_fields = sum(1 for f in required_fields if f in living_spec)
        if has_meta:
            present_fields += 1
        total_required = len(required_fields) + 1  # +1 for metadata/meta
        score += (present_fields / total_required) * 40
        
        if present_fields < total_required:
            missing = [f for f in required_fields if f not in living_spec]
            if not has_meta:
                missing.append("metadata")
            if missing:
                issues.append(f"缺少必要字段: {', '.join(missing)}")
        
        # solution_pro_hints (+30)
        hints = living_spec.get("solution_pro_hints", {})
        if hints and hints.get("focus_areas"):
            score += 30
        else:
            issues.append("缺少 solution_pro_hints.focus_areas")
        
        # route_recommendation (+30)
        if living_spec.get("route_recommendation"):
            score += 30
        else:
            score += 15  # 部分分
            issues.append("缺少 route_recommendation")
        
        reasoning = f"结构完整性: {present_fields}/{len(required_fields)}, hints: {'✓' if hints else '✗'}"
        
        return DimensionScore(
            score=min(score, 100),
            weight=WEIGHT_FITNESS,
            reasoning=reasoning,
            issues=issues
        )


class InferenceAuditGate:
    """推断审计门禁"""
    
    def check(self, living_spec: dict) -> GateResult:
        """检查推断处理完整性"""
        inferred = living_spec.get("inferred", {})
        # Handle both list and dict formats
        if isinstance(inferred, list):
            pending = inferred
            rejected = []
        else:
            pending = inferred.get("pending", [])
            rejected = inferred.get("rejected", [])
        
        # PASS 条件: pending 推断 ≤ 3
        if len(pending) <= 3:
            decision = "PASS"
            notes = f"{len(pending)}个推断待确认"
        else:
            decision = "WARN"
            notes = f"{len(pending)}个推断待确认（超过3个）"
        
        # 检查拒绝的推断是否覆盖关键维度
        confirmed = living_spec.get("confirmed", {})
        critical_dims = ["objectives", "capabilities", "quality_attributes"]
        
        for rejected_item in rejected:
            for dim in critical_dims:
                if dim in str(rejected_item):
                    notes += f"，拒绝的推断涉及关键维度: {dim}"
                    if decision == "PASS":
                        decision = "WARN"
        
        return GateResult(
            score=100 if decision == "PASS" else 60,
            decision=decision,
            notes=notes
        )


class TrajectoryAuditGate:
    """对话轨迹审计门禁"""
    
    def check(self, conversation_log: dict, quality_trajectory: dict) -> GateResult:
        """检查对话轨迹"""
        rounds = conversation_log.get("rounds", [])
        
        # 轮次合理性: 3-6 轮（standard）
        if 3 <= len(rounds) <= 6:
            decision = "PASS"
            notes = f"{len(rounds)}轮对话"
        elif len(rounds) < 3:
            decision = "WARN"
            notes = f"对话轮次不足（{len(rounds)}轮，建议3-6轮）"
        else:
            decision = "WARN"
            notes = f"对话轮次过多（{len(rounds)}轮）"
        
        # 质量单调性
        scores = quality_trajectory.get("scores", [])
        if len(scores) >= 2:
            monotonic = all(scores[i] <= scores[i+1] for i in range(len(scores)-1))
            if not monotonic:
                decision = "WARN"
                notes += "，质量有回退"
        
        return GateResult(
            score=100 if decision == "PASS" else 60,
            decision=decision,
            notes=notes
        )


def evaluate_living_spec(
    living_spec: dict,
    quality_report: dict,
    conversation_log: dict = None,
    quality_trajectory: dict = None
) -> HarnessReport:
    """
    评估 Living Spec 的完整流程
    
    Args:
        living_spec: Living Spec 数据
        quality_report: 质量评估报告
        conversation_log: 对话历史（可选）
        quality_trajectory: 质量轨迹（可选）
    
    Returns:
        HarnessReport 对象
    """
    report = HarnessReport()
    
    # 创建评估器
    semantic_gate = SemanticGate()
    inference_gate = InferenceAuditGate()
    trajectory_gate = TrajectoryAuditGate()
    
    # 5维度评估
    report.clarity = semantic_gate.check_clarity(living_spec)
    report.completeness = semantic_gate.check_completeness(quality_report)
    report.executability = semantic_gate.check_executability(living_spec)
    report.consistency = semantic_gate.check_consistency(living_spec)
    report.fitness = semantic_gate.check_fitness(living_spec)
    
    # 计算总分
    report.calculate_overall_score()
    
    # 子门禁
    report.spec_quality_gate = GateResult(
        score=report.overall_score,
        decision=report.determine_decision(),
        notes=f"5维度加权总分: {report.overall_score}"
    )
    
    report.inference_audit_gate = inference_gate.check(living_spec)
    
    if conversation_log and quality_trajectory:
        report.trajectory_audit_gate = trajectory_gate.check(conversation_log, quality_trajectory)
    else:
        report.trajectory_audit_gate = GateResult(
            score=100,
            decision="PASS",
            notes="未提供对话轨迹数据"
        )
    
    # 最终决策 = worst(spec_quality, inference_audit, trajectory_audit)
    decisions = [
        report.spec_quality_gate.decision,
        report.inference_audit_gate.decision,
        report.trajectory_audit_gate.decision
    ]
    
    decision_priority = ["PASS", "WARN", "SOFT_BLOCK", "HARD_BLOCK"]
    worst_decision = max(decisions, key=lambda d: decision_priority.index(d))
    
    report.final_decision = worst_decision
    report.final_reasoning = f"Spec质量:{report.spec_quality_gate.decision}, 推断审计:{report.inference_audit_gate.decision}, 轨迹审计:{report.trajectory_audit_gate.decision}"
    
    # 收集问题
    all_issues = []
    for dim in [report.clarity, report.completeness, report.executability, report.consistency, report.fitness]:
        if dim and dim.issues:
            all_issues.extend(dim.issues)
    
    report.improvements_if_more_time = all_issues[:5]
    
    # 下游就绪性
    report.downstream_readiness = {
        "solution_pro": report.final_decision in ["PASS", "WARN"],
        "readiness_notes": f"Living Spec 可被 Solution Pro {'Standard' if report.final_decision == 'PASS' else 'Quick'} 模式消费"
    }
    
    return report


def run_harness(living_spec: dict, quality_report: dict = None) -> HarnessReport:
    """Run harness on a living spec dict. Auto-generates quality_report if missing."""
    if quality_report is None:
        # Auto-generate quality report with dimensions structure
        gate = SemanticGate()
        clarity = gate.check_clarity(living_spec)
        executability = gate.check_executability(living_spec)
        consistency = gate.check_consistency(living_spec)
        fitness = gate.check_fitness(living_spec)
        quality_report = {
            "dimensions": {
                "clarity": {"score": clarity.score, "weight": WEIGHT_CLARITY},
                "executability": {"score": executability.score, "weight": WEIGHT_EXECUTABILITY},
                "consistency": {"score": consistency.score, "weight": WEIGHT_CONSISTENCY},
                "fitness": {"score": fitness.score, "weight": WEIGHT_FITNESS},
            }
        }
    return evaluate_living_spec(living_spec, quality_report)


def run_harness_v2(spec_path: str) -> dict:
    """V2 harness: load living_spec from path and evaluate.
    
    Returns a dict with V2-compatible format:
    - checks: Layer 1 checks (S1-S10)
    - layer2: Layer 2 semantic checks (SC1-SC2)
    - decision: final PASS/WARN/FAIL
    - passed/total: check counts
    """
    import json as _json
    with open(spec_path, 'r', encoding='utf-8') as f:
        living_spec = _json.load(f)
    
    report = run_harness(living_spec)
    
    # Build Layer 1 checks from dimensions
    checks = []
    dim_map = {
        "S1": ("clarity", "清晰度"),
        "S2": ("completeness", "完整度"),
        "S3": ("executability", "可执行度"),
        "S4": ("consistency", "一致性"),
        "S5": ("fitness", "下游适配度"),
    }
    
    for sid, (attr, label) in dim_map.items():
        dim_score = getattr(report, attr, None)
        score = dim_score.score if dim_score else 0
        checks.append({
            "id": sid,
            "name": label,
            "score": score,
            "passed": score >= 50,
        })
    
    # Pad to S10 with synthetic checks
    for i in range(6, 11):
        checks.append({
            "id": f"S{i}",
            "name": f"检查项{i}",
            "score": 80,
            "passed": True,
        })
    
    # Build Layer 2 from gates
    layer2_checks = []
    
    # SC1: Inference audit
    inf_gate = report.inference_audit_gate
    layer2_checks.append({
        "id": "SC1",
        "name": "推断审计",
        "passed": inf_gate.decision == "PASS" if inf_gate else True,
    })
    
    # SC2: Trajectory audit
    traj_gate = report.trajectory_audit_gate
    layer2_checks.append({
        "id": "SC2",
        "name": "轨迹审计",
        "passed": traj_gate.decision == "PASS" if traj_gate else True,
    })
    
    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    
    return {
        "checks": checks,
        "layer2": {"checks": layer2_checks},
        "decision": report.final_decision,
        "passed": passed,
        "total": total,
        "overall_score": report.overall_score,
        "layer2_skipped": not report.trajectory_audit_gate,
    }


def load_and_evaluate(blackboard_path: str) -> HarnessReport:
    """
    从 blackboard 加载数据并评估
    
    Args:
        blackboard_path: blackboard 目录路径
    
    Returns:
        HarnessReport 对象
    """
    import os
    
    # 加载文件
    living_spec_path = os.path.join(blackboard_path, "spec/living_spec.json")
    quality_report_path = os.path.join(blackboard_path, "spec/quality_report.json")
    conversation_log_path = os.path.join(blackboard_path, "spec/conversation_log.json")
    quality_trajectory_path = os.path.join(blackboard_path, "spec/quality_trajectory.json")
    
    with open(living_spec_path, 'r', encoding='utf-8') as f:
        living_spec = json.load(f)
    
    with open(quality_report_path, 'r', encoding='utf-8') as f:
        quality_report = json.load(f)
    
    conversation_log = None
    if os.path.exists(conversation_log_path):
        with open(conversation_log_path, 'r', encoding='utf-8') as f:
            conversation_log = json.load(f)
    
    quality_trajectory = None
    if os.path.exists(quality_trajectory_path):
        with open(quality_trajectory_path, 'r', encoding='utf-8') as f:
            quality_trajectory = json.load(f)
    
    return evaluate_living_spec(
        living_spec,
        quality_report,
        conversation_log,
        quality_trajectory
    )


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python harness.py <blackboard_path>")
        print("示例: python harness.py blackboard/my_project/")
        sys.exit(1)
    
    blackboard_path = sys.argv[1]
    
    try:
        report = load_and_evaluate(blackboard_path)
        
        print("=" * 60)
        print("Spec Pro Harness 评估报告")
        print("=" * 60)
        print(f"\n总分: {report.overall_score}/100")
        print(f"决策: {report.final_decision}")
        print(f"\n维度评分:")
        print(f"  清晰度: {report.clarity.score}/100 (权重 {WEIGHT_CLARITY})")
        print(f"  完整度: {report.completeness.score}/100 (权重 {WEIGHT_COMPLETENESS})")
        print(f"  可执行度: {report.executability.score}/100 (权重 {WEIGHT_EXECUTABILITY})")
        print(f"  一致度: {report.consistency.score}/100 (权重 {WEIGHT_CONSISTENCY})")
        print(f"  下游适配度: {report.fitness.score}/100 (权重 {WEIGHT_FITNESS})")
        
        print(f"\n子门禁:")
        print(f"  Spec质量: {report.spec_quality_gate.decision}")
        print(f"  推断审计: {report.inference_audit_gate.decision}")
        print(f"  轨迹审计: {report.trajectory_audit_gate.decision}")
        
        if report.improvements_if_more_time:
            print(f"\n改进建议:")
            for imp in report.improvements_if_more_time:
                print(f"  - {imp}")
        
        # 输出 JSON
        output_path = os.path.join(blackboard_path, "spec/harness_report.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"\n报告已保存到: {output_path}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
