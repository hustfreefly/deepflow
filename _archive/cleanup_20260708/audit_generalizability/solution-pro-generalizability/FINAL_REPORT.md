# Solution Pro V2 泛化性深度审计报告

> **版本**: 1.0 | **日期**: 2026-07-07
> **审计方法**: 6 个 Agent × 3 个模型 × 3 个非软件域场景 × 交叉验证
> **审计范围**: 36 个 Prompt + 8 个核心代码文件 + 全部 Schema/Contract + 3 个跨域压力测试

---

## 一、核心结论

### 综合评分：**5.4 / 10**

| 维度 | 评分 | 判定 |
|------|:---:|------|
| Prompt 层 | 5.5/10 | 🟠 示例全软件，指令结构泛化 |
| Schema/Contract 层 | 5.8/10 | 🟠 Literal 硬阻塞，核心契约泛化 |
| 编排代码层 | 5.9/10 | 🟠 task_builder 最严重，基类/收敛层泛化 |
| 输入（Living Spec） | 7.0/10 | 🟢 基本泛化，缺少领域特化字段 |
| 输出（Final Solution） | 3.5/10 | 🔴 完全面向软件架构 |

### 一句话总结

> **Solution Pro V2 的骨架（三阶段管线 + 约束体系 + 收敛机制 + Gate 验证）是高度泛化的 AI Native 架构，但皮肤（示例、术语、输出模板、领域枚举）全面绑定了软件开发。**
>
> 非软件域输入会在 2 个 CRITICAL 阻塞点被 Pydantic 拒绝，即使绕过也会在 5 个 MAJOR 问题点产出低质量的软件化输出。

---

## 二、跨域压力测试结果

3 个完全不同领域的场景独立测试，发现了**高度一致**的阻塞模式：

| 场景 | 模型 | 端到端通过率 | CRITICAL | MAJOR | MINOR |
|------|------|:-----------:|:--------:|:-----:|:-----:|
| 🔬 硬件散热设计（GPU 服务器） | qwen3.7-max | ~15% | 7 | 12 | 5 |
| 💰 投资分析（VC 尽调） | kimi-for-coding | ~12% | 7 | 12 | 5 |
| 📊 商业策略（日本市场进入） | kimi-k2.6 | ~10% | 7 | 12 | 5 |

**三个场景的 CRITICAL 阻塞点完全相同**——证实了问题的系统性和结构性。

---

## 三、7 个系统性阻塞点（按严重度排序）

### 🔴 阻塞点 1: `DOMAIN_CATEGORIES` Literal 硬编码

**发现者**: Agent B（Schema）+ Agent D/E/F（压力测试）— 四方独立确认

```python
# schemas/schemas.py
DOMAIN_CATEGORIES = Literal[
    "backend_api", "frontend_ui", "mobile", "data_migration",
    "devops", "ml", "iac", "security", "performance",
    "testing_qa", "accessibility",
]
```

**影响**: 非软件域输入在 Pydantic validation 层面被 REJECT。这是**最高级别的阻塞**——系统在第一个检查点就拒绝了非软件输入。

**修复**: `Literal` → `str`，增加 `suggested_categories` 参考列表。

---

### 🔴 阻塞点 2: `EXPERT_TEMPLATE_REGISTRY` 全软件

**发现者**: Agent B + Agent D/E/F — 四方独立确认

Registry 只有 9 个软件领域的专家模板。投资分析需要的"专利律师/材料科学家/行业分析师"、硬件设计需要的"热工程师/材料工程师/声学工程师"、商业策略需要的"市场分析师/合规律师/财务分析师"全部不存在。

**修复**: Registry 从硬编码 → YAML 配置文件驱动，支持外部注入。

---

### 🔴 阻塞点 3: `task_builder.py` 全软件硬编码（3/10）

**发现者**: Agent C（Code）— 最严重文件

| 硬编码点 | 内容 |
|---------|------|
| Designer 输出 | `architecture/components/interfaces/data_model` — 全软件概念 |
| 种子 URL | 阿里云开发者/AWS架构/Martin Fowler — 全技术文档站 |
| Reviewer 检查项 | 架构设计/技术选型/性能指标/扩展性/技术债务 — 全软件维度 |
| Harness Final | 容错机制/数据流/测试策略/监控运维 — 全软件运维 |

