"""
Research Pro 路径注册表

Version: 1.0.0
Author: DeepFlow Research Pro
Date: 2026-07-12

Research Pro 阶段路径:
- planning: 研究计划
- search: 搜索执行
- analysis: 深度分析
- report: 研究报告
- quality_review: 质量审查
"""

import core.bootstrap  # 契约笼子: 通过 bootstrap 自动加入 sys.path
from core.blackboard.registry_base import DomainRegistry
from core.blackboard.blackboard_manager import BlackboardManager as CoreBlackboardManager


# ============================================================================
# 路径注册表（唯一事实源）
# 所有 stage 文件路径必须从这里获取，禁止自行拼接
# ============================================================================
STAGE_PATH_REGISTRY = {
    # 研究阶段输出
    "planning":         "planning",
    "search":           "search",
    "analysis":         "analysis",
    "report":           "report",
    "quality_review":   "quality_review",

    # 输入
    "input":            "input",
}


# ============================================================================
# Research Pro Registry（继承 DomainRegistry）
# ============================================================================
class ResearchRegistry(DomainRegistry):
    """Research Pro 路径注册表"""
    STAGE_PATH_REGISTRY = STAGE_PATH_REGISTRY


# ============================================================================
# BlackboardManager 别名（向后兼容）
# ============================================================================
class BlackboardManager(CoreBlackboardManager):
    """
    Research Pro BlackboardManager（向后兼容）

    自动配置 ResearchRegistry，无需手动 set_registry()
    """

    def __init__(self, session_id: str = None, base_dir=None):
        if session_id is None:
            session_id = "research_default"
        super().__init__(session_id, base_dir=base_dir, registry=ResearchRegistry)
