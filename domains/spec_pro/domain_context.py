"""
Spec Pro 域上下文模块

复用 Solution Pro 的 domain_loader 基础设施，为 Spec Pro 的 Prompt 提供域上下文。
设计原则：
- YAML 配置是数据（few-shot 参考），不是硬编码
- LLM 读取域上下文理解模式，但不受限于 YAML 内容
- 新增领域 = 加 YAML 文件，不改代码
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def build_domain_context(domain_type: Optional[str] = None) -> str:
    """
    构建域上下文文本，用于注入到 Spec Pro 的 Prompt 中。
    
    Args:
        domain_type: 域类型（如 "software", "investment", "hardware", "business"）
                    如果为 None，返回空字符串（LLM 自由推断）
    
    Returns:
        域上下文文本（markdown 格式），可直接拼接到 Prompt 中
    """
    if not domain_type:
        return ""
    
    try:
        from domains.solution_pro.config.domain_loader import load_domain_config
        config = load_domain_config(domain_type)
    except (ImportError, Exception) as e:
        logger.warning(f"Failed to load domain config for '{domain_type}': {e}")
        return ""
    
    if not config:
        return ""
    
    # 从 YAML 配置构建域上下文
    parts = []
    
    domain_label = config.get("domain_label", domain_type)
    parts.append(f"## 领域上下文：{domain_label}")
    parts.append("")
    
    # 术语类别（从 expert_templates 的 key 提取）
    expert_templates = config.get("expert_templates", {})
    if expert_templates and isinstance(expert_templates, dict):
        categories = list(expert_templates.keys())
        parts.append(f"**常见任务类别**：{', '.join(categories)}")
        parts.append("")
    
    # 质量维度
    quality_dims = config.get("quality_dimensions", [])
    if quality_dims:
        parts.append(f"**关键质量维度**：{', '.join(quality_dims)}")
        parts.append("")
    
    # 输出结构
    output_struct = config.get("output_structure", [])
    if output_struct:
        parts.append(f"**典型输出结构**：{', '.join(output_struct)}")
        parts.append("")
    
    # 评审维度
    review_dims = config.get("review_dimensions", [])
    if review_dims:
        parts.append(f"**评审关注点**：{', '.join(review_dims)}")
        parts.append("")
    
    return "\n".join(parts)