**修复**: 重写 task_builder，输出结构/种子URL/检查项全部从配置文件动态加载。

---

### 🔴 阻塞点 4: Prompt 示例层全面软件化

**发现者**: Agent A（Prompt）— 12 个 prompt 受影响

| Prompt | 软件示例 |
|--------|---------|
| meta_planner.md | CRUD API / 支付系统 / ML推荐系统 |
| expert_planner_base.md | HTTPS/bcrypt/OWASP / API响应时间/水平扩展 |
| convergence_planner.md | PostgreSQL/Redis/Memcached/REST API |
| reviewer_convergence.md | curl/psql/ESLint 验证命令 |
| planner_harness.md | QPS/SLA/RTO/RPO 技术指标 |

**影响**: LLM 模仿 few-shot 示例 → 即使指令通用，也会输出软件化结果。这是**最隐蔽的问题**——系统"看起来"在工作，但输出被示例污染。

**修复**: 每个核心 prompt 增加 2-3 个非软件领域示例（投资+硬件+商业），或改为参数化占位符。

---

### 🔴 阻塞点 5: Summary 输出模板硬编码软件结构

**发现者**: Agent A + Agent C — 双重确认

```python
# summary_orchestrator.py
"- 方案概述\n- 架构设计\n- 技术选型（含对比）\n- 实施计划\n- 风险缓解\n- 约束覆盖追溯"
```

```markdown
# summary_base_synthesizer.md
## 2. 架构设计
## 3. 技术选型（含版本号）
## 5. 数据设计
## 6. 安全设计（认证、授权、加密）
## 7. 性能设计
```

**影响**: 最终输出强制为软件架构文档格式，投资分析报告/硬件设计方案/商业策略报告无法产出。

**修复**: 输出模板从 frozen_spec 的 `output_template` 字段动态获取，或由 LLM 根据领域自适应生成章节结构。

---

### 🟠 阻塞点 6: Research "具体技术名称+版本号" 硬要求

**发现者**: Agent A + Agent D/E/F — 四方确认

```markdown
# research_expert_base.md
"必须包含具体技术名称 + 版本号 + 量化数据"
"示例: TLS 1.3 + AES-256-GCM"
"必须执行至少 15 次 web_search 搜索: 技术选型对比、最佳实践、已知坑点"
```

**领域适配需求**:
- 硬件: 材料型号 + 物性参数 + 供应商（如 "Fujikura 6mm 热管，等效导热系数 5000 W/m·K"）
- 投资: 专利号 + 财务数据 + 市场份额（如 "CN202310XXXXXX，发明专利，有效期至 2043"）
- 商业: 法规条款 + 市场数据 + 竞品名称（如 "APPI 第23条：跨境数据传输需获得用户明确同意"）

**修复**: 改为 "必须包含具体可验证的引用（名称/型号/条款/数据 + 来源）"，不预设"技术+版本号"格式。

---

### 🟠 阻塞点 7: Output Schema 绑定软件概念

**发现者**: Agent B（Schema）

| Schema | 软件绑定字段 | 泛化评分 |
|--------|-------------|:--------:|
| `ArchitectureSchema` | `technology_stack` / `deployment_view` / `data_flows` | 4/10 |
| `DetailedDesignSchema` | `modules` / `apis` / `database_schema` / `sequence_diagrams` | 3/10 |
| `ResearchExpertSchema` | `technology_recommendations` | 6/10 |

**修复**: 
- `technology_stack` → `selection_stack`（通用选型清单）
- `deployment_view` → `delivery_view`（通用交付视图）
- `modules` → `components` / `apis` → `interfaces` / `database_schema` → `data_model`
- `technology_recommendations` → `recommendations`

---

## 四、泛化性良好的部分（无需修改，值得保留）

