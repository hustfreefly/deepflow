# Solution Pro V2 泛化性实施方案

> **版本**: 1.0 | **日期**: 2026-07-07
> **约束**: ① 架构不动 ② 软件基础功能不降级 ③ 跨域泛化落地
> **基于**: FINAL_REPORT.md（6 Agent × 3 模型交叉审计）

---

## 设计原则

1. **配置驱动，不硬编码** — 领域知识从 YAML 配置注入，代码零修改即可接入新领域
2. **向后兼容** — 软件域行为与改造前完全一致（现有 147 测试全绿）
3. **AI Native 验证** — 每轮修复后，多专家 AI Native 评审 + 3 场景 E2E 验证
4. **渐进交付** — 每 Phase 独立可验证，不依赖后续 Phase

---

## Phase 0: 领域适配基础设施设计（Day 1-2）

> **目标**: 设计 Domain Adaptation Layer（DAL），让新领域零代码接入
> **AI Native 本质**: 架构已泛化（9/10），缺的是注入内容的泛化。DAL 就是注入机制。

### 0.1 设计 Domain Template YAML Schema

定义统一的领域模板格式：

```yaml
# config/domains/software.yaml（默认域，向后兼容）
domain_id: "software"
domain_label: "软件开发"
description: "后端API、前端UI、移动端、数据迁移、DevOps、ML、IaC、安全、性能、测试、无障碍"

# Meta-Planner 配置
meta_planner:
  suggested_categories:
    - backend_api
    - frontend_ui
    - mobile
    - data_migration
    - devops
    - ml
    - iac
    - security
    - performance
    - testing_qa
    - accessibility
  gate_b_checks:
    - name: "security_audit"
      pass_criteria: "无高危漏洞，OWASP Top 10 已缓解"
    - name: "performance_benchmarks"
      pass_criteria: "API 响应时间 < 200ms"

# 专家模板
expert_templates:
  backend_api:
    - name: "security_expert"
      lens: "security vulnerabilities and OWASP compliance"
    - name: "performance_expert"
      lens: "latency, throughput, and resource optimization"
  frontend_ui:
    - name: "ux_design"
      lens: "user experience and interaction design"
  # ...（当前 EXPERT_TEMPLATE_REGISTRY 的完整内容）

# 种子 URL（Research 阶段的搜索起点）
seed_urls:
  - "https://developer.aliyun.com"
  - "https://aws.amazon.com/architecture"
  - "https://martinfowler.com"

# 质量维度（Quality Attributes 的预设分类）
quality_dimensions:
  - latency
  - throughput
  - availability
  - security
  - scalability

# 输出结构（Summary 阶段的章节模板）
output_structure:
  - "方案概述"
  - "架构设计"
  - "技术选型（含对比）"
  - "数据设计"
  - "安全设计"
  - "性能设计"
  - "实施计划"
  - "风险缓解"
```

```yaml
# config/domains/investment.yaml
domain_id: "investment"
domain_label: "投资分析"

meta_planner:
  suggested_categories:
    - due_diligence
    - patent_analysis
    - market_analysis
    - financial_projection
    - risk_assessment
    - team_evaluation
  gate_b_checks:
    - name: "data_source_audit"
      pass_criteria: "所有关键结论有可溯源数据支撑"
    - name: "risk_coverage"
      pass_criteria: "主要风险维度已覆盖"

expert_templates:
  due_diligence:
    - name: "patent_analyst"
      lens: "专利组合分析、技术壁垒评估"
    - name: "financial_analyst"
      lens: "财务健康度、估值合理性"
  market_analysis:
    - name: "market_researcher"
      lens: "市场规模、竞争格局、增长趋势"
  # ...

seed_urls:
  - "https://www.crunchbase.com"
  - "https://pitchbook.com"
  - "https://www.statista.com"

quality_dimensions:
  - data_accuracy
  - risk_coverage
  - market_size
  - competitive_moat

output_structure:
  - "投资概述"
  - "市场分析"
  - "竞争格局"
  - "团队评估"
  - "财务分析"
  - "风险评估"
  - "投资建议"
```

