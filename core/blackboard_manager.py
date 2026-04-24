"""
BlackboardManager — V1.0 内部字典 + 文件持久化

职责：Agent 间通过文件传递数据，session 状态持久化。
设计：简化为内部字典 + 文件持久化，每个 session 独立目录。

Author: 小满
Date: 2026-04-18
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union


class BlackboardManager:
    """Agent 间文件通信 + 状态持久化。"""

    def __init__(self, session_id: str, base_dir: Optional[Path] = None) -> None:
        if not session_id:
            raise ValueError("session_id must not be empty")
        self._session_id = session_id
        self._base = base_dir or (Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard")
        self._session_dir = self._base / session_id

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    def init_session(self) -> Path:
        """创建 session 目录并初始化 shared_state。"""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        sp = self._state_path()
        if not sp.exists():
            self._write_json(sp, {"session_id": self._session_id, "stage_history": [],
                                  "quality_scores": [], "convergence": {"converged": False, "round": 0}})
        return self._session_dir

    # ── 文件读写 ──

    def write(self, filename: str, content: Union[str, Dict[str, Any]], subdir: Optional[str] = None) -> Path:
        """原子写入（临时文件 → fsync → 重命名）。"""
        target = self._resolve(filename, subdir)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            data = json.dumps(content, ensure_ascii=False, indent=2).encode() if isinstance(content, dict) else content.encode()
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
        target = self._resolve(filename, subdir)
        if not target.exists():
            return default
        try:
            return target.read_text(encoding="utf-8")
        except OSError:
            return default

    def read_json(self, filename: str, subdir: Optional[str] = None, default: Optional[Dict] = None) -> Optional[Dict]:
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
        return self._read_shared()

    # ── 清理 ──

    def cleanup(self) -> bool:
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
