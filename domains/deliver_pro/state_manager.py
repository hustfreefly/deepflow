"""
Deliver Pro State Manager — 流水线状态管理。

# DEPRECATED: 无生产调用方。状态管理已由 wp_runner.py 中的 DeliverWPRunner
# 和 orchestrator.py 中的 DeliverOrchestrator 直接处理 delivery_state.json。
# 保留仅用于测试兼容性，新代码不应引用此类。

管理 delivery_state.json（单一真相源），控制状态转换合法性。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .blackboard import DeliverProBlackboard
from .contracts.pipeline_state import PipelinePhase, PipelineState, VALID_TRANSITIONS


class StateTransitionError(Exception):
    """非法状态转换。"""
    pass


class DeliverProStateManager:  # DEPRECATED — 无生产调用方，保留仅用于测试兼容
    """
    Deliver Pro 状态管理器。

    DEPRECATED: 无生产调用方。状态管理已由 wp_runner.py.DeliverWPRunner
    和 orchestrator.py.DeliverOrchestrator 直接处理。

    职责：
    1. 管理 delivery_state.json（单一真相源）
    2. 状态转换合法性检查
    3. 任务状态跟踪（pending/running/completed/failed）
    4. 同步写入 .stage_progress（兼容性文件）
    """

    def __init__(self, blackboard: DeliverProBlackboard):
        """
        初始化状态管理器。

        Args:
            blackboard: Blackboard 实例
        """
        self.blackboard = blackboard
        self.state_dir = blackboard.get_stage_path("state")
        self.state_file = self.state_dir / "delivery_state.json"
        self.progress_file = self.state_dir / ".stage_progress"

    def load_or_init(self, wp_id: str) -> PipelineState:
        """
        加载或初始化流水线状态。

        Args:
            wp_id: Work Package ID

        Returns:
            PipelineState 实例
        """
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                state = PipelineState(**data)
                return state
            except (json.JSONDecodeError, Exception):
                # N7: 状态文件损坏 — 记录完整错误 + 备份损坏文件
                import logging as _logging
                _sm_logger = _logging.getLogger(__name__)
                _sm_logger.error(
                    "State file corrupted, reinitializing: %s",
                    self.state_file,
                    exc_info=True,
                )
                try:
                    backup_path = self.state_file.with_suffix(".json.corrupted")
                    self.state_file.rename(backup_path)
                    _sm_logger.warning("Corrupted state backed up to %s", backup_path)
                except OSError as backup_err:
                    _sm_logger.error("Failed to backup corrupted state: %s", backup_err)

        # 初始化新状态
        state = PipelineState(wp_id=wp_id)
        self.save(state)
        return state

    def save(self, state: PipelineState) -> None:
        """
        保存状态到 delivery_state.json。

        使用原子写入（先 .tmp 再 rename）。

        Args:
            state: 要保存的状态
        """
        state.updated_at = datetime.now().isoformat()
        data = state.model_dump(mode="json")

        # 原子写入
        fd, tmp_path = tempfile.mkstemp(
            dir=self.state_dir,
            suffix=".tmp",
            prefix=".delivery_state_"
        )
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            os.write(fd, content)
            os.fsync(fd)
            os.close(fd)
            Path(tmp_path).rename(self.state_file)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(tmp_path).unlink(missing_ok=True)
            raise

        # 同步写入 .stage_progress
        self.write_progress_file(state)

    def transition(self, state: PipelineState, new_phase: PipelinePhase) -> None:
        """
        状态转换（含合法性检查）。

        Args:
            state: 当前状态
            new_phase: 目标阶段

        Raises:
            StateTransitionError: 如果转换不合法
        """
        allowed = VALID_TRANSITIONS.get(state.phase, [])
        if new_phase not in allowed:
            raise StateTransitionError(
                f"Invalid transition: {state.phase.value} → {new_phase.value}. "
                f"Allowed: {[p.value for p in allowed]}"
            )

        state.transition_to(new_phase)
        self.save(state)

    def mark_task_completed(self, state: PipelineState, task_id: str) -> None:
        """
        标记任务完成。

        Args:
            state: 当前状态
            task_id: 任务 ID
        """
        state.mark_task_completed(task_id)
        self.save(state)

    def mark_task_failed(self, state: PipelineState, task_id: str) -> None:
        """
        标记任务失败。

        Args:
            state: 当前状态
            task_id: 任务 ID
        """
        state.mark_task_failed(task_id)
        self.save(state)

    def write_progress_file(self, state: Optional[PipelineState] = None) -> None:
        """
        写 .stage_progress 兼容性文件。

        Args:
            state: 状态（如果为 None，则从文件加载）
        """
        if state is None:
            if not self.state_file.exists():
                return
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                state = PipelineState(**data)
            except (json.JSONDecodeError, Exception) as exc:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "Failed to read state for progress file: %s", exc
                )
                return

        progress = {
            "wp_id": state.wp_id,
            "phase": state.phase.value,
            "round_count": state.round_count,
            "max_rounds": state.max_rounds,
            "completed_tasks": state.completed_tasks,
            "failed_tasks": state.failed_tasks,
            "pending_tasks": state.pending_tasks,
            "running_tasks": state.running_tasks,
            "validation_score": state.validation_score,
            "last_verdict": state.last_verdict,
            "updated_at": state.updated_at,
        }

        # 原子写入
        fd, tmp_path = tempfile.mkstemp(
            dir=self.state_dir,
            suffix=".tmp",
            prefix=".stage_progress_"
        )
        try:
            content = json.dumps(progress, ensure_ascii=False, indent=2).encode("utf-8")
            os.write(fd, content)
            os.fsync(fd)
            os.close(fd)
            Path(tmp_path).rename(self.progress_file)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(tmp_path).unlink(missing_ok=True)
            raise


__all__ = ["DeliverProStateManager", "StateTransitionError"]