### 0.2 设计配置加载机制

```python
# domains/solution_pro/config/domain_loader.py（新建）
"""领域适配配置加载器"""
import yaml
from pathlib import Path
from functools import lru_cache

DOMAINS_DIR = Path(__file__).parent / "domains"

@lru_cache(maxsize=32)
def load_domain_config(domain_id: str) -> dict:
    """加载领域配置，software 为默认回退"""
    path = DOMAINS_DIR / f"{domain_id}.yaml"
    if not path.exists():
        path = DOMAINS_DIR / "software.yaml"  # 向后兼容
    with open(path) as f:
        return yaml.safe_load(f)

def get_suggested_categories(domain_id: str) -> list[str]:
    cfg = load_domain_config(domain_id)
    return cfg.get("meta_planner", {}).get("suggested_categories", [])

def get_expert_templates(domain_id: str) -> dict:
    cfg = load_domain_config(domain_id)
    return cfg.get("expert_templates", {})

def get_seed_urls(domain_id: str) -> list[str]:
    cfg = load_domain_config(domain_id)
    return cfg.get("seed_urls", [])

def get_output_structure(domain_id: str) -> list[str]:
    cfg = load_domain_config(domain_id)
    return cfg.get("output_structure", [])

def infer_domain_id(living_spec: dict) -> str:
    """从 Living Spec 推断领域 ID"""
    # 优先使用显式声明
    if living_spec.get("meta", {}).get("domain_type"):
        return living_spec["meta"]["domain_type"]
    # 回退到 software
    return "software"
```

### 0.3 交付物

| 文件 | 说明 |
|------|------|
| `config/domains/software.yaml` | 软件域配置（从现有代码提取） |
| `config/domains/investment.yaml` | 投资分析域配置 |
| `config/domains/hardware.yaml` | 硬件设计域配置 |
| `config/domains/business.yaml` | 商业策略域配置 |
| `config/domain_loader.py` | 配置加载器 |
| `config/domains/README.md` | 新领域接入指南 |

### 0.4 验收标准

- [ ] `load_domain_config("software")` 返回与现有 `EXPERT_TEMPLATE_REGISTRY` 一致的数据
- [ ] `load_domain_config("investment")` 返回投资分析领域配置
- [ ] `load_domain_config("unknown_domain")` 回退到 software
- [ ] 现有 147 测试全绿

---

## Phase 1: 解除 Pydantic 硬阻塞（Day 3-5）

> **目标**: 非软件域输入不再被 Pydantic 拒绝
> **约束**: 软件域行为不变

### 1.1 DOMAIN_CATEGORIES: Literal → str + 建议列表

**文件**: `schemas/schemas.py:34-37`

```python
# Before:
DOMAIN_CATEGORIES = Literal[
    "backend_api", "frontend_ui", ...
]

# After:
# 保留为建议列表，不再强制
SUGGESTED_DOMAIN_CATEGORIES = [
    "backend_api", "frontend_ui", "mobile", "data_migration",
    "devops", "ml", "iac", "security", "performance",
    "testing_qa", "accessibility",
]
# DOMAIN_CATEGORIES 变为类型别名，接受任何字符串
DOMAIN_CATEGORIES = str  # 兼容现有引用
```

**向后兼容**: 所有引用 `DOMAIN_CATEGORIES` 的代码不需要改动（`str` 是 `Literal` 的超集）。

### 1.2 EXPERT_TEMPLATE_REGISTRY: 硬编码 → 配置驱动

**文件**: `schemas/schemas.py:40-80`

```python
# Before: 93 行硬编码
EXPERT_TEMPLATE_REGISTRY: dict[str, list[dict[str, str]]] = {
    "backend_api": [...],
    ...
}

# After: 从配置加载 + 保留原变量名兼容
from domains.solution_pro.config.domain_loader import get_expert_templates

# 默认加载 software 域（向后兼容）
EXPERT_TEMPLATE_REGISTRY: dict[str, list[dict[str, str]]] = get_expert_templates("software")

def get_registry_for_domain(domain_id: str) -> dict[str, list[dict[str, str]]]:
    """获取指定领域的专家模板"""
    return get_expert_templates(domain_id)
```