| 组件 | 评分 | 为什么好 |
|------|:---:|---------|
| 三阶段管线（Planning→Research→Summary） | 9/10 | 通用的"分析→调研→综合"问题解决范式 |
| Pipeline State 状态机 | 9/10 | 完全通用的状态管理 |
| Stage Contract 契约 | 9/10 | 完全通用的 checkpoint 契约 |
| ai_native_cognitive_base.md | 9/10 | 完全领域无关的认知基底 |
| compliance_checker_base.md | 9/10 | 完全领域无关 |
| Constraint/ExpertPlanSchema | 8/10 | RFC 2119 优先级通用，字段名通用 |
| Living Spec 输入格式 | 7/10 | objective/pain_points/scenarios/capabilities 通用 |
| 收敛层/Gate 机制 | 7/10 | Gate A 四维度（完整性/必要性/一致性/全局影响）通用 |
| 运动员≠裁判分离 | 8/10 | 通用的质量保障模式 |
| BlackboardManager API | 8/10 | 完全通用的模块间通信 |
| 信息守恒契约 | 8/10 | 验证逻辑通用 |
| Summary 下游 prompt（13个） | 7-8/10 | 操作对象是"方案"，不关心内容领域 |

**结论**: Solution Pro V2 的**架构骨架**是优秀的 AI Native 设计，问题出在**内容层**而非**结构层**。这意味着修复不需要重构架构，只需要替换/参数化内容。

---

## 五、改进路线图

### Phase 1: 解除硬阻塞（预估 3-5 天）

| # | 任务 | 影响文件 | 效果 |
|---|------|---------|------|
| 1.1 | `DOMAIN_CATEGORIES`: Literal → str + suggested list | `schemas/schemas.py` | 解除 Pydantic 阻塞 |
| 1.2 | `EXPERT_TEMPLATE_REGISTRY`: 硬编码 → YAML 配置 | `schemas/schemas.py` + 新建 `config/domain_templates.yaml` | 支持外部注入领域模板 |
| 1.3 | `research_orchestrator.py`: Generalist Expert domain 动态化 | `research_orchestrator.py` | 从 living_spec 推断 domain |
| 1.4 | `summary_orchestrator.py`: Summarizer 输出模板参数化 | `summary_orchestrator.py` | 从配置或 LLM 推断章节结构 |

**验收标准**: 非软件域输入不再被 Pydantic 拒绝，能跑通端到端流程。

### Phase 2: 泛化 Prompt 层（预估 5-7 天）

| # | 任务 | 影响文件 | 效果 |
|---|------|---------|------|
| 2.1 | meta_planner.md: 增加 3 个非软件示例 | `prompts/solution_pro/meta_planner.md` | LLM 不再只输出软件专家 |
| 2.2 | expert_planner_base.md: 多领域示例 | `prompts/solution_pro/expert_planner_base.md` | 约束不再只有 HTTPS/TLS |
| 2.3 | convergence_planner.md: 多领域示例 | `prompts/solution_pro/convergence_planner.md` | 验证方法不再只有 curl/psql |
| 2.4 | research_expert_base.md: 去"技术名称+版本号"硬要求 | `prompts/solution_pro/research_expert_base.md` | 研究输出适配领域 |
| 2.5 | summary_base_synthesizer.md: 领域自适应输出模板 | `prompts/solution_pro/summary_base_synthesizer.md` | 报告结构适配领域 |
| 2.6 | 其他 7 个 4-6 分 prompt 的示例泛化 | 7 个 prompt 文件 | 全面消除软件示例偏差 |

**验收标准**: 非软件域场景产出的方案报告不包含不相关的软件概念。

### Phase 3: 泛化 Schema 和代码（预估 5-7 天）

| # | 任务 | 影响文件 | 效果 |
|---|------|---------|------|
| 3.1 | Schema 字段重命名（technology_stack → selection_stack 等） | `schemas/schemas.py` | 字段名通用化 |
| 3.2 | task_builder.py 重写：输出结构/种子URL/检查项配置化 | `task_builder.py` | 最严重的 3/10 文件修复 |
| 3.3 | research_expert_base.md: "15 次搜索"方向领域自适应 | `prompts/solution_pro/research_expert_base.md` | 搜索内容匹配领域 |
| 3.4 | Gate B 检查项配置化（从 YAML 加载领域检查项） | `meta_planner.md` + 配置文件 | Gate 检查项匹配领域 |
| 3.5 | Cage F6/F7: 硬编码 LLM 关键词 → 配置化 | `schemas/schemas.py` | 去除特定项目约束 |

