"""
DDGS (DuckDuckGo Search) 客户端模块。

替代原先 orchestrator.py 中通过 subprocess 调用 DDGS 的方式。
直接 import 调用，避免 subprocess 代码注入风险和进程管理开销。

DDGS 是 Research Pro 的 **备选搜索引擎**（fallback）。
主搜索引擎是 OpenClaw 的 web_search 工具（通过子 Agent 调用）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# DDGS 超时（秒）
DDGS_TIMEOUT_SECONDS = 12


def search_ddgs(query: str, max_results: int = 5, timeout: int = DDGS_TIMEOUT_SECONDS) -> list[dict[str, str]]:
    """通过 DuckDuckGo Search 搜索。

    Args:
        query: 搜索关键词
        max_results: 最大结果数
        timeout: 超时秒数（仅作为参考，DDGS 库自身有超时机制）

    Returns:
        [{"url": str, "title": str, "snippet": str}, ...]
        失败时返回空列表。
    """
    try:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            try:
                from ddgs import DDGS  # type: ignore[no-redef]
            except ImportError:
                logger.warning("duckduckgo-search 未安装，DDGS 搜索不可用")
                return []

        output: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                url = item.get("href") or item.get("url") or ""
                title = item.get("title") or query
                snippet = item.get("body") or item.get("snippet") or ""
                if url:
                    output.append({
                        "url": str(url),
                        "title": str(title),
                        "snippet": str(snippet),
                    })
        return output

    except Exception as exc:
        logger.warning("DDGS 搜索失败 (%s): %s", query[:80], exc)
        return []
