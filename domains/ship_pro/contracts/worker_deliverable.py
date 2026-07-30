"""
Ship Pro - Worker Deliverable Schema

Phase 2 Worker 的输出定义。
遵循 AI Native 原则：
- 灵活的内容结构（让 LLM 自由组织交付物）
- 只约束必要字段（确保可验证性）
- 支持多种交付物类型（工作包、AC、依赖图等）
"""
import warnings
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any


class WorkPackage(BaseModel):
    """工作包定义
    
    契约铁律：不可信的约束不是约束。
    acceptance_criteria 和 deliverables 不再是可选项——没有它们，WP 无法验收。
    """
    
    id: str = Field(..., alias="wp_id", description="工作包 ID，格式: {prefix}-NNN（如 CORE-001, LOOP-002）。接受 wp_id 别名。")
    
    @model_validator(mode='before')
    @classmethod
    def _map_wp_id(cls, data):
        if isinstance(data, dict):
            if 'wp_id' in data and 'id' not in data:
                data['id'] = data['wp_id']
            elif 'id' in data and 'wp_id' not in data:
                data['wp_id'] = data['id']
        return data

    @model_validator(mode='after')
    def _warn_empty_covered_req_ids(self):
        """P1-2: covered_req_ids 为空时发出 warning（不阻断）。
        
        空 covered_req_ids 意味着本 WP 无法被信息守恒追踪，
        下游 Consolidator/Gate 可能标记为 WARNING。
        """
        if not self.covered_req_ids:
            warnings.warn(
                f"WorkPackage {self.id}: covered_req_ids 为空。"
                f"建议填写本 WP 覆盖的需求 ID，以确保信息守恒可追溯。",
                UserWarning,
                stacklevel=2,
            )
        return self
    
    @model_validator(mode='before')
    @classmethod
    def _coerce_effort_hours(cls, data):
        """扩展接受：字符串数字自动转换为整数（AI Native 原则：代码适应 LLM 输出）。
        
        支持：
        - "40" → 40
        - "40.0" → 40
        - 40.0 → 40
        """
        if isinstance(data, dict) and 'effort_hours' in data:
            val = data['effort_hours']
            if isinstance(val, str):
                try:
                    # 尝试转换为整数（支持 "40" 或 "40.0"）
                    data['effort_hours'] = int(float(val))
                except (ValueError, TypeError):
                    pass  # 保持原值，让 Pydantic 报错
            elif isinstance(val, float) and val.is_integer():
                # 支持 40.0 → 40
                data['effort_hours'] = int(val)
        return data
    title: str = Field(..., description="工作包标题")
    description: str = Field(
        ..., min_length=100,
        description="工作包描述（≥100 字符，必须说清楚做什么、为什么这么做、技术边界）"
    )
    
    acceptance_criteria: List[str] = Field(
        ..., min_length=2,
        description="验收标准列表（≥2 条，每条必须可测试）"
    )
    
    dependencies: List[str] = Field(
        default_factory=list,
        description="依赖的其他工作包 ID 列表"
    )
    
    effort_hours: Optional[int] = Field(
        default=None,
        description="预估工时（小时）。必须是整数（如 40，不是 '40' 或 40.5）。"
    )
    
    covered_req_ids: List[str] = Field(
        default_factory=list,
        description="本 WP 覆盖的需求 ID 列表（可选，用于信息守恒验证）"
    )
    
    anchored_to: List[str] = Field(
        default_factory=list,
        description="本 WP 遵循的 Semantic Anchor 名称列表（契约笼子：信息守恒反馈字段）。"
                    "Worker 必须从 context.json 的 semantic_anchors 中选取与本 WP 相关的 anchor name。"
                    "空列表 = 上游无 Semantic Anchors 或本 WP 未引用任何约束（Consolidator/Gate 将标记为 WARNING）。"
    )
    
    deliverables: List[str] = Field(
        ..., min_length=1,
        description="交付物列表（≥1 项，不能为空）"
    )
    
    source_worker: Optional[str] = Field(
        default=None,
        description="产出此 WP 的 Worker 角色名（Consolidator 组装时标记来源，用于追溯）"
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
