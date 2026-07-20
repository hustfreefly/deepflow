"""
Solution Pro 领域分析模块（AI Native）

设计原则：
- LLM 语义推断领域特征，不依赖预定义配置
- 4 个 YAML 仅作为 few-shot 参考（教 LLM 怎么思考）
- 任何领域都能处理，零配置接入
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DomainProfile(BaseModel):
    """LLM 动态生成的领域 profile"""
    domain_id: str = Field(description="领域标识（如 software, investment, hardware, medical 等）")
    domain_label: str = Field(description="领域中文名")
    description: str = Field(description="领域简述（一句话）")

    # 领域分析维度
    suggested_categories: list[str] = Field(
        default_factory=list,
        description="该领域下的任务分类建议（如 backend_api / due_diligence / thermal_design）"
    )

    # 专家角色
    expert_roles: list[dict] = Field(
        default_factory=list,
        description="该领域需要的专家角色列表，每个包含 name + lens"
    )

    # 质量维度
    quality_dimensions: list[str] = Field(
        default_factory=list,
        description="该领域的质量评估维度"
    )

    # 搜索方向
    seed_urls: list[str] = Field(
        default_factory=list,
        description="该领域的参考搜索方向（URL 或搜索关键词）"
    )

    # 输出结构
    output_structure: list[str] = Field(
        default_factory=list,
        description="该领域的方案文档结构"
    )

    # 验证标准
    review_dimensions: list[str] = Field(
        default_factory=list,
        description="该领域的评审维度"
    )

    # Harness 检查
    harness_checks: list[str] = Field(
        default_factory=list,
        description="该领域的交付质量检查项"
    )


class DomainAnalysisPrompt:
    """领域分析的 Prompt 构建器"""

    SYSTEM_PROMPT = """你是领域分析专家。你的任务是根据项目描述，推断该项目所属的领域，并生成该领域的完整 profile。

## 核心能力
- 从项目描述中推断领域特征
- 为任何领域生成合理的专家角色、质量维度、验证标准
- 参考已知领域模式，但不局限于已知领域

## 输出要求
返回 JSON 格式的 DomainProfile，包含以下字段：
- domain_id: 领域标识（小写下划线，如 software / investment / hardware / medical / legal）
- domain_label: 领域中文名
- description: 领域简述
- suggested_categories: 该领域下的任务分类（3-8 个）
- expert_roles: 该领域需要的专家角色（3-6 个，每个包含 name 和 lens）
- quality_dimensions: 质量评估维度（4-6 个）
- seed_urls: 参考搜索方向（3-5 个 URL 或关键词）
- output_structure: 方案文档章节结构（6-10 个章节）
- review_dimensions: 评审维度（4-6 个）
- harness_checks: 交付质量检查项（3-5 个）

## 思考步骤
1. 分析项目描述中的关键术语和目标
2. 判断领域类型（是否为已知领域？全新领域？）
3. 推断该领域需要的专家角色类型
4. 推断质量评估的关键维度
5. 推断搜索方向（该领域的权威来源在哪？）
6. 推断文档结构（该领域的方案通常包含哪些章节？）
7. 推断验证标准（该领域的方案如何验证质量？）"""

def domain_profile_to_prompt_context(profile: DomainProfile) -> str:
    """将 domain_profile 转换为可注入 Prompt 的上下文文本"""
    if profile is None:
        return ""
    if not isinstance(profile, DomainProfile):
        logger.warning(f"Expected DomainProfile, got {type(profile).__name__}, returning empty context")
        return ""
    parts = [
        f"## 领域分析结果",
        f"- **领域**: {profile.domain_label}（{profile.domain_id}）",
        f"- **描述**: {profile.description}",
        f"- **任务分类**: {', '.join(profile.suggested_categories)}",
        f"- **专家角色**:",
    ]

    for role in profile.expert_roles:
        parts.append(f"  - {role.get('name', 'unknown')}: {role.get('lens', '')}")

    parts.extend([
        f"- **质量维度**: {', '.join(profile.quality_dimensions)}",
        f"- **搜索方向**: {', '.join(profile.seed_urls[:3])}",
        f"- **文档结构**: {' → '.join(profile.output_structure)}",
        f"- **评审维度**: {', '.join(profile.review_dimensions)}",
        f"- **交付检查**: {', '.join(profile.harness_checks)}",
    ])

    return "\n".join(parts)
