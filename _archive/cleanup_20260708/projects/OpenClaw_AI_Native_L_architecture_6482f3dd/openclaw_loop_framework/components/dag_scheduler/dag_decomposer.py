"""Dynamic decomposition of user goals into executable DAG plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class DAGNode:
    """A single executable unit in a DAG plan."""

    node_id: str
    name: str
    description: str
    dependencies: tuple[str, ...] = ()
    status: str = "pending"
    result: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DAGPlan:
    """A dependency graph produced from a user goal."""

    goal: str
    nodes: tuple[DAGNode, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def node_map(self) -> dict[str, DAGNode]:
        return {node.node_id: node for node in self.nodes}


@dataclass(frozen=True)
class DecompositionResult:
    """DAG decomposition output and quality metadata."""

    plan: DAGPlan
    route: str
    quality_score: float
    elapsed_seconds: float


class LLMScheduler(Protocol):
    """Boundary expected from an external LLM scheduler."""

    def decompose(self, goal: str, route_hint: str) -> Mapping[str, Any] | DAGPlan:
        """Return a decomposed DAG plan or a serializable plan mapping."""


class DAGDecomposer:
    """Create DAG task plans with an injectable LLM scheduler."""

    COMPLEX_ROUTE = "opus/gpt-4"

    def __init__(self, llm_scheduler: LLMScheduler | None = None) -> None:
        self._llm_scheduler = llm_scheduler

    def decompose(self, goal: str) -> DecompositionResult:
        started_at = monotonic()
        route = self.route_model(goal)

        if self._llm_scheduler is None:
            plan = self._fallback_plan(goal, route)
        else:
            raw_plan = self._llm_scheduler.decompose(goal, route)
            plan = self._coerce_plan(goal, raw_plan, route)

        quality_score = self.score_quality(plan)
        return DecompositionResult(
            plan=plan,
            route=route,
            quality_score=quality_score,
            elapsed_seconds=monotonic() - started_at,
        )

    def decompose_subgoal(
        self,
        goal: str,
        failed_node: DAGNode,
        inherited_dependencies: Sequence[str],
    ) -> DAGPlan:
        """Re-decompose a failed node while preserving upstream dependencies."""

        base_id = failed_node.node_id
        nodes = (
            DAGNode(
                node_id=f"{base_id}.diagnose",
                name=f"Diagnose {failed_node.name}",
                description=f"Identify why {failed_node.description} failed.",
                dependencies=tuple(inherited_dependencies),
            ),
            DAGNode(
                node_id=f"{base_id}.retry",
                name=f"Retry {failed_node.name}",
                description=failed_node.description,
                dependencies=(f"{base_id}.diagnose",),
            ),
            DAGNode(
                node_id=f"{base_id}.verify",
                name=f"Verify {failed_node.name}",
                description=f"Validate the retried work for {goal}.",
                dependencies=(f"{base_id}.retry",),
            ),
        )
        return DAGPlan(goal=goal, nodes=nodes, metadata={"replanned_from": base_id})

    def route_model(self, goal: str) -> str:
        complexity_terms = ("rest api", "登录", "login", "auth", "database", "test")
        normalized = goal.lower()
        if any(term in normalized for term in complexity_terms) or len(goal) > 24:
            return self.COMPLEX_ROUTE
        return "fast/general"

    def score_quality(self, plan: DAGPlan) -> float:
        node_ids = {node.node_id for node in plan.nodes}
        if not plan.nodes:
            return 0.0

        completeness = min(len(plan.nodes) / 3.0, 1.0)
        dependency_edges = sum(len(node.dependencies) for node in plan.nodes)
        valid_dependencies = all(
            dependency in node_ids
            for node in plan.nodes
            for dependency in node.dependencies
        )
        dependency_score = 1.0 if valid_dependencies and dependency_edges else 0.4
        named_score = (
            sum(1 for node in plan.nodes if node.name and node.description)
            / len(plan.nodes)
        )
        return round((0.4 * completeness) + (0.4 * dependency_score) + (0.2 * named_score), 3)

    def _fallback_plan(self, goal: str, route: str) -> DAGPlan:
        nodes = (
            DAGNode(
                node_id="auth",
                name="Authentication",
                description="Design login, credential validation, and token issuance.",
            ),
            DAGNode(
                node_id="api",
                name="REST API",
                description="Implement protected REST API routes and request handling.",
                dependencies=("auth",),
            ),
            DAGNode(
                node_id="tests",
                name="Tests",
                description="Cover login and protected API behavior with automated tests.",
                dependencies=("api",),
            ),
        )
        return DAGPlan(goal=goal, nodes=nodes, metadata={"route": route, "source": "fallback"})

    def _coerce_plan(
        self,
        goal: str,
        raw_plan: Mapping[str, Any] | DAGPlan,
        route: str,
    ) -> DAGPlan:
        if isinstance(raw_plan, DAGPlan):
            return raw_plan

        raw_nodes = raw_plan.get("nodes", ())
        nodes = tuple(
            DAGNode(
                node_id=str(item["id"]),
                name=str(item.get("name", item["id"])),
                description=str(item.get("description", "")),
                dependencies=tuple(str(dep) for dep in item.get("dependencies", ())),
                status=str(item.get("status", "pending")),
                result=item.get("result"),
            )
            for item in raw_nodes
        )
        metadata = dict(raw_plan.get("metadata", {}))
        metadata.setdefault("route", route)
        return DAGPlan(goal=str(raw_plan.get("goal", goal)), nodes=nodes, metadata=metadata)
