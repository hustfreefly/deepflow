"""
ProcessManager — 最小原语：wait_for

替代 spawn-yield 的被动等待，提供阻塞式文件等待。
LLM 调用方式：exec: pm.wait_for("stages/xxx.json", timeout=1800)

返回原始状态（不是 action 指令），LLM 基于结果做语义判断。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WaitResult:
    """wait_for 返回的原始状态（LLM 基于此做语义判断）"""
    found: bool
    path: str
    elapsed: float
    timeout: int
    file_size: int | None = None
    file_mtime: float | None = None
    # 额外诊断信息（供 LLM 判断）
    exists_but_empty: bool = False
    exists_but_invalid_json: bool = False

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "path": self.path,
            "elapsed": round(self.elapsed, 1),
            "timeout": self.timeout,
            "file_size": self.file_size,
            "file_mtime": self.file_mtime,
            "exists_but_empty": self.exists_but_empty,
            "exists_but_invalid_json": self.exists_but_invalid_json,
        }


class ProcessManager:
    """
    过程管理器（最小原语）

    职责：阻塞式等待文件出现，返回原始状态。
    不做调度决策（那是 LLM 的事）。

    用法（Orchestrator 在 exec 中调用）:
        pm = ProcessManager("/path/to/blackboard/session")
        result = pm.wait_for("stages/planning_convergence.json", timeout=1800)
        # result.found=True → 文件出现，LLM 读取并验证
        # result.found=False → 超时，LLM 决定 RESPAWN 或 FAIL
    """

    def __init__(self, session_dir: str | Path):
        self.session_dir = Path(session_dir)

    def wait_for(
        self,
        path: str,
        timeout: int = 1800,
        poll_interval: int = 15,
        min_size: int = 0,
        validate_json: bool = False,
    ) -> WaitResult:
        """
        阻塞式等待文件出现。

        Args:
            path: 相对于 session_dir 的文件路径
            timeout: 超时秒数（默认 30 分钟）
            poll_interval: 轮询间隔秒数（默认 15s，防 stuck abort）
            min_size: 最小文件大小（字节），0 表示不检查
            validate_json: 是否验证 JSON 可解析

        Returns:
            WaitResult（原始状态，LLM 做判断）
        """
        target = self.session_dir / path
        start = time.time()
        last_progress = 0

        print(f"WAIT_FOR_START: {path} (timeout={timeout}s)", flush=True)

        while time.time() - start < timeout:
            elapsed = time.time() - start

            # 定期输出进度（防 stuck abort，spike 验证每 15s 有效）
            if elapsed - last_progress >= poll_interval:
                print(f"WAIT_FOR_PROGRESS: {path} elapsed={elapsed:.0f}s / {timeout}s", flush=True)
                last_progress = elapsed

            # 检查文件
            if target.exists():
                size = target.stat().st_size
                mtime = target.stat().st_mtime

                # 检查最小大小
                if size < min_size:
                    time.sleep(1)
                    continue

                # 检查空文件
                if size == 0:
                    return WaitResult(
                        found=True, path=path, elapsed=elapsed, timeout=timeout,
                        file_size=0, file_mtime=mtime, exists_but_empty=True,
                    )

                # 验证 JSON
                if validate_json:
                    try:
                        json.loads(target.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        time.sleep(1)  # 可能正在写入，等一下
                        continue

                print(f"WAIT_FOR_FOUND: {path} elapsed={elapsed:.0f}s size={size}", flush=True)
                return WaitResult(
                    found=True, path=path, elapsed=elapsed, timeout=timeout,
                    file_size=size, file_mtime=mtime,
                )

            time.sleep(1)

        elapsed = time.time() - start
        print(f"WAIT_FOR_TIMEOUT: {path} elapsed={elapsed:.0f}s", flush=True)
        return WaitResult(
            found=False, path=path, elapsed=elapsed, timeout=timeout,
        )

    def check(self, path: str, min_size: int = 0, validate_json: bool = False) -> WaitResult:
        """
        立即检查文件（非阻塞）。

        Returns:
            WaitResult（elapsed=0 表示立即返回）
        """
        target = self.session_dir / path

        if not target.exists():
            return WaitResult(found=False, path=path, elapsed=0, timeout=0)

        size = target.stat().st_size
        mtime = target.stat().st_mtime

        if size < min_size:
            return WaitResult(
                found=False, path=path, elapsed=0, timeout=0,
                file_size=size, file_mtime=mtime,
            )

        if size == 0:
            return WaitResult(
                found=True, path=path, elapsed=0, timeout=0,
                file_size=0, file_mtime=mtime, exists_but_empty=True,
            )

        if validate_json:
            try:
                json.loads(target.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return WaitResult(
                    found=True, path=path, elapsed=0, timeout=0,
                    file_size=size, file_mtime=mtime, exists_but_invalid_json=True,
                )

        return WaitResult(
            found=True, path=path, elapsed=0, timeout=0,
            file_size=size, file_mtime=mtime,
        )

    def wait_for_any(
        self,
        paths: list[str],
        timeout: int = 1800,
        poll_interval: int = 15,
    ) -> WaitResult:
        """等待任一文件出现（用于并行 worker 场景）"""
        start = time.time()
        last_progress = 0

        print(f"WAIT_FOR_ANY_START: {len(paths)} files (timeout={timeout}s)", flush=True)

        while time.time() - start < timeout:
            elapsed = time.time() - start

            if elapsed - last_progress >= poll_interval:
                print(f"WAIT_FOR_ANY_PROGRESS: elapsed={elapsed:.0f}s / {timeout}s", flush=True)
                last_progress = elapsed

            for path in paths:
                result = self.check(path)
                if result.found:
                    print(f"WAIT_FOR_ANY_FOUND: {path} elapsed={elapsed:.0f}s", flush=True)
                    return result

            time.sleep(1)

        elapsed = time.time() - start
        print(f"WAIT_FOR_ANY_TIMEOUT: elapsed={elapsed:.0f}s", flush=True)
        return WaitResult(found=False, path="(any)", elapsed=elapsed, timeout=timeout)

    def wait_for_all(
        self,
        paths: list[str],
        timeout: int = 1800,
        poll_interval: int = 15,
    ) -> dict[str, WaitResult]:
        """等待所有文件出现，返回每个文件的状态"""
        start = time.time()
        last_progress = 0
        results: dict[str, WaitResult] = {}
        remaining = set(paths)

        print(f"WAIT_FOR_ALL_START: {len(paths)} files (timeout={timeout}s)", flush=True)

        while time.time() - start < timeout and remaining:
            elapsed = time.time() - start

            if elapsed - last_progress >= poll_interval:
                done = len(paths) - len(remaining)
                print(f"WAIT_FOR_ALL_PROGRESS: {done}/{len(paths)} done, elapsed={elapsed:.0f}s / {timeout}s", flush=True)
                last_progress = elapsed

            for path in list(remaining):
                result = self.check(path)
                if result.found:
                    results[path] = result
                    remaining.discard(path)
                    print(f"WAIT_FOR_ALL_FOUND: {path} elapsed={elapsed:.0f}s", flush=True)

            if remaining:
                time.sleep(1)

        # 超时的文件标记为 not found
        elapsed = time.time() - start
        for path in remaining:
            results[path] = WaitResult(found=False, path=path, elapsed=elapsed, timeout=timeout)

        print(f"WAIT_FOR_ALL_DONE: {len(paths) - len(remaining)}/{len(paths)} found, elapsed={elapsed:.0f}s", flush=True)
        return results
