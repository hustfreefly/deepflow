"""
DomainRegistry 基类 — 所有域的路径注册表必须继承此类

职责:
- 定义 STAGE_PATH_REGISTRY 接口规范
- 提供路径获取、验证、完整性检查
- 强制命名规则（纯 ASCII、无嵌套 blackboard）

各域只需定义自己的 STAGE_PATH_REGISTRY，
读写逻辑由 core/blackboard/blackboard_manager.py 统一提供。

Version: 2.0.0
Author: DeepFlow
Date: 2026-06-22
"""

from pathlib import Path
from typing import Dict, List, Optional


class DomainRegistry:
    """
    域路径注册表基类

    子类必须定义:
        STAGE_PATH_REGISTRY: Dict[str, str]

    示例:
        class SolutionRegistry(DomainRegistry):
            STAGE_PATH_REGISTRY = {
                "planning": "stages/planning.json",
                "audit": "stages/audit.json",
            }
    """

    STAGE_PATH_REGISTRY: Dict[str, str] = {}

    @classmethod
    def get_path(cls, stage_name: str) -> str:
        """
        从注册表获取路径（相对路径）

        Args:
            stage_name: 阶段名称

        Returns:
            相对路径字符串

        Raises:
            ValueError: stage_name 不在注册表中
        """
        if stage_name not in cls.STAGE_PATH_REGISTRY:
            available = list(cls.STAGE_PATH_REGISTRY.keys())
            raise ValueError(f"Unknown stage: '{stage_name}'. Available: {available}")
        return cls.STAGE_PATH_REGISTRY[stage_name]

    @classmethod
    def get_all_stages(cls) -> List[str]:
        """返回所有已注册的阶段名称"""
        return list(cls.STAGE_PATH_REGISTRY.keys())

    @classmethod
    def has_stage(cls, stage_name: str) -> bool:
        """检查阶段是否已注册"""
        return stage_name in cls.STAGE_PATH_REGISTRY

    @classmethod
    def validate(cls) -> List[str]:
        """
        验证注册表完整性

        检查:
        - 所有路径为纯 ASCII（避免中文编码问题）
        - 无嵌套 blackboard/ 目录
        - 无重复路径值
        - 路径不以 / 开头（相对路径）

        Returns:
            错误列表，空列表表示通过
        """
        errors = []

        # 检查注册表非空
        if not cls.STAGE_PATH_REGISTRY:
            errors.append("STAGE_PATH_REGISTRY is empty")
            return errors

        # 检查每个条目
        seen_paths = set()
        for name, path in cls.STAGE_PATH_REGISTRY.items():
            # 纯 ASCII
            if not path.isascii():
                errors.append(f"Non-ASCII path in '{name}': {path}")

            # 无嵌套 blackboard
            if "blackboard/" in path or path.startswith("blackboard"):
                errors.append(f"Nested blackboard in '{name}': {path}")

            # 相对路径（不以 / 开头）
            if path.startswith("/"):
                errors.append(f"Absolute path in '{name}': {path}")

            # 无重复路径
            if path in seen_paths:
                errors.append(f"Duplicate path in '{name}': {path}")
            seen_paths.add(path)

        return errors

    @classmethod
    def get_output_path(cls, base_path: Path, stage_name: str) -> Path:
        """
        获取 stage 输出的完整路径

        Args:
            base_path: blackboard 根目录
            stage_name: 阶段名称

        Returns:
            完整文件路径
        """
        relative = cls.get_path(stage_name)
        return base_path / relative
