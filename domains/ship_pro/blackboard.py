"""
Ship Pro 路径注册表

Version: 2.0.0
Author: DeepFlow Ship Pro
Date: 2026-06-22

变更:
- 瘦身为纯 Registry 定义，读写逻辑委托给 core.BlackboardManager
- 本地 BlackboardManager 实现（已废弃）
"""

from core.blackboard.registry_base import DomainRegistry
from core.blackboard.blackboard_manager import BlackboardManager as CoreBlackboardManager


# ============================================================================
# 路径注册表（唯一事实源）
# 所有 stage 文件路径必须从这里获取，禁止自行拼接
# ============================================================================
STAGE_PATH_REGISTRY = {
    # Agent 阶段输出
    "architect":    "architect",
    "decomposer":   "decomposer",
    "specifier":    "specifier",
    "reviewer":     "reviewer",
    "packager":     "packager",

    # 交付物
    "ship_package": "ship_package",
    "summary":      "summary",

    # 输入
    "input":        "input",
}

PIPELINE_STAGES = (
    "architect",
    "decomposer",
    "specifier",
    "reviewer",
    "packager",
)

# Agent 间依赖关系
AGENT_DEPENDENCIES = {
    "architect":  [],
    "decomposer": ["architect"],
    "specifier":  ["architect", "decomposer"],
    "reviewer":   ["architect", "decomposer", "specifier"],
    "packager":   ["architect", "specifier", "reviewer"],
}


# ============================================================================
# Ship Pro Registry（继承 DomainRegistry）
# ============================================================================
class ShipRegistry(DomainRegistry):
    """Ship Pro 路径注册表"""
    STAGE_PATH_REGISTRY = STAGE_PATH_REGISTRY


# ============================================================================
# BlackboardManager 别名（向后兼容）
# ============================================================================
class BlackboardManager(CoreBlackboardManager):
    """
    Ship Pro BlackboardManager（向后兼容）

    自动配置 ShipRegistry，无需手动 set_registry()
    """

    def __init__(self, session_id: str = None, base_dir=None):
        # 向后兼容：V1 接受 base_path: Path 参数
        if session_id is None:
            session_id = "ship_default"
        super().__init__(session_id, base_dir=base_dir, registry=ShipRegistry)
