"""
BlackboardManager — 统一黑板管理器

职责：Agent 间通过文件传递数据，session 状态持久化。
设计：内部字典 + 文件持久化，每个 session 独立目录。
     支持 DomainRegistry 集成，提供 stage 级读写。

变更:
- 集成 DomainRegistry，提供 write_stage/read_stage
- 使用 PathConfig 获取默认 base_dir
- 基础文件读写 + shared_state

Author: 小满
Date: 2026-06-22
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union, Type

from core.blackboard.registry_base import DomainRegistry


class BlackboardManager:
    """Agent 间文件通信 + 状态持久化 + Registry 集成。"""

    def __init__(
        self,
        session_id: str,
        base_dir: Optional[Path] = None,
        registry: Optional[Type[DomainRegistry]] = None,
    ) -> None:
        """
        初始化 BlackboardManager

        Args:
            session_id: 会话 ID
            base_dir: 黑板根目录（默认使用 PathConfig）
            registry: 域路径注册表（可选）
        """
        if not session_id:
            raise ValueError("session_id must not be empty")

        self._session_id = session_id
        self._registry = registry

        # 使用 PathConfig 获取默认 base_dir
        if base_dir is None:
            try:
                from core.config.path_config import PathConfig
                config = PathConfig.resolve()
                base_dir = config.blackboard_dir
            except (ImportError, RuntimeError):
                # fallback: 硬编码路径
                base_dir = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"

        self._base = Path(base_dir)
        self._session_dir = self._base / session_id

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_registry(self, registry: Type[DomainRegistry]) -> None:
        """
        设置域路径注册表

        Args:
            registry: DomainRegistry 子类
        """
        self._registry = registry

    def init_session(self) -> Path:
        """创建 session 目录并初始化 shared_state。"""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        sp = self._state_path()
        if not sp.exists():
            self._write_json(sp, {
                "session_id": self._session_id,
                "stage_history": [],
                "quality_scores": [],
                "convergence": {"converged": False, "round": 0}
            })
        return self._session_dir

    # ── Registry 集成方法 ──

    def write_stage(self, stage_name: str, data: Dict[str, Any]) -> Path:
        """
        写入 stage 输出（通过 Registry 获取路径）

        Args:
            stage_name: 阶段名称（如 'planning', 'audit'）
            data: stage 输出数据

        Returns:
            写入的文件路径

        Raises:
            ValueError: 未设置 Registry 或 stage_name 不在注册表中
        """
        if self._registry is None:
            raise ValueError("Registry not set. Call set_registry() first.")

        relative_path = self._registry.get_path(stage_name)
        return self.write(relative_path, data)

    def read_stage(self, stage_name: str, default: Optional[Dict] = None) -> Optional[Dict]:
        """
        读取 stage 输出（通过 Registry 获取路径）

        Args:
            stage_name: 阶段名称
            default: 文件不存在时的默认值

        Returns:
            stage 数据（dict）或 default
        """
        if self._registry is None:
            raise ValueError("Registry not set. Call set_registry() first.")

        relative_path = self._registry.get_path(stage_name)
        return self.read_json(relative_path, default=default)

    def get_stage_path(self, stage_name: str) -> Path:
        """
        获取 stage 文件的完整路径

        Args:
            stage_name: 阶段名称

        Returns:
            完整文件路径
        """
        if self._registry is None:
            raise ValueError("Registry not set. Call set_registry() first.")

        relative_path = self._registry.get_path(stage_name)
        return self._session_dir / relative_path

    def list_stages(self) -> Dict[str, bool]:
        """
        列出所有 stage 及其存在状态

        Returns:
            {stage_name: exists}
        """
        if self._registry is None:
            return {}

        result = {}
        for stage_name in self._registry.get_all_stages():
            path = self.get_stage_path(stage_name)
            result[stage_name] = path.exists()
        return result

    def validate_registry(self) -> list:
        """
        验证 Registry 完整性

        Returns:
            错误列表，空列表表示通过
        """
        if self._registry is None:
            return ["Registry not set"]
        return self._registry.validate()

    # ── 基础文件读写（向后兼容）──

    def write(self, filename: str, content: Union[str, Dict[str, Any]], subdir: Optional[str] = None) -> Path:
        """原子写入（临时文件 → fsync → 重命名）。"""
        target = self._resolve(filename, subdir)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            if isinstance(content, dict):
                data = json.dumps(content, ensure_ascii=False, indent=2).encode()
            else:
                data = content.encode()
            import os
            os.write(fd, data)
            os.fsync(fd)
            os.close(fd)
            Path(tmp).rename(target)
        except BaseException:
            import os
            try:
                os.close(fd)
            except OSError:
                pass
            Path(tmp).unlink(missing_ok=True)
            raise
        return target

    def read(self, filename: str, subdir: Optional[str] = None, default: Optional[str] = None) -> Optional[str]:
        """读取文件内容（文本）"""
        target = self._resolve(filename, subdir)
        if not target.exists():
            return default
        try:
            return target.read_text(encoding="utf-8")
        except OSError:
            return default

    def read_json(self, filename: str, subdir: Optional[str] = None, default: Optional[Dict] = None) -> Optional[Dict]:
        """读取文件内容（JSON）"""
        raw = self.read(filename, subdir)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    # ── 共享状态 ──

    def append_state(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """合并更新 shared_state。"""
        from datetime import datetime
        state = self._read_shared()
        state.update(updates)
        state["updated_at"] = datetime.now().isoformat()
        self._write_shared(state)
        return state

    def get_state(self) -> Dict[str, Any]:
        """读取 shared_state"""
        return self._read_shared()

    # ── 清理 ──

    def cleanup(self) -> bool:
        """删除 session 目录"""
        import shutil
        if self._session_dir.exists():
            try:
                shutil.rmtree(self._session_dir)
                return True
            except OSError:
                return False
        return False

    # ── 内部方法 ──

    def _resolve(self, filename: str, subdir: Optional[str]) -> Path:
        base = self._session_dir / subdir if subdir else self._session_dir
        return base / filename

    def _state_path(self) -> Path:
        return self._session_dir / "shared_state.json"

    def _read_shared(self) -> Dict[str, Any]:
        return self.read_json("shared_state.json", default={})

    def _write_shared(self, state: Dict[str, Any]) -> None:
        self.write("shared_state.json", state)

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any]) -> None:
        import os
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(tmp_fd, json.dumps(data, ensure_ascii=False, indent=2).encode())
            os.fsync(tmp_fd)
            os.close(tmp_fd)
            Path(tmp_path).rename(path)
        except BaseException:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
            Path(tmp_path).unlink(missing_ok=True)
            raise
