"""Multi-dimensional dead-loop signal detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Iterable, Sequence

from .adaptive_threshold import AdaptiveThreshold, Complexity


class SignalType(StrEnum):
    """Circuit breaker signal categories."""

    PROGRESS_AWARE_REPEAT = "progress_aware_repeat"
    TOKEN_ANOMALY = "token_anomaly"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    NO_PROGRESS = "no_progress"


@dataclass(frozen=True)
class WorkerEvent:
    """A single worker action/status sample."""

    worker_id: str
    action_id: str
    token_count: int
    timestamp: datetime
    progress_marker: str | None = None


@dataclass(frozen=True)
class WorkerSignal:
    """Detected circuit breaker signal."""

    worker_id: str
    signal_type: SignalType
    details: dict[str, object] = field(default_factory=dict)


class SignalDetector:
    """Detect repeated actions, token anomalies, stalled progress, and heartbeat loss."""

    def __init__(
        self,
        thresholds: AdaptiveThreshold | None = None,
        heartbeat_timeout_seconds: int = 300,
        token_growth_threshold: float = 0.50,
        token_growth_streak_threshold: int = 3,
    ) -> None:
        self._thresholds = thresholds or AdaptiveThreshold()
        self._heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)
        self._token_growth_threshold = token_growth_threshold
        self._token_growth_streak_threshold = token_growth_streak_threshold

    def detect(
        self,
        events: Sequence[WorkerEvent],
        *,
        complexity: Complexity | str = Complexity.MEDIUM,
        now: datetime | None = None,
    ) -> list[WorkerSignal]:
        """Run all signal detectors for a worker event history."""

        signals: list[WorkerSignal] = []
        repeat_signal = self.detect_progress_aware_repeat(events, complexity=complexity)
        token_signal = self.detect_token_anomaly(events)
        no_progress_signal = self.detect_no_progress(events, complexity=complexity)
        heartbeat_signal = self.detect_heartbeat_timeout(events, now=now)

        for signal in (
            repeat_signal,
            token_signal,
            no_progress_signal,
            heartbeat_signal,
        ):
            if signal is not None:
                signals.append(signal)
        return signals

    def detect_progress_aware_repeat(
        self,
        events: Sequence[WorkerEvent],
        *,
        complexity: Complexity | str = Complexity.MEDIUM,
    ) -> WorkerSignal | None:
        """Detect repeated actions only when progress has not changed."""

        ordered_events = self._ordered(events)
        if not ordered_events:
            return None

        threshold = self._thresholds.repeat_threshold(complexity)
        tail = ordered_events[-1]
        repeat_count = 0
        for event in reversed(ordered_events):
            same_action = event.action_id == tail.action_id
            same_progress = event.progress_marker == tail.progress_marker
            if not same_action or not same_progress:
                break
            repeat_count += 1

        if repeat_count < threshold:
            return None

        return WorkerSignal(
            worker_id=tail.worker_id,
            signal_type=SignalType.PROGRESS_AWARE_REPEAT,
            details={
                "action_id": tail.action_id,
                "repeat_count": repeat_count,
                "threshold": threshold,
                "detection_type": "progress_aware",
            },
        )

    def detect_token_anomaly(
        self,
        events: Sequence[WorkerEvent],
    ) -> WorkerSignal | None:
        """Detect a token growth streak above the configured threshold."""

        ordered_events = self._ordered(events)
        if len(ordered_events) < 2:
            return None

        streak = 0
        last_growth_rate = 0.0
        for previous, current in zip(ordered_events, ordered_events[1:]):
            if previous.token_count <= 0:
                streak = 0
                continue

            growth_rate = (current.token_count - previous.token_count) / previous.token_count
            if growth_rate > self._token_growth_threshold:
                streak += 1
                last_growth_rate = growth_rate
            else:
                streak = 0

            if streak >= self._token_growth_streak_threshold:
                return WorkerSignal(
                    worker_id=current.worker_id,
                    signal_type=SignalType.TOKEN_ANOMALY,
                    details={
                        "growth_rate": last_growth_rate,
                        "streak": streak,
                        "threshold": self._token_growth_threshold,
                    },
                )
        return None

    def detect_no_progress(
        self,
        events: Sequence[WorkerEvent],
        *,
        complexity: Complexity | str = Complexity.MEDIUM,
    ) -> WorkerSignal | None:
        """Detect consecutive samples with unchanged progress."""

        ordered_events = self._ordered(events)
        if not ordered_events:
            return None

        threshold = self._thresholds.repeat_threshold(complexity)
        tail = ordered_events[-1]
        no_progress_count = 0
        for event in reversed(ordered_events):
            if event.progress_marker != tail.progress_marker:
                break
            no_progress_count += 1

        if no_progress_count < threshold:
            return None

        return WorkerSignal(
            worker_id=tail.worker_id,
            signal_type=SignalType.NO_PROGRESS,
            details={
                "progress_marker": tail.progress_marker,
                "no_progress_count": no_progress_count,
                "threshold": threshold,
            },
        )

    def detect_heartbeat_timeout(
        self,
        events: Sequence[WorkerEvent],
        *,
        now: datetime | None = None,
    ) -> WorkerSignal | None:
        """Detect missing Blackboard status updates beyond the heartbeat threshold."""

        ordered_events = self._ordered(events)
        if not ordered_events:
            return None

        last_event = ordered_events[-1]
        reference_time = now or datetime.now(tz=last_event.timestamp.tzinfo or timezone.utc)
        elapsed = reference_time - last_event.timestamp
        if elapsed < self._heartbeat_timeout:
            return None

        return WorkerSignal(
            worker_id=last_event.worker_id,
            signal_type=SignalType.HEARTBEAT_TIMEOUT,
            details={
                "elapsed_seconds": int(elapsed.total_seconds()),
                "threshold_seconds": int(self._heartbeat_timeout.total_seconds()),
            },
        )

    @staticmethod
    def _ordered(events: Iterable[WorkerEvent]) -> list[WorkerEvent]:
        return sorted(events, key=lambda event: event.timestamp)
