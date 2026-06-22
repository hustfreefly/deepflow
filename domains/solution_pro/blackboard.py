"""
Solution Pro 路径注册表

Version: 3.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-22

变更:
- 瘦身为纯 Registry 定义，读写逻辑委托给 core.BlackboardManager
- 本地 BlackboardManager 实现（已废弃）
"""

from typing import Type

from core.blackboard.registry_base import DomainRegistry
from core.blackboard.blackboard_manager import BlackboardManager as CoreBlackboardManager


# ============================================================================
# 路径注册表（唯一事实源）
# 所有 stage 文件路径必须从这里获取，禁止自行拼接
# ============================================================================
STAGE_PATH_REGISTRY = {
    "data_collection": "data/collection.json",
    "structured_requirements": "data/structured_requirements.json",
    "frozen_spec": "data/frozen_spec.json",
    "requirements_traceability_matrix": "requirements_traceability_matrix.json",
    "planning": "stages/planning.json",
    "reviewer_technical": "stages/reviewer_technical.json",
    "reviewer_business": "stages/reviewer_business.json",
    "reviewer_risk": "stages/reviewer_risk.json",
    "research_expert_1": "stages/research_expert_1.json",
    "research_expert_2": "stages/research_expert_2.json",
    "research_expert_3": "stages/research_expert_3.json",
    "design": "stages/design.json",
    "audit": "stages/audit.json",
    "fix": "stages/fix.json",
    "fixer_expert": "stages/fixer_expert.json",
    "consolidator": "stages/consolidator.json",
    "harness_final": "stages/harness_final.json",
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
# Solution Pro Registry（继承 DomainRegistry）
# ============================================================================
class SolutionRegistry(DomainRegistry):
    """Solution Pro 路径注册表"""
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
