"""
spawn_fn 统一解析模块

本模块提供统一的 spawn_fn 解析逻辑，避免各模块重复实现。

**设计原则**:
- 子 Agent 环境中必须返回 None（不崩溃）
- 主 Agent 环境中返回 sessions_spawn（如果可用）
- 所有模块必须使用本模块的 resolve_spawn_fn()

**契约笼子**: 2026-05-31 创建
"""

from typing import Optional, Callable


def resolve_spawn_fn() -> Optional[Callable]:
    """
    解析 spawn_fn 函数
    
    Returns:
        Callable: sessions_spawn 函数（如果在主 Agent 环境中）
        None: 如果在子 Agent 环境中或 sessions_spawn 不可用
    
    注意:
        - 子 Agent 环境中调用此函数不会崩溃
        - 返回 None 时，调用方应该优雅降级
    """
    try:
        # 尝试导入 sessions_spawn
        from openclaw import sessions_spawn
        
        # 验证是否可用
        if callable(sessions_spawn):
            return sessions_spawn
        else:
            return None
            
    except ImportError:
        # 子 Agent 环境中 openclaw 不可用
        return None
    except Exception:
        # 其他异常情况
        return None


def is_spawn_available() -> bool:
    """
    检查 spawn_fn 是否可用
    
    Returns:
        bool: True 如果 spawn_fn 可用，False 否则
    """
    return resolve_spawn_fn() is not None


def require_spawn_fn() -> Callable:
    """
    获取 spawn_fn，如果不可用则抛出异常
    
    Returns:
        Callable: sessions_spawn 函数
        
    Raises:
        RuntimeError: 如果 spawn_fn 不可用
    """
    spawn_fn = resolve_spawn_fn()
    if spawn_fn is None:
        raise RuntimeError(
            "spawn_fn 不可用。请确保在主 Agent 环境中运行。\n"
            "如果是子 Agent，请使用 sessions_spawn 工具调用。"
        )
    return spawn_fn
