"""Input-layer validation for LLM requests."""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class InputGateResult:
    """Decision returned by the input gate."""

    accepted: bool
    missing_fields: list[str]

    @property
    def should_forward(self) -> bool:
        return self.accepted


class InputGate:
    """Rejects malformed LLM requests before downstream execution."""

    def __init__(self, required_fields: Sequence[str] | None = None) -> None:
        self.required_fields = tuple(required_fields or ("task_id", "action_type"))

    def check(self, request: Mapping[str, Any]) -> InputGateResult:
        missing_fields = [
            field
            for field in self.required_fields
            if field not in request or request[field] in (None, "")
        ]
        return InputGateResult(
            accepted=not missing_fields,
            missing_fields=missing_fields,
        )
