"""HandoffPackage Pydantic 契约 — Spec Pro → Solution Pro 跨域交接契约

设计意图：
  契约笼子的核心执行：用 Pydantic 强类型模型替代裸 dict，
  确保 spec_pro 产出的 handoff package 满足 solution_pro 的消费预期。

  铁律：验证失败 → raise ValueError，绝不静默降级。

Version: 2.0.0
Date: 2026-07-06
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class DensityGateResult(BaseModel):
    """Density Gate 结果子契约

    嵌套在 HandoffPackage 中，确保 density_gate_result 结构合法。
    """
    passed: bool
    issues: List[str] = Field(default_factory=list)


class HandoffPackage(BaseModel):
    """Spec Pro → Solution Pro 跨域契约

    字段说明：
      - schema_version: 契约版本号，用于前向兼容检测
      - handoff_allowed: 是否允许交接（density gate 通过后为 True）
      - living_spec: 完整 Living Spec 数据（不可为空）
      - quality_report: 质量报告数据（可选，默认空 dict）
      - density_gate_result: Density Gate 结果（嵌套模型）
      - semantic_anchors: 语义锚点列表（供下游检索）
      - block_reason: 阻塞原因列表（handoff_allowed=False 时必须有值）
      - trace_id: 追踪 ID（为 Fix 2 预留，可选）

    契约铁律：
      1. living_spec 不可为空
      2. handoff_allowed=False 时必须有 block_reason
    """
    schema_version: str = "2.0.0"
    handoff_allowed: bool
    living_spec: Dict[str, Any]
    quality_report: Dict[str, Any] = Field(default_factory=dict)
    density_gate_result: DensityGateResult
    semantic_anchors: List[Dict[str, Any]] = Field(default_factory=list)
    block_reason: Optional[List[str]] = None
    trace_id: Optional[str] = None  # 为 Fix 2 预留

    @field_validator("living_spec")
    @classmethod
    def living_spec_not_empty(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """契约铁律：living_spec 不可为空 dict"""
        if not v:
            raise ValueError("living_spec 不能为空")
        return v

    @field_validator("semantic_anchors")
    @classmethod
    def validate_semantic_anchor_dicts(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """契约铁律：每个 semantic anchor dict 必须有 name/category/constraint 字段"""
        required_keys = {"name", "category", "constraint"}
        for i, anchor in enumerate(v):
            if not isinstance(anchor, dict):
                raise ValueError(f"semantic_anchors[{i}] 必须是 dict，实际类型: {type(anchor).__name__}")
            missing = required_keys - set(anchor.keys())
            if missing:
                raise ValueError(
                    f"semantic_anchors[{i}] 缺少必填字段: {missing}。"
                    f"name='{anchor.get('name', '?')}'"
                )
        return v

    @field_validator("density_gate_result", mode="before")
    @classmethod
    def coerce_density_gate(cls, v: Any) -> Any:
        """兼容处理：如果传入的是 dict，自动转为 DensityGateResult 模型

        设计意图：build_handoff_package 生成的是裸 dict，
        Pydantic 需要能自动嵌套解析。
        """
        if isinstance(v, dict):
            return DensityGateResult(**v)
        return v

    def model_post_init(self, __context: Any) -> None:
        """跨字段一致性校验：handoff_allowed=False 时必须有 block_reason

        设计意图：
          field_validator 无法可靠做跨字段校验（字段顺序不确定），
          所以用 model_post_init 做最终一致性检查。
        """
        if not self.handoff_allowed and not self.block_reason:
            raise ValueError(
                "契约一致性违反：handoff_allowed=False 时必须提供 block_reason"
            )