### 1.3 SemanticAnchor.category: 封闭枚举 → 开放字符串

**文件**: `domains/spec_pro/contracts/living_spec.py:133-138`

```python
# Before:
valid = {"platform_api", "architecture_principle", "external_system", "technical_constraint"}
if v not in valid:
    raise ValueError(...)

# After: 开放枚举 + 建议列表
SUGGESTED_CATEGORIES = {
    # 软件域（原有）
    "platform_api", "architecture_principle", "external_system", "technical_constraint",
    # 投资域
    "market_segment", "patent_portfolio", "regulatory_framework", "financial_metric",
    # 硬件域
    "physical_constraint", "material_spec", "manufacturing_process", "thermal_parameter",
    # 商业域
    "business_rule", "compliance_requirement", "partnership_model", "revenue_stream",
}

@field_validator("category")
@classmethod
def validate_category(cls, v):
    v = v.strip()
    if len(v) < 2:
        raise ValueError(f"SemanticAnchor.category 太短: '{v}'")
    if v not in SUGGESTED_CATEGORIES:
        logger.info(f"SemanticAnchor.category '{v}' 不在建议列表中，但已接受（开放枚举）")
    return v
```

**向后兼容**: 原有 4 个类别仍然合法。新增类别不触发 ValueError。

### 1.4 DOMAIN_CATEGORIES 在 Meta-Planner Prompt 中的引用

**文件**: `prompts/meta_planner.md`

```markdown
# Before:
"领域分类：backend_api / frontend_ui / data_migration / ..."

# After:
"领域分类：根据项目性质选择合适的领域标识。
以下是常见领域参考（非穷举，可根据实际情况自定义）：
- 软件类: backend_api, frontend_ui, mobile, ml, devops, ...
- 投资类: due_diligence, patent_analysis, market_analysis, ...
- 硬件类: thermal_design, mechanical_engineering, ...
- 商业类: market_entry, competitive_strategy, ..."
```

### 1.5 交付物

| 文件 | 修改 |
|------|------|
| `schemas/schemas.py` | DOMAIN_CATEGORIES → str, Registry → 配置驱动 |
| `living_spec.py` | category → 开放枚举 |
| `prompts/meta_planner.md` | 领域分类 → 建议列表 |
| `config/domain_loader.py` | 新建 |
| `config/domains/*.yaml` | 4 个领域配置文件 |

### 1.6 验收标准

- [ ] 投资分析 Living Spec 不被 Pydantic 拒绝
- [ ] 硬件设计 Living Spec 不被 Pydantic 拒绝
- [ ] 商业策略 Living Spec 不被 Pydantic 拒绝
- [ ] 软件域 Living Spec 行为与改造前完全一致
- [ ] 现有 147 测试全绿
- [ ] **E2E 冒烟**: 软件域场景跑通 Planning→Research→Summary

---

## Phase 2: task_builder.py 软件硬编码修复（Day 5-7）

> **目标**: 2283 行的 task_builder.py 中的软件硬编码改为配置驱动
> **审计评分**: 3/10（最严重文件）

### 2.1 Designer 输出结构泛化

**位置**: `build_designer_task()` (line ~849)

```python
# Before: 硬编码软件概念
"你需要输出：architecture / components / interfaces / data_model"

# After: 从领域配置加载
domain_cfg = load_domain_config(domain_id)
design_output = domain_cfg.get("design_output", {
    "sections": ["方案结构", "组件设计", "接口定义", "数据模型"]  # 默认=软件
})
```

### 2.2 种子 URL 配置化

**位置**: `build_researcher_task()` (line ~725)

```python
# Before: 硬编码技术文档站
SEED_URLS = ["阿里云开发者", "AWS架构", "Martin Fowler"]

# After: 从领域配置加载
seed_urls = get_seed_urls(domain_id)
```

### 2.3 Reviewer 检查项配置化

**位置**: `build_reviewer_task()` (line ~1239)

