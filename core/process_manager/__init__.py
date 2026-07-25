"""
core.process_manager — DeepFlow 通用过程管理器（最小原语）

提供阻塞式 wait_for 原语，替代 spawn-yield 被动等待。
代码做控制流（Python while 循环，100% 确定），LLM 只做语义判断。

设计原则:
- 最小原语：只做"等文件出现"，不做调度决策
- 零 LLM 调用（纯确定性代码）
- 零内存状态（全部从文件系统推导）
- 进度输出防 stuck abort（spike 验证：每 15s 输出可存活）

Spike 验证（2026-07-25）:
- 阻塞 exec + 每 15s 进度输出 → 存活 300s+ 未被 abort
- 平台 stuck 检测看的是"有无进展输出"，不是"turn 时长"
"""

from .manager import ProcessManager, WaitResult

__all__ = ["ProcessManager", "WaitResult"]
