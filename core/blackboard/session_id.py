"""
统一 session_id 生成器 — 全域共用

职责:
- 生成纯 ASCII 的 session_id（避免中文编码问题）
- 格式: {domain}_{hash8}（如 solution_a1b2c3d4）
- 跨平台安全（无特殊字符）

各域调用此模块生成 session_id，不再各自拼接。

Version: 2.0.0
Author: DeepFlow
Date: 2026-06-22
"""

import hashlib
import re
import time
from typing import Optional


# 允许的域前缀
VALID_DOMAINS = {"solution_pro", "ship_pro", "spec_pro", "research_pro"}

# session_id 最大长度（防 DoS，与 PathConfig.MAX_SESSION_ID_LENGTH 对齐）
MAX_LENGTH = 255


def generate_session_id(
    domain: str,
    topic: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    """
    生成纯 ASCII session_id

    格式: {domain}_{hash8}
    示例: solution_a1b2c3d4, ship_e5f6g7h8

    Args:
        domain: 域名称（solution / ship / spec / research）
        topic: 主题字符串（用于生成 hash，可选）
        suffix: 额外后缀（可选，如 run_id）

    Returns:
        纯 ASCII session_id

    Raises:
        ValueError: domain 不在允许列表中
    """
    # 验证 domain
    if domain not in VALID_DOMAINS:
        raise ValueError(
            f"Invalid domain: '{domain}'. Must be one of: {sorted(VALID_DOMAINS)}"
        )

    # 生成 hash
    hash_input = topic or f"{domain}_{time.time()}"
    hash_value = hashlib.md5(hash_input.encode("utf-8")).hexdigest()[:8]

    # 组合 session_id
    session_id = f"{domain}_{hash_value}"

    # 添加后缀（如果有）
    if suffix:
        session_id = f"{session_id}_{suffix}"

    # 长度检查
    if len(session_id) > MAX_LENGTH:
        session_id = session_id[:MAX_LENGTH]

    return session_id


def generate_run_id(domain: str, fmt: str = "d") -> str:
    """
    生成 run_id（用于 Ship Pro 等流水线）

    格式: run_{timestamp}_{fmt}
    示例: run_20260622_191324_d

    Args:
        domain: 域名称
        fmt: 格式标识（a/b/c/d）

    Returns:
        run_id 字符串
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{timestamp}_{fmt.lower()}"


def sanitize_topic(topic: str, max_len: int = 50) -> str:
    """
    清理 topic 字符串（用于生成 hash 前的预处理）

    - 去除特殊字符
    - 保留字母、数字、中文、hyphen
    - 截断到 max_len

    Args:
        topic: 原始 topic
        max_len: 最大长度

    Returns:
        清理后的 topic
    """
    # 去除特殊字符，保留字母、数字、中文、hyphen
    sanitized = re.sub(r"[^\w\u4e00-\u9fff-]", "-", topic.lower().strip())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    sanitized = sanitized[:max_len]
    return sanitized or "untitled"
