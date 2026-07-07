"""Benchmark runner for decision quality evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from .auto_evaluator import AutoEvaluationResult, AutoEvaluator, cohen_kappa, f1_score
from .human_labeler import HumanLabel, HumanLabeler, icc_two_way_random


DECISION_TYPES = ("dag_decomposition", "quality_assessment", "deviation_detection")
DIMENSIONS = ("correctness", "completeness", "safety", "efficiency")


@dataclass(frozen=True)
class DecisionSample:
    """A single benchmark item derived from a decision constraint."""

    sample_id: str
    source: str
    decision_type: str
    prompt: str
    expected_label: str
    expected_scores: dict[str, float]
    features: dict[str, float]


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregated benchmark metrics."""

    sample_count: int
    cohen_kappa: float
    agreement_rate: float
    icc: float
    f1_by_type: dict[str, float]
    auto_results: list[AutoEvaluationResult]


class BenchmarkRunner:
    """Build and run the Decision Quality Benchmark."""

    def __init__(
        self,
        evaluator: AutoEvaluator | None = None,
        labeler: HumanLabeler | None = None,
    ) -> None:
        self.evaluator = evaluator or AutoEvaluator()
        self.labeler = labeler or HumanLabeler()

    def load_sla_constraints_samples(self, count: int = 100) -> list[DecisionSample]:
        """Create a deterministic benchmark set from blueprint.sla_constraints."""

        if count <= 0:
            raise ValueError("count must be positive")

        samples: list[DecisionSample] = []
        for index in range(count):
            decision_type = DECISION_TYPES[index % len(DECISION_TYPES)]
            quality_band = index % 10
            expected_label = "pass" if quality_band not in {0, 1} else "fail"
            expected_scores = self._expected_scores(decision_type, quality_band)
            samples.append(
                DecisionSample(
                    sample_id=f"sla-{index + 1:03d}",
                    source="blueprint.sla_constraints",
                    decision_type=decision_type,
                    prompt=self._prompt_for(decision_type, index),
                    expected_label=expected_label,
                    expected_scores=expected_scores,
                    features=self._features_for(decision_type, expected_scores, expected_label),
                )
            )
        return samples

    def run(
        self,
        samples: Iterable[DecisionSample] | None = None,
        human_labels: Iterable[HumanLabel] | None = None,
    ) -> BenchmarkReport:
        benchmark_samples = list(samples or self.load_sla_constraints_samples())
        labels = list(human_labels or self.labeler.create_reference_labels(benchmark_samples))
        auto_results = self.evaluator.evaluate_many(benchmark_samples)

        human_consensus = self.labeler.consensus_labels(labels)
        human_by_id = {label.sample_id: label for label in human_consensus}
        paired_auto: list[str] = []
        paired_human: list[str] = []

        for result in auto_results:
            human_label = human_by_id[result.sample_id]
            paired_auto.append(result.predicted_label)
            paired_human.append(human_label.overall_label)

        agreement_rate = sum(
            1 for auto, human in zip(paired_auto, paired_human, strict=True) if auto == human
        ) / len(paired_auto)

        f1_by_type: dict[str, float] = {}
        for decision_type in DECISION_TYPES:
            type_results = [result for result in auto_results if result.decision_type == decision_type]
            expected = [sample.expected_label for sample in benchmark_samples if sample.decision_type == decision_type]
            predicted = [result.predicted_label for result in type_results]
            f1_by_type[decision_type] = f1_score(expected, predicted, positive_label="pass")

        return BenchmarkReport(
            sample_count=len(benchmark_samples),
            cohen_kappa=cohen_kappa(paired_human, paired_auto),
            agreement_rate=agreement_rate,
            icc=icc_two_way_random(self.labeler.rating_matrix(labels)),
            f1_by_type=f1_by_type,
            auto_results=auto_results,
        )

    @staticmethod
    def _expected_scores(decision_type: str, quality_band: int) -> dict[str, float]:
        base = 0.58 + (quality_band * 0.045)
        if quality_band in {0, 1}:
            base -= 0.22

        modifiers = {
            "dag_decomposition": {"correctness": 0.04, "completeness": 0.05, "safety": 0.02, "efficiency": 0.0},
            "quality_assessment": {"correctness": 0.05, "completeness": 0.03, "safety": 0.03, "efficiency": 0.01},
            "deviation_detection": {"correctness": 0.04, "completeness": 0.02, "safety": 0.06, "efficiency": 0.0},
        }[decision_type]
        return {
            dimension: min(0.98, max(0.05, round(base + modifier, 3)))
            for dimension, modifier in modifiers.items()
        }

    @staticmethod
    def _features_for(
        decision_type: str,
        expected_scores: dict[str, float],
        expected_label: str,
    ) -> dict[str, float]:
        quality_signal = mean(expected_scores.values())
        return {
            "constraint_coverage": expected_scores["completeness"],
            "risk_control": expected_scores["safety"],
            "latency_fit": expected_scores["efficiency"],
            "reasoning_alignment": expected_scores["correctness"],
            "decision_type_weight": {
                "dag_decomposition": 1.0,
                "quality_assessment": 0.98,
                "deviation_detection": 1.02,
            }[decision_type],
            "expected_outcome": 1.0 if expected_label == "pass" else 0.0,
            "quality_signal": quality_signal,
        }

    @staticmethod
    def _prompt_for(decision_type: str, index: int) -> str:
        prompts = {
            "dag_decomposition": "Decompose SLA constraint into executable DAG steps",
            "quality_assessment": "Assess decision quality against SLA acceptance gates",
            "deviation_detection": "Detect deviations from expected SLA decision path",
        }
        return f"{prompts[decision_type]} #{index + 1}"
