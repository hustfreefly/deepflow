"""
URL 安全验证工具模块。

从 source_registry.py 提取，解决 safe_fetcher ↔ source_registry 循环导入。
被 safe_fetcher.py 和 source_registry.py 共同依赖。
"""

from __future__ import annotations

import ipaddress
from urllib.parse import ParseResult, urlparse, urlunparse


def _is_private_or_disallowed_host(hostname: str) -> bool:
    """拒绝本机、私网、保留、链路本地和多播地址。"""
    if not hostname:
        return True

    lower = hostname.lower()
    if lower == "localhost" or lower.endswith(".localhost"):
        return True

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False

    return any(
        [
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        ]
    )


def validate_safe_url(url: str) -> tuple[ParseResult, str]:
    """校验 URL 是否可用于外部抓取，并返回解析结果与规范化 URL。

    Args:
        url: 待验证的 URL 字符串

    Returns:
        (parsed_url, canonical_url) 元组

    Raises:
        ValueError: URL 协议非法、缺少域名、包含 userinfo 或主机为私网地址
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"非法 URL 协议: {parsed.scheme}, 仅支持 http/https")
    if not parsed.hostname:
        raise ValueError("非法 URL: 缺少域名")
    if parsed.username or parsed.password:
        raise ValueError("非法 URL: 不允许包含 userinfo")
    if _is_private_or_disallowed_host(parsed.hostname):
        raise ValueError(f"非法 URL 主机: {parsed.hostname}")

    port = parsed.port
    if port is None:
        netloc = parsed.hostname
    else:
        default_port = 80 if parsed.scheme == "http" else 443
        netloc = parsed.hostname if port == default_port else f"{parsed.hostname}:{port}"

    canonical_path = parsed.path or "/"
    canonical = urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            canonical_path,
            parsed.params,
            parsed.query,
            "",
        )
    )
    return parsed, canonical
