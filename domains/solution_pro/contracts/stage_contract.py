"""StageContract: checkpoint 的 schema + semantic minimums + artifact path 验证。"""
import json
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StageContract(BaseModel):
    """定义一个 stage checkpoint 的完整契约。"""
    stage_name: str
    required_keys: List[str] = Field(default_factory=list)
    schema_type: Optional[str] = None  # "dict" | "list" | "string_content"
    content: Optional[str] = None  # 可选内容字段（兼容 Mothership 直传）
    min_content_length: int = 10  # 内容最小长度（防止空壳 dict）
    artifact_path: Optional[str] = None  # 关联的 artifact 路径


# 各 stage 的契约定义
STAGE_CONTRACTS: Dict[str, StageContract] = {
    "planning": StageContract(
        stage_name="planning",
        required_keys=["content"],
        schema_type="dict",
        min_content_length=50,
    ),
    "research": StageContract(
        stage_name="research",
        required_keys=["content"],
        schema_type="dict",
        min_content_length=50,
    ),
    "base_solution": StageContract(
        stage_name="base_solution",
        required_keys=["content"],
        schema_type="dict",
        min_content_length=100,
    ),
    "refined_solution": StageContract(
        stage_name="refined_solution",
        required_keys=["content"],
        schema_type="dict",
        min_content_length=100,
    ),
    "solution_document": StageContract(
        stage_name="solution_document",
        required_keys=["content"],
        schema_type="dict",
        min_content_length=100,
    ),
    "final_solution": StageContract(
        stage_name="final_solution",
        required_keys=["schema_version"],
        schema_type="dict",
        min_content_length=50,
    ),
    "summary_plan": StageContract(
        stage_name="summary_plan",
        required_keys=["content"],
        schema_type="dict",
        min_content_length=50,
    ),
    # Convergence checkpoints — 结构灵活，不强制 required_keys，只检查最小内容长度
    "planning_convergence": StageContract(
        stage_name="planning_convergence",
        required_keys=[],
        schema_type="dict",
        min_content_length=100,
    ),
    "research_convergence": StageContract(
        stage_name="research_convergence",
        required_keys=[],
        schema_type="dict",
        min_content_length=100,
    ),
    "meta_planning": StageContract(
        stage_name="meta_planning",
        required_keys=[],
        schema_type="dict",
        min_content_length=50,
    ),
    "knowledge_freshness": StageContract(
        stage_name="knowledge_freshness",
        required_keys=[],
        schema_type="dict",
        min_content_length=50,
    ),
}


def validate_checkpoint(contract: StageContract, data: dict) -> tuple:
    """验证 checkpoint 数据是否符合契约。

    P1-11 FIX: 加强语义最小验证 — `{}` 不再通过。
    每个 stage 必须有实质性内容，不能是空壳 dict。

    Returns:
        (is_valid, reason)
    """
    # 0. P1-11: Empty dict 铁律拒绝
    if not data or len(data) == 0:
        return False, "P1-11: 空 dict 不符合任何 stage 契约"

    # 1. required_keys
    missing = [k for k in contract.required_keys if k not in data]
    if missing:
        return False, f"缺少必需字段: {missing}"

    # 2. min_content_length（仅当 data 含有 content 字段时检查）
    if "content" in data:
        content = data["content"]
        if isinstance(content, str) and len(content) < contract.min_content_length:
            return False, f"内容长度 {len(content)} < 最小 {contract.min_content_length}"
        elif isinstance(content, dict) and len(str(content)) < contract.min_content_length:
            return False, f"内容长度 {len(str(content))} < 最小 {contract.min_content_length}"

    # 3. 排除损坏的 dict
    if "error" in data and len(data) <= 2:
        return False, f"数据看起来是错误记录: {data}"

    # 4. P1-11: Stage-specific semantic minimums
    stage = contract.stage_name
    if stage == "planning_convergence":
        if not (data.get("unified_constraints") or data.get("gate_verdict")
                or data.get("gate_a_scores")):
            return False, (
                "P1-11: planning_convergence 缺少实质性内容 "
                "(需要 unified_constraints / gate_verdict / gate_a_scores 之一)"
            )
    elif stage == "research_convergence":
        if not (data.get("research_summary") or data.get("key_findings")
                or data.get("consolidated_findings") or data.get("findings_index")):
            return False, (
                "P1-11: research_convergence 缺少实质性内容 "
                "(需要 research_summary / key_findings / consolidated_findings 之一)"
            )
    elif stage == "final_solution":
        if not (data.get("full_solution") or data.get("status")
                or data.get("schema_version")):
            return False, (
                "P1-11: final_solution 缺少实质性内容 "
                "(需要 full_solution / status / schema_version 之一)"
            )

    # 5. P1-11: Non-content stages must have meaningful size
    if "content" not in data and contract.required_keys == []:
        serialized = json.dumps(data, sort_keys=True) if isinstance(data, dict) else str(data)
        if len(serialized) < contract.min_content_length:
            return False, (
                f"P1-11: {stage} 序列化长度 {len(serialized)} < "
                f"最小 {contract.min_content_length}"
            )

    return True, "OK"