```python
# Before: 硬编码软件维度
REVIEW_CHECKS = ["架构设计", "技术选型", "性能指标", "扩展性", "技术债务"]

# After: 从领域配置加载
review_dimensions = domain_cfg.get("review_dimensions", [...])
```

### 2.4 Harness Final 检查项配置化

**位置**: `build_harness_final_task()` (line ~1443)

```python
# Before: 硬编码软件运维
HARNESS_CHECKS = ["容错机制", "数据流", "测试策略", "监控运维"]

# After: 从领域配置加载
harness_checks = domain_cfg.get("harness_checks", [...])
```

### 2.5 domain_id 透传机制

**问题**: task_builder 的各 `build_*_task()` 函数目前不接收 `domain_id`。

**方案**: 在 `frozen_spec` 或 `living_spec` 中携带 `domain_id`，各 build 函数从 spec 中提取。

```python
# 每个 build_*_task 函数的通用逻辑
def build_xxx_task(..., living_spec=None):
    domain_id = "software"
    if living_spec:
        domain_id = living_spec.get("meta", {}).get("domain_type", "software")
    domain_cfg = load_domain_config(domain_id)
    # 使用 domain_cfg 替代硬编码
```

### 2.6 交付物

| 文件 | 修改 |
|------|------|
| `task_builder.py` | ~15 处硬编码 → 配置驱动 |
| `config/domains/*.yaml` | 增加 design_output / review_dimensions / harness_checks 字段 |

### 2.7 验收标准

- [ ] `build_designer_task(domain_id="investment")` 输出投资分析相关结构
- [ ] `build_researcher_task(domain_id="hardware")` 使用硬件种子 URL
- [ ] `build_reviewer_task(domain_id="business")` 使用商业检查维度
- [ ] 所有 `build_*_task(domain_id="software")` 输出与改造前一致
- [ ] 现有 147 测试全绿

---

## Phase 3: Prompt 层泛化（Day 7-12）

> **目标**: 12 个核心 Prompt 的示例/术语/约束泛化
> **审计中 12 个评分 3-5 的 Prompt**

### 3.1 核心策略

每个 Prompt 的泛化遵循**统一模式**：

1. **保留指令结构** — Prompt 的 Role/Constraints/Output 框架不动
2. **参数化示例** — 将硬编码的软件示例改为 `{{domain_examples}}`
3. **注入领域示例** — 由 `domain_loader` 在运行时注入对应领域的 few-shot 示例
4. **保留软件示例作为默认** — 不传 domain_id 时，行为与改造前一致

### 3.2 各 Prompt 修改计划

#### P0 — 评分 ≤ 4（必须修改）

| Prompt | 当前评分 | 修改内容 |
|--------|:--------:|---------|
| `meta_planner.md` (201行) | 3/10 | ① 领域枚举 → 建议列表 ② 3 个软件示例 → 保留 1 个软件 + 增加投资/硬件/商业各 1 个 ③ Gate B 检查项 → 参数化 |
| `expert_planner_base.md` (121行) | 3/10 | ① 2 个软件示例 → 保留 1 个 + 增加 1 个非软件 ② 约束数量指导 → 领域自适应 |
| `planner_harness.md` (262行) | 4/10 | ① 方案类型从 architecture/technical → 通用化 ② 维度提取从 QPS/SLA → 领域自适应 |
| `convergence_planner.md` (271行) | 4/10 | ① PostgreSQL/Redis 示例 → 参数化 ② 验证命令 curl/psql → 领域自适应 |
| `reviewer_convergence.md` (294行) | 4/10 | ① 验证方法示例 → 多领域 |

#### P1 — 评分 5-6（应修改）

| Prompt | 当前评分 | 修改内容 |
|--------|:--------:|---------|
| `planning_planner.md` | 5/10 | 约束维度枚举 → LLM 推断 |
| `planning_expert_base.md` | 5/10 | 示例约束 → 多领域 |
| `review_layer_b.md` | 5/10 | 验证方法示例 → 多领域 |
| `research_expert_base.md` (169行) | 5/10 | ① "技术名称+版本号" → "具体可验证引用" ② 搜索方向 → 领域自适应 |
| `summary_base_synthesizer.md` (184行) | 6/10 | 输出章节模板 → 领域自适应 |
| `summary_summarizer.md` (252行) | 6/10 | 同上 |
| `research_module.md` | 6/10 | "技术推荐" → "方案推荐" |

