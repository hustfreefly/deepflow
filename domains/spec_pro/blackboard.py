"""
Spec Pro 路径注册表

Version: 1.0.0
Author: DeepFlow Spec Pro
Date: 2026-06-22

Spec Pro 使用混合路径模式:
- 固定路径: spec/living_spec.json 等
- 动态路径: stages/round_{NN}_parse.json 等（轮次号动态）
"""

from core.blackboard.registry_base import DomainRegistry
from core.blackboard.blackboard_manager import BlackboardManager as CoreBlackboardManager


# ============================================================================
# 固定路径注册表（唯一事实源）
# ============================================================================
STAGE_PATH_REGISTRY = {
    # Spec 核心文件
    "living_spec":             "spec/living_spec.json",
    "conversation_log":        "spec/conversation_log.json",
    "harness_report":          "spec/harness_report.json",
    "quality_trajectory":      "spec/quality_trajectory.json",

    # 输入
    "input":                   "input.md",
    "coord_state":             "coord_state.json",
}


# ============================================================================
# 动态路径生成器（轮次相关）
# ============================================================================
def round_path(round_num: int, stage_type: str) -> str:
    """
    生成轮次相关文件路径

    Args:
        round_num: 轮次号 (1-based)
        stage_type: 阶段类型 (parse / response / questions / confirmation)

    Returns:
        相对路径，如 "stages/round_01_parse.json"
    """
    return f"stages/round_{round_num:02d}_{stage_type}.json"


# ============================================================================
# Spec Pro Registry（继承 DomainRegistry）
# ============================================================================
class SpecRegistry(DomainRegistry):
    """Spec Pro 路径注册表"""
    STAGE_PATH_REGISTRY = STAGE_PATH_REGISTRY

    @classmethod
    def get_round_path(cls, round_num: int, stage_type: str) -> str:
        """获取轮次相关文件路径"""
        return round_path(round_num, stage_type)


# ============================================================================
# BlackboardManager（向后兼容）
# ============================================================================
class BlackboardManager(CoreBlackboardManager):
    """
    Spec Pro BlackboardManager

    自动配置 SpecRegistry + 轮次路径支持
    """

    def __init__(self, session_id: str, base_dir=None):
        super().__init__(session_id, base_dir=base_dir, registry=SpecRegistry)

    def write_round(self, round_num: int, stage_type: str, data: dict) -> "Path":
        """写入轮次文件"""
        from pathlib import Path
        rel_path = round_path(round_num, stage_type)
        return self.write(rel_path, data)

    def read_round(self, round_num: int, stage_type: str, default=None) -> dict:
        """读取轮次文件"""
        rel_path = round_path(round_num, stage_type)
        return self.read_json(rel_path, default=default or {})
