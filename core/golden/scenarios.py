"""Golden behavior scenario contract.

The scenario set is a cage contract (GOLD-001..003): it locks the 20
highest-risk prompt/orchestrator behaviors. Structural validation runs in
G3. Execution is explicit and reads recorded results; CI never calls an LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "cage" / "active" / "golden_behavior_v1.0.yaml"
EXPECTED_SCENARIO_COUNT = 20

DOMAINS = ("spec_pro", "solution_pro", "ship_pro", "deliver_pro", "research_pro")
ORCHESTRATOR = "orchestrator"
ALL_DOMAINS = (*DOMAINS, ORCHESTRATOR)
REQUIRED_ORCHESTRATOR_TAGS = ("routing", "handoff", "injection", "failure", "gate")


class Expectation(BaseModel):
    """Deterministic assertions over a normalized execution result.

    Every field is optional, but at least one must be set. Unknown keys are
    rejected so a typo cannot silently weaken a scenario.
    """

    model_config = ConfigDict(extra="forbid")

    must_route_to: str | None = None
    must_ask_clarification: bool | None = None
    max_questions: int | None = Field(default=None, ge=0)
    must_not_generate: list[str] = Field(default_factory=list)
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    must_stop_at_gate: str | None = None
    must_not_send_alerts: bool | None = None
    must_cite_sources: bool | None = None
    must_preserve_ids: list[str] = Field(default_factory=list)
    must_spawn_max: int | None = Field(default=None, ge=0)
    must_report_blocker: bool | None = None
    must_treat_external_as_data: bool | None = None
    must_not_retry_more_than: int | None = Field(default=None, ge=0)
    must_produce_files: list[str] = Field(default_factory=list)
    output_format: str | None = None
    forbidden_tools: list[str] = Field(default_factory=list)

    def has_assertion(self) -> bool:
        """True when at least one deterministic assertion is configured."""
        return any(value not in (None, [], "") for value in self.model_dump().values())


class GoldenScenario(BaseModel):
    """One fixed input + expected behavior, not a golden text snapshot."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^golden-[a-z0-9-]+$")
    domain: Literal[
        "spec_pro",
        "solution_pro",
        "ship_pro",
        "deliver_pro",
        "research_pro",
        "orchestrator",
    ]
    title: str = Field(min_length=4)
    input: str = Field(min_length=8)
    expect: Expectation
    rubric: str = Field(min_length=8)
    severity: Literal["P0", "P1", "P2"] = "P1"
    tags: list[str] = Field(default_factory=list)
    runner: Literal["prompt", "orchestrator", "dry_run"] = "prompt"

    @model_validator(mode="after")
    def validate_route(self) -> "GoldenScenario":
        route = self.expect.must_route_to
        if route is not None and route not in ALL_DOMAINS:
            raise ValueError(f"unknown route {route!r}")
        if route is not None and self.domain != ORCHESTRATOR and route != self.domain:
            raise ValueError(
                f"domain scenario {self.id} cannot route to {route!r}; "
                f"expected {self.domain!r}"
            )
        return self


class GoldenScenarioSet(BaseModel):
    """Top-level contract. Extra cage metadata is intentionally allowed."""

    model_config = ConfigDict(extra="allow")

    component: str
    version: str
    scenarios: list[GoldenScenario]

    @model_validator(mode="after")
    def validate_set(self) -> "GoldenScenarioSet":
        if len(self.scenarios) != EXPECTED_SCENARIO_COUNT:
            raise ValueError(
                f"expected {EXPECTED_SCENARIO_COUNT} scenarios, "
                f"got {len(self.scenarios)}"
            )
        ids = [scenario.id for scenario in self.scenarios]
        duplicates = sorted(
            {scenario_id for scenario_id in ids if ids.count(scenario_id) > 1}
        )
        if duplicates:
            raise ValueError(f"duplicate scenario ids: {duplicates}")
        return self


def load_scenarios(path: Path | None = None) -> GoldenScenarioSet:
    """Load and validate the golden scenario contract."""
    contract_path = path or CONTRACT_PATH
    raw = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    return GoldenScenarioSet.model_validate(raw)


