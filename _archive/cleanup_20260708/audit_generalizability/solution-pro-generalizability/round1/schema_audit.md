# Schema/Contract 层泛化性审计报告

> Agent B | 模型: qwen3.7-max | 耗时: 2m48s

## 汇总

| Schema | 评分 | 严重度 | 核心问题 |
|--------|------|--------|---------|
| DOMAIN_CATEGORIES | 2/10 | 🔴 CRITICAL | Literal 硬编码 11 个软件域，Pydantic 层面阻止非软件域 |
| EXPERT_TEMPLATE_REGISTRY | 2/10 | 🔴 CRITICAL | 全部 9 个 key 为软件领域，expert 角色全是软件工程师 |
| ExpertManifestSchema | 7/10 | 🟡 | 结构泛化但依赖 REGISTRY 限制实际可用范围 |
| Constraint/ExpertPlanSchema | 8/10 | 🟢 | 字段名通用，RFC 2119 priority 通用 |
| UnifiedConstraintsSchema | 5/10 | 🟠 | Cage F6 硬编码 "LLM控制" 关键词，F7 偏离检测绑定特定项目 |
| ResearchExpertSchema | 6/10 | 🟡 | `technology_recommendations` 字段名绑定技术 |
| ArchitectureSchema | 4/10 | 🟠 | `technology_stack`/`deployment_view`/`data_flows` 软件专属 |
| DetailedDesignSchema | 3/10 | 🔴 | `modules`/`apis`/`database_schema`/`sequence_diagrams` 全软件 |
| ConsolidationSchema | 7/10 | 🟡 | 大部分概念通用 |
| FinalSolutionSchema | 7/10 | 🟡 | 部分通用 |
| Living Spec (Input) | 8/10 | 🟢 | 结构泛化，少量软件偏向 |
| Frozen Spec | 7/10 | 🟡 | GROUP_MAP 偏向 Functional/NonFunctional 软件分类 |
| Pipeline State | 9/10 | 🟢 | 完全通用状态机 |
| Stage Contract | 9/10 | 🟢 | 完全通用契约 |
| Information Conservation | 8/10 | 🟢 | 验证逻辑通用 |

## CRITICAL 发现（阻止非软件域运行）

### 1. DOMAIN_CATEGORIES — Literal 类型硬编码
```python
DOMAIN_CATEGORIES = Literal[
    "backend_api", "frontend_ui", "mobile", "data_migration",
    "devops", "ml", "iac", "security", "performance",
    "testing_qa", "accessibility",
]
```
- **影响**: 非软件域输入会在 Pydantic validation 层面被 REJECT
- **修复**: 改为 `str` + 动态注册表，或 `Enum` + 配置文件驱动

### 2. EXPERT_TEMPLATE_REGISTRY — 硬编码软件角色
- **影响**: Meta-Planner 只能从软件工程师角色中选择专家
- **修复**: Registry 由 YAML 配置文件驱动，领域定义可从外部注入

### 3. DetailedDesignSchema — 全软件概念
```python
class DetailedDesignSchema(V2BaseSchema):
    modules: list[dict]
    apis: list[dict]
    database_schema: dict
    sequence_diagrams: list[dict]
```
- **影响**: 投资分析/硬件产品/商业策略无法产生这些输出
- **修复**: 重命名为 `components`/`interfaces`/`data_model`/`interaction_flows`，或改为可选

### 4. Cage F6/F7 — 特定项目约束硬编码
```python
scope_keywords = ['业务控制流', '运维控制流', 'Python.*确定性']
trigger_keywords = ['全LLM控制', 'LLM控制']
```
- **影响**: 非 LLM 控制类项目会被错误的验证逻辑拦截
- **修复**: 抽取为可配置的 domain-specific rules

## MAJOR 发现

### 5. ArchitectureSchema — `technology_stack` + `deployment_view`
- 投资分析方案没有"技术栈"概念
- 商业策略没有"部署视图"概念
- **修复**: 拆分为 `generic_architecture` + `domain_extensions`

### 6. ResearchExpertSchema — `technology_recommendations`
- 投资分析需要"投资建议"而非"技术推荐"
- **修复**: `technology_recommendations` → `recommendations`

## 泛化性良好的部分（值得保留）

- ✅ Pipeline State 状态机（9/10）— 完全通用
- ✅ Stage Contract 契约（9/10）— 完全通用
- ✅ Constraint/ExpertPlanSchema（8/10）— RFC 2119 通用标准
- ✅ Living Spec 输入格式（8/10）— objective/pain_points/scenarios/capabilities 通用
- ✅ Information Conservation（8/10）— 验证逻辑通用
- ✅ ExpertManifestSchema 结构（7/10）— 三层架构通用

## 改进路线图建议

### Phase 1: 解除硬阻塞（1-2天）
1. `DOMAIN_CATEGORIES`: Literal → str + config
2. `EXPERT_TEMPLATE_REGISTRY`: 硬编码 → YAML 配置
3. Cage F6/F7: 硬编码 → 配置化

### Phase 2: 抽象化 Schema（3-5天）
4. DetailedDesignSchema: 重命名 + 可选化
5. ArchitectureSchema: 拆分通用/领域
6. ResearchExpertSchema: 去 "technology" 前缀

### Phase 3: Prompt 适配（1-2周）
7. meta_planner.md: 添加非软件示例
8. summary_base_synthesizer.md: 输出模板参数化
9. research_expert_base.md: 去 "技术名称+版本号" 硬要求
