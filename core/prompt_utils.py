"""
Prompt工具函数 - 契约笼子合规版
================================

统一所有领域的prompt加载方式，消除编码风格漂移。

契约引用: cage/active/ (see registry.yaml)
版本: 2.0.0
日期: 2026-05-01
"""

import logging

from core.config.path_config import PathConfig

logger = logging.getLogger(__name__)


def read_prompt(domain: str, filename: str) -> str:
    """
    统一读取prompt文件（契约笼子合规）
    
    自动剥离YAML Front Matter，只返回prompt正文，避免污染LLM上下文。
    
    参数:
        domain: 领域名称，如 "investment", "solution_pro"
        filename: prompt文件名，如 "planner.md", "researcher_finance.md"
    
    返回:
        prompt正文内容（不含YAML元数据）
    
    示例:
        >>> read_prompt("investment", "researcher_finance.md")
        >>> read_prompt("solution_pro", "planner.md")
    
    契约合规:
        - PROMPT-001: 统一函数签名
        - PROMPT-002: 统一路径构建
        - PROMPT-003: 统一错误处理
        - PROMPT-004: 自动清理YAML元数据，防止上下文污染
    """
    base = PathConfig.resolve().base_dir
    path = base / "prompts" / domain / filename
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return f"# {filename}\n\n执行分析任务。"
    
    # 自动剥离YAML Front Matter，防止污染LLM上下文
    if content.startswith('---'):
        try:
            parts = content.split('---', 2)
            if len(parts) >= 3:
                # 返回第三部分（正文），去掉开头的换行
                return parts[2].strip()
        except Exception as e:
            logger.debug(f"read_prompt failed: {e}")
    
    return content


def read_prompt_with_meta(domain: str, filename: str) -> dict:
    """
    读取prompt文件并解析YAML元数据
    
    参数:
        domain: 领域名称
        filename: prompt文件名
    
    返回:
        {
            "content": "prompt正文",
            "meta": {name, version, role, variables, ...}
        }
    """
    content = read_prompt(domain, filename)
    meta = {}
    
    # 解析YAML Front Matter
    if content.startswith('---'):
        try:
            parts = content.split('---', 2)
            if len(parts) >= 3:
                import yaml
                meta = yaml.safe_load(parts[1])
                content = parts[2].strip()
        except Exception as e:
            logger.debug(f"read_prompt_with_meta failed: {e}")
    
    return {
        "content": content,
        "meta": meta
    }
