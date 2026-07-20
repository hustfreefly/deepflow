"""
Deliver Pro — Prompt Registry (轻量版)

从 prompts/ 目录加载 .md prompt 模板，支持 {variable} 替换。

设计原则：
- 不依赖全局 PromptRegistry（Deliver Pro 是独立域）
- prompts/ 目录在同级目录下
- 支持 {deepflow_root} 路径替换
- 自动剥离 YAML Front Matter（防止污染 LLM 上下文）

用法：
    from domains.deliver_pro.prompt_registry import load_prompt

    prompt = load_prompt("analyze_agent", wp_id="WP-001", scenario="code")
    prompt = load_prompt("worker_code", task_id="T-001", task_title="实现注册接口")
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Deliver Pro prompts 目录
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# DeepFlow 根目录（用于 {deepflow_root} 替换）
_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent

# 缓存已加载的 prompt 模板
_template_cache: dict[str, str] = {}


def load_prompt(name: str, **kwargs: Any) -> str:
    """
    加载 prompt 模板并替换变量。

    Args:
        name: prompt 名称（不含 .md 后缀），如 "analyze_agent", "worker_code"
        **kwargs: 模板变量，如 wp_id="WP-001", scenario="code"
                  特殊变量 {deepflow_root} 自动替换

    Returns:
        替换后的 prompt 文本

    Raises:
        FileNotFoundError: prompt 文件不存在
        ValueError: 必需的变量未提供
    """
    template = _load_template(name)
    return _render_template(template, name, **kwargs)


def _load_template(name: str) -> str:
    """加载 prompt 模板文件（带缓存）。"""
    if name in _template_cache:
        return _template_cache[name]

    # 支持 .md 和不带后缀两种形式
    filename = name if name.endswith(".md") else f"{name}.md"
    filepath = _PROMPTS_DIR / filename

    if not filepath.exists():
        available = [f.stem for f in _PROMPTS_DIR.glob("*.md")]
        raise FileNotFoundError(
            f"Prompt not found: {name}\n"
            f"  Expected: {filepath}\n"
            f"  Available: {available or '(prompts/ is empty)'}"
        )

    content = filepath.read_text(encoding="utf-8")

    # 自动剥离 YAML Front Matter
    content = _strip_front_matter(content)

    _template_cache[name] = content
    logger.debug(f"Loaded prompt template: {name} ({len(content)} chars)")
    return content


def _strip_front_matter(content: str) -> str:
    """剥离 YAML Front Matter（--- ... --- 块）。"""
    if not content.startswith("---"):
        return content

    # 找第二个 --- 的位置
    end = content.find("---", 3)
    if end == -1:
        return content  # 没有闭合的 ---，返回原文

    # 跳过第二个 --- 后的换行
    rest = content[end + 3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    elif rest.startswith("\r\n"):
        rest = rest[2:]

    return rest.strip()


def _render_template(template: str, name: str, **kwargs: Any) -> str:
    """
    渲染模板：替换 {variable} 占位符。

    自动注入的变量：
    - {deepflow_root}: DeepFlow 根目录路径

    模板中使用 {{variable}} 双花括号表示必须提供的变量，
    使用 {variable} 单花括号表示可选变量（未提供则保留原文）。
    """
    result = template

    # 自动注入 deepflow_root
    kwargs.setdefault("deepflow_root", str(_DEEPFLOW_ROOT))

    # 替换 {{variable}}（必须提供）
    required_vars = re.findall(r"\{\{(\w+)\}\}", result)
    for var in required_vars:
        if var not in kwargs:
            raise ValueError(
                f"Missing required variable '{var}' for prompt '{name}'\n"
                f"  Provided: {list(kwargs.keys())}"
            )
        result = result.replace(f"{{{{{var}}}}}", str(kwargs[var]))

    # 替换 {variable}（可选，未提供则保留原文）
    optional_vars = re.findall(r"(?<!\{)\{(\w+)\}(?!\})", result)
    for var in optional_vars:
        if var in kwargs:
            result = result.replace(f"{{{var}}}", str(kwargs[var]))

    return result


def list_prompts() -> list[str]:
    """列出所有可用的 prompt 名称。"""
    if not _PROMPTS_DIR.exists():
        return []
    return sorted(f.stem for f in _PROMPTS_DIR.glob("*.md"))


def clear_cache() -> None:
    """清除模板缓存（用于开发调试）。"""
    _template_cache.clear()
    logger.debug("Prompt template cache cleared")
