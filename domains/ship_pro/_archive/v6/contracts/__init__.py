"""
Ship Pro V6 - Contracts Package

导出所有契约定义和 Gate 实现。
"""
from .planner_output import PlannerOutput, WorkerSpec, get_planner_output_schema
from .worker_deliverable import WorkerDeliverable, WorkPackage, get_worker_deliverable_schema
from .ship_package import ShipPackage, DependencyGraph, get_ship_package_schema
from .gates import (
    GateResult,
    PlannerGate,
    WorkerGate,
    InformationConservationGate,
    CompletenessGate,
    HarnessV3
)

__all__ = [
    # Schemas
    "PlannerOutput",
    "WorkerSpec",
    "WorkerDeliverable",
    "WorkPackage",
    "ShipPackage",
    "DependencyGraph",
    
    # Gates
    "GateResult",
    "PlannerGate",
    "WorkerGate",
    "InformationConservationGate",
    "CompletenessGate",
    "HarnessV3",
    
    # Schema helpers
    "get_planner_output_schema",
    "get_worker_deliverable_schema",
    "get_ship_package_schema",
]
