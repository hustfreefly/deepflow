"""Zone 2 system-level auto tuning for MetaLoop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SLAConstraints:
    """System-level SLA constraints sourced from a blueprint."""

    token_budget: int
    token_budget_threshold: float = 1.0
    min_success_rate: float = 0.7
    max_concurrent_agents: int = 6
    target_quality_gate_threshold: float = 0.7
    manual_review_step: float = 0.15


@dataclass(frozen=True)
class Blueprint:
    """Minimal blueprint contract needed by the Zone 2 tuner."""

    sla_constraints: SLAConstraints


@dataclass(frozen=True)
class Zone2Metrics:
    """Historical system metrics used for Zone 2 tuning decisions."""

    token_consumed: int = 0
    success_rate: float = 1.0
    concurrent_agents: int = 0
    model: str = "opus"
    compression_frequency: int = 1
    quality_gate_threshold: float = 0.6
    manual_review_ratio: float = 0.0
    parallelism: int = 6
    serial_dependency_ratio: float = 0.0


@dataclass(frozen=True)
class TuningAction:
    """A single concrete Zone 2 tuning recommendation."""

    parameter: str
    before: Any
    after: Any
    reason: str


@dataclass(frozen=True)
class Zone2TuningPlan:
    """Aggregate result of a Zone 2 tuning pass."""

    actions: list[TuningAction] = field(default_factory=list)
    model: str = "opus"
    compression_frequency: int = 1
    quality_gate_threshold: float = 0.6
    manual_review_ratio: float = 0.0
    parallelism: int = 6
    serial_dependency_ratio: float = 0.0

    @property
    def triggered(self) -> bool:
        return bool(self.actions)


class Zone2Tuner:
    """Analyzes system history and emits deterministic Zone 2 adjustments."""

    STANDARD_MODEL = "sonnet"

    def analyze(
        self,
        blueprint: Blueprint | Mapping[str, Any],
        history: Sequence[Zone2Metrics | Mapping[str, Any]],
    ) -> Zone2TuningPlan:
        if not history:
            return Zone2TuningPlan()

        constraints = _coerce_constraints(blueprint)
        metrics = [_coerce_metrics(item) for item in history]
        current = metrics[-1]

        plan = Zone2TuningPlan(
            model=current.model,
            compression_frequency=current.compression_frequency,
            quality_gate_threshold=current.quality_gate_threshold,
            manual_review_ratio=current.manual_review_ratio,
            parallelism=current.parallelism,
            serial_dependency_ratio=current.serial_dependency_ratio,
        )
        actions: list[TuningAction] = []

        token_threshold = constraints.token_budget * constraints.token_budget_threshold
        if current.token_consumed > token_threshold:
            if _is_high_complexity_model(current.model):
                actions.append(
                    TuningAction(
                        parameter="model",
                        before=current.model,
                        after=self.STANDARD_MODEL,
                        reason="token_consumed_exceeds_sla_budget_threshold",
                    )
                )
                plan = _replace_plan(plan, model=self.STANDARD_MODEL)
            else:
                next_frequency = current.compression_frequency + 1
                actions.append(
                    TuningAction(
                        parameter="compression_frequency",
                        before=current.compression_frequency,
                        after=next_frequency,
                        reason="token_consumed_exceeds_sla_budget_threshold",
                    )
                )
                plan = _replace_plan(plan, compression_frequency=next_frequency)

        if _has_three_consecutive_low_success_rates(metrics, constraints.min_success_rate):
            if current.quality_gate_threshold < constraints.target_quality_gate_threshold:
                target_threshold = constraints.target_quality_gate_threshold
                actions.append(
                    TuningAction(
                        parameter="quality_gate_threshold",
                        before=current.quality_gate_threshold,
                        after=target_threshold,
                        reason="success_rate_below_sla_for_three_rounds",
                    )
                )
                plan = _replace_plan(plan, quality_gate_threshold=target_threshold)
            else:
                next_ratio = min(1.0, current.manual_review_ratio + constraints.manual_review_step)
                actions.append(
                    TuningAction(
                        parameter="manual_review_ratio",
                        before=current.manual_review_ratio,
                        after=next_ratio,
                        reason="success_rate_below_sla_for_three_rounds",
                    )
                )
                plan = _replace_plan(plan, manual_review_ratio=next_ratio)

        if current.concurrent_agents >= constraints.max_concurrent_agents:
            next_parallelism = max(1, min(current.parallelism, constraints.max_concurrent_agents) - 1)
            next_serial_ratio = min(1.0, current.serial_dependency_ratio + 0.2)
            actions.extend(
                [
                    TuningAction(
                        parameter="parallelism",
                        before=current.parallelism,
                        after=next_parallelism,
                        reason="concurrent_agents_at_sla_limit",
                    ),
                    TuningAction(
                        parameter="serial_dependency_ratio",
                        before=current.serial_dependency_ratio,
                        after=next_serial_ratio,
                        reason="concurrent_agents_at_sla_limit",
                    ),
                ]
            )
            plan = _replace_plan(
                plan,
                parallelism=next_parallelism,
                serial_dependency_ratio=next_serial_ratio,
            )

        return _replace_plan(plan, actions=actions)


def _coerce_constraints(blueprint: Blueprint | Mapping[str, Any]) -> SLAConstraints:
    raw_constraints: SLAConstraints | Mapping[str, Any]
    if isinstance(blueprint, Blueprint):
        return blueprint.sla_constraints

    raw_constraints = blueprint["sla_constraints"]
    if isinstance(raw_constraints, SLAConstraints):
        return raw_constraints

    return SLAConstraints(
        token_budget=int(raw_constraints["token_budget"]),
        token_budget_threshold=float(raw_constraints.get("token_budget_threshold", 1.0)),
        min_success_rate=float(raw_constraints.get("min_success_rate", 0.7)),
        max_concurrent_agents=int(raw_constraints.get("max_concurrent_agents", 6)),
        target_quality_gate_threshold=float(
            raw_constraints.get("target_quality_gate_threshold", 0.7)
        ),
        manual_review_step=float(raw_constraints.get("manual_review_step", 0.15)),
    )


def _coerce_metrics(metrics: Zone2Metrics | Mapping[str, Any]) -> Zone2Metrics:
    if isinstance(metrics, Zone2Metrics):
        return metrics

    return Zone2Metrics(
        token_consumed=int(metrics.get("token_consumed", 0)),
        success_rate=float(metrics.get("success_rate", 1.0)),
        concurrent_agents=int(metrics.get("concurrent_agents", 0)),
        model=str(metrics.get("model", "opus")),
        compression_frequency=int(metrics.get("compression_frequency", 1)),
        quality_gate_threshold=float(metrics.get("quality_gate_threshold", 0.6)),
        manual_review_ratio=float(metrics.get("manual_review_ratio", 0.0)),
        parallelism=int(metrics.get("parallelism", 6)),
        serial_dependency_ratio=float(metrics.get("serial_dependency_ratio", 0.0)),
    )


def _is_high_complexity_model(model: str) -> bool:
    return "opus" in model.lower()


def _has_three_consecutive_low_success_rates(
    metrics: Sequence[Zone2Metrics],
    minimum_success_rate: float,
) -> bool:
    return (
        len(metrics) >= 3
        and all(item.success_rate < minimum_success_rate for item in metrics[-3:])
    )


def _replace_plan(plan: Zone2TuningPlan, **changes: Any) -> Zone2TuningPlan:
    values = {
        "actions": plan.actions,
        "model": plan.model,
        "compression_frequency": plan.compression_frequency,
        "quality_gate_threshold": plan.quality_gate_threshold,
        "manual_review_ratio": plan.manual_review_ratio,
        "parallelism": plan.parallelism,
        "serial_dependency_ratio": plan.serial_dependency_ratio,
    }
    values.update(changes)
    return Zone2TuningPlan(**values)