def validate_coverage(data: GoldenScenarioSet) -> list[str]:
    """Coverage rules for GOLD-001/003.

    Three scenarios per domain, five orchestrator scenarios, one P0 per
    domain, and the five cross-cutting risk tags must all be present.
    """
    errors: list[str] = []
    for domain in DOMAINS:
        items = [scenario for scenario in data.scenarios if scenario.domain == domain]
        if len(items) < 3:
            errors.append(f"{domain}: expected >=3 scenarios, got {len(items)}")
        if not any(scenario.severity == "P0" for scenario in items):
            errors.append(f"{domain}: expected at least one P0 scenario")

    orchestrator = [s for s in data.scenarios if s.domain == ORCHESTRATOR]
    if len(orchestrator) < 5:
        errors.append(f"orchestrator: expected >=5 scenarios, got {len(orchestrator)}")

    tags = {tag for scenario in data.scenarios for tag in scenario.tags}
    missing_tags = sorted(set(REQUIRED_ORCHESTRATOR_TAGS) - tags)
    if missing_tags:
        errors.append(f"missing cross-cutting tags: {missing_tags}")

    p0_count = sum(1 for scenario in data.scenarios if scenario.severity == "P0")
    if p0_count < 8:
        errors.append(f"expected >=8 P0 scenarios, got {p0_count}")
    return errors


def evaluate_result(scenario: GoldenScenario, result: dict[str, Any]) -> list[str]:
    """Evaluate a normalized execution result against deterministic assertions.

    Returns a list of human-readable failures; an empty list means PASS.
    Rubrics are intentionally not evaluated here (LLM judge is a separate,
    explicit step).
    """
    failures: list[str] = []
    expect = scenario.expect

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(f"{scenario.id}: {message}")

    if expect.must_route_to is not None:
        actual = result.get("routed_to")
        check(
            actual == expect.must_route_to,
            f"routed_to={actual!r}, expected {expect.must_route_to!r}",
        )
    if expect.must_ask_clarification is not None:
        actual = bool(result.get("asked_clarification"))
        check(
            actual == expect.must_ask_clarification,
            f"asked_clarification={actual!r}, expected {expect.must_ask_clarification!r}",
        )
    if expect.max_questions is not None:
        questions = result.get("questions") or []
        check(
            len(questions) <= expect.max_questions,
            f"questions={len(questions)}, expected <= {expect.max_questions}",
        )

    generated = set(result.get("generated") or [])
    for artifact in expect.must_not_generate:
        check(artifact not in generated, f"forbidden artifact generated: {artifact}")

    text = str(result.get("text") or "")
    for needle in expect.must_contain:
        check(needle in text, f"missing required text: {needle!r}")
    for needle in expect.must_not_contain:
        check(needle not in text, f"forbidden text present: {needle!r}")

    if expect.must_stop_at_gate is not None:
        actual = result.get("stopped_at")
        check(
            actual == expect.must_stop_at_gate,
            f"stopped_at={actual!r}, expected {expect.must_stop_at_gate!r}",
        )
    if expect.must_not_send_alerts:
        check(not result.get("alerts_sent"), "alerts were sent but dry-run expected")
    if expect.must_cite_sources:
        citations = result.get("citations") or []
        check(bool(citations), "no citations provided")
    if expect.must_preserve_ids:
        req_ids = set(result.get("req_ids") or [])
        missing = sorted(set(expect.must_preserve_ids) - req_ids)
        check(not missing, f"missing REQ-IDs: {missing}")
    if expect.must_spawn_max is not None:
        spawn_count = result.get("spawn_count") or 0
        check(
            spawn_count <= expect.must_spawn_max,
            f"spawn_count={spawn_count}, expected <= {expect.must_spawn_max}",
        )
    if expect.must_report_blocker:
        check(bool(result.get("blocker")), "blocker was not reported")
    if expect.must_treat_external_as_data:
        check(
            bool(result.get("external_treated_as_data")),
            "external content was not treated as data",
        )
    if expect.must_not_retry_more_than is not None:
        retries = result.get("retries") or 0
        check(
            retries <= expect.must_not_retry_more_than,
            f"retries={retries}, expected <= {expect.must_not_retry_more_than}",
        )
    if expect.must_produce_files:
        files = set(result.get("files") or [])
        missing = sorted(set(expect.must_produce_files) - files)
        check(not missing, f"missing files: {missing}")
    if expect.output_format is not None:
        actual = result.get("output_format")
        check(
            actual == expect.output_format,
            f"output_format={actual!r}, expected {expect.output_format!r}",
        )
    if expect.forbidden_tools:
        used = set(result.get("tools_used") or [])
        forbidden = sorted(set(expect.forbidden_tools) & used)
        check(not forbidden, f"forbidden tools used: {forbidden}")

    return failures
