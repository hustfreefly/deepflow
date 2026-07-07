"""Model tier routing for LLM requests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class TaskComplexity(StrEnum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    complexity: TaskComplexity
    model: str
    tier: str
    latency_ms: float


class ModelRouter:
    """Deterministic router from task complexity to model tier."""

    DEFAULT_ROUTES: Mapping[TaskComplexity, tuple[str, str]] = {
        TaskComplexity.SIMPLE: ("flash", "economy"),
        TaskComplexity.MEDIUM: ("standard", "standard"),
        TaskComplexity.COMPLEX: ("opus", "premium"),
    }

    def __init__(
        self,
        routes: Mapping[TaskComplexity | str, tuple[str, str]] | None = None,
    ) -> None:
        selected_routes = routes or self.DEFAULT_ROUTES
        self._routes = {
            TaskComplexity(complexity): route
            for complexity, route in selected_routes.items()
        }

    def route(self, complexity: TaskComplexity | str) -> RouteDecision:
        started_at = time.perf_counter()
        normalized = TaskComplexity(complexity)

        try:
            model, tier = self._routes[normalized]
        except KeyError as exc:
            raise ValueError(f"no route configured for {normalized.value}") from exc

        return RouteDecision(
            complexity=normalized,
            model=model,
            tier=tier,
            latency_ms=(time.perf_counter() - started_at) * 1000,
        )
