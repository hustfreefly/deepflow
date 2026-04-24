"""QualityGate - 4维质量评估与门控判断模块.

职责:
- 4维质量评估(accuracy/completeness/depth/elegance)
- 加权计算总分
- 门控判断(PASS/HITL/REJECT)
- 收敛检测
- HITL自动触发
"""



import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.observability import Observability


logger = Observability.get_logger("quality_gate")


class GateDecision(str, Enum):
    """门控决策结果."""
    PASS = "PASS"
    HITL = "HITL"
    REJECT = "REJECT"


@dataclass
class ConvergenceResult:
    """收敛检测结果."""
    converged: bool
    variance: Optional[float]
    reason: str


@dataclass
class QualityReport:
    """质量评估报告."""
    overall_score: float
    dimensions: Dict[str, float]
    decision: GateDecision
    reasoning: str
    timestamp: float = field(default_factory=lambda: __import__('time').time())

    @property
    def all_passed(self) -> bool:
        """检查所有维度是否都达标(>=0.6)."""
        return all(s >= 0.6 for s in self.dimensions.values())

    @property
    def failed_dimensions(self) -> List[str]:
        """返回未达标的维度列表."""
        return [name for name, score in self.dimensions.items() if score < 0.6]


class QualityGate:
    """质量门控 - 4维评估与门控判断."""

    DEFAULT_WEIGHTS = {
        "accuracy": 0.4,
        "completeness": 0.3,
        "depth": 0.2,
        "elegance": 0.1,
    }

    DEFAULT_THRESHOLDS = {
        "auto_pass": 0.85,
        "hitl": 0.70,
        "dimension": 0.60,
    }

    # 预编译正则
    _RE_PERCENT = re.compile(r"\d+(?:\.\d+)?%?")
    _RE_HEADINGS = re.compile(r"^(?:#{1,6}\s|第[一二三四五六七八九十]+[章节部分])", re.MULTILINE)
    _RE_BULLETS = re.compile(r"^[•\-\*\d+\.]\s", re.MULTILINE)
    _RE_BLANK_LINES = re.compile(r"\n\s*\n")
    _RE_CODE_BLOCK = re.compile(r"```(?:\w*)\n(.*?)```", re.DOTALL)
    _RE_TABLE_ROW = re.compile(r"\|.*\|")

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化质量门控.

        Args:
            config: 配置字典,包含weights/thresholds等

        Raises:
            ValueError: 配置格式错误
        """
        self._config = config or {}
        self._weights = self._config.get("weights", self.DEFAULT_WEIGHTS.copy())
        self._thresholds = self._config.get("thresholds", self.DEFAULT_THRESHOLDS.copy())
        self._score_history: List[float] = []
        self._validate_config()

    def _validate_config(self) -> None:
        """验证配置合法性."""
        if abs(sum(self._weights.values()) - 1.0) > 0.01:
            raise ValueError(f"权重和必须约等于1.0,当前:{sum(self._weights.values())}")
        for dim in self._weights.keys():
            if dim not in ["accuracy", "completeness", "depth", "elegance"]:
                raise ValueError(f"无效维度:{dim}")

    def evaluate(self, content: str, dimensions: Optional[List[str]] = None) -> QualityReport:
        """执行4维质量评估.

        Args:
            content: 待评估内容(Markdown格式)
            dimensions: 指定评估维度,None则评估全部4维

        Returns:
            QualityReport: 质量报告

        Raises:
            ValueError: 内容为空或维度无效
        """
        if not content or not content.strip():
            raise ValueError("内容不能为空")

        dims_to_eval = dimensions or list(self._weights.keys())
        for dim in dims_to_eval:
            if dim not in self._weights:
                raise ValueError(f"无效维度:{dim}")

        dim_scores: Dict[str, float] = {}
        for dim in dims_to_eval:
            score = self._evaluate_dimension(dim, content)
            dim_scores[dim] = score

        # 计算加权总分(未评估维度权重平均分配给已评估维度)
        evaluated_weight_sum = sum(self._weights[d] for d in dims_to_eval)
        if evaluated_weight_sum == 0:
            overall = 0.0
        else:
            overall = sum(dim_scores[d] * (self._weights[d] / evaluated_weight_sum) for d in dims_to_eval)

        decision = self._compute_decision(overall, dim_scores)
        reasoning = self._build_reasoning(overall, dim_scores, decision)

        report = QualityReport(
            overall_score=round(overall, 4),
            dimensions=dim_scores,
            decision=decision,
            reasoning=reasoning,
        )

        self._score_history.append(overall)
        Observability.record_quality_score(overall, "overall")
        for dim_name, dim_score in dim_scores.items():
            Observability.record_quality_score(dim_score, dim_name)
        return report

    def _evaluate_dimension(self, dimension: str, content: str) -> float:
        """单维度评分(0-1范围)."""
        stripped = content.strip()
        length = len(stripped)
        lines = stripped.count("\n") + 1
        words = len(stripped.split())

        if dimension == "accuracy":
            return self._score_accuracy(stripped, length, lines, words)
        elif dimension == "completeness":
            return self._score_completeness(stripped, length, lines, words)
        elif dimension == "depth":
            return self._score_depth(stripped, length, lines, words)
        elif dimension == "elegance":
            return self._score_elegance(stripped, length, lines, words)
        return 0.5

    def _score_accuracy(self, output: str, length: int, lines: int, words: int) -> float:
        """准确度评分."""
        score = 0.5
        lower = output.lower()

        if any(kw in lower for kw in ("结论", "总结", "therefore", "综上所述")):
            score += 0.15
        if self._RE_PERCENT.search(output):
            score += 0.10
        if any(kw in lower for kw in ("来源", "参考", "according to", "根据")):
            score += 0.10

        if length < 50:
            score -= 0.30
        elif length > 10000:
            score -= 0.05

        return max(0.0, min(1.0, round(score, 4)))

    def _score_completeness(self, output: str, length: int, lines: int, words: int) -> float:
        """完整度评分."""
        score = 0.4

        score += min(lines * 0.02, 0.25)

        headings = len(self._RE_HEADINGS.findall(output))
        score += min(headings * 0.05, 0.20)

        bullets = len(self._RE_BULLETS.findall(output))
        score += min(bullets * 0.015, 0.15)

        return max(0.0, min(1.0, round(score, 4)))

    def _score_depth(self, output: str, length: int, lines: int, words: int) -> float:
        """深度评分."""
        score = 0.45
        lower = output.lower()

        if any(kw in lower for kw in ("原因", "根因", "root cause", "due to")):
            score += 0.15
        if any(kw in lower for kw in ("对比", "权衡", "vs", "pros and cons")):
            score += 0.15
        if any(kw in lower for kw in ("建议", "改进", "recommend", "优化")):
            score += 0.15
        if any(kw in lower for kw in ("风险", "局限", "risk", "limitation")):
            score += 0.10

        return max(0.0, min(1.0, round(score, 4)))

    def _score_elegance(self, output: str, length: int, lines: int, words: int) -> float:
        """优雅度评分."""
        score = 0.55

        blank_ratio = len(self._RE_BLANK_LINES.findall(output)) / max(lines, 1)
        if blank_ratio > 0.3:
            score -= 0.15
        elif blank_ratio > 0.15:
            score -= 0.05

        code_blocks = self._RE_CODE_BLOCK.findall(output)
        if code_blocks:
            non_empty = sum(1 for block in code_blocks if block.strip())
            score += min(non_empty * 0.10, 0.10)

        table_rows = self._RE_TABLE_ROW.findall(output)
        if len(table_rows) >= 3:
            score += 0.10
        elif "|" in output and "---" in output:
            score += 0.05

        max_line_len = max((len(line) for line in output.split("\n")), default=0)
        if max_line_len > 200:
            score -= 0.10

        return max(0.0, min(1.0, round(score, 4)))

    def evaluate_4d(self, accuracy: float, completeness: float, depth: float, elegance: float) -> float:
        """计算4维加权总分.

        Args:
            accuracy: 准确性得分(0-1)
            completeness: 完整性得分(0-1)
            depth: 深度得分(0-1)
            elegance: 优雅度得分(0-1)

        Returns:
            float: 加权总分(0-1)

        Note:
            超出0-1范围的输入会被自动裁剪并记录
        """
        scores = {
            "accuracy": max(0.0, min(1.0, accuracy)),
            "completeness": max(0.0, min(1.0, completeness)),
            "depth": max(0.0, min(1.0, depth)),
            "elegance": max(0.0, min(1.0, elegance)),
        }

        # 检查是否有裁剪
        for name, value in [("accuracy", accuracy), ("completeness", completeness),
                           ("depth", depth), ("elegance", elegance)]:
            if value < 0.0 or value > 1.0:
                logger.warning("score_clamped", dimension=name, original=value, clamped=scores[name])

        total = sum(scores[d] * self._weights[d] for d in scores)
        return round(total, 4)

    def gate_decision(self, score: float, threshold: float = 0.85) -> GateDecision:
        """门控决策判断.

        Args:
            score: 总分(0-1或0-100)
            threshold: 通过阈值,默认0.85

        Returns:
            GateDecision: PASS/HITL/REJECT
        """
        # 自动检测0-100范围并转换
        if score > 1.0:
            score = score / 100.0

        hitl_threshold = self._thresholds.get("hitl", 0.70)

        if score >= threshold:
            return GateDecision.PASS
        elif score >= hitl_threshold:
            return GateDecision.HITL
        return GateDecision.REJECT

    def check_convergence(self, scores: List[float], window: int = 3, threshold: float = 0.02) -> ConvergenceResult:
        """收敛检测.

        Args:
            scores: 历史得分列表
            window: 收敛窗口大小
            threshold: 收敛阈值(方差小于此值视为收敛)

        Returns:
            ConvergenceResult: 收敛状态和方差

        Raises:
            ValueError: window <= 0
        """
        if window <= 0:
            raise ValueError("window必须大于0")

        if len(scores) < window:
            return ConvergenceResult(converged=False, variance=None, reason="历史数据不足")

        recent = scores[-window:]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)

        converged = variance < threshold
        reason = f"方差{variance:.4f}{'<' if converged else '>='}阈值{threshold}"

        return ConvergenceResult(converged=converged, variance=round(variance, 4), reason=reason)

    def hitl_trigger(self, score: float, human_threshold: float = 0.70) -> bool:
        """判断是否触发人工介入.

        Args:
            score: 当前得分
            human_threshold: 人工介入阈值

        Returns:
            bool: score < human_threshold时返回True
        """
        if score > 1.0:
            score = score / 100.0
        return score < human_threshold

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置副本."""
        return {
            "weights": self._weights.copy(),
            "thresholds": self._thresholds.copy(),
        }

    def reset_history(self) -> None:
        """清空历史得分记录."""
        self._score_history.clear()

    def _compute_decision(self, overall_score: float, dimensions: Dict[str, float]) -> GateDecision:
        """内部:计算门控决策."""
        auto_pass = self._thresholds.get("auto_pass", 0.85)
        hitl_threshold = self._thresholds.get("hitl", 0.70)
        dim_threshold = self._thresholds.get("dimension", 0.60)

        all_passed = all(s > dim_threshold for s in dimensions.values())

        if all_passed and overall_score >= auto_pass:
            return GateDecision.PASS
        elif overall_score >= hitl_threshold:
            return GateDecision.HITL
        return GateDecision.REJECT

    def _build_reasoning(self, overall: float, dimensions: Dict[str, float], decision: GateDecision) -> str:
        """内部:构建决策理由."""
        parts = [f"总分:{overall:.2f}"]
        for name, score in dimensions.items():
            status = "✓" if score > 0.6 else "✗"
            parts.append(f"{status}{name}:{score:.2f}")

        if decision == GateDecision.PASS:
            parts.append("→PASS:全部达标")
        elif decision == GateDecision.HITL:
            failed = [n for n, s in dimensions.items() if s <= 0.6]
            parts.append(f"→HITL:需人工确认[{','.join(failed)}]")
        else:
            parts.append("→REJECT:低于阈值")

        return "|".join(parts)
