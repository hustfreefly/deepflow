"""
core.process_manager — DeepFlow 通用过程管理器（最小原语）

提供阻塞式 wait_for 原语，替代 spawn-yield 被动等待。
代码做控制流（Python while 循环，100% 确定），LLM 只做语义判断。

设计原则:
- 最小原语：只做"等文件出现"，不做调度决策
- 零 LLM 调用（纯确定性代码）
- 零内存状态（全部从文件系统推导）
- 进度输出防 stuck abort（spike 验证：每 15s 输出可存活）

增强版（2026-07-27）:
- 契约笼方法：Pydantic models → JSON Schema → 代码实现
- 输出文件验证：不依赖 mark_completed，直接检查输出文件
- 多信号 stall 检测：心跳超时 + 文件 mtime 超时
- 强制原子写：所有文件写入必须 .tmp + rename
- 单源状态：从 .run.json 派生，删除双写
- 独立 watchdog：cron 1min 扫描心跳过期 + webhook 告警
- 超时 webhook 告警：wait_for 超时时写入告警文件 + 调用 webhook

Spike 验证（2026-07-25）:
- 阻塞 exec + 每 15s 进度输出 → 存活 300s+ 未被 abort
- 平台 stuck 检测看的是"有无进展输出"，不是"turn 时长"
"""

from .manager import ProcessManager, WaitResult
from .lifecycle import ModuleLifecycleManager, ModuleWaitResult, RunInfo
from .state import SingleSourceStateManager
from .watchdog import Watchdog, run_watchdog_once
from .contracts import (
    WaitResultContract,
    ModuleWaitResultContract,
    RunRecordContract,
    AtomicWriteContract,
    WatchdogAlertContract,
    FileValidationContract,
    StallDetectionContract,
    TimeoutAlertContract,
)

__all__ = [
    # 核心类
    "ProcessManager",
    "WaitResult",
    "ModuleLifecycleManager",
    "ModuleWaitResult",
    "RunInfo",
    # 新增：单源状态管理
    "SingleSourceStateManager",
    # 新增：独立 watchdog
    "Watchdog",
    "run_watchdog_once",
    # 契约定义
    "WaitResultContract",
    "ModuleWaitResultContract",
    "RunRecordContract",
    "AtomicWriteContract",
    "WatchdogAlertContract",
    "FileValidationContract",
    "StallDetectionContract",
    "TimeoutAlertContract",
]
