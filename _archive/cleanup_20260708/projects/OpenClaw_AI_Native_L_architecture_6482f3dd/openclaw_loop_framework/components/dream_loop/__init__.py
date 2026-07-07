"""Dream Loop three-layer reflection validation protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from .l1_5_cross_validate import (
    CrossValidationResult,
    CrossValidator,
    FunctionVerifier,
    LessonVerifier,
)
from .l1_trajectory import L1ValidationResult, TrajectoryRecord, TrajectoryValidator
from .l2_effect_tracking import EffectTracker, EffectTrackingResult, LessonStatus


@dataclass(frozen=True)
class IdleState:
    rounds_without_new_nodes: int
    last_activity_at: datetime
    active_subagents: int


@dataclass(frozen=True)
class DreamLoopValidationResult:
    l1: L1ValidationResult
    l1_5: CrossValidationResult

    @property
    def status(self) -> str:
        return "verified" if self.l1.status == "verified" and self.l1_5.status == "verified" else "unverified"


class DreamLoopValidator:
    """Coordinates L1 trajectory validation, L1.5 consensus, and idle triggering."""

    def __init__(
        self,
        trajectory_validator: TrajectoryValidator | None = None,
        cross_validator: CrossValidator | None = None,
    ) -> None:
        self.trajectory_validator = trajectory_validator or TrajectoryValidator()
        self.cross_validator = cross_validator or CrossValidator()

    def validate_lesson(
        self,
        lesson: str,
        trajectories: Sequence[TrajectoryRecord],
        verifiers: Sequence[LessonVerifier],
    ) -> DreamLoopValidationResult:
        l1 = self.trajectory_validator.validate(lesson, trajectories)
        l1_5 = self.cross_validator.validate(lesson, verifiers) if l1.status == "verified" else CrossValidationResult(
            lesson=lesson,
            status="unverified",
            agreement_ratio=0.0,
            votes=(),
        )
        return DreamLoopValidationResult(l1=l1, l1_5=l1_5)

    def should_trigger_reflection(
        self,
        idle_state: IdleState,
        now: datetime,
        required_idle_rounds: int = 3,
        required_inactivity: timedelta = timedelta(minutes=15),
    ) -> bool:
        return (
            idle_state.rounds_without_new_nodes >= required_idle_rounds
            and now - idle_state.last_activity_at >= required_inactivity
            and idle_state.active_subagents == 0
        )

    def trigger_reflection_if_idle(self, idle_state: IdleState, now: datetime) -> bool:
        return self.should_trigger_reflection(idle_state=idle_state, now=now)


__all__ = [
    "CrossValidationResult",
    "CrossValidator",
    "DreamLoopValidationResult",
    "DreamLoopValidator",
    "EffectTracker",
    "EffectTrackingResult",
    "FunctionVerifier",
    "IdleState",
    "L1ValidationResult",
    "LessonStatus",
    "LessonVerifier",
    "TrajectoryRecord",
    "TrajectoryValidator",
]
