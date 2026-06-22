"""
Solution Pro 路径注册表

Version: 3.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-23

变更:
- V3.1: STAGE_PATH_REGISTRY 标记 @deprecated，推荐使用 V6 read_stage/write_stage
- 瘦身为纯 Registry 定义，读写逻辑委托给 core.BlackboardManager
- 本地 BlackboardManager 实现（已废弃）
"""

from typing import Type

from core.blackboard.registry_base import DomainRegistry
from core.blackboard.blackboard_manager import BlackboardManager as CoreBlackboardManager


# ============================================================================
# 路径注册表（唯一事实源）— @deprecated
# 推荐使用 V6 API: read_stage / write_stage / stage_exists / list_stages
# 所有 stage 文件路径必须从这里获取，禁止自行拼接
# ============================================================================

# 使用 helper 构建 stage 路径，避免硬编码路径模式
_S = "stages"
_J = ".json"


def _sp(name: str) -> str:
    """构建 stage 相对路径"""
    return f"{_S}/{name}{_J}"


# @deprecated: 推荐使用 BlackboardManager V6 API (read_stage / write_stage)
STAGE_PATH_REGISTRY = {
    "data_collection": "data/collection.json",
    "structured_requirements": "data/structured_requirements.json",
    "frozen_spec": "data/frozen_spec.json",
    "requirements_traceability_matrix": "requirements_traceability_matrix.json",
    "planning": _sp("planning"),
    "reviewer_technical": _sp("reviewer_technical"),
    "reviewer_business": _sp("reviewer_business"),
    "reviewer_risk": _sp("reviewer_risk"),
    "research_expert_1": _sp("research_expert_1"),
    "research_expert_2": _sp("research_expert_2"),
    "research_expert_3": _sp("research_expert_3"),
    "design": _sp("design"),
    "audit": _sp("audit"),
    "fix": _sp("fix"),
    "fixer_expert": _sp("fixer_expert"),
    "consolidator": _sp("consolidator"),
    "harness_final": _sp("harness_final"),
    "summarizer": "final_result.json",
}


PIPELINE_STAGES = (
    "data_collection",
    "planning",
    "reviewers",
    "research",
    "consolidator",
    "audit",
    "fix",
    "fixer_expert",
    "harness_final",
    "summarizer",
)


# ============================================================================
# Solution Pro Registry（继承 DomainRegistry）— @deprecated
# ============================================================================
class SolutionRegistry(DomainRegistry):
    """Solution Pro 路径注册表 — @deprecated: 推荐使用 BlackboardManager V6 API"""
    STAGE_PATH_REGISTRY = STAGE_PATH_REGISTRY


# ============================================================================
# BlackboardManager 别名（向后兼容）
# ============================================================================
# 旧代码: from domains.solution_pro.blackboard import BlackboardManager
# 新代码: 自动委托给 core.BlackboardManager，预配置 SolutionRegistry
# ============================================================================
class BlackboardManager(CoreBlackboardManager):
    """
    Solution Pro BlackboardManager（向后兼容）

    自动配置 SolutionRegistry，无需手动 set_registry()
    """

    def __init__(self, session_id: str, base_dir=None):
        super().__init__(session_id, base_dir=base_dir, registry=SolutionRegistry)