#### P2 — 评分 7+（微调或不改）

> 13 个 prompt 评分 7+，仅需微调术语。具体清单见 round1/prompt_audit.md。

### 3.3 领域示例注入机制

```python
# 在 task_builder 构建 prompt 时注入
def build_meta_planner_task(frozen_spec, ...):
    domain_id = infer_domain_id(living_spec)
    domain_examples = load_domain_examples(domain_id)
    
    prompt = render_template("meta_planner.md", {
        "domain_examples": domain_examples,
        # ... 其他变量
    })
```

### 3.4 交付物

| 文件 | 修改 |
|------|------|
| 5 个 P0 prompt | 示例泛化 + 参数化 |
| 7 个 P1 prompt | 术语/示例泛化 |
| `config/domain_loader.py` | 增加 `load_domain_examples()` |
| `config/domains/*.yaml` | 增加 few-shot 示例数据 |

### 3.5 验收标准

- [ ] 每个修改的 Prompt，用投资/硬件/商业场景测试，LLM 输出不包含不相关的软件概念
- [ ] 用软件场景测试，输出质量不低于改造前
- [ ] **AI Native 专家评审**（见 Phase 5）

---

## Phase 4: Schema 字段名泛化（Day 12-15）

> **目标**: Schema 字段名通用化
> **约束**: 使用 Pydantic alias 保持 JSON 输出向后兼容

### 4.1 字段重命名（alias 兼容）

```python
class ArchitectureSchema(BaseModel):
    # Before: technology_stack: list[str]
    # After:
    selection_stack: list[str] = Field(
        alias="technology_stack",  # JSON 输出保持 technology_stack
        description="选型清单（技术/材料/方案/供应商等）"
    )
    
    # Before: deployment_view: str
    # After:
    delivery_view: str = Field(
        alias="deployment_view",
        description="交付/部署视图"
    )
```

### 4.2 DetailedDesignSchema 泛化

```python
class DetailedDesignSchema(BaseModel):
    components: list[dict] = Field(alias="modules", description="组件/模块列表")
    interfaces: list[dict] = Field(alias="apis", description="接口定义")
    data_model: dict = Field(alias="database_schema", description="数据模型")
    interaction_flows: list[dict] = Field(alias="sequence_diagrams", description="交互流程")
```

### 4.3 Output Schema 泛化

| 原字段 | 新字段 | alias | 说明 |
|--------|--------|-------|------|
| `technology_stack` | `selection_stack` | `technology_stack` | 通用选型清单 |
| `deployment_view` | `delivery_view` | `deployment_view` | 通用交付视图 |
| `modules` | `components` | `modules` | 通用组件 |
| `apis` | `interfaces` | `apis` | 通用接口 |
| `database_schema` | `data_model` | `database_schema` | 通用数据模型 |
| `technology_recommendations` | `recommendations` | `technology_recommendations` | 通用推荐 |

### 4.4 交付物

| 文件 | 修改 |
|------|------|
| `schemas/schemas.py` | 6 个字段重命名 + alias |
| `task_builder.py` | 引用新字段名 |

### 4.5 验收标准

- [ ] JSON 输出格式与改造前完全一致（alias 生效）
- [ ] Python 代码可使用新字段名
- [ ] 现有 147 测试全绿
- [ ] 非软件域场景的输出 Schema 不包含误导性字段名

---

## Phase 5: AI Native 专家评审（贯穿全程）

> **目标**: 每 Phase 完成后，多专家 AI Native 评审 → 迭代修复
> **方法**: 3 轮 × 3 专家 × 交叉验证

### 5.1 评审维度

| 专家 | 模型 | 视角 | 关注点 |
|------|------|------|--------|
| AI Native 架构师 | DeepSeek V4 Pro | 能力正交 + 信息守恒 | 修改是否破坏了 AI Native 原则？配置注入 vs 硬编码是否彻底？ |
| 泛化性测试师 | Qwen 3.7 Max | 跨域验证 | 3 个非软件场景能否跑通？软件场景是否降级？ |
| 向后兼容审计师 | Kimi K2.6 | 回归安全 | 现有 147 测试是否全绿？软件域行为是否一致？ |

