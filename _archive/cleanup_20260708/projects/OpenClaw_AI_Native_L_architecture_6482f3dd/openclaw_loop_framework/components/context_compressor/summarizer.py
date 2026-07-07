"""Hierarchical context summarization with Blackboard preservation."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Iterable, Mapping, MutableMapping, Sequence


TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class ConversationTurn:
    """One task-loop turn in the active context."""

    role: str
    content: str
    iteration: int
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CompressionResult:
    """Result of replacing detailed context with hierarchical summaries."""

    compressed_context: list[dict[str, object]]
    original_token_count: int
    compressed_token_count: int
    compression_ratio: float
    blackboard_key: str | None
    compressed: bool


class BlackboardArchive:
    """Append-only archive for detailed turns and critical state."""

    def __init__(self) -> None:
        self.records: dict[str, list[dict[str, object]]] = {}

    def append(self, key: str, turns: Sequence[ConversationTurn]) -> None:
        self.records.setdefault(key, []).append(
            {
                "turns": [self._serialize_turn(turn) for turn in turns],
                "preservation": "append_only_original_detail",
            }
        )

    @staticmethod
    def _serialize_turn(turn: ConversationTurn) -> dict[str, object]:
        return {
            "role": turn.role,
            "content": turn.content,
            "iteration": turn.iteration,
            "metadata": dict(turn.metadata),
        }


class HierarchicalSummarizer:
    """Creates compact summaries while preserving decisions and state."""

    DECISION_MARKERS = ("decision", "decided", "ADR", "批准", "决策")
    STATE_MARKERS = ("key state", "关键状态", "state", "status", "blocked", "done", "状态")

    def summarize(self, turns: Sequence[ConversationTurn]) -> list[dict[str, object]]:
        if not turns:
            return []

        decision_lines = self._extract_marked_lines(turns, self.DECISION_MARKERS)
        state_lines = self._extract_marked_lines(turns, self.STATE_MARKERS)
        overview = self._overview(turns)

        return [
            {
                "role": "system",
                "content": (
                    "[Hierarchical Context Summary]\n"
                    f"Scope: iterations {turns[0].iteration}-{turns[-1].iteration}\n"
                    f"Overview: {overview}\n"
                    f"Decision Records: {self._format_lines(decision_lines)}\n"
                    f"Key State: {self._format_lines(state_lines)}"
                ),
                "metadata": {
                    "kind": "hierarchical_summary",
                    "source_iterations": f"{turns[0].iteration}-{turns[-1].iteration}",
                },
            }
        ]

    def _overview(self, turns: Sequence[ConversationTurn]) -> str:
        parts: list[str] = []
        for turn in turns:
            first_sentence = re.split(r"(?<=[.!?。！？])\s+", turn.content.strip(), maxsplit=1)[0]
            parts.append(self._truncate(first_sentence, 18))
        return " | ".join(parts)

    def _extract_marked_lines(
        self, turns: Sequence[ConversationTurn], markers: Iterable[str]
    ) -> list[str]:
        found: list[str] = []
        lowered_markers = tuple(marker.lower() for marker in markers)
        for turn in turns:
            clauses = re.split(r"[\n.;。；]+", turn.content)
            for clause in clauses:
                lower = clause.lower()
                marker_offsets = [
                    lower.find(marker) for marker in lowered_markers if marker in lower
                ]
                if marker_offsets:
                    found.append(self._truncate(clause[min(marker_offsets) :].strip(), 20))
        return found

    @staticmethod
    def _format_lines(lines: Sequence[str]) -> str:
        return "; ".join(lines) if lines else "None recorded in compressed window"

    @staticmethod
    def _truncate(text: str, max_tokens: int) -> str:
        tokens = TOKEN_PATTERN.findall(text)
        if len(tokens) <= max_tokens:
            return text
        return " ".join(tokens[:max_tokens]) + "..."


class ContextCompressor:
    """Compresses task-loop context according to blueprint SLA constraints."""

    DEFAULT_FREQUENCY = 5

    def __init__(
        self,
        blueprint: Mapping[str, object],
        blackboard: BlackboardArchive | None = None,
        summarizer: HierarchicalSummarizer | None = None,
    ) -> None:
        self.frequency = self._read_frequency(blueprint)
        self.blackboard = blackboard or BlackboardArchive()
        self.summarizer = summarizer or HierarchicalSummarizer()

    def should_compress(self, iteration: int) -> bool:
        return iteration > 0 and iteration % self.frequency == 0

    def compress(
        self,
        turns: Sequence[ConversationTurn],
        iteration: int,
        active_context_tail: Sequence[Mapping[str, object]] | None = None,
    ) -> CompressionResult:
        original_tokens = self.count_tokens(turn.content for turn in turns)
        if not self.should_compress(iteration):
            return CompressionResult(
                compressed_context=[self._turn_to_context(turn) for turn in turns],
                original_token_count=original_tokens,
                compressed_token_count=original_tokens,
                compression_ratio=0.0,
                blackboard_key=None,
                compressed=False,
            )

        blackboard_key = f"context_window_{turns[0].iteration}_{turns[-1].iteration}"
        self.blackboard.append(blackboard_key, turns)

        summary_context = self.summarizer.summarize(turns)
        summary_context = self._fit_target_band(summary_context, turns, original_tokens)
        compressed_context = summary_context + [dict(item) for item in active_context_tail or []]
        compressed_tokens = self.count_tokens(str(item.get("content", "")) for item in compressed_context)
        ratio = 1 - (compressed_tokens / original_tokens) if original_tokens else 0.0

        return CompressionResult(
            compressed_context=compressed_context,
            original_token_count=original_tokens,
            compressed_token_count=compressed_tokens,
            compression_ratio=ratio,
            blackboard_key=blackboard_key,
            compressed=True,
        )

    @staticmethod
    def count_tokens(texts: Iterable[str]) -> int:
        return sum(len(TOKEN_PATTERN.findall(text)) for text in texts)

    @staticmethod
    def _turn_to_context(turn: ConversationTurn) -> dict[str, object]:
        return {
            "role": turn.role,
            "content": turn.content,
            "metadata": dict(turn.metadata),
        }

    def _fit_target_band(
        self,
        summary_context: list[dict[str, object]],
        turns: Sequence[ConversationTurn],
        original_tokens: int,
    ) -> list[dict[str, object]]:
        if not summary_context or not original_tokens:
            return summary_context

        minimum_tokens = math.ceil(original_tokens * 0.20)
        current_tokens = self.count_tokens(str(item.get("content", "")) for item in summary_context)
        if current_tokens >= minimum_tokens:
            return summary_context

        retained_snippets: list[str] = []
        for turn in turns:
            retained_snippets.append(
                f"Iteration {turn.iteration} trace: {self.summarizer._truncate(turn.content, 30)}"
            )
            candidate = "\n".join(retained_snippets)
            candidate_tokens = current_tokens + self.count_tokens([candidate])
            if candidate_tokens >= minimum_tokens:
                break

        adjusted = [dict(item) for item in summary_context]
        adjusted[0]["content"] = f"{adjusted[0]['content']}\nRetained Trace:\n" + "\n".join(
            retained_snippets
        )
        return adjusted

    @classmethod
    def _read_frequency(cls, blueprint: Mapping[str, object]) -> int:
        constraints = blueprint.get("sla_constraints")
        if isinstance(constraints, MutableMapping) or isinstance(constraints, Mapping):
            value = constraints.get("context_compression_every_rounds")
            if isinstance(value, int) and value > 0:
                return value
            value = constraints.get("context_compression_frequency")
            if isinstance(value, int) and value > 0:
                return value
        return cls.DEFAULT_FREQUENCY
