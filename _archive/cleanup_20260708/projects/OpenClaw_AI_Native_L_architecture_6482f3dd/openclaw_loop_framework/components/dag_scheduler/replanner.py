"""Dynamic replanning for failed DAG nodes."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Mapping

from .dag_decomposer import DAGDecomposer, DAGNode, DAGPlan
from .topo_validator import TopologicalValidation, TopologicalValidator


@dataclass(frozen=True)
class ReplanResult:
    plan: DAGPlan
    preserved_results: Mapping[str, Mapping[str, Any]]
    validation: TopologicalValidation
    elapsed_seconds: float


class DAGReplanner:
    """Replan failed nodes and downstream dependents while preserving checkpoints."""

    def __init__(
        self,
        decomposer: DAGDecomposer | None = None,
        validator: TopologicalValidator | None = None,
    ) -> None:
        self._decomposer = decomposer or DAGDecomposer()
        self._validator = validator or TopologicalValidator()

    def replan(
        self,
        plan: DAGPlan,
        failed_node_id: str,
        blackboard_checkpoint: Mapping[str, Mapping[str, Any]],
    ) -> ReplanResult:
        started_at = monotonic()
        node_by_id = plan.node_map()
        if failed_node_id not in node_by_id:
            raise ValueError(f"failed node {failed_node_id!r} does not exist")

        affected = self._affected_nodes(plan, failed_node_id)
        preserved_nodes = tuple(
            self._restore_success(node, blackboard_checkpoint)
            for node in plan.nodes
            if node.node_id not in affected
        )
        preserved_ids = {node.node_id for node in preserved_nodes}
        preserved_results = {
            node.node_id: dict(node.result or blackboard_checkpoint.get(node.node_id, {}))
            for node in preserved_nodes
            if node.status == "success"
        }

        failed_node = node_by_id[failed_node_id]
        inherited_dependencies = tuple(
            dependency
            for dependency in failed_node.dependencies
            if dependency in preserved_ids
        )
        subplan = self._decomposer.decompose_subgoal(
            plan.goal,
            failed_node,
            inherited_dependencies,
        )
        replacements = self._replacement_nodes(
            plan,
            failed_node_id,
            affected,
            preserved_ids,
            subplan.nodes,
        )

        replanned = DAGPlan(
            goal=plan.goal,
            nodes=preserved_nodes + replacements,
            metadata={**dict(plan.metadata), "replanned_failed_node": failed_node_id},
        )
        validation = self._validator.validate(replanned)
        return ReplanResult(
            plan=replanned,
            preserved_results=preserved_results,
            validation=validation,
            elapsed_seconds=monotonic() - started_at,
        )

    def _affected_nodes(self, plan: DAGPlan, failed_node_id: str) -> set[str]:
        dependents: dict[str, list[str]] = {node.node_id: [] for node in plan.nodes}
        for node in plan.nodes:
            for dependency in node.dependencies:
                if dependency in dependents:
                    dependents[dependency].append(node.node_id)

        affected = {failed_node_id}
        stack = [failed_node_id]
        while stack:
            current = stack.pop()
            for dependent in dependents[current]:
                if dependent not in affected:
                    affected.add(dependent)
                    stack.append(dependent)
        return affected

    def _restore_success(
        self,
        node: DAGNode,
        blackboard_checkpoint: Mapping[str, Mapping[str, Any]],
    ) -> DAGNode:
        if node.status != "success":
            return node
        checkpoint = blackboard_checkpoint.get(node.node_id)
        if checkpoint is None:
            return node
        return DAGNode(
            node_id=node.node_id,
            name=node.name,
            description=node.description,
            dependencies=node.dependencies,
            status="success",
            result=dict(checkpoint),
        )

    def _replacement_nodes(
        self,
        plan: DAGPlan,
        failed_node_id: str,
        affected: set[str],
        preserved_ids: set[str],
        replacements: tuple[DAGNode, ...],
    ) -> tuple[DAGNode, ...]:
        replacement_ids = {node.node_id for node in replacements}
        reattached: list[DAGNode] = []
        for node in replacements:
            dependencies = tuple(
                dependency
                for dependency in node.dependencies
                if dependency in replacement_ids or dependency in preserved_ids
            )
            reattached.append(
                DAGNode(
                    node_id=node.node_id,
                    name=node.name,
                    description=node.description,
                    dependencies=dependencies,
                    status=node.status,
                    result=node.result,
                )
            )
        failed_tail_id = replacements[-1].node_id
        for node in plan.nodes:
            if node.node_id == failed_node_id or node.node_id not in affected:
                continue
            dependencies = tuple(
                remapped
                for dependency in node.dependencies
                if (
                    remapped := self._remap_dependency(
                        dependency,
                        failed_node_id,
                        affected,
                        preserved_ids,
                        failed_tail_id,
                    )
                )
                is not None
            )
            reattached.append(
                DAGNode(
                    node_id=f"{node.node_id}.replanned",
                    name=f"Replan {node.name}",
                    description=node.description,
                    dependencies=dependencies,
                )
            )
        return tuple(reattached)

    def _remap_dependency(
        self,
        dependency: str,
        failed_node_id: str,
        affected: set[str],
        preserved_ids: set[str],
        failed_tail_id: str,
    ) -> str | None:
        if dependency == failed_node_id:
            return failed_tail_id
        if dependency in affected:
            return f"{dependency}.replanned"
        if dependency in preserved_ids:
            return dependency
        return None
