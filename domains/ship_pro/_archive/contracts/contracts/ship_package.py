"""
Ship Pro V6 - ShipPackage Contract

定义 ShipPackage 的数据结构。
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from .worker_deliverable import WorkPackage


class DependencyGraph(BaseModel):
    """依赖图"""
    edges: List[Dict[str, str]] = Field(
        default_factory=list,
        description="依赖边列表，每个边包含 from 和 to 字段"
    )
    execution_layers: List[List[str]] = Field(
        default_factory=list,
        description="执行层级，每层包含可以并行执行的 work_package ID 列表"
    )


class ShipPackage(BaseModel):
    """ShipPackage - Ship Pro 的最终输出"""
    solution_name: str = Field(
        ...,
        description="解决方案名称"
    )
    work_packages: List[WorkPackage] = Field(
        default_factory=list,
        description="工作包列表"
    )
    dependency_graph: DependencyGraph = Field(
        default_factory=DependencyGraph,
        description="依赖图"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="元数据"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "solution_name": "Example Solution",
                "work_packages": [],
                "dependency_graph": {
                    "edges": [],
                    "execution_layers": []
                },
                "metadata": {}
            }
        }
