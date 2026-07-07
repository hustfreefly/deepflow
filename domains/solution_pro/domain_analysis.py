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

    @staticmethod
    def build_user_prompt(objective: str, context: dict = None) -> str:
        """构建用户提示"""
        parts = [f"## 项目描述\n{objective}"]

        if context:
            confirmed = context.get("confirmed", {})
            if confirmed.get("goal"):
                parts.append(f"## 项目目标\n{confirmed['goal']}")
            if confirmed.get("constraints"):
                parts.append(f"## 约束条件\n{', '.join(confirmed['constraints'])}")

        # 增加 few-shot 参考提示（从 4 个 YAML 中提取的思维模式）
        parts.append("""## 参考模式（仅供思考参考，不要局限于这些）
以下是几个已知领域的分析模式，帮助你理解"领域分析"的含义：

### 软件领域模式（推断链条示例）
- 识别信号：项目涉及"API/系统架构/数据库/部署/微服务" → 判断为软件领域
- 因此需要的专家角色：
  - 技术架构师（因为需要设计系统整体结构和组件交互）
  - 安全专家（因为需要识别认证、授权、数据泄露等风险）
  - 性能工程师（因为需要确保延迟、吞吐量满足要求）
  - DevOps（因为需要可靠的构建、部署和运维流程）
- 因此关键的质量维度：延迟（响应时间是否达标）、可用性（系统是否可靠）、安全性（是否有漏洞）、可扩展性（能否应对增长）
- 因此验证方法：API 测试（功能正确性）、负载测试（性能边界）、安全扫描（漏洞检测）

### 投资分析领域模式（推断链条示例）
- 识别信号：项目涉及"尽调/估值/专利/市场份额" → 判断为投资分析领域
- 因此需要的专家角色：
  - 专利分析师（因为需要评估技术壁垒和知识产权风险）
  - 财务分析师（因为需要验证估值合理性和现金流健康度）
  - 市场研究员（因为需要判断市场规模和竞争格局）
- 因此关键的质量维度：数据准确性（结论依赖可靠数据）、风险覆盖（识别主要风险）、市场规模（判断天花板）
- 因此验证方法：数据源交叉验证（多个独立数据源确认）、假设敏感性分析（关键假设变化对结论的影响）

### 硬件设计领域模式（推断链条示例）
- 识别信号：项目涉及"散热/材料/制造/TDP/结构" → 判断为硬件设计领域
- 因此需要的专家角色：
  - 热管理工程师（因为需要解决热量传递和温度控制问题）
  - 材料工程师（因为需要选择合适的材料满足性能和工艺要求）
  - DFM 工程师（因为设计必须可制造，良率和成本是关键约束）
- 因此关键的质量维度：热效率（散热性能是否达标）、制造良率（工艺是否可控）、单位成本（BOM 是否合理）
- 因此验证方法：热仿真（CFD 模拟验证热设计）、材料物性测试（实测验证材料参数）

### 商业模式领域模式（推断链条示例）
- 识别信号：项目涉及"盈利模式/用户增长/定价/渠道/竞争策略" → 判断为商业模式领域
- 因此需要的专家角色：
  - 商业策略师（因为需要设计盈利模式和竞争策略）
  - 用户增长专家（因为需要规划获客和留存路径）
  - 财务模型师（因为需要验证商业可行性和财务预测）
- 因此关键的质量维度：市场可行性（需求是否真实）、盈利可持续性（模式能否长期运转）、竞争壁垒（是否容易被复制）
- 因此验证方法：市场验证（MVP 或用户访谈）、财务建模（盈亏平衡和敏感性分析）、竞品对标（对比同类商业模式）

### 你的任务
根据项目描述，推断该领域的分析模式。可以是上述已知领域，也可以是全新领域（如医疗、法律、教育、农业等）。""")

        return "\n\n".join(parts)

    @staticmethod
    def get_domain_analysis_prompt() -> str:
        """获取完整的 domain_analysis prompt（供 MasterOrchestrator 使用）"""
        return DomainAnalysisPrompt.SYSTEM_PROMPT


def build_domain_analysis_task(objective: str, context: dict = None) -> dict:
    """构建 domain_analysis 的 spawn 任务描述"""
    user_prompt = DomainAnalysisPrompt.build_user_prompt(objective, context)

    return {
        "system_prompt": DomainAnalysisPrompt.SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "output_schema": DomainProfile.model_json_schema(),
        "expected_output": "JSON 格式的 DomainProfile",
    }


def parse_domain_profile(raw_output: str) -> DomainProfile:
    """解析 LLM 输出的 domain_profile"""
    import json

    # 尝试直接解析
    try:
        data = json.loads(raw_output)
        return DomainProfile.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass

    # 尝试从 markdown 代码块中提取
    import re
    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', raw_output, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return DomainProfile.model_validate(data)
        except (json.JSONDecodeError, Exception):
            pass

    # 回退：生成默认 software profile
    logger.warning("无法解析 domain_profile，回退到 software 默认")
    return DomainProfile(
        domain_id="software",
        domain_label="软件开发",
        description="默认软件领域（解析失败回退）",
        suggested_categories=["backend_api", "frontend_ui", "devops", "testing_qa"],
        expert_roles=[{"name": "architect", "lens": "系统架构设计"}],
        quality_dimensions=["latency", "availability", "security"],
        seed_urls=[],
        output_structure=["方案概述", "方案设计", "关键选型", "详细设计", "实施计划", "风险与缓解"],
        review_dimensions=["方案合理性", "选型适当性"],
        harness_checks=["容错机制", "数据流完整性"],
    )


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
