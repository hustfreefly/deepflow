"""
Domain Loader — 领域配置加载器

泛化性设计：支持多领域（software/investment/hardware/business/其他）
每个领域可以自定义：
- anchor_priorities: SemanticAnchor category 的优先级分层
- 其他领域特定配置
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 内置领域配置 — 仅保留 software 作为最小 fallback。
# 其他域（investment/hardware/business）从 YAML 加载（domain_analysis.py 已有此能力）。
# 如果 YAML 不存在，fallback 到空配置而非硬编码。
BUILTIN_DOMAIN_CONFIGS: Dict[str, Dict[str, Any]] = {
    "software": {
        "domain_id": "software",
        "domain_name": "软件工程",
        "anchor_priorities": {
            "platform_api": "MUST",
            "architecture_principle": "MUST",
            "external_system": "SHOULD",
            "technical_constraint": "CONTEXT",
        },
        "suggested_categories": [
            "platform_api", "architecture_principle", "external_system", "technical_constraint"
        ],
        "expert_templates": {
            "backend_api": [{"name": "backend_architect", "lens": "API 设计、数据库建模、性能优化"}],
            "frontend_ui": [{"name": "frontend_engineer", "lens": "组件设计、状态管理、可访问性"}],
            "devops": [{"name": "infra_engineer", "lens": "部署、监控、可靠性"}],
        },
        "seed_urls": [],
        "output_structure": {
            "sections": ["architecture", "api_design", "data_model", "deployment"]
        },
        "quality_dimensions": ["correctness", "scalability", "maintainability", "security"],
        "review_dimensions": ["architecture", "code_quality", "security", "performance"],
        "harness_checks": ["unit_tests", "integration_tests", "lint", "type_check"],
        "design_output": ["sequence_diagram", "class_diagram", "api_spec"],
        "gate_b_checks": ["requirement_coverage", "anchor_consistency", "guardrail_compliance"],
        "domain_examples": [],
    },
}


def load_domain_config(domain_id: str) -> Dict[str, Any]:
    """加载领域配置
    
    优先级：
    1. 自定义配置文件（domains/{domain_id}/config.yaml）
    2. 内置配置（BUILTIN_DOMAIN_CONFIGS）
    3. 默认软件域配置
    
    Args:
        domain_id: 领域 ID（如 "software", "investment"）
    
    Returns:
        领域配置字典
    """
    if not domain_id or not isinstance(domain_id, str):
        domain_id = "software"
    
    domain_id = domain_id.strip().lower()
    
    # 1. 尝试加载自定义配置文件
    custom_config_path = Path(__file__).parent.parent.parent / domain_id / "config.yaml"
    if custom_config_path.exists():
        try:
            import yaml
            with open(custom_config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if config and isinstance(config, dict):
                logger.debug(f"Loaded custom domain config from {custom_config_path}")
                return config
        except Exception as e:
            logger.warning(f"Failed to load custom domain config from {custom_config_path}: {e}")
    
    # 2. 内置 fallback（仅 software）
    if domain_id in BUILTIN_DOMAIN_CONFIGS:
        return BUILTIN_DOMAIN_CONFIGS[domain_id]
    
    # 3. 空配置（不硬编码其他域）
    logger.info(f"Domain '{domain_id}' not found, using empty config")
    return {
        "domain_id": domain_id,
        "domain_name": domain_id,
        "anchor_priorities": {},
        "expert_templates": [],
        "seed_urls": [],
        "output_structure": {"sections": []},
        "quality_dimensions": [],
        "review_dimensions": [],
        "harness_checks": [],
        "design_output": [],
        "gate_b_checks": [],
        "domain_examples": [],
    }


def list_available_domains() -> List[str]:
    """列出所有可用的领域 ID
    
    Returns:
        领域 ID 列表（如 ["software", "investment", "hardware", "business"]）
    """
    domains = set(BUILTIN_DOMAIN_CONFIGS.keys())
    
    # 扫描自定义配置目录
    domains_dir = Path(__file__).parent.parent.parent
    if domains_dir.exists():
        for child in domains_dir.iterdir():
            if child.is_dir() and (child / "config.yaml").exists():
                domains.add(child.name)
    
    return sorted(domains)


def get_expert_templates(domain_id: str) -> Dict[str, List[Dict[str, str]]]:
    """获取指定领域的专家模板

    从领域配置中加载 expert_templates，回退到 software 域默认值。

    Args:
        domain_id: 领域 ID（如 "software", "investment"）

    Returns:
        dict[str, list[dict[str, str]]] — {category: [{name, lens}, ...]}
    """
    config = load_domain_config(domain_id)
    templates = config.get("expert_templates", {})
    if not templates:
        # 回退到 software 域默认模板
        templates = BUILTIN_DOMAIN_CONFIGS.get("software", {}).get("expert_templates", {})
        if not templates:
            # 硬编码兜底（防止配置文件缺失）
            templates = {
                "backend_api": [
                    {"name": "security_expert", "lens": "security vulnerabilities and OWASP compliance"},
                    {"name": "performance_expert", "lens": "latency, throughput, and resource optimization"},
                    {"name": "scalability_expert", "lens": "horizontal scaling and state management"},
                ],
            }
            logger.warning(f"No expert_templates found for domain '{domain_id}', using fallback")
    return templates


def get_domain_name(domain_id: str) -> str:
    """获取领域的显示名称"""
    config = load_domain_config(domain_id)
    return config.get("domain_name", domain_id)


def get_suggested_categories(domain_id: str = "software") -> List[str]:
    """获取领域建议的 SemanticAnchor categories"""
    config = load_domain_config(domain_id)
    return config.get("suggested_categories", [])


def get_output_structure(domain_id: str = "software") -> Dict[str, Any]:
    """获取领域的输出结构"""
    config = load_domain_config(domain_id)
    return config.get("output_structure", {})


def get_gate_b_checks(domain_id: str = "software") -> List[str]:
    """获取领域的 Gate B 检查项"""
    config = load_domain_config(domain_id)
    return config.get("gate_b_checks", [])


def get_domain_examples(domain_id: str = "software") -> List[Dict[str, Any]]:
    """获取领域的示例"""
    config = load_domain_config(domain_id)
    return config.get("domain_examples", [])


def infer_domain_id(text: str = "", domain_profile=None, meta: dict = None) -> str:
    """推断领域 ID（AI Native）

    优先级：
    1. domain_profile（LLM 动态生成）
    2. meta.domain_type（Living Spec 声明）
    3. 回退到 software

    Args:
        text: 输入文本（保留参数，不再用于关键词匹配）
        domain_profile: LLM 生成的 DomainProfile（可选）
        meta: Living Spec 的 meta 字典（可选）

    Returns:
        推断的领域 ID
    """
    # 1. LLM 动态生成（最高优先级）
    if domain_profile:
        domain_id = (
            domain_profile.domain_id
            if hasattr(domain_profile, 'domain_id')
            else domain_profile.get('domain_id', 'software')
        )
        if domain_id and isinstance(domain_id, str) and domain_id.strip():
            return domain_id.strip().lower()

    # 2. meta.domain_type（Living Spec 声明）
    if meta and isinstance(meta, dict):
        meta_domain = meta.get("domain_type", "").strip().lower()
        if meta_domain:
            logger.info(f"infer_domain_id: using meta.domain_type='{meta_domain}'")
            return meta_domain

    # 3. 回退
    return "software"


def validate_domain_config(domain_id: str) -> Dict[str, Any]:
    """验证领域配置的完整性
    
    Args:
        domain_id: 领域 ID
    
    Returns:
        验证结果 {"valid": bool, "issues": List[str]}
    """
    config = load_domain_config(domain_id)
    issues = []
    
    required_fields = ["domain_id", "domain_name", "anchor_priorities"]
    for field in required_fields:
        if field not in config:
            issues.append(f"Missing required field: {field}")
    
    anchor_priorities = config.get("anchor_priorities", {})
    valid_priorities = {"MUST", "SHOULD", "CONTEXT"}
    for category, priority in anchor_priorities.items():
        if priority not in valid_priorities:
            issues.append(f"Invalid priority '{priority}' for category '{category}'")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }
