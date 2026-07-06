"""
DeepFlow Quality Judge — 独立 LLM 质量评分框架

设计意图：在关键输出点（Solution Pro 方案文档、Ship Pro 交付包）
调用独立 Judge Agent 进行语义级质量评估，与生成 Agent 隔离。

架构：
  生成 Agent（运动员）→ 产出 deliverable
  QualityJudge（裁判）→ 独立评估 deliverable
  Gate 合并 L1 结构验证 + L2 语义评分 → PASS/FAIL

约束：
  - Judge prompt 必须包含评分维度 + 评分标准 + 输出格式
  - Judge 不能访问生成 Agent 的内部状态（只看输出）
  - 评分结果必须结构化（JSON），不能是自由文本
"""
import json
import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class QualityDimension:
    """评分维度

    每个维度代表质量评估的一个独立角度，带权重和评分标准说明。
    权重用于计算加权综合分。
    """
    name: str           # 维度名，如 "completeness"
    weight: float = 1.0 # 权重（越大越重要）
    description: str = ""  # 评分标准说明（给 Judge 看的）


@dataclass
class QualityVerdict:
    """质量评分结果

    由 Judge Agent 产出，包含综合分、各维度分、优缺点列表和最终建议。
    Gate 层根据 recommendation 决定是否通过。
    """
    overall_score: float        # 0-10 综合分
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendation: str = ""    # PASS / CONDITIONAL / FAIL
    raw_response: str = ""      # Judge 原始回复（用于调试/追溯）

    @property
    def passed(self) -> bool:
        """是否通过（PASS 或 CONDITIONAL 都算通过）"""
        return self.recommendation in ("PASS", "CONDITIONAL")


class QualityJudge:
    """
    独立 LLM 质量评估器

    设计原则：
    1. 运动员-裁判分离：Judge 只看交付物，不接触生成过程
    2. spawn_fn 注入：不硬编码 sessions_spawn，由调用方提供
    3. 降级模式：spawn_fn 为 None 时使用启发式评估（保证可用性）
    4. 结构化输出：强制 JSON 格式，避免自由文本解析困难

    用法：
        judge = QualityJudge(dimensions=[
            QualityDimension("completeness", weight=2.0, description="是否覆盖所有需求"),
            QualityDimension("clarity", weight=1.0, description="表述是否清晰"),
        ])
        verdict = judge.evaluate(
            deliverable="方案文档内容...",
            context="用户需求: ...",
            spawn_fn=sessions_spawn,  # 由调用方注入
        )
    """

    def __init__(self, dimensions: List[QualityDimension], min_pass_score: float = 6.0):
        """
        Args:
            dimensions: 评分维度列表
            min_pass_score: 最低通过分（低于此分 recommendation 为 CONDITIONAL/FAIL）
        """
        self.dimensions = dimensions
        self.min_pass_score = min_pass_score

    def build_judge_prompt(self, deliverable: str, context: str = "") -> str:
        """构建 Judge Agent 的评估 prompt

        设计意图：
        - 明确角色（独立裁判）
        - 限定评估范围（只看交付物本身）
        - 强制结构化输出（JSON 格式）
        - 提供清晰评分标准（8-10/6-7/4-5/0-3）

        Args:
            deliverable: 待评估的交付物内容
            context: 背景上下文（可选，帮助 Judge 理解需求）

        Returns:
            完整的 Judge prompt 字符串
        """
        dims_text = "\n".join(
            f"- **{d.name}** (权重 {d.weight}): {d.description}"
            for d in self.dimensions
        )
        return f"""你是独立质量评审专家。请评估以下交付物的质量。

## 交付物
{deliverable[:8000]}

## 背景上下文
{context[:2000] if context else "无额外上下文"}

## 评分维度
{dims_text}

## 输出要求（JSON 格式，严格遵守）
```json
{{
    "overall_score": 0-10 的综合分,
    "dimension_scores": {{"维度名": 分数, ...}},
    "strengths": ["优点1", "优点2"],
    "weaknesses": ["不足1", "不足2"],
    "recommendation": "PASS 或 CONDITIONAL 或 FAIL"
}}
```

评分标准：
- 8-10: 优秀，直接使用
- 6-7: 合格，可能有小问题但不阻塞
- 4-5: 有条件通过，需要修订
- 0-3: 不合格，需要重做

注意：你是独立裁判，只看交付物本身，不要参考生成过程。"""

    def evaluate(
        self,
        deliverable: str,
        context: str = "",
        spawn_fn: Optional[Callable] = None,
    ) -> QualityVerdict:
        """
        执行质量评估

        流程：
        1. 如果有 spawn_fn → 调用独立 Judge Agent（完整 LLM 评估）
        2. 如果无 spawn_fn → 降级为启发式评估（基于长度的粗略评分）
        3. 如果 LLM 调用失败 → 降级为启发式评估（容错）

        Args:
            deliverable: 待评估的交付物内容
            context: 背景上下文
            spawn_fn: Agent spawn 函数（由调用方注入）
                      签名: spawn_fn(task: str, mode: str, label: str) -> Any

        Returns:
            QualityVerdict 评分结果
        """
        if spawn_fn is None:
            # 降级模式：基于长度的启发式评估
            logger.warning("无 spawn_fn，使用启发式降级评估")
            return self._heuristic_evaluate(deliverable)

        prompt = self.build_judge_prompt(deliverable, context)

        try:
            result = spawn_fn(
                task=prompt,
                mode="run",
                label="quality-judge",
            )
            # 解析 Judge 返回的 JSON
            verdict = self._parse_verdict(result)
            return verdict
        except Exception as e:
            logger.error(f"Judge 评估失败: {e}")
            return self._heuristic_evaluate(deliverable)

    def _extract_json_block(self, text: str) -> Optional[str]:
        """从文本中提取包含 overall_score 的 JSON 块

        使用括号计数法，支持嵌套 {} 和 []。
        找到包含 "overall_score" 的 { 起点，然后找匹配的 }。

        Args:
            text: 原始文本

        Returns:
            JSON 字符串，或 None
        """
        # 找到 "overall_score" 的位置
        idx = text.find('"overall_score"')
        if idx == -1:
            return None

        # 向左找最近的 {
        start = text.rfind('{', 0, idx)
        if start == -1:
            return None

        # 从 start 开始向右做括号计数，找匹配的 }
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

        return None

    def _parse_verdict(self, raw_result: Any) -> QualityVerdict:
        """解析 Judge 返回结果为 QualityVerdict

        解析策略：
        1. 尝试从文本中提取 JSON 块（正则匹配 overall_score 关键字）
        2. 解析成功 → 返回完整 QualityVerdict
        3. 解析失败 → 返回保守评估（CONDITIONAL + 警告）

        Args:
            raw_result: Judge Agent 的原始返回

        Returns:
            QualityVerdict
        """
        text = str(raw_result) if not isinstance(raw_result, str) else raw_result
        try:
            # 提取 JSON 块（支持嵌套 braces）
            # 策略：找到包含 overall_score 的 { 起点，然后用括号计数找匹配的 }
            json_str = self._extract_json_block(text)
            if json_str:
                data = json.loads(json_str)
                return QualityVerdict(
                    overall_score=float(data.get("overall_score", 5.0)),
                    dimension_scores=data.get("dimension_scores", {}),
                    strengths=data.get("strengths", []),
                    weaknesses=data.get("weaknesses", []),
                    recommendation=data.get("recommendation", "CONDITIONAL"),
                    raw_response=text,
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Judge JSON 解析失败: {e}")

        # 解析失败，返回保守评估
        return QualityVerdict(
            overall_score=5.0,
            recommendation="CONDITIONAL",
            raw_response=text,
            weaknesses=["Judge 输出解析失败，降级为 CONDITIONAL"],
        )

    def _heuristic_evaluate(self, deliverable: str) -> QualityVerdict:
        """启发式降级评估（无 LLM 时使用）

        设计意图：保证系统在无 LLM 时仍可运行（降级而非崩溃）。
        评分逻辑：按交付物长度粗略评分（500 字符 = 10 分）。
        这是最低限度的评估，实际使用时应尽量提供 spawn_fn。

        Args:
            deliverable: 待评估的交付物内容

        Returns:
            QualityVerdict（标注为启发式评估）
        """
        length = len(deliverable)
        # 粗略按长度评分：500 字符满分，最少 1 分
        score = min(10.0, max(1.0, length / 500))
        recommendation = "PASS" if score >= self.min_pass_score else "CONDITIONAL"
        return QualityVerdict(
            overall_score=round(score, 1),
            recommendation=recommendation,
            strengths=[f"交付物长度: {length} 字符"],
            weaknesses=["启发式评估（无 LLM Judge）", "仅基于长度，未做语义分析"],
        )


# ── 预设 Judge 配置 ──
# 为 DeepFlow 关键域提供开箱即用的 Judge 实例

def solution_quality_judge() -> QualityJudge:
    """Solution Pro 方案质量 Judge

    评估维度：
    - completeness (权重 2.0): 方案是否覆盖所有需求点
    - feasibility (权重 2.0): 技术方案是否可行
    - clarity (权重 1.0): 表述是否清晰，团队能否理解并执行
    - innovation (权重 0.5): 是否有创新性或最佳实践引用
    """
    return QualityJudge(dimensions=[
        QualityDimension("completeness", 2.0, "方案是否覆盖所有需求点"),
        QualityDimension("feasibility", 2.0, "技术方案是否可行"),
        QualityDimension("clarity", 1.0, "表述是否清晰，团队能否理解并执行"),
        QualityDimension("innovation", 0.5, "是否有创新性或最佳实践引用"),
    ])


def ship_package_quality_judge() -> QualityJudge:
    """Ship Pro 交付包质量 Judge

    评估维度：
    - completeness (权重 2.0): 工作包是否覆盖所有需求
    - actionability (权重 2.0): 每个 WP 是否可直接执行
    - dependency_correctness (权重 1.5): 依赖关系是否合理（无环、无遗漏）
    - effort_estimation (权重 1.0): 工时估算是否合理
    """
    return QualityJudge(dimensions=[
        QualityDimension("completeness", 2.0, "工作包是否覆盖所有需求"),
        QualityDimension("actionability", 2.0, "每个 WP 是否可直接执行"),
        QualityDimension("dependency_correctness", 1.5, "依赖关系是否合理（无环、无遗漏）"),
        QualityDimension("effort_estimation", 1.0, "工时估算是否合理"),
    ])