**验收标准**: 三个测试场景（投资/硬件/商业）的端到端通过率 > 70%。

### Phase 4: 领域模板体系（预估 3-5 天）

| # | 任务 | 效果 |
|---|------|------|
| 4.1 | 设计 `domain_templates.yaml` 配置格式 | 统一的领域模板注入机制 |
| 4.2 | 创建 4 个领域模板：software / investment / hardware / business | 开箱即用的多领域支持 |
| 4.3 | Living Spec 增加 `domain_type` 字段 | 自动选择领域模板 |
| 4.4 | master_orchestrator.py: 根据 domain_type 加载模板 | 零代码切换领域 |

**验收标准**: 新增领域只需编写 YAML 配置文件，无需改代码或 prompt。

---

## 六、投入产出评估

| Phase | 工时 | 效果 | 优先级 |
|-------|:---:|------|:------:|
| Phase 1: 解除硬阻塞 | 3-5 天 | 非软件域能跑通 | 🔴 P0 |
| Phase 2: 泛化 Prompt | 5-7 天 | 输出质量显著提升 | 🟠 P1 |
| Phase 3: 泛化 Schema/代码 | 5-7 天 | 全面泛化 | 🟠 P1 |
| Phase 4: 领域模板体系 | 3-5 天 | 可扩展的多领域支持 | 🟡 P2 |
| **总计** | **16-24 天** | **从 5.4/10 提升到 8.5/10** | |

---

## 七、新发现：SemanticAnchor.category 白名单阻塞

> **发现者**: Agent D（投资分析压力测试，kimi-for-coding）— 其他 5 个 Agent 均未发现

```python
# domains/spec_pro/contracts/living_spec.py
valid = {"platform_api", "architecture_principle", "external_system", "technical_constraint"}
if v not in valid:
    raise ValueError(...)
```

**影响**: SemanticAnchor 是信息守恒的核心机制（全链路透传的不可变实体）。它的 `category` 字段只接受 4 个软件工程类别。如果 Spec Pro 提取投资/硬件/商业领域的语义锚点（如 `market_segment`、`patent_portfolio`、`regulatory_framework`），Pydantic 会直接 `raise ValueError`。

**这意味着**: 即使绕过了 `DOMAIN_CATEGORIES` 的 Literal 阻塞，SemanticAnchor 会在更上游（Spec Pro 阶段）就阻断非软件领域的信息守恒链路。

**严重度**: 🔴 CRITICAL（与阻塞点 1 同级）
**修复**: 扩展为开放字符串 + 建议列表，或增加领域特定类别。

---

## 八、AI Native 视角的反思

### 当前系统做对了什么

1. **能力正交**: Code 做编排（确定性），LLM 做内容生成（非确定性）— 这个分工是正确的
2. **信息守恒**: Semantic Anchors + 全链路透传 + Judge 验证 — 信息流保障机制完善
3. **多层验证**: Gate A/B + Harness + Review Layer B + 独立 Judge — 质量保障体系健全
4. **收敛机制**: 三轮收敛 + 动态专家 + 可配置 Gate — 架构灵活

### 当前系统做错了什么

1. **示例 = 契约**: Prompt 中的 few-shot 示例实际上充当了隐式契约，但设计时没有意识到这一点
2. **Literal ≠ 泛化**: Pydantic Literal 类型用于领域分类，违背了"代码适应 LLM 输出"的原则
3. **模板 ≠ 硬编码**: 输出模板应该是"参考框架"而非"固定结构"
4. **搜索方向 ≠ 搜索次数**: "15 次搜索"是量化约束（好），但搜索方向写死了（坏）

### 教训

> **AI Native 系统的泛化性不取决于架构的泛化性，而取决于注入内容的泛化性。**
>
> Solution Pro V2 的架构是泛化的（9/10），但注入的示例、术语、模板是软件的（3/10）。
> 这导致了一个"AI Native 壳 + 软件开发核"的系统。
>
> **修复方向不是重构架构，而是泛化注入内容。**

---

*2026-07-07 | 小满 + 6 个审计 Agent | 3 个模型交叉验证*
