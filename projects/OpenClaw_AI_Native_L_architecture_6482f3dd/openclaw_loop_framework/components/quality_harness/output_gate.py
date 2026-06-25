"""Output-layer quality gate using an Evaluator-Optimizer split."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Evaluation:
    """Evaluator LLM quality assessment."""

    score: float
    rationale: str = ""


@dataclass(frozen=True)
class OutputGateResult:
    """Decision returned by the output gate."""

    accepted: bool
    score: float
    action: str
    retry_count: int
    rationale: str = ""

    @property
    def requires_retry(self) -> bool:
        return self.action == "retry"

    @property
    def escalate_to_human(self) -> bool:
        return self.action == "human_review"


Evaluator = Callable[[Mapping[str, Any]], Evaluation]


class OutputGate:
    """Evaluates final worker output and delegates rework decisions."""

    def __init__(
        self,
        evaluator: Evaluator,
        threshold: float = 0.6,
        max_retries: int = 3,
    ) -> None:
        self.evaluator = evaluator
        self.threshold = threshold
        self.max_retries = max_retries

    def check(
        self,
        worker_output: Mapping[str, Any],
        retry_count: int = 0,
    ) -> OutputGateResult:
        evaluation = self.evaluator(worker_output)
        accepted = evaluation.score >= self.threshold

        if accepted:
            action = "accept"
        elif retry_count < self.max_retries:
            action = "retry"
        else:
            action = "human_review"

        return OutputGateResult(
            accepted=accepted,
            score=evaluation.score,
            action=action,
            retry_count=retry_count,
            rationale=evaluation.rationale,
        )
