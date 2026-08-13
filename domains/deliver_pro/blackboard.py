"""
Deliver Pro Blackboard DAL — 数据访问层。

管理 Blackboard 目录结构和文件读写。
所有文件操作使用原子写入（先 .tmp 再 rename）。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional


class DeliverProBlackboard:
    """
    Deliver Pro Blackboard 数据访问层。

    目录结构：
    blackboard/{project_name}/deliver_pro/
    ├── data/              # WP 原始数据
    ├── stages/            # 各阶段输出
    └── stages/
        ├── worker_outputs/    # Worker 产出（按 task_id 分目录）
        ├── integrated_draft/  # Integrate 组装草稿
        └── final_deliverable/ # Package 最终交付物
    """

    def __init__(self, project_name: str, base_dir: Optional[Path] = None, wp_subdir: str = ""):
        """
        初始化 Blackboard。

        Args:
            project_name: 项目名称（用于构建路径）
            base_dir: 基础目录（默认为当前工作目录）
            wp_subdir: WP 子目录（Fix commit 3489118: 路径需包含 wp_subdir 层）
        """
        self.project_name = project_name
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        # Fix(commit 3489118): 路径必须包含 wp_subdir 层，与 wp_runner.py 对齐
        self.wp_subdir = wp_subdir
        self.root = self.base_dir / "blackboard" / project_name / "deliver_pro" / wp_subdir

        # 创建目录结构
        self._init_directories()

    def _init_directories(self) -> None:
        """创建必要的目录结构。"""
        dirs = [
            self.root / "data",
            self.root / "stages",
            self.root / "stages" / "worker_outputs",
            self.root / "stages" / "integrated_draft",
            self.root / "stages" / "final_deliverable",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def get_stage_path(self, stage: str) -> Path:
        """
        获取 stage 目录路径。

        Args:
            stage: 阶段名称（如 "analyze", "generate", "integrate"）

        Returns:
            stage 目录的 Path 对象
        """
        path = self.root / "stages" / stage
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_worker_output_dir(self, task_id: str) -> Path:
        """
        获取 Worker 输出目录。

        Args:
            task_id: 任务 ID

        Returns:
            Worker 输出目录的 Path 对象
        """
        path = self.root / "stages" / "worker_outputs" / task_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, stage: str, data: dict, filename: str) -> Path:
        """
        原子写入 JSON 文件。

        Args:
            stage: 阶段名称
            data: 要写入的数据（dict）
            filename: 文件名（如 "execution_plan.json"）

        Returns:
            写入的文件路径
        """
        target_dir = self.get_stage_path(stage)
        target = target_dir / filename

        # 原子写入：先写 .tmp，再 rename
        fd, tmp_path = tempfile.mkstemp(
            dir=target_dir,
            suffix=".tmp",
            prefix=f".{filename}_"
        )
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            os.write(fd, content)
            os.fsync(fd)
            os.close(fd)
            Path(tmp_path).rename(target)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(tmp_path).unlink(missing_ok=True)
            raise

        return target

    def load_json(self, stage: str, filename: str) -> Optional[dict]:
        """
        读取 JSON 文件。

        Args:
            stage: 阶段名称
            filename: 文件名

        Returns:
            dict 或 None（文件不存在时）
        """
        target = self.get_stage_path(stage) / filename
        if not target.exists():
            return None

        try:
            return json.loads(target.read_text(encoding="utf-8"))  # safe-json: 通用工具方法，解析失败显式 raise ValueError 由调用方处理（当前无生产调用方）
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Failed to load JSON from {target}: {e}") from e

    def save_file(self, stage: str, content: str, filename: str) -> Path:
        """
        原子写入文本文件。

        Args:
            stage: 阶段名称
            content: 文件内容
            filename: 文件名

        Returns:
            写入的文件路径
        """
        target_dir = self.get_stage_path(stage)
        target = target_dir / filename

        # 原子写入
        fd, tmp_path = tempfile.mkstemp(
            dir=target_dir,
            suffix=".tmp",
            prefix=f".{filename}_"
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            Path(tmp_path).rename(target)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(tmp_path).unlink(missing_ok=True)
            raise

        return target

    def load_file(self, stage: str, filename: str) -> Optional[str]:
        """
        读取文本文件。

        Args:
            stage: 阶段名称
            filename: 文件名

        Returns:
            文件内容或 None（文件不存在时）
        """
        target = self.get_stage_path(stage) / filename
        if not target.exists():
            return None

        try:
            return target.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"Failed to load file from {target}: {e}") from e

    def exists(self, stage: str, filename: str) -> bool:
        """
        检查文件是否存在。

        Args:
            stage: 阶段名称
            filename: 文件名

        Returns:
            True 如果文件存在
        """
        target = self.get_stage_path(stage) / filename
        return target.exists()

    @property
    def data_dir(self) -> Path:
        """data 目录路径。"""
        return self.root / "data"

    @property
    def stages_dir(self) -> Path:
        """stages 目录路径。"""
        return self.root / "stages"

    @property
    def worker_outputs_dir(self) -> Path:
        """worker_outputs 目录路径。"""
        return self.root / "stages" / "worker_outputs"

    @property
    def integrated_draft_dir(self) -> Path:
        """integrated_draft 目录路径。"""
        return self.root / "stages" / "integrated_draft"

    @property
    def final_deliverable_dir(self) -> Path:
        """final_deliverable 目录路径。"""
        return self.root / "stages" / "final_deliverable"


__all__ = ["DeliverProBlackboard"]
