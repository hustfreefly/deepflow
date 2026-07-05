"""
DeepFlow 环境引导 — 确保 .deepflow 在 sys.path 中

所有域的脚本入口、exec 命令、子 Agent 的 Python 调用
都应通过此模块确保 import 路径正确。

用法:
    import core.bootstrap  # 自动将 .deepflow 加入 sys.path
    from domains.solution_pro.xxx import yyy  # 现在可以正常 import

跨平台: Windows / macOS / Linux 均兼容
幂等: 多次 import 不会重复添加

Version: 2.0.0
Author: DeepFlow
Date: 2026-06-22
"""

import sys
from pathlib import Path

# 基于 __file__ 推导 .deepflow 根目录（跨平台安全）
_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent
_DEEPFLOW_ROOT_STR = str(_DEEPFLOW_ROOT)


def bootstrap() -> None:
    """将 .deepflow 加入 sys.path（幂等）"""
    if _DEEPFLOW_ROOT_STR not in sys.path:
        sys.path.insert(0, _DEEPFLOW_ROOT_STR)


# 模块导入时自动执行
bootstrap()


def get_deepflow_root() -> Path:
    """获取 .deepflow 根目录路径"""
    return _DEEPFLOW_ROOT
