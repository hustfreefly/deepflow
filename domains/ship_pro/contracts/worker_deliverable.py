"""
Ship Pro V6 - Worker Deliverable Schema

Phase 2 Worker 的输出定义。
遵循 AI Native 原则：
- 灵活的内容结构（让 LLM 自由组织交付物）
- 只约束必要字段（确保可验证性）
- 支持多种交付物类型（工作包、AC、依赖图等）
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class WorkPackage(BaseModel):
    """工作包定义"""
    
    id: str = Field(..., description="工作包 ID，格式: {prefix}-NNN（如 CORE-001, LOOP-002）")
    title: str = Field(..., description="工作包标题")
    description: str = Field(..., description="工作包描述")
    
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="验收标准列表"
    )
    
    dependencies: List[str] = Field(
        default_factory=list,
        description="依赖的其他工作包 ID 列表"
    )
    
    estimated_effort: Optional[str] = Field(
        default=None,
        description="预估工作量（自由格式）"
    )
    
    deliverables: List[str] = Field(
        default_factory=list,
        description="交付物列表"
    )


class WorkerDeliverable(BaseModel):
    """Worker 的交付物"""
    
    worker_role: str = Field(..., description="Worker 角色名称")
    wp_id_prefix: str = Field(..., description="WP ID 前缀（由 Orchestrator 注入，必须与 WorkerSpec 一致）")
    
    work_packages: List[WorkPackage] = Field(
        ...,
        min_length=1,
        description="工作包列表（至少 1 个 — 0 WP 的 Worker 没有意义）"
    )
    
    # 灵活的元数据（让 LLM 自由组织）
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="元数据（自由格式）"
    )
    
    # 可选建议（物理隔离）
    optional_suggestions: List[str] = Field(
        default_factory=list,
        description="可选建议（不影响主交付物）"
    )
    
    # 搜索日志（可追溯性）
    web_search_logs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="web_search 日志（如有使用）"
    )


def get_worker_deliverable_schema() -> Dict[str, Any]:
    """获取 WorkerDeliverable 的 JSON Schema"""
    return WorkerDeliverable.model_json_schema()
