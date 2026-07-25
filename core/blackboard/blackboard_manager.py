"""
BlackboardManager — 统一黑板管理器 

职责：Agent 间通过文件传递数据，session 状态持久化。
设计：内部字典 + 文件持久化，每个 session 独立目录。
     支持 DomainRegistry 集成，提供 stage 级读写。

变更:
- 新增 7 个 API: stage_exists, list_stages(v2), delete_stage,
  append_stage, read_stage_raw, get_session_dir, copy_stage
- write_stage 返回 bool + 原子写入 + log warning
- get_stage_path 标记 @deprecated
- list_stages 返回 list[str]（Breaking Change from v5）
- fire-and-forget → log warning（非静默）

Author: 小满
Date: 2026-06-23
"""

import json
import logging
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Type

from core.blackboard.registry_base import DomainRegistry

logger = logging.getLogger(__name__)


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
            session_id: 会话 ID（由 Orchestrator 生成）
            base_dir: 黑板根目录（默认使用 PathConfig）
            registry: 域路径注册表（可选）

        Raises:
            ValueError: session_id 为空
        """
        # 契约笼子：sanitize session_id，将 / 替换为 _，避免路径问题
        # 源头修复：所有下游代码不需要特殊处理斜杠
        session_id = session_id.replace("/", "_")
        
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
                # fallback: 硬编码路径（保留 + warning）
                logger.warning(
                    "PathConfig not available, using hardcoded fallback for base_dir"
                )
                base_dir = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"

        self._base = Path(base_dir)
        self._session_dir = self._base / session_id
        self._stages_dir = self._session_dir / "stages"

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_registry(self, registry: Type[DomainRegistry]) -> None:
        """设置域路径注册表"""
        self._registry = registry

    def init_session(self) -> Path:
        """创建 session 目录并初始化 shared_state。"""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._stages_dir.mkdir(exist_ok=True)
        sp = self._state_path()
        if not sp.exists():
            self._write_json(sp, {
                "session_id": self._session_id,
                "stage_history": [],
                "quality_scores": [],
                "convergence": {"converged": False, "round": 0}
            })
        return self._session_dir

    # ── Stage API（直接操作 stages/ 目录，不依赖 Registry）──

    def _stage_path(self, stage_name: str) -> Path:
        """获取 stage 文件路径（内部方法）"""
        return self._stages_dir / f"{stage_name}.json"

    def write_stage(self, stage_name: str, data: Dict[str, Any]) -> bool:
        """
        写入 stage 文件（覆盖写入，原子性）

        Args:
            stage_name: stage 名称，如 "planning", "research_expert_1"
            data: 要写入的数据（dict）

        Returns:
            bool: 写入是否成功

        注意:
            - 覆盖写入（非合并）
            - 使用 tempfile + fsync + rename 保证原子性
            - 失败时 log warning 并返回 False
        """
        try:
            self._stages_dir.mkdir(parents=True, exist_ok=True)
            file_path = self._stage_path(stage_name)

            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8',
                dir=self._stages_dir, delete=False, suffix='.tmp'
            ) as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = tmp.name

            os.replace(tmp_path, file_path)
            return True
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"write_stage failed for '{stage_name}': {e}")
            # 清理临时文件
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError as e:
                logger.debug(f"write_stage cleanup failed: {e}")
            return False

    def read_stage(self, stage_name: str, default: Optional[Dict] = None) -> Optional[Dict]:
        """
        读取 stage 文件

        Args:
            stage_name: stage 名称
            default: 文件不存在或读取失败时的默认值

        Returns:
            dict | None: 文件内容，或 default 参数，或 None
        """
        try:
            file_path = self._stage_path(stage_name)
            if not file_path.exists():
                return default
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"read_stage failed for '{stage_name}': {e}")
            return default

    def write_dynamic_stage(self, template: str, data: Dict[str, Any], **kwargs) -> bool:
        """
        写入动态命名的 stage

        Args:
            template: stage 名称模板，如 "research_expert_{expert_id}"
            data: 要写入的数据
            **kwargs: 模板参数

        Returns:
            bool: 写入是否成功
        """
        stage_name = template.format(**kwargs)
        return self.write_stage(stage_name, data)

    def stage_exists(self, stage_name: str) -> bool:
        """
        检查 stage 文件是否存在

        Args:
            stage_name: stage 名称

        Returns:
            bool: 文件是否存在
        """
        return self._stage_path(stage_name).exists()

    def list_stages(self) -> List[str]:
        """
        列出所有已存在的 stage 名称

        Returns:
            list[str]: stage 名称列表（仅已存在的）

        ⚠️ Breaking Change (from v5):
            v5 返回 Dict[str, bool]（所有注册的 stage + 存在状态）
            v6 返回 list[str]（仅已存在的 stage）
        """
        if not self._stages_dir.exists():
            return []
        return sorted([
            f.stem for f in self._stages_dir.iterdir()
            if f.is_file() and f.suffix == ".json"
        ])

    def delete_stage(self, stage_name: str) -> bool:
        """
        删除 stage 文件

        Args:
            stage_name: stage 名称

        Returns:
            bool: 删除是否成功（文件不存在也返回 True）
        """
        try:
            file_path = self._stage_path(stage_name)
            if file_path.exists():
                file_path.unlink()
            return True
        except OSError as e:
            logger.warning(f"delete_stage failed for '{stage_name}': {e}")
            return False

    def append_stage(self, stage_name: str, updates: Dict[str, Any]) -> bool:
        """
        增量更新 stage（read-modify-write 的原子操作）

        Args:
            stage_name: stage 名称
            updates: 要合并的字段（dict，浅合并）

        Returns:
            bool: 更新是否成功
        """
        try:
            existing = self.read_stage(stage_name, default={})
            existing.update(updates)
            return self.write_stage(stage_name, existing)
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"append_stage failed for '{stage_name}': {e}")
            return False

    def read_stage_raw(self, stage_name: str) -> Optional[str]:
        """
        读取 stage 文件的原始文本（非 JSON）

        Args:
            stage_name: stage 名称（自动尝试 .md, .txt, .json 后缀）

        Returns:
            str | None: 文件内容，或 None
        """
        try:
            for suffix in ['.md', '.txt', '.json', '']:
                file_path = self._stages_dir / f"{stage_name}{suffix}"
                if file_path.exists():
                    return file_path.read_text(encoding='utf-8')
            return None
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"read_stage_raw failed for '{stage_name}': {e}")
            return None

    def get_session_dir(self) -> Path:
        """
        获取 session 目录的 Path 对象

        用于写入非 stage 文件（如日志、临时文件）。
        不要用于构建 stage 路径（使用 write_stage 代替）。
        """
        return self._session_dir

    def copy_stage(self, from_name: str, to_name: str) -> bool:
        """
        复制 stage 文件（用于快照）

        Args:
            from_name: 源 stage 名称
            to_name: 目标 stage 名称

        Returns:
            bool: 复制是否成功
        """
        try:
            import shutil

            src_path = self._stage_path(from_name)
            dst_path = self._stage_path(to_name)

            if not src_path.exists():
                return False

            self._stages_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(
                mode='wb', dir=self._stages_dir, delete=False, suffix='.tmp'
            ) as tmp:
                shutil.copyfileobj(src_path.open('rb'), tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = tmp.name

            os.replace(tmp_path, dst_path)
            return True
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"copy_stage failed: '{from_name}' -> '{to_name}': {e}")
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError as e:
                logger.debug(f"copy_stage cleanup failed: {e}")
            return False

    # ── Registry 集成方法（向后兼容，逐步废弃）──

    def write_registry_stage(self, stage_name: str, data: Dict[str, Any]) -> Optional[Path]:
        """
        通过 Registry 写入 stage（向后兼容）

        ⚠️ 建议使用 write_stage() 代替
        """
        if self._registry is None:
            raise ValueError("Registry not set. Call set_registry() first.")
        relative_path = self._registry.get_path(stage_name)
        return self.write(relative_path, data)

    def read_registry_stage(self, stage_name: str, default: Optional[Dict] = None) -> Optional[Dict]:
        """
        通过 Registry 读取 stage（向后兼容）

        ⚠️ 建议使用 read_stage() 代替
        """
        if self._registry is None:
            raise ValueError("Registry not set. Call set_registry() first.")
        relative_path = self._registry.get_path(stage_name)
        return self.read_json(relative_path, default=default)

    def get_stage_path(self, stage_name: str) -> Path:
        """
        ⚠️ DEPRECATED: 获取 stage 文件的完整路径

        此方法暴露了路径细节，违反了"LLM 不应接触路径"原则。
        请使用 write_stage / read_stage 代替。

        将在 v7 中移除。
        """
        warnings.warn(
            "get_stage_path is deprecated. Use write_stage/read_stage instead. "
            "Will be removed in v7.",
            DeprecationWarning,
            stacklevel=2
        )
        if self._registry is not None:
            relative_path = self._registry.get_path(stage_name)
            return self._session_dir / relative_path
        return self._stage_path(stage_name)

    def list_stages_registry(self) -> Dict[str, bool]:
        """
        列出所有注册的 stage 及其存在状态（通过 Registry）

        ⚠️ Breaking Change: list_stages() 现在返回 list[str]
        此方法保留旧的 Dict[str, bool] 行为，用于向后兼容。

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
        """验证 Registry 完整性"""
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
            os.write(fd, data)
            os.fsync(fd)
            os.close(fd)
            Path(tmp).rename(target)
        except BaseException:
            try:
                os.close(fd)
            except OSError as e:
                logger.debug(f"write cleanup fd close failed: {e}")
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
        """读取文件内容（JSON）
        
        自动解包双重编码: 如果 json.loads() 结果是 str，再尝试一次 json.loads()。
        这样无论文件是正常 dict、纯 markdown string、还是双重编码，
        都能返回正确的结构化数据。
        """
        raw = self.read(filename, subdir)
        if raw is None:
            return default
        try:
            data = json.loads(raw)
            # Auto-unwrap double-encoded JSON (str wrapping dict/list)
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    pass  # Not double-encoded, return original str
            return data
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
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(tmp_fd, json.dumps(data, ensure_ascii=False, indent=2).encode())
            os.fsync(tmp_fd)
            os.close(tmp_fd)
            Path(tmp_path).rename(path)
        except BaseException:
            try:
                os.close(tmp_fd)
            except OSError as e:
                logger.debug(f"_write_json cleanup fd close failed: {e}")
            Path(tmp_path).unlink(missing_ok=True)
            raise
