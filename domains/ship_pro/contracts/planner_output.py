"""
Ship Pro - Planner Output Schema

DEPRECATED: Use domains.ship_pro.pipeline_designer.WorkerSpec and PipelinePlan instead.
This module is kept for backward compatibility only.
The unified schema in pipeline_designer.py includes all fields from this module
(must_constraints, wp_id_prefix, needs_web_search, web_search_scope, solution_pro_refs)
plus additional operational fields (execution_order, module_purpose, interface_provides/requires).

遵循 AI Native 原则：
- 不硬编码枚举（让 LLM 自由分类）
- 不限制角色名称（让 LLM 自由命名）
- 只约束必要字段（让 LLM 有充分空间）
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class WorkerSpec(BaseModel):
    """
    DEPRECATED: Use domains.ship_pro.pipeline_designer.WorkerSpec instead.
    单个 Worker 的规格定义（保留向后兼容）
    """
    
    role: str = Field(..., description="Worker 角色名称（自由命名）")
    
    task_description: str = Field(..., description="任务描述")
    
    required_inputs: List[str] = Field(
        default_factory=list,
        description="需要读取的 Blackboard stage 列表"
    )
    
    expected_output_stage: str = Field(..., description="输出写入的 stage 名称")
    
    output_schema: str = Field(
        default="WorkerDeliverable",
        description="输出必须符合的 Pydantic 模型名"
    )
    
    depends_on: List[str] = Field(
        default_factory=list,
        description="依赖的其他 Worker role 列表"
    )
    
    needs_web_search: bool = Field(
        default=False,
        description="是否需要 web search 权限"
    )
    
    web_search_scope: Optional[str] = Field(
        default=None,
        description="搜索范围描述（如有权限）"
    )
    
    must_constraints: List[str] = Field(
        default_factory=list,
        description="从 Solution Pro 继承的 MUST 约束描述（语义描述，非 ID）"
    )
    
    solution_pro_refs: List[str] = Field(
        default_factory=list,
        description="引用的 Solution Pro 具体字段路径"
    )
    
    covered_req_ids: List[str] = Field(
        default_factory=list,
        description="该 Worker 覆盖的 Solution Pro REQ-ID 列表（量化漂移检测用）"
    )
    
    wp_id_prefix: str = Field(
        ...,
        description="WP ID 前缀（如 CORE-、LOOP-），所有该 Worker 生成的 WP ID 必须以此为前缀"
    )


class PlannerOutput(BaseModel):
    """
    DEPRECATED: Use domains.ship_pro.pipeline_designer.PipelinePlan instead.
    Phase 1 Planner 的结构化输出（保留向后兼容）
    """
    
    # 分析结论（自由文本，不硬编码枚举）
    input_type: str = Field(..., description="输入类型（自由分类）")
    complexity: str = Field(..., description="复杂度（自由分类）")
    domain: str = Field(..., description="领域描述")
    analysis_summary: str = Field(..., description="1-2 句分析结论")
    
    # 拆解计划
    workers: List[WorkerSpec] = Field(..., description="Worker 规格列表")
    
    # 整合策略（自由文本，不硬编码枚举）
    integration_strategy: str = Field(..., description="整合策略（自由描述）")
    
    # 延迟需求（Solution Pro 标记为 deferred/default 的 REQ-ID）
    pending_req_ids: List[str] = Field(
        default_factory=list,
        description="Solution Pro 标记为 deferred/默认行为的 REQ-ID（不需显式 WP 覆盖，但需记录）"
    )


def get_planner_output_schema() -> Dict[str, Any]:
    """获取 PlannerOutput 的 JSON Schema（用于 LLM 输出约束）"""
    return PlannerOutput.model_json_schema()
