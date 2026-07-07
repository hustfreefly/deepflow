"""L1.5 independent cross-validation for Dream Loop lessons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence, Literal


CrossValidationStatus = Literal["verified", "unverified"]


class LessonVerifier(Protocol):
    name: str

    def validate(self, lesson: str) -> bool:
        """Return whether this independent verifier accepts the lesson."""


@dataclass(frozen=True)
class FunctionVerifier:
    name: str
    validator: Callable[[str], bool]

    def validate(self, lesson: str) -> bool:
        return self.validator(lesson)


@dataclass(frozen=True)
class CrossValidationVote:
    verifier_name: str
    accepted: bool


@dataclass(frozen=True)
class CrossValidationResult:
    lesson: str
    status: CrossValidationStatus
    agreement_ratio: float
    votes: tuple[CrossValidationVote, ...]


class CrossValidator:
    """Requires independent verifier consensus before accepting a lesson."""

    def __init__(self, required_consistency: float = 0.6) -> None:
        self.required_consistency = required_consistency

    def validate(
        self, lesson: str, verifiers: Sequence[LessonVerifier]
    ) -> CrossValidationResult:
        if not verifiers:
            return CrossValidationResult(
                lesson=lesson,
                status="unverified",
                agreement_ratio=0.0,
                votes=(),
            )

        votes = tuple(
            CrossValidationVote(verifier_name=verifier.name, accepted=verifier.validate(lesson))
            for verifier in verifiers
        )
        accepted = sum(1 for vote in votes if vote.accepted)
        ratio = accepted / len(votes)
        status: CrossValidationStatus = (
            "verified" if accepted >= 2 and ratio > self.required_consistency else "unverified"
        )

        return CrossValidationResult(
            lesson=lesson,
            status=status,
            agreement_ratio=ratio,
            votes=votes,
        )
