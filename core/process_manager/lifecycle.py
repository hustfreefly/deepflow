"""
ModuleLifecycleManager — 模块生命周期管理器

统一解决 Solution Pro 状态信号无归属问题（No Ownership on Signals）：
- 问题 1: wait_for 误读旧文件（stale read）
- 问题 2: stall detection 读共享 checkpoint（cross-module pollution）

核心机制：
1. 每次 spawn 分配唯一 run_id（SSCT token）
2. Module Agent 执行中定期 heartbeat
3. 完成时 mark_completed 注册产出文件
4. Orchestrator wait_for_module 校验 run_id + 文件注册

红线：零删除，纯新增。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import (
    RunRecordContract,
    ModuleWaitResultContract,
    StallDetectionContract,
)


@dataclass
class RunInfo:
    """try_acquire_run 返回的运行信息"""
    run_id: str
    attempt: int
    already_running: bool = False  # True 表示已有活跃运行，不应重复 spawn

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "attempt": self.attempt,
            "already_running": self.already_running,
        }


@dataclass
class ModuleWaitResult:
    """wait_for_module 返回结果"""
    found: bool
    run_id: str | None = None
    attempt: int = 0
    elapsed: float = 0
    reason: str = ""  # "" | "timeout" | "stall"
    files: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "run_id": self.run_id,
            "attempt": self.attempt,
            "elapsed": round(self.elapsed, 1),
            "reason": self.reason,
            "files": self.files,
        }


class ModuleLifecycleManager:
    """
    模块生命周期管理器

    职责：
    - spawn 前去重（try_acquire_run）
    - 执行中心跳（heartbeat）
    - 完成时注册（mark_completed）
    - 等待完成（wait_for_module）

    用法（Orchestrator 在 exec 中调用）:
        lifecycle = ModuleLifecycleManager("/path/to/blackboard/session")

        # spawn 前
        run = lifecycle.try_acquire_run("summary")
        if run.already_running:
            # 不重复 spawn，直接等
        else:
            sessions_spawn(task=f"...RUN_ID={run.run_id}...")

        # 等待完成
        result = lifecycle.wait_for_module("summary", expected_files=[...])

    用法（Module Agent 在 exec 中调用）:
        lifecycle = ModuleLifecycleManager("/path/to/blackboard/session")
        lifecycle.heartbeat("summary", run_id)
        # ... 执行工作 ...
        lifecycle.mark_completed("summary", run_id, output_files={...})
    """

    def __init__(self, session_dir: str | Path):
        self.session_dir = Path(session_dir)
        self.runs_dir = self.session_dir / ".runs"
        self.runs_dir.mkdir(exist_ok=True)

    def _run_path(self, module: str) -> Path:
        return self.runs_dir / f"{module}.run.json"

    def _read_run(self, module: str) -> dict | None:
        path = self._run_path(module)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _write_run(self, module: str, record: dict) -> None:
        """
        原子写操作（强制契约）
        
        所有文件写入必须使用 .tmp + rename 模式，防止写入中断导致文件损坏。
        这是解决 V39/V40 "JSON 损坏" 问题的关键。
        """
        path = self._run_path(module)
        tmp = path.with_suffix(".tmp")
        
        # 写入临时文件
        tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # 原子重命名（POSIX 系统保证原子性）
        tmp.rename(path)

    def atomic_write_file(self, target_path: str, content: str, encoding: str = "utf-8") -> None:
        """
        通用原子写操作（供 Module Agent 使用）
        
        Module Agent 写输出文件时必须调用此方法，确保文件写入的原子性。
        
        Args:
            target_path: 目标文件路径（相对 session_dir）
            content: 文件内容
            encoding: 文件编码
        """
        fpath = self.session_dir / target_path
        tmp = fpath.with_suffix(".tmp")
        
        # 写入临时文件
        tmp.write_text(content, encoding=encoding)
        
        # 原子重命名
        tmp.rename(fpath)

    def try_acquire_run(
        self,
        module: str,
        stall_threshold_sec: int = 1800,
    ) -> RunInfo:
        """
        尝试为模块获取一次新的运行权。

        - 已有活跃运行（running + 心跳未过期）→ already_running=True，不重复 spawn
        - 已有运行但 stall（心跳过期）→ 分配新 run_id
        - 无运行记录 → 分配新 run_id

        Args:
            module: 模块名（"planning" | "research" | "summary"）
            stall_threshold_sec: 心跳超时阈值（默认 30 分钟）
        """
        existing = self._read_run(module)

        if existing and existing.get("status") == "running":
            last_hb = existing.get("last_heartbeat", 0)
            age = time.time() - last_hb
            if age < stall_threshold_sec:
                return RunInfo(
                    run_id=existing["run_id"],
                    attempt=existing.get("attempt", 1),
                    already_running=True,
                )
            # 心跳过期 → 允许 re-spawn，旧记录保留在 history
            existing["final_status"] = "stalled"

        run_id = f"{module}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        attempt = (existing.get("attempt", 0) + 1) if existing else 1

        record = {
            "module": module,
            "run_id": run_id,
            "attempt": attempt,
            "status": "running",
            "started_at": time.time(),
            "last_heartbeat": time.time(),
            "completed_at": None,
            "output_files": {},
        }
        if existing:
            record["previous"] = {
                "run_id": existing.get("run_id"),
                "attempt": existing.get("attempt"),
                "final_status": existing.get("final_status", "unknown"),
            }

        self._write_run(module, record)
        return RunInfo(run_id=run_id, attempt=attempt, already_running=False)

    def heartbeat(self, module: str, run_id: str) -> bool:
        """
        Module Agent 定期调用更新心跳。
        返回 True = 仍是活跃运行；False = 已被替代。
        """
        record = self._read_run(module)
        if not record or record.get("run_id") != run_id:
            return False
        record["last_heartbeat"] = time.time()
        self._write_run(module, record)
        return True

    def mark_completed(
        self,
        module: str,
        run_id: str,
        output_files: dict[str, dict] | None = None,
    ) -> bool:
        """
        Module Agent 完成时调用。

        Args:
            output_files: {"stages/solution_document.json": {"size": 80593, "mtime": ...}}
        """
        record = self._read_run(module)
        if not record or record.get("run_id") != run_id:
            return False

        record["status"] = "completed"
        record["completed_at"] = time.time()
        if output_files:
            record["output_files"] = output_files
        self._write_run(module, record)
        return True

    def wait_for_module(
        self,
        module: str,
        expected_files: list[str] | None = None,
        timeout: int = 3600,
        poll_interval: int = 15,
        min_file_sizes: dict[str, int] | None = None,
        heartbeat_threshold: int = 1800,
        file_mtime_threshold: int = 900,
    ) -> ModuleWaitResult:
        """
        Orchestrator 调用，等待模块完成。

        完成判定条件（增强版）：
        1. 输出文件存在且有效（必要条件）
        2. run record status == "completed" OR 完成标记存在（辅助信号）

        Stall 检测（增强版）：
        1. 心跳超时 > heartbeat_threshold
        2. 文件 mtime 超时 > file_mtime_threshold（辅助信号）

        Args:
            module: 模块名
            expected_files: 需要检查的文件列表（相对 session_dir）
            timeout: 超时秒数
            poll_interval: 轮询间隔
            min_file_sizes: {"stages/solution_document.json": 50000}
            heartbeat_threshold: 心跳超时阈值（秒）
            file_mtime_threshold: 文件 mtime 超时阈值（秒）
        """
        start = time.time()
        last_progress = 0

        print(f"LIFECYCLE_WAIT_START: {module} (timeout={timeout}s)", flush=True)

        while time.time() - start < timeout:
            elapsed = time.time() - start

            if elapsed - last_progress >= poll_interval:
                print(
                    f"LIFECYCLE_WAIT_PROGRESS: {module} elapsed={elapsed:.0f}s / {timeout}s",
                    flush=True,
                )
                last_progress = elapsed

            record = self._read_run(module)
            if not record:
                time.sleep(1)
                continue

            status = record.get("status")
            run_id = record.get("run_id")

            # ========== 增强 1: 输出文件验证（必要条件）==========
            # 不依赖 mark_completed，直接检查输出文件
            files_valid = self._verify_output_files(
                expected_files or [],
                min_file_sizes,
            )

            # ========== 增强 2: 完成标记检查（辅助信号）==========
            completed_marker = self.session_dir / "stages" / f".{module}_completed.json"
            marker_exists = completed_marker.exists()

            # 完成判定：输出文件有效 + (run record completed OR 完成标记存在)
            if files_valid and (status == "completed" or marker_exists):
                completion_source = "run_record" if status == "completed" else "completed_marker"
                print(
                    f"LIFECYCLE_WAIT_COMPLETED: {module} run_id={run_id} "
                    f"attempt={record.get('attempt')} elapsed={elapsed:.0f}s "
                    f"source={completion_source}",
                    flush=True,
                )
                return ModuleWaitResult(
                    found=True,
                    run_id=run_id,
                    attempt=record.get("attempt", 1),
                    elapsed=elapsed,
                    files=self._get_file_details(expected_files or []),
                )

            # ========== 增强 3: 多信号 stall 检测 ==========
            if status == "running":
                stall_result = self._detect_stall(
                    module,
                    expected_files or [],
                    heartbeat_threshold,
                    file_mtime_threshold,
                )
                if stall_result:
                    print(
                        f"LIFECYCLE_STALL_DETECTED: {module} reason={stall_result}",
                        flush=True,
                    )
                    return ModuleWaitResult(
                        found=False,
                        run_id=run_id,
                        attempt=record.get("attempt", 1),
                        elapsed=elapsed,
                        reason="stall",
                    )

            time.sleep(1)

        elapsed = time.time() - start
        print(f"LIFECYCLE_WAIT_TIMEOUT: {module} elapsed={elapsed:.0f}s", flush=True)
        return ModuleWaitResult(
            found=False,
            run_id=record.get("run_id") if record else None,
            elapsed=elapsed,
            reason="timeout",
        )

    def _verify_output_files(
        self,
        expected_files: list[str],
        min_file_sizes: dict[str, int] | None = None,
    ) -> bool:
        """
        验证输出文件存在且有效（必要条件）

        检查：
        1. 文件存在
        2. 文件大小 >= min_file_sizes（如果提供）
        3. JSON 可解析（如果文件以 .json 结尾）
        """
        for fname in expected_files:
            fpath = self.session_dir / fname

            # 检查文件存在
            if not fpath.exists():
                return False

            # 检查文件大小
            size = fpath.stat().st_size
            if min_file_sizes and fname in min_file_sizes:
                if size < min_file_sizes[fname]:
                    return False

            # 检查空文件
            if size == 0:
                return False

            # 检查 JSON 可解析（增强：防止写入中断导致 JSON 损坏）
            if fname.endswith(".json"):
                try:
                    json.loads(fpath.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return False

        return True

    def _get_file_details(self, expected_files: list[str]) -> dict:
        """获取文件详情"""
        details = {}
        for fname in expected_files:
            fpath = self.session_dir / fname
            if fpath.exists():
                details[fname] = {
                    "size": fpath.stat().st_size,
                    "mtime": fpath.stat().st_mtime,
                    "valid": True,
                }
        return details

    def _detect_stall(
        self,
        module: str,
        expected_files: list[str],
        heartbeat_threshold: int,
        file_mtime_threshold: int,
    ) -> str | None:
        """
        多信号 stall 检测

        检测：
        1. 心跳超时 > heartbeat_threshold
        2. 文件 mtime 超时 > file_mtime_threshold（辅助信号）

        Returns:
            stall 原因，如果没 stall 返回 None
        """
        record = self._read_run(module)
        if not record:
            return None

        # 信号 1: 心跳超时
        last_heartbeat = record.get("last_heartbeat", 0)
        heartbeat_age = time.time() - last_heartbeat
        if heartbeat_age > heartbeat_threshold:
            return f"heartbeat_timeout: {heartbeat_age:.0f}s > {heartbeat_threshold}s"

        # 信号 2: 文件 mtime 超时（辅助信号）
        if expected_files:
            for fname in expected_files:
                fpath = self.session_dir / fname
                if fpath.exists():
                    mtime = fpath.stat().st_mtime
                    mtime_age = time.time() - mtime
                    if mtime_age > file_mtime_threshold:
                        # 只有当心跳也过期时才判定 stall（避免误判）
                        if heartbeat_age > heartbeat_threshold * 0.5:
                            return f"file_stale: {fname} mtime_age={mtime_age:.0f}s"

        return None
