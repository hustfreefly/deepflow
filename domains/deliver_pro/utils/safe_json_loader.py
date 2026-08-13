"""SafeJsonLoader — LLM 输出安全读取 + 熔断计数

设计原则（多专家审查共识）：
1. 只读 + 校验 + 返回结果，不写合成文件（合成由 synthesize_fallback 显式调用）
2. mtime 宽限：<60s 视为写入中，跳过不判（防竞态）
3. 异常分类：OSError → 重试（瞬态），ValidationError → 判死（逻辑）
4. 调用方决定 fallback 策略（Loader 不越界）
5. 熔断（2026-08-14 P1-C）：同一文件连续损坏 ≥ CIRCUIT_BREAKER_THRESHOLD 次
   → raise CircuitBreakerTripped。计数器是独立隐藏文件（.{name}.corrupt_count），
   不与被保护文件共享生命周期（教训：retry counter 必须独立文件）。
   成功读取自动清零。OSError（瞬态）与 write_in_progress 不计数。

使用示例：
    from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader, LoadResult
    from domains.deliver_pro.contracts.worker_task import WorkerOutputMeta
    
    result = SafeJsonLoader.load(path, WorkerOutputMeta)
    if result.state == "ok":
        manifest = result.parsed
    elif result.state == "invalid_json":
        # 调用方决定：合成 / 告警 / 重试
        ...
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Type

from pydantic import BaseModel, ValidationError


# 写入中宽限期（秒）— 文件 mtime 在此时间内视为正在被写入
WRITE_IN_PROGRESS_WINDOW_SECONDS = 60

# 熔断阈值：同一文件连续损坏达到此次数 → CircuitBreakerTripped
# 依据：LLM 持续产出坏 JSON = 系统性故障，重建-再损坏循环必须熔断待人工介入
CIRCUIT_BREAKER_THRESHOLD = 3


class CircuitBreakerTripped(Exception):
    """熔断触发：同一文件连续损坏达到阈值。

    契约笼子哲学：raise error > 文档声明。持续损坏不允许静默继续。
    """

    def __init__(self, path: Path, count: int, threshold: int = CIRCUIT_BREAKER_THRESHOLD):
        self.path = path
        self.count = count
        self.threshold = threshold
        super().__init__(
            f"Circuit breaker tripped: {path} corrupted {count} consecutive times "
            f"(threshold={threshold}). 项目已冻结，排查后运行 "
            f"`python3 -m domains.deliver_pro.pulse_cli unfreeze --project <name>` 恢复。"
        )


def corruption_counter_path(path: Path) -> Path:
    """熔断计数器文件路径（独立隐藏文件，与被保护文件同目录）。"""
    return path.parent / f".{path.name}.corrupt_count"


def _record_corruption(path: Path) -> int:
    """记录一次损坏，返回连续损坏次数。"""
    counter_file = corruption_counter_path(path)
    try:
        count = int(counter_file.read_text().strip()) + 1
    except (OSError, ValueError):
        count = 1
    try:
        counter_file.write_text(str(count))
    except OSError:
        pass  # 计数器写失败不阻塞主流程（下次重新从 1 计）
    return count


def _reset_corruption(path: Path) -> None:
    """成功读取 → 清零连续损坏计数。"""
    try:
        corruption_counter_path(path).unlink(missing_ok=True)
    except OSError:
        pass


@dataclass
class LoadResult:
    """JSON 加载结果（纯数据，无副作用）"""
    
    data: Optional[dict] = None
    """原始 JSON 数据（解析成功时）"""
    
    parsed: Optional[BaseModel] = None
    """Pydantic 对象（schema 校验通过时）"""
    
    state: Literal["ok", "not_found", "write_in_progress", "invalid_json", "schema_validation_failed"] = "ok"
    """加载状态：
    - ok: 成功
    - not_found: 文件不存在
    - write_in_progress: 文件正在被写入（mtime < 60s）
    - invalid_json: JSON 解析失败
    - schema_validation_failed: Pydantic 校验失败
    """
    
    error: Optional[str] = None
    """错误信息（state != ok 时）"""
    
    backup_path: Optional[Path] = None
    """损坏文件的备份路径（invalid_json/schema_validation_failed 时）"""


class SafeJsonLoader:
    """LLM 输出安全加载器（纯函数）"""
    
    @staticmethod
    def load(
        path: Path,
        schema_cls: Optional[Type[BaseModel]] = None,
        mtime_window: int = WRITE_IN_PROGRESS_WINDOW_SECONDS,
    ) -> LoadResult:
        """读取 JSON 文件并用 Pydantic 校验。
        
        Args:
            path: JSON 文件路径
            schema_cls: Pydantic model 类（可选，不传则只做 JSON 解析）
            mtime_window: 写入中宽限期（秒），默认 60s
        
        Returns:
            LoadResult — 调用方根据 state 决定 fallback 策略
        
        行为：
        1. 文件不存在 → state="not_found"
        2. mtime < mtime_window → state="write_in_progress"（跳过不判）
        3. JSON 解析失败 → state="invalid_json" + 备份原文件到 .corrupted
        4. Schema 校验失败 → state="schema_validation_failed" + 备份
        5. 成功 → state="ok" + parsed=obj
        """
        if not path.exists():
            return LoadResult(state="not_found")
        
        # mtime 宽限：文件正在被写入，跳过不判（防竞态）
        try:
            mtime = path.stat().st_mtime
            # MagicMock 兼容：mock 环境下 mtime 可能不是数字
            if isinstance(mtime, (int, float)) and time.time() - mtime < mtime_window:
                return LoadResult(state="write_in_progress", error=f"mtime={mtime} is within {mtime_window}s window")
        except OSError as e:
            # stat 失败不影响主流程，继续尝试读取
            pass
        
        # 读取 + JSON 解析
        try:
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text)  # safe-json: SafeJsonLoader 本体，损坏处理见下方分支
        except json.JSONDecodeError as e:
            # JSON 损坏 → 备份 + 熔断计数 + 返回错误
            backup = _backup_corrupted_file(path)
            count = _record_corruption(path)
            if count >= CIRCUIT_BREAKER_THRESHOLD:
                raise CircuitBreakerTripped(path, count) from e
            return LoadResult(state="invalid_json", error=str(e), backup_path=backup)
        except OSError as e:
            # I/O 错误（瞬态）→ 不备份、不计数，返回错误让调用方重试
            return LoadResult(state="invalid_json", error=f"OSError: {e}")
        
        # Schema 校验（如果提供了 schema_cls）
        if schema_cls is not None:
            try:
                parsed = schema_cls.model_validate(data)
                _reset_corruption(path)
                return LoadResult(data=data, parsed=parsed, state="ok")
            except ValidationError as e:
                # Schema 校验失败 → 备份 + 熔断计数 + 返回错误
                backup = _backup_corrupted_file(path)
                count = _record_corruption(path)
                if count >= CIRCUIT_BREAKER_THRESHOLD:
                    raise CircuitBreakerTripped(path, count) from e
                return LoadResult(
                    data=data,
                    state="schema_validation_failed",
                    error=str(e),
                    backup_path=backup,
                )
        
        # 无 schema 或校验通过 → 清零熔断计数
        _reset_corruption(path)
        return LoadResult(data=data, state="ok")
    
    @staticmethod
    def load_raw(
        path: Path,
        mtime_window: int = WRITE_IN_PROGRESS_WINDOW_SECONDS,
    ) -> LoadResult:
        """读取 JSON 文件（只做 JSON 解析，不做 Pydantic 校验）。
        
        这是 load() 的简化版本，适用于没有 Pydantic schema 的场景。
        
        Args:
            path: JSON 文件路径
            mtime_window: 写入中宽限期（秒），默认 60s
        
        Returns:
            LoadResult — 调用方根据 state 决定 fallback 策略
        """
        return SafeJsonLoader.load(path, schema_cls=None, mtime_window=mtime_window)
    
    @staticmethod
    def synthesize_fallback(path: Path, template: dict) -> None:
        """写合成 fallback 文件（独立方法，调用方显式选择）。
        
        注意：这不是 load() 的一部分，而是独立的业务决策。
        调用方必须明确知道自己在做什么。
        
        Args:
            path: 目标路径
            template: 合成内容模板
        """
        from domains.deliver_pro.contracts.atomic_io import atomic_write_json
        atomic_write_json(path, template)


def _backup_corrupted_file(path: Path) -> Optional[Path]:
    """备份损坏文件到 .corrupted.{timestamp}
    
    Returns:
        备份路径，如果备份失败则返回 None
    """
    try:
        timestamp = int(time.time())
        backup = path.with_suffix(f".corrupted.{timestamp}")
        shutil.move(str(path), str(backup))
        return backup
    except OSError:
        return None
