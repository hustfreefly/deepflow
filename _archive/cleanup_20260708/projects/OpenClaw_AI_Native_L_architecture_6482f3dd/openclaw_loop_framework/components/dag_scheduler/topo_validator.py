"""Topological sorting and dependency validation for DAG plans."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush

from .dag_decomposer import DAGPlan


@dataclass(frozen=True)
class TopologicalValidation:
    is_valid: bool
    ordered_node_ids: tuple[str, ...]
    errors: tuple[str, ...] = ()


class TopologicalValidator:
    """Validate that dependencies exist and produce an acyclic topological order."""

    def validate(self, plan: DAGPlan) -> TopologicalValidation:
        node_ids = {node.node_id for node in plan.nodes}
        errors: list[str] = []

        if len(node_ids) != len(plan.nodes):
            errors.append("duplicate node_id detected")

        dependents: dict[str, list[str]] = {node.node_id: [] for node in plan.nodes}
        indegree: dict[str, int] = {node.node_id: 0 for node in plan.nodes}

        for node in plan.nodes:
            for dependency in node.dependencies:
                if dependency not in node_ids:
                    errors.append(f"{node.node_id} depends on missing node {dependency}")
                    continue
                dependents[dependency].append(node.node_id)
                indegree[node.node_id] += 1

        if errors:
            return TopologicalValidation(False, (), tuple(errors))

        ready: list[str] = []
        for node_id, degree in indegree.items():
            if degree == 0:
                heappush(ready, node_id)

        ordered: list[str] = []
        while ready:
            node_id = heappop(ready)
            ordered.append(node_id)
            for dependent in sorted(dependents[node_id]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heappush(ready, dependent)

        if len(ordered) != len(plan.nodes):
            cycle_nodes = tuple(
                node_id for node_id, degree in sorted(indegree.items()) if degree > 0
            )
            return TopologicalValidation(
                False,
                tuple(ordered),
                (f"cycle detected involving {', '.join(cycle_nodes)}",),
            )

        return TopologicalValidation(True, tuple(ordered))
