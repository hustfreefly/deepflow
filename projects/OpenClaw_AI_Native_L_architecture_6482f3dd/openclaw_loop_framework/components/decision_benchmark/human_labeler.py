"""Human labeling primitives and agreement metrics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Iterable, Sequence


DIMENSIONS = ("correctness", "completeness", "safety", "efficiency")


@dataclass(frozen=True)
class HumanLabel:
    """A multi-dimensional human decision label."""

    sample_id: str
    annotator_id: str
    scores: dict[str, float]
    overall_label: str

    @property
    def average_score(self) -> float:
        return mean(self.scores[dimension] for dimension in DIMENSIONS)


class HumanLabeler:
    """Creates and aggregates human labels for benchmark decisions."""

    def create_label(
        self,
        sample_id: str,
        annotator_id: str,
        scores: dict[str, float],
        threshold: float = 0.70,
    ) -> HumanLabel:
        self._validate_scores(scores)
        overall = "pass" if mean(scores.values()) >= threshold else "fail"
        return HumanLabel(sample_id=sample_id, annotator_id=annotator_id, scores=dict(scores), overall_label=overall)

    def create_reference_labels(self, samples: Iterable[object], annotators: int = 3) -> list[HumanLabel]:
        """Generate stable reference labels that model expert annotations."""

        labels: list[HumanLabel] = []
        for sample in samples:
            for annotator_index in range(annotators):
                scores = {
                    dimension: self._annotator_adjustment(score, annotator_index)
                    for dimension, score in sample.expected_scores.items()
                }
                labels.append(
                    self.create_label(
                        sample_id=sample.sample_id,
                        annotator_id=f"expert-{annotator_index + 1}",
                        scores=scores,
                    )
                )
        return labels

    def consensus_labels(self, labels: Iterable[HumanLabel]) -> list[HumanLabel]:
        grouped: dict[str, list[HumanLabel]] = defaultdict(list)
        for label in labels:
            grouped[label.sample_id].append(label)

        consensus: list[HumanLabel] = []
        for sample_id, sample_labels in sorted(grouped.items()):
            scores = {
                dimension: mean(label.scores[dimension] for label in sample_labels)
                for dimension in DIMENSIONS
            }
            consensus.append(
                self.create_label(
                    sample_id=sample_id,
                    annotator_id="consensus",
                    scores=scores,
                )
            )
        return consensus

    def rating_matrix(self, labels: Iterable[HumanLabel]) -> list[list[float]]:
        grouped: dict[str, dict[str, float]] = defaultdict(dict)
        annotators: set[str] = set()
        for label in labels:
            grouped[label.sample_id][label.annotator_id] = label.average_score
            annotators.add(label.annotator_id)

        ordered_annotators = sorted(annotators)
        matrix: list[list[float]] = []
        for sample_id in sorted(grouped):
            ratings = grouped[sample_id]
            if set(ratings) != set(ordered_annotators):
                raise ValueError(f"sample {sample_id} does not have a balanced annotator set")
            matrix.append([ratings[annotator] for annotator in ordered_annotators])
        return matrix

    @staticmethod
    def _annotator_adjustment(score: float, annotator_index: int) -> float:
        offsets = (-0.015, 0.0, 0.015)
        return min(1.0, max(0.0, round(score + offsets[annotator_index % len(offsets)], 3)))

    @staticmethod
    def _validate_scores(scores: dict[str, float]) -> None:
        missing = set(DIMENSIONS) - set(scores)
        extra = set(scores) - set(DIMENSIONS)
        if missing or extra:
            raise ValueError(f"scores must contain dimensions {DIMENSIONS}")
        for dimension, score in scores.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"{dimension} score must be between 0 and 1")


def icc_two_way_random(rating_matrix: Sequence[Sequence[float]]) -> float:
    """Compute ICC(2,1) for a balanced subject-by-rater matrix."""

    if not rating_matrix:
        raise ValueError("rating_matrix must not be empty")
    subject_count = len(rating_matrix)
    rater_count = len(rating_matrix[0])
    if subject_count < 2 or rater_count < 2:
        raise ValueError("ICC requires at least two subjects and two raters")
    if any(len(row) != rater_count for row in rating_matrix):
        raise ValueError("rating_matrix must be balanced")

    row_means = [mean(row) for row in rating_matrix]
    column_means = [mean(row[column] for row in rating_matrix) for column in range(rater_count)]
    grand_mean = mean(row_means)

    ss_subject = rater_count * sum((row_mean - grand_mean) ** 2 for row_mean in row_means)
    ss_rater = subject_count * sum((column_mean - grand_mean) ** 2 for column_mean in column_means)
    ss_total = sum((score - grand_mean) ** 2 for row in rating_matrix for score in row)
    ss_error = ss_total - ss_subject - ss_rater

    ms_subject = ss_subject / (subject_count - 1)
    ms_rater = ss_rater / (rater_count - 1)
    ms_error = ss_error / ((subject_count - 1) * (rater_count - 1))

    denominator = ms_subject + (rater_count - 1) * ms_error + (rater_count * (ms_rater - ms_error) / subject_count)
    if denominator == 0:
        return 1.0
    return max(-1.0, min(1.0, (ms_subject - ms_error) / denominator))
