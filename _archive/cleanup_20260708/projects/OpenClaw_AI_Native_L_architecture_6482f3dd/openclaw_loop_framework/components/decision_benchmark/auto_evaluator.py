"""Automated decision quality evaluation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import Iterable, Sequence


@dataclass(frozen=True)
class AutoEvaluationResult:
    """Evaluation output for a single decision sample."""

    sample_id: str
    decision_type: str
    dimension_scores: dict[str, float]
    quality_score: float
    predicted_label: str


class AutoEvaluator:
    """Scores decisions from structured benchmark features."""

    def __init__(self, threshold: float = 0.70) -> None:
        self.threshold = threshold

    def evaluate_many(self, samples: Iterable[object]) -> list[AutoEvaluationResult]:
        return [self.evaluate(sample) for sample in samples]

    def evaluate(self, sample: object) -> AutoEvaluationResult:
        dimension_scores = {
            "correctness": self._score_dimension(sample, "reasoning_alignment"),
            "completeness": self._score_dimension(sample, "constraint_coverage"),
            "safety": self._score_dimension(sample, "risk_control"),
            "efficiency": self._score_dimension(sample, "latency_fit"),
        }
        quality_score = mean(dimension_scores.values())
        predicted_label = "pass" if quality_score >= self.threshold else "fail"
        return AutoEvaluationResult(
            sample_id=sample.sample_id,
            decision_type=sample.decision_type,
            dimension_scores=dimension_scores,
            quality_score=quality_score,
            predicted_label=predicted_label,
        )

    @staticmethod
    def _score_dimension(sample: object, feature_name: str) -> float:
        raw_score = sample.features[feature_name] * sample.features["decision_type_weight"]
        return min(1.0, max(0.0, round(raw_score, 3)))


def cohen_kappa(expected: Sequence[str], observed: Sequence[str]) -> float:
    """Compute Cohen's kappa for categorical labels."""

    if len(expected) != len(observed):
        raise ValueError("expected and observed must have the same length")
    if not expected:
        raise ValueError("labels must not be empty")

    total = len(expected)
    observed_agreement = sum(1 for left, right in zip(expected, observed, strict=True) if left == right) / total
    expected_counts = Counter(expected)
    observed_counts = Counter(observed)
    chance_agreement = sum(
        (expected_counts[label] / total) * (observed_counts[label] / total)
        for label in set(expected_counts) | set(observed_counts)
    )
    if chance_agreement == 1.0:
        return 1.0
    return (observed_agreement - chance_agreement) / (1.0 - chance_agreement)


def f1_score(expected: Sequence[str], observed: Sequence[str], positive_label: str) -> float:
    """Compute binary F1 for the requested positive label."""

    if len(expected) != len(observed):
        raise ValueError("expected and observed must have the same length")
    true_positive = sum(
        1
        for left, right in zip(expected, observed, strict=True)
        if left == positive_label and right == positive_label
    )
    false_positive = sum(
        1
        for left, right in zip(expected, observed, strict=True)
        if left != positive_label and right == positive_label
    )
    false_negative = sum(
        1
        for left, right in zip(expected, observed, strict=True)
        if left == positive_label and right != positive_label
    )

    if true_positive == 0:
        return 0.0
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    return 2 * precision * recall / (precision + recall)
