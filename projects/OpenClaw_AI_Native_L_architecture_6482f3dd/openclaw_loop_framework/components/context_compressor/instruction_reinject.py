"""Core instruction reinjection for long-running task loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CoreInstructionSet:
    """Instructions that must remain visible after context growth."""

    goal_statement: str
    zone0_safety_rules: Sequence[str]
    key_constraints: Sequence[str]


class InstructionReinjector:
    """Reinjects core instructions on the configured task-loop cadence."""

    DEFAULT_FREQUENCY = 10

    def __init__(self, blueprint: Mapping[str, object]) -> None:
        self.blueprint = blueprint
        self.frequency = self._read_frequency(blueprint)

    def should_reinject(self, iteration: int) -> bool:
        return iteration > 0 and iteration % self.frequency == 0

    def build_payload(self, instructions: CoreInstructionSet) -> str:
        zone0 = "\n".join(f"- {rule}" for rule in instructions.zone0_safety_rules)
        constraints = "\n".join(f"- {constraint}" for constraint in instructions.key_constraints)
        return (
            "[Core Instructions Reinjection]\n"
            f"Goal Statement: {instructions.goal_statement}\n"
            "Zone 0 Safety Rules:\n"
            f"{zone0}\n"
            "Key Constraints:\n"
            f"{constraints}"
        )

    def reinject(
        self,
        active_context: Sequence[Mapping[str, str]],
        iteration: int,
        instructions: CoreInstructionSet,
    ) -> list[dict[str, str]]:
        if not self.should_reinject(iteration):
            return [dict(message) for message in active_context]

        reinjection = {
            "role": "system",
            "content": self.build_payload(instructions),
            "metadata": {
                "kind": "core_instruction_reinjection",
                "iteration": str(iteration),
            },
        }
        return [dict(message) for message in active_context] + [reinjection]

    @classmethod
    def _read_frequency(cls, blueprint: Mapping[str, object]) -> int:
        constraints = blueprint.get("sla_constraints")
        if isinstance(constraints, Mapping):
            value = constraints.get("instruction_reinject_every_rounds")
            if isinstance(value, int) and value > 0:
                return value
            value = constraints.get("core_instruction_reinject_frequency")
            if isinstance(value, int) and value > 0:
                return value
        return cls.DEFAULT_FREQUENCY
