"""L2 applied-effect tracking for Dream Loop lessons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LessonStatus = Literal["verified", "contested", "unverified"]


@dataclass
class LessonState:
    lesson_id: str
    lesson: str
    status: LessonStatus
    baseline_success_rate: float


@dataclass(frozen=True)
class ApplicationRecord:
    lesson_id: str
    task_id: str
    success: bool


@dataclass(frozen=True)
class EffectTrackingResult:
    lesson_id: str
    status: LessonStatus
    baseline_success_rate: float
    current_success_rate: float
    success_rate_delta: float
    applications: int


class EffectTracker:
    """Tracks whether verified lessons improve later task outcomes."""

    def __init__(self, contest_drop_threshold: float = 0.10) -> None:
        self.contest_drop_threshold = contest_drop_threshold
        self._lessons: dict[str, LessonState] = {}
        self._applications: list[ApplicationRecord] = []

    def register_lesson(
        self,
        lesson_id: str,
        lesson: str,
        status: LessonStatus,
        baseline_success_rate: float,
    ) -> None:
        if not 0.0 <= baseline_success_rate <= 1.0:
            raise ValueError("baseline_success_rate must be between 0 and 1")
        self._lessons[lesson_id] = LessonState(
            lesson_id=lesson_id,
            lesson=lesson,
            status=status,
            baseline_success_rate=baseline_success_rate,
        )

    def record_application(self, lesson_id: str, task_id: str, success: bool) -> None:
        if lesson_id not in self._lessons:
            raise KeyError(f"unknown lesson_id: {lesson_id}")
        self._applications.append(
            ApplicationRecord(lesson_id=lesson_id, task_id=task_id, success=success)
        )

    def evaluate(self, lesson_id: str) -> EffectTrackingResult:
        lesson = self._lessons[lesson_id]
        applications = [
            application
            for application in self._applications
            if application.lesson_id == lesson_id
        ]

        if applications:
            current_rate = sum(1 for application in applications if application.success) / len(
                applications
            )
        else:
            current_rate = lesson.baseline_success_rate

        delta = current_rate - lesson.baseline_success_rate
        if lesson.status == "verified" and delta < -self.contest_drop_threshold:
            lesson.status = "contested"

        return EffectTrackingResult(
            lesson_id=lesson_id,
            status=lesson.status,
            baseline_success_rate=lesson.baseline_success_rate,
            current_success_rate=current_rate,
            success_rate_delta=delta,
            applications=len(applications),
        )
