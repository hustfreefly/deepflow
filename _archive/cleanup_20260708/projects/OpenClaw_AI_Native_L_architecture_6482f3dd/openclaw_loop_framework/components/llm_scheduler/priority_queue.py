"""Stable priority queue for LLM requests."""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Priority(IntEnum):
    """Request priority where lower numeric values are processed first."""

    HIGH = 0
    MEDIUM = 1
    LOW = 2


@dataclass(frozen=True, slots=True)
class PriorityRequest:
    request_id: str
    payload: Any
    priority: Priority


@dataclass(slots=True)
class RequestPriorityQueue:
    """FIFO-preserving priority queue."""

    _items: list[tuple[int, int, PriorityRequest]] = field(default_factory=list)
    _sequence: itertools.count = field(default_factory=itertools.count)

    def put(self, request: PriorityRequest) -> None:
        heapq.heappush(
            self._items,
            (int(request.priority), next(self._sequence), request),
        )

    def get(self) -> PriorityRequest:
        if not self._items:
            raise IndexError("priority queue is empty")
        return heapq.heappop(self._items)[2]

    def __len__(self) -> int:
        return len(self._items)

    @property
    def empty(self) -> bool:
        return not self._items
