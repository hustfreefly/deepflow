"""
Ship Pro - ShipPackage Contract

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
        ...,
        min_length=1,
        description="工作包列表（必须包含完整 WP，不允许空列表或摘要化）"
    )
    dependency_graph: DependencyGraph = Field(
        default_factory=DependencyGraph,
        description="依赖图"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="元数据"
    )
    
    # 契约笼子：Semantic Anchors 透传（信息守恒强制字段）
    semantic_anchors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="从 Solution Pro 透传的语义锚点（契约笼子：必须保留，不可丢弃）。"
                    "每条包含 name/category/constraint/source_quote。"
                    "Consolidator 必须从 solution_pro_input 中原样复制到此处。"
    )
    anchor_coverage: Dict[str, Any] = Field(
        default_factory=dict,
        description="Semantic Anchor 覆盖统计（契约笼子：自动计算）。"
                    "格式: {anchor_name: [wp_id, ...], ...}，"
                    "以及 _uncovered: [anchor_name, ...] 列出未被任何 WP 引用的 anchor。"
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


def get_ship_package_schema() -> Dict[str, Any]:
    """返回 ShipPackage 的 JSON Schema"""
    return ShipPackage.model_json_schema()