### 5.2 评审流程

```
Phase N 完成
    ↓
Round 1: 3 专家并行评审（spawn 3 subagents）
    ↓
整合评审意见 → 分类（阻塞 / 改进 / 建议）
    ↓
修复阻塞项
    ↓
Round 2: 3 专家复审（只看修复项）
    ↓
Phase N+1 开始
```

### 5.3 评审 Prompt 模板

```markdown
你是 AI Native 架构评审专家。

## 你的任务
评审 Solution Pro V2 泛化性改造的第 {phase} 阶段修改。

## 评审原则
1. **架构不动**: 三阶段管线 + 约束体系 + 收敛机制 + Gate 验证不得修改
2. **软件不降级**: 软件域的行为和输出质量不得下降
3. **泛化要落地**: 非软件域输入能跑通且输出质量可接受
4. **AI Native 纯度**: 修改必须符合 AI Native 原则（LLM 做语义，代码做格式）

## 具体检查项
- [ ] 修改是否引入了新的硬编码？
- [ ] 配置注入机制是否领域无关？
- [ ] 向后兼容性是否有测试保障？
- [ ] 是否有 fallback/静默降级的反模式？
- [ ] Prompt 修改是否保留了 AI Native 的约束强度？

## 输出格式
| # | 发现 | 严重度 | 证据 | 修复建议 |
```

---

## Phase 6: E2E 端到端验证（Day 15-17）

> **目标**: 3 个跨域场景跑通全流程

### 6.1 测试场景

| 场景 | Living Spec 输入 | 预期输出 |
|------|-----------------|---------|
| 🔬 硬件散热 | GPU 服务器散热模组（TDP 450W / 噪音 < 55dB） | 热设计方案 + 材料选择 + 成本分析 |
| 💰 投资分析 | VC 尽调（专利 + 技术壁垒 + 市场竞争） | 尽调框架 + 风险评估 + 投资判断 |
| 📊 商业策略 | AI 平台日本市场进入策略 | 市场分析 + 合规方案 + 财务预测 |

### 6.2 验证标准

| 检查项 | 标准 |
|--------|------|
| Pydantic 通过 | 无 ValueError 被拒 |
| 端到端完成 | Planning → Research → Summary 全跑通 |
| 输出质量 | 不包含不相关的软件概念（如 OWASP、PostgreSQL） |
| 软件域回归 | 软件场景输出质量 ≥ 改造前 |
| 耗时 | 单场景 < 15 分钟 |

---

## 总时间线

```
Day 1-2:   Phase 0 — DAL 设计 + YAML Schema
Day 3-5:   Phase 1 — Pydantic 硬阻塞解除
Day 5-7:   Phase 2 — task_builder 硬编码修复
Day 7-12:  Phase 3 — Prompt 层泛化（12 个 prompt）
Day 12-15: Phase 4 — Schema 字段名泛化
Day 15-17: Phase 6 — E2E 验证

贯穿:       Phase 5 — 每 Phase 完成后 AI Native 专家评审
```

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 配置注入导致 Prompt 变长 | 控制每个领域配置 < 2KB，裁剪不相关内容 |
| alias 兼容在某些 Pydantic 版本不生效 | Phase 4 开始前验证 alias 行为 |
| 非软件场景 E2E 耗时过长 | 先用 Mock 验证配置加载，再跑真实 LLM |
| 专家评审发现架构级问题 | 严格遵守"架构不动"约束，发现则回退 |

## 预期效果

| 指标 | 改造前 | 改造后 |
|------|:------:|:------:|
| 综合评分 | 5.4/10 | 8.5/10 |
| 非软件端到端通过率 | 10-15% | > 80% |
| 软件域回归 | 基线 | ≥ 基线 |
| 新领域接入成本 | 改代码 | 写 YAML |
| CRITICAL 阻塞点 | 8 个 | 0 个 |
