"""L1 trajectory-linked validation for Dream Loop lessons."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Literal


ValidationStatus = Literal["verified", "unverified"]


@dataclass(frozen=True)
class TrajectoryRecord:
    """A concrete execution trace that can support or reject a lesson."""

    record_id: str
    prompt: str
    outcome: str
    success: bool
    action: str = ""
    evidence: str = ""


@dataclass(frozen=True)
class L1ValidationResult:
    lesson: str
    status: ValidationStatus
    matched_record_ids: tuple[str, ...]
    reason: str


class TrajectoryValidator:
    """Validates that a lesson can be traced to failed execution evidence."""

    _AVOID_PATTERNS = (
        re.compile(r"(?:should|must|需要|应该)\s+(?:avoid|避免)(?:\s+using)?\s+(.+?)(?:\s+method|方法|$)", re.I),
        re.compile(r"(?:avoid|避免)(?:\s+using)?\s+(.+?)(?:\s+method|方法|$)", re.I),
    )

    def validate(self, lesson: str, trajectories: Iterable[TrajectoryRecord]) -> L1ValidationResult:
        target = self._extract_target(lesson)
        if not target:
            return L1ValidationResult(
                lesson=lesson,
                status="unverified",
                matched_record_ids=(),
                reason="lesson does not state an avoidable method",
            )

        matched_ids: list[str] = []
        for record in trajectories:
            if record.success:
                continue
            if self._contains_target(record, target):
                matched_ids.append(record.record_id)

        if matched_ids:
            return L1ValidationResult(
                lesson=lesson,
                status="verified",
                matched_record_ids=tuple(matched_ids),
                reason=f"found failed trajectory evidence for {target!r}",
            )

        return L1ValidationResult(
            lesson=lesson,
            status="unverified",
            matched_record_ids=(),
            reason=f"no failed trajectory evidence found for {target!r}",
        )

    def _extract_target(self, lesson: str) -> str:
        for pattern in self._AVOID_PATTERNS:
            match = pattern.search(lesson)
            if match:
                return self._normalize(match.group(1))
        return ""

    def _contains_target(self, record: TrajectoryRecord, target: str) -> bool:
        haystack = self._normalize(
            " ".join((record.prompt, record.action, record.outcome, record.evidence))
        )
        return target in haystack

    @staticmethod
    def _normalize(value: str) -> str:
        value = re.sub(r"[\"'`.,;:!?，。；：！？]", " ", value.casefold())
        return re.sub(r"\s+", " ", value).strip()
