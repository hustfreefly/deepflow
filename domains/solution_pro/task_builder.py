"""
任务构建器,使用 BlackboardManager API 替代路径拼接

Version: 2.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
Solution Task Builder 2.0.0 - Harness 修复版
===============================================

为 Solution 领域 Workers 构建 Task。
包含 Harness 修复:Layer 2 约束注入、格式标准化

禁止:直接调用 openclaw

变更日志:
- Harness P0/P1 修复
  - P0-1: Layer 2 约束 Prompt 注入
  - P0-2: 文件格式标准化
  - P1-1: 约束数量限制(最多2条)
- 使用PromptRegistry(Phase 2试点)
- 使用统一prompt读取函数
- 初始版本
"""

import os
import json
from typing import Dict, List, Tuple
import logging
logger = logging.getLogger(__name__)

# Harness 豁免阶段:这些阶段不需要 4 维 harness_check
HARNESS_EXEMPT_STAGES = frozenset(["data_collection", "planning", "summarizer"])

def validate_stage_output(output: dict, stage_name: str) -> Tuple[bool, str]:
    """
    验证 Stage 输出是否符合 Harness 标准格式(P0-2 修复)

    Args:
        output: Stage 输出字典
        stage_name: Stage 名称(用于错误信息)

    Returns:
        (是否有效, 错误信息)
    """
    # 检查是否为字典
    if not isinstance(output, dict):
        return False, f"{stage_name} 输出必须是字典"

    # 豁免阶段: 只检查 covered_req_ids(不要求 status/stage/harness_check)
    if stage_name in HARNESS_EXEMPT_STAGES:
        if "covered_req_ids" not in output:
            return False, f"{stage_name} 输出缺少必需字段: covered_req_ids"
    else:
        # 非豁免阶段: 检查完整字段集
        required_fields = ["status", "stage", "covered_req_ids"]
        for field in required_fields:
            if field not in output:
                return False, f"{stage_name} 输出缺少必需字段: {field}"
        # 非豁免阶段必须有 harness_check
        if "harness_check" not in output:
            return False, f"{stage_name} 输出缺少必需字段: harness_check"

        # 检查 harness_check 结构
        hc = output["harness_check"]
        if not isinstance(hc, dict):
            return False, f"{stage_name} harness_check 必须是字典"

        # 格式检测: 有 layer1_system_guardrails
        if "layer1_system_guardrails" in hc:
            # 格式: 使用 Pydantic HarnessCheck 验证（含契约笼子）
            try:
                from .schemas.schemas import HarnessCheckV2
                HarnessCheckV2(**hc)
            except ImportError:
                # schema 未安装，回退到基本检查
                if "overall_verdict" not in hc:
                    return False, f"{stage_name} harness_check 缺少 overall_verdict"
            except Exception as e:
                return False, f"{stage_name} harness_check 验证失败: {e}"
        else:
            # 格式（向后兼容）
            hc_required = ["completeness", "necessity", "alignment", "global_impact", "overall_score", "decision"]
            for field in hc_required:
                if field not in hc:
                    return False, f"{stage_name} harness_check 缺少: {field}"

            # 检查 decision 值
            valid_decisions = ["PASS", "PASS_WITH_CONDITIONS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]
            if hc["decision"] not in valid_decisions:
                return False, f"{stage_name} 无效的 decision: {hc['decision']}"

            # 检查分数范围
            for dim in ["completeness", "necessity", "alignment", "global_impact"]:
                if dim not in hc:
                    return False, f"{stage_name} harness_check 缺少维度: {dim}"
                dim_data = hc[dim]
                if isinstance(dim_data, dict):
                    score = dim_data.get("score")
                else:
                    score = dim_data
                if score is None:
                    return False, f"{stage_name} {dim} 缺少 score"
                if not (0.0 <= score <= 1.0):
                    return False, f"{stage_name} {dim} 分数超出范围: {score}"

    req_ids = output.get("covered_req_ids")
    if not isinstance(req_ids, list):
        return False, f"{stage_name} covered_req_ids 必须是数组"
    for req_id in req_ids:
        if not isinstance(req_id, str) or not req_id.startswith("REQ-"):
            return False, f"{stage_name} covered_req_ids 包含非法REQ-ID: {req_id}"

    # P0-6 修复: 非豁免阶段必须包含 requirement_evidence(REQ-ID 追踪契约)
    if stage_name not in HARNESS_EXEMPT_STAGES:
        req_evidence = output.get("requirement_evidence")
        if req_evidence is None:
            return False, f"{stage_name} 缺少 requirement_evidence"
        if not isinstance(req_evidence, list):
            return False, f"{stage_name} requirement_evidence 必须是数组"
        for item in req_evidence:
            if not isinstance(item, dict):
                return False, f"{stage_name} requirement_evidence 每项必须是对象"
            if "req_id" not in item or "status" not in item:
                return False, f"{stage_name} requirement_evidence 每项必须包含 req_id 和 status"

    return True, ""



