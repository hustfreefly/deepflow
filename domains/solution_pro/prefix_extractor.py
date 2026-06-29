"""
前缀提取工具

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
V1-LEGACY: This file is part of V1 pipeline (10-stage architecture).
V2 uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + ReviewQCOrchestrator.
Do not import this file for new V2 workflows.
"""

# domains/solution_pro/prefix_extractor.py
"""
会话前缀提取器

从长文本需求中提取核心主题作为会话前缀，用于生成有意义的 session_id。
"""
import re
from typing import Optional


async def extract_prefix(topic: str, model_caller) -> str:
    """
    从长文本需求中提取核心主题作为会话前缀
    
    Args:
        topic: 用户输入的长文本需求（可能包含背景、目标、要求等）
        model_caller: ModelCaller 实例，用于调用 LLM 提取前缀
        
    Returns:
        str: 提取的核心主题（最多30字符，特殊字符替换为下划线）
        
    Example:
        >>> topic = "随着业务快速发展，我们公司面临严重的算力资源分配不均问题..."
        >>> prefix = await extract_prefix(topic, model_caller)
        >>> print(prefix)  # "异构算力调度"
    """
    # 如果 topic 很短（<= 30字符），直接使用
    if len(topic) <= 30:
        return _sanitize_prefix(topic)
    
    # 使用 LLM 提取核心主题
    prompt = f"""请从以下需求描述中提取最核心的主题，用2-8个汉字概括：

{topic}

只输出核心主题词，不要有任何解释、标点或多余文字。例如：
- "设计一个支持异构算力接入的调度平台" → "异构算力调度"
- "构建高并发电商交易系统" → "电商交易系统"
- "开发智能客服机器人" → "智能客服"
"""
    
    try:
        result = await model_caller.call(
            prompt=prompt,
            temperature=0.1,
            max_tokens=50
        )
        
        # 提取响应文本
        extracted = result.get("content", "") or result.get("text", "") or ""
        extracted = extracted.strip()
        
        # 如果提取失败或为空，回退到简单策略
        if not extracted:
            return _fallback_extract(topic)
        
        # 清理和截断
        return _sanitize_prefix(extracted)
        
    except Exception as e:
        # LLM 调用失败时回退
        return _fallback_extract(topic)


def _sanitize_prefix(text: str) -> str:
    """
    清理前缀文本：替换特殊字符为下划线，截断到30字符
    
    Args:
        text: 原始文本
        
    Returns:
        str: 清理后的前缀
    """
    # 替换非单词字符和非中文字符为下划线
    sanitized = re.sub(r'[^\w\u4e00-\u9fff]', '_', text)
    # 截断到30字符
    return sanitized[:30]


def _fallback_extract(topic: str) -> str:
    """
    回退策略：简单提取前30字符
    
    Args:
        topic: 原始文本
        
    Returns:
        str: 清理后的前缀
    """
    # 尝试提取第一句（遇到句号、问号、感叹号停止）
    match = re.match(r'^([^.!?？！。]{1,30})', topic)
    if match:
        first_sentence = match.group(1).strip()
        if len(first_sentence) >= 2:
            return _sanitize_prefix(first_sentence)
    
    # 最后回退：直接取前30字符
    return _sanitize_prefix(topic[:30])
