"""Tool-layer validation for tool call results."""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ToolGateResult:
    """Decision returned by the tool gate."""

    valid: bool
    missing_fields: list[str]
    action: str
    deviation_log: list[str]

    @property
    def should_retry(self) -> bool:
        return self.action == "retry"


class ToolGate:
    """Validates tool output against a minimal expected schema."""

    def check(
        self,
        tool_name: str,
        result: Mapping[str, Any],
        expected_schema: Mapping[str, Any],
    ) -> ToolGateResult:
        required_fields = self._required_fields(expected_schema)
        missing_fields = [
            field
            for field in required_fields
            if field not in result or result[field] is None
        ]

        deviation_log = [
            f"{tool_name}: missing required field '{field}'"
            for field in missing_fields
        ]

        valid = not missing_fields
        return ToolGateResult(
            valid=valid,
            missing_fields=missing_fields,
            action="accept" if valid else "retry",
            deviation_log=deviation_log,
        )

    @staticmethod
    def _required_fields(expected_schema: Mapping[str, Any]) -> Sequence[str]:
        required = expected_schema.get("required", ())
        if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
            raise TypeError("expected_schema['required'] must be a sequence of field names")
        return required
