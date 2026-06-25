"""Complexity-aware thresholds for circuit breaker signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Complexity(StrEnum):
    """Supported task complexity levels."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass(frozen=True)
class AdaptiveThreshold:
    """Resolve signal thresholds based on task complexity."""

    repeat_thresholds: dict[Complexity, int] = field(
        default_factory=lambda: {
            Complexity.SIMPLE: 3,
            Complexity.MEDIUM: 5,
            Complexity.COMPLEX: 10,
        }
    )

    def repeat_threshold(self, complexity: Complexity | str) -> int:
        """Return the repeat threshold for a task complexity."""

        normalized = Complexity(complexity)
        return self.repeat_thresholds[normalized]
