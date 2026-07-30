"""
Deliver Pro State Manager — 契约笼子（Contract Cage）

# DEPRECATED: DeliverProStateManager 已废弃。
# 状态管理已由 wp_runner.DeliverWPRunner + orchestrator.DeliverOrchestrator 直接处理。
#
# 契约笼子（2026-07-30 DryRun V3.7 修复）：
#   实例化时 raise ValueError，防止新代码误用。
#   如需状态管理，请使用 wp_runner.DeliverWPRunner。
"""

from __future__ import annotations


class StateTransitionError(Exception):
    """非法状态转换（保留用于其他模块兼容）。"""
    pass


class DeliverProStateManager:
    """
    🔴 DEPRECATED — 契约笼子：实例化时 raise ValueError。

    状态管理已由 wp_runner.DeliverWPRunner 和 orchestrator.DeliverOrchestrator
    直接处理 delivery_state.json。此类不再有任何功能。

    如需状态管理，请使用：
    - domains.deliver_pro.wp_runner.DeliverWPRunner
    - domains.deliver_pro.orchestrator.DeliverOrchestrator
    """

    def __init__(self, *args, **kwargs):
        raise ValueError(
            "DeliverProStateManager is DEPRECATED (contract cage). "
            "State management is handled by DeliverWPRunner / DeliverOrchestrator. "
            "See domains/deliver_pro/state_manager.py for details."
        )


__all__ = ["DeliverProStateManager", "StateTransitionError"]
