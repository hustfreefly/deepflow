# 向后兼容性审计报告

> **审计对象**: Solution Pro V2 泛化性实施方案 (IMPLEMENTATION_PLAN.md)
> **审计视角**: 向后兼容性与回归安全
> **审计日期**: 2026-07-07
> **审计范围**: Pydantic 兼容性、代码引用链、Prompt 兼容性、测试覆盖、运行时行为

---

## 总体评价：CONDITIONAL

**结论**: 实施方案大方向可行，但存在 **3 个遗漏的引用链断点** 和 **5 个测试覆盖缺口**。Phase 1-2 风险可控，Phase 3-4 需要补充关键修改点后方可安全执行。

**关键发现**:
1. ✅ `DOMAIN_CATEGORIES` 和 `EXPERT_TEMPLATE_REGISTRY` 实际引用面极窄（仅 schemas.py 内部定义 + `__all__` 导出），方案影响评估准确
2. 🔴 **遗漏**: `frozen_spec.py:412` 硬编码消费 `SemanticAnchor.category` 的 4 个固定值，方案未提及
3. 🔴 **遗漏**: `extract_semantic_anchors.py` 的 LLM Prompt 硬编码 4 个分类维度，方案未提及
4. 🔴 **遗漏**: `coordinator.py:611` 的 Prompt 模板硬编码 4 个分类维度，方案未提及
5. 🟡 Phase 4 的 Schema alias 方案有 3 处下游消费者需要同步验证
6. 🟡 `@lru_cache` 在多域并发场景存在缓存串扰风险

---

## 影响面分析

| 修改项 | 受影响代码 | 兼容性风险 | 缓解方案 |
|--------|-----------|-----------|---------|
| Phase 1.1: `DOMAIN_CATEGORIES` Literal → str | `schemas.py:34-39` 定义处；`__all__` 导出 | 🟢 **低** — 无外部 Python 文件 import 此符号 | 方案正确，`str` 是 `Literal` 超集 |
| Phase 1.2: `EXPERT_TEMPLATE_REGISTRY` → 配置驱动 | `schemas.py:40-90` 定义处；`__all__` 导出 | 🟢 **低** — 无外部 Python 文件 import 此符号 | 需确保 YAML 内容与硬编码完全一致 |
| Phase 1.3: `SemanticAnchor.category` 开放枚举 | `living_spec.py:133-138` validator；**`frozen_spec.py:412-416`** 优先级分层；**`extract_semantic_anchors.py:36-45`** LLM Prompt；**`coordinator.py:611`** Prompt 模板 | 🔴 **高** — 方案遗漏 3 处下游引用 | 见下方「必须新增修改点」|
| Phase 2: task_builder.py 硬编码修复 | `task_builder.py:537-538` 种子 URL fallback；`master_orchestrator.py:783` 默认 domain | 🟡 **中** — 散落硬编码点需逐一排查 | 方案基本覆盖，但 master_orchestrator.py:783 未提及 |
| Phase 3: Prompt 层泛化 | 12+ 个 `.md` prompt 文件含软件术语 | 🟡 **中** — 改 Prompt 会改变 LLM 输出分布 | 需 A/B 对比验证软件域输出质量 |
| Phase 4: Schema 字段 alias | `schemas.py` ArchitectureSchema/DetailedDesignSchema；下游 `context_injector.py:227`、`gen_blueprint.py`、`e2e_solution_test.py:293,438` | 🟡 **中** — alias 仅在 `by_alias=True` 时生效 | 需验证所有序列化路径的 alias 行为 |

---

## 引用链追踪

### 1. `DOMAIN_CATEGORIES` 引用链

| 引用处 | 文件:行号 | 用途 | 兼容 | 说明 |
|--------|----------|------|:----:|------|
| 定义 | `schemas/schemas.py:34` | `Literal[...]` 类型 | ✅ | 改为 `str` 不影响 |
| `__all__` 导出 | `schemas/schemas.py:934` | 公开 API | ✅ | 名称不变 |
| **外部 import** | **无** | — | ✅ | grep 确认无任何 `.py` 文件 import 此符号 |

**结论**: `DOMAIN_CATEGORIES` 实际是一个"死代码"符号 — 定义了但未被任何运行时代码消费。改为 `str` 零风险。

### 2. `EXPERT_TEMPLATE_REGISTRY` 引用链

| 引用处 | 文件:行号 | 用途 | 兼容 | 说明 |
|--------|----------|------|:----:|------|
| 定义 | `schemas/schemas.py:40` | 硬编码专家模板 | ✅ | 改为配置加载 |
| `__all__` 导出 | `schemas/schemas.py:935` | 公开 API | ✅ | 名称不变 |
| **外部 import** | **无** | — | ✅ | grep 确认无任何 `.py` 文件 import 此符号 |

**结论**: `EXPERT_TEMPLATE_REGISTRY` 同样是"死代码"符号。改为配置驱动零风险，但需确保 YAML 提取内容与硬编码完全一致。

### 3. `SemanticAnchor.category` 引用链（⚠️ 方案遗漏）

| 引用处 | 文件:行号 | 用途 | 兼容 | 说明 |
|--------|----------|------|:----:|------|
| Pydantic validator | `living_spec.py:133-138` | 验证 category ∈ 4 固定值 | 🔴 | 方案已覆盖，改为开放枚举 |
| **优先级分层** | **`frozen_spec.py:412-416`** | `if cat in ["platform_api", "architecture_principle"]` → MUST_FOLLOW | 🔴 | **方案未提及！** 新 category 值会全部落入 CONTEXT 层 |
| **LLM 提取 Prompt** | **`extract_semantic_anchors.py:36-45`** | Prompt 中硬编码 4 个分类维度 | 🔴 | **方案未提及！** LLM 只会产出 4 个固定值 |
| **Prompt 示例** | **`extract_semantic_anchors.py:62`** | `"category": "platform_api"` 硬编码示例 | 🔴 | **方案未提及！** |
| **coordinator Prompt** | **`coordinator.py:611,619`** | 提取维度描述 + 示例 | 🔴 | **方案未提及！** |
| pipeline_designer 检查 | `ship_pro/pipeline_designer.py:364-366` | 只检查 `"category" in anchor`，不验证值 | ✅ | 不验证具体值，兼容 |
| conservation_judge | `ship_pro/conservation_judge.py` | 不涉及 category 值 | ✅ | 无关 |
| handoff.py | `spec_pro/handoff.py:32,40,53` | 透传 semantic_anchors，不检查 category 值 | ✅ | 无关 |
| gate.py | `spec_pro/contracts/gate.py:156-157` | 只检查 semantic_anchors 是否非空 | ✅ | 无关 |

**关键风险**: `frozen_spec.py:412-416` 的优先级分层逻辑：
```python
if cat in ["platform_api", "architecture_principle"]:
    priority_layers["MUST_FOLLOW"].append(name)
elif cat == "technical_constraint":
    priority_layers["SHOULD_FOLLOW"].append(name)
else:
    priority_layers["CONTEXT"].append(name)
```
如果开放 category 枚举但不修改此处分层逻辑，投资域的 `patent_portfolio`、`market_segment` 等新 category 会全部落入 `CONTEXT`（最低优先级），而非业务期望的 `MUST_FOLLOW`。**这会导致非软件域的约束优先级错乱**。

### 4. `task_builder.py` 硬编码引用链

| 引用处 | 文件:行号 | 用途 | 兼容 | 说明 |
|--------|----------|------|:----:|------|
| 种子 URL fallback | `task_builder.py:537-538` | 硬编码阿里云/AWS/Martin Fowler | 🟡 | 方案已覆盖 |
| 默认 domain | `master_orchestrator.py:783` | `config.get("domain", "backend_api")` | 🟡 | **方案未提及此 fallback 值** |
| build_*_task 签名 | `task_builder.py` 各 build 函数 | 当前不接收 domain_id | 🟡 | 方案 2.5 已规划透传机制 |

### 5. Phase 4 Schema 字段 alias 下游消费者

| 引用处 | 文件:行号 | 消费方式 | 兼容 | 说明 |
|--------|----------|---------|:----:|------|
| context_injector | `core/blackboard/context_injector.py:227` | Markdown 表格中引用 `technology_stack` 字段名 | 🟡 | 这是 Prompt 文本，不是代码消费 |
| gen_blueprint | `blackboard/gen_blueprint.py:179,193,207...` | 构造 `technology_stack` 数据 | 🟡 | 这是写入 blackboard 的数据，不走 Schema |
| e2e_solution_test | `tests/e2e_solution_test.py:293,438` | 检查 `deployment_view` 字段存在 | 🟡 | 测试直接检查 JSON key |
| state_manager | `state_manager.py:89` | `model_dump(mode="json")` | 🟡 | 需确认是否 `by_alias=True` |

**关键风险**: Pydantic V2 的 `Field(alias=...)` 行为：
- `model_dump(by_alias=True)` → 输出 alias 名（如 `technology_stack`）
- `model_dump(by_alias=False)`（默认） → 输出字段名（如 `selection_stack`）
- `model_dump_json()` → 默认 `by_alias=True`

如果下游消费者使用 `model_dump()` 而非 `model_dump(by_alias=True)`，输出的 JSON key 会从 `technology_stack` 变为 `selection_stack`，**导致下游断裂**。

---

## 测试覆盖缺口

### 现有测试统计

| 测试文件 | 测试数 | 覆盖修改点 |
|---------|:------:|-----------|
| `test_schemas.py` | 16 | Gate 权重、ExpertManifest、ExpertPlan、UnifiedConstraints、PlanningConvergence、validate_stage_output |
| `test_base_classes.py` | 21 | Blackboard 路径、deprecated aliases、V1→V2 映射 |
| `test_integration.py` | 23 | 端到端管线流程（mock） |
| `test_phase1_acceptance.py` | 24 | Planning Orchestrator 集成测试 |
| `test_phase3_acceptance.py` | 17 | Phase 3 验收测试 |
| `test_planning_orchestrator.py` | 12 | Planning 各子阶段 |
| `test_verification_constraints.py` | 10 | 约束验证 |
| `test_convergence_migration.py` | 5 | 收敛点迁移 |
| `test_golden_case_010/011/012.py` | 9 | Golden case E2E |
| `test_ship_pro.py` | 19 | Ship Pro 管线 |
| 全局测试 (unit + contract) | ~200+ | 各种契约测试 |
| **总计** | **~356** | — |

> 注: 方案声称"147 测试"，实际计数约 356 个 test function。可能是方案统计口径不同。

### 覆盖缺口分析

| 修改点 | 现有测试覆盖 | 缺口 | 风险等级 |
|--------|:----------:|------|:-------:|
| DOMAIN_CATEGORIES Literal → str | ❌ 无直接测试 | 无测试验证 DOMAIN_CATEGORIES 的类型行为 | 🟢 低风险（死代码） |
| EXPERT_TEMPLATE_REGISTRY → 配置 | ❌ 无直接测试 | 无测试验证 Registry 内容一致性 | 🟢 低风险（死代码） |
| SemanticAnchor.category 开放枚举 | ❌ 无测试 | **无测试验证新 category 值通过 validator** | 🔴 高风险 |
| frozen_spec.py 优先级分层 | ❌ 无测试 | **无测试验证新 category 的优先级分配** | 🔴 高风险 |
| extract_semantic_anchors.py Prompt | ❌ 无测试 | **无测试验证 LLM 产出新 category 值** | 🔴 高风险 |
| domain_loader.py 配置加载 | ❌ 不存在 | **新文件，需全新测试** | 🔴 高风险 |
| domain_loader.py lru_cache | ❌ 不存在 | **无测试验证缓存隔离** | 🟡 中风险 |
| task_builder.py 种子 URL 配置化 | ❌ 无直接测试 | 无测试验证非软件域种子 URL | 🟡 中风险 |
| task_builder.py domain_id 透传 | ❌ 无直接测试 | 无测试验证 domain_id 从 spec 到 build 函数的透传 | 🟡 中风险 |
| Schema alias 序列化 | ⚠️ 部分 | `test_deprecated_aliases_mapping` 测试 stage aliases，不测试 Field alias | 🟡 中风险 |
| master_orchestrator.py:783 fallback | ❌ 无测试 | 无测试验证 domain fallback 行为 | 🟡 中风险 |
| Prompt 修改后 LLM 输出格式 | ❌ 无测试 | 无测试验证修改后 Prompt 仍满足 Schema | 🟡 中风险 |

---

## 运行时风险

### 1. `@lru_cache` 多域并发风险

**位置**: `domain_loader.py` 的 `load_domain_config(domain_id: str)` 使用 `@lru_cache(maxsize=32)`

**风险**: 
- `lru_cache` 是进程级缓存，不是线程级。在多线程/异步场景下，不同 domain_id 的请求共享同一缓存
- **缓存串扰**: 如果先加载 `software` 配置，再加载 `investment` 配置，两者互不影响（key 不同）— 这本身没问题
- **真正风险**: 如果 YAML 文件在运行时被修改（用户编辑配置），`lru_cache` 会返回过期数据，无失效机制
- **maxsize=32**: 如果领域数量超过 32，最旧配置会被淘汰。当前 4 个领域不会触发

**缓解方案**:
```python
# 方案 A: 添加 cache_invalidate 方法
def invalidate_domain_cache(domain_id: str = None):
    if domain_id:
        load_domain_config.cache_clear()  # 清除所有缓存
    # 或使用 diskcache 替代 lru_cache

# 方案 B: 使用 yaml mtime 作为 cache key
```

**评级**: 🟡 中风险 — 当前场景可控，但缺乏配置热更新能力

### 2. YAML 文件缺失 fallback 行为

**位置**: `domain_loader.py` 的 `load_domain_config`:
```python
if not path.exists():
    path = DOMAINS_DIR / "software.yaml"  # 向后兼容
```

**风险**:
- 静默 fallback 到 software 域 — 用户可能不知道配置缺失
- 如果 `software.yaml` 也不存在，`open()` 会 raise `FileNotFoundError`，无友好错误信息
- 与方案的"配置驱动"理念矛盾 — 未知领域应该报错或明确降级，而非静默替换

**缓解方案**:
```python
if not path.exists():
    if domain_id != "software":
        logger.warning(f"Domain config '{domain_id}.yaml' not found, falling back to 'software.yaml'")
    path = DOMAINS_DIR / "software.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Default domain config 'software.yaml' not found at {path}")
```

**评级**: 🟡 中风险 — fallback 逻辑需增加日志和双重缺失保护

### 3. 配置加载失败错误处理

**风险**: `yaml.safe_load()` 可能因 YAML 语法错误抛出 `yaml.YAMLError`，当前方案无 try/except

**缓解方案**:
```python
try:
    with open(path) as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError(f"Domain config must be a YAML mapping, got {type(config).__name__}")
    return config
except yaml.YAMLError as e:
    raise ValueError(f"Domain config YAML syntax error in {path}: {e}") from e
```

**评级**: 🟡 中风险 — 需增加 YAML 解析错误的友好提示

### 4. Pydantic alias 序列化不一致风险

**位置**: Phase 4 的 `Field(alias="technology_stack")` 方案

**风险**:
- Pydantic V2 (当前版本 2.13.4) 中，`model_dump()` 默认 `by_alias=False`
- `model_dump_json()` 默认 `by_alias=True`
- 如果下游消费者混合使用两种方法，会出现字段名不一致

**现有代码中的 alias 使用**:
- `schemas.py:220` — `AcceptanceCriterion` 使用 `populate_by_name=True` + `alias="criteria_id"`
- `schemas.py:618,663,758` — `metadata: dict = Field(alias="_metadata")`
- `state_manager.py:89` — `model_dump(mode="json")` 未指定 `by_alias`

**关键验证点**:
```python
# 需验证: ArchitectureSchema 序列化后 technology_stack 还是 selection_stack?
schema = ArchitectureSchema(...)
schema.model_dump()  # → {"selection_stack": [...]} (字段名)
schema.model_dump(by_alias=True)  # → {"technology_stack": [...]} (alias)
schema.model_dump_json()  # → '{"technology_stack": [...]}' (alias)
```

**评级**: 🟡 中风险 — 需全量排查所有序列化路径

---

## 必须新增的测试清单

### 🔴 P0 — 阻塞发布

| # | 测试名称 | 覆盖修改点 | 预期行为 |
|---|---------|-----------|---------|
| T1 | `test_semantic_anchor_accepts_investment_categories` | Phase 1.3 | `SemanticAnchor(category="patent_portfolio")` 不抛 ValueError |
| T2 | `test_semantic_anchor_accepts_hardware_categories` | Phase 1.3 | `SemanticAnchor(category="thermal_parameter")` 不抛 ValueError |
| T3 | `test_semantic_anchor_rejects_short_category` | Phase 1.3 | `SemanticAnchor(category="x")` 抛 ValueError（太短） |
| T4 | `test_frozen_spec_priority_layers_for_investment_anchors` | **遗漏修改点** | 投资域 anchor 的 priority_layers 分配正确 |
| T5 | `test_domain_loader_loads_software_config` | Phase 0 | `load_domain_config("software")` 返回与原 `EXPERT_TEMPLATE_REGISTRY` 一致的数据 |
| T6 | `test_domain_loader_fallback_to_software` | Phase 0 | `load_domain_config("unknown")` 回退到 software |
| T7 | `test_domain_loader_missing_file_error` | Phase 0 | software.yaml 也不存在时抛出清晰错误 |
| T8 | `test_schema_alias_serialization_consistency` | Phase 4 | `ArchitectureSchema.model_dump(by_alias=True)` 输出 `technology_stack` |

### 🟡 P1 — 应在同 Phase 内完成

| # | 测试名称 | 覆盖修改点 | 预期行为 |
|---|---------|-----------|---------|
| T9 | `test_domain_loader_lru_cache_isolation` | Phase 0 | 连续调用不同 domain_id 返回各自配置 |
| T10 | `test_task_builder_researcher_seed_urls_for_investment` | Phase 2 | `build_researcher_task(domain_id="investment")` 包含投资种子 URL |
| T11 | `test_task_builder_designer_output_structure_for_hardware` | Phase 2 | `build_designer_task(domain_id="hardware")` 包含硬件设计结构 |
| T12 | `test_master_orchestrator_domain_fallback` | Phase 2 遗漏 | `master_orchestrator.py:783` domain 默认值为 "software" |
| T13 | `test_extract_semantic_anchors_prompts_investment_categories` | **遗漏修改点** | 投资域 narrative 提取出 `patent_portfolio` 等 category |
| T14 | `test_prompt_meta_planner_no_software_bias_for_investment` | Phase 3 | 投资域 meta_planner prompt 不包含 OWASP/PostgreSQL |
| T15 | `test_schema_model_dump_json_uses_alias` | Phase 4 | `model_dump_json()` 输出 alias 名 |

### 🟢 P2 — 可后续迭代

| # | 测试名称 | 覆盖修改点 | 预期行为 |
|---|---------|-----------|---------|
| T16 | `test_domain_loader_yaml_syntax_error_handling` | Phase 0 | YAML 语法错误时抛出友好错误 |
| T17 | `test_domain_loader_concurrent_access` | Phase 0 | 多线程并发加载不同 domain 不串扰 |
| T18 | `test_e2e_investment_domain_pipeline` | Phase 6 | 投资域 E2E 管线跑通 |
| T19 | `test_e2e_hardware_domain_pipeline` | Phase 6 | 硬件域 E2E 管线跑通 |
| T20 | `test_software_domain_regression_baseline` | 全程 | 软件域输出质量 ≥ 改造前基线 |

---

## 方案遗漏的必须修改点

### 🔴 遗漏 1: `frozen_spec.py:412-416` 优先级分层逻辑

**文件**: `domains/solution_pro/frozen_spec.py`  
**行号**: 412-416  
**当前代码**:
```python
if cat in ["platform_api", "architecture_principle"]:
    priority_layers["MUST_FOLLOW"].append(name)
elif cat == "technical_constraint":
    priority_layers["SHOULD_FOLLOW"].append(name)
else:
    priority_layers["CONTEXT"].append(name)
```

**问题**: 新领域的 category 值（如 `patent_portfolio`、`thermal_parameter`）会全部落入 `CONTEXT`（最低优先级），导致关键约束被忽略。

**建议修复**: 从领域配置中读取优先级映射，或改为基于 confidence 的自动分层：
```python
# 方案 A: 配置驱动
priority_map = domain_cfg.get("category_priority", {
    "platform_api": "MUST_FOLLOW",
    "architecture_principle": "MUST_FOLLOW",
    "technical_constraint": "SHOULD_FOLLOW",
})
layer = priority_map.get(cat, "CONTEXT")

# 方案 B: 基于 confidence 自动分层
if anchor.get("confidence", 0) >= 0.9:
    priority_layers["MUST_FOLLOW"].append(name)
elif anchor.get("confidence", 0) >= 0.7:
    priority_layers["SHOULD_FOLLOW"].append(name)
else:
    priority_layers["CONTEXT"].append(name)
```

### 🔴 遗漏 2: `extract_semantic_anchors.py` LLM Prompt

**文件**: `domains/spec_pro/extract_semantic_anchors.py`  
**行号**: 36-62  
**当前代码**: EXTRACTION_PROMPT 硬编码 4 个分类维度

**问题**: LLM 被 instruction 限制只能产出 4 个固定 category 值，即使开放了 Pydantic validator，LLM 也不会产出新值。

**建议修复**: Prompt 中添加领域自适应的分类维度描述，或在 Phase 3 的 Prompt 泛化中一并处理。

### 🔴 遗漏 3: `coordinator.py:611,619` Prompt 模板

**文件**: `domains/spec_pro/coordinator.py`  
**行号**: 611, 619  
**当前代码**: 提取维度描述硬编码 4 个分类

**问题**: 与 `extract_semantic_anchors.py` 同理。

### 🟡 遗漏 4: `master_orchestrator.py:783` 默认 domain

**文件**: `domains/solution_pro/master_orchestrator.py`  
**行号**: 783  
**当前代码**: `config.get("domain", "backend_api")`

**问题**: fallback 值 `"backend_api"` 是软件域特定值。当 domain 配置缺失时，非软件域需求会被错误归类为 software/backend_api。

**建议修复**: 改为 `config.get("domain", infer_domain_id(living_spec))` 或至少改为 `"software"`。

---

## 附录: 文件影响清单

| Phase | 修改文件 | 新增文件 | 风险等级 |
|-------|---------|---------|:-------:|
| Phase 0 | — | `config/domain_loader.py`, `config/domains/*.yaml` | 🟢 低 |
| Phase 1 | `schemas/schemas.py`, `living_spec.py`, `prompts/meta_planner.md` | — | 🟢 低 |
| Phase 1 (遗漏) | **`frozen_spec.py`**, **`extract_semantic_anchors.py`**, **`coordinator.py`** | — | 🔴 高 |
| Phase 2 | `task_builder.py`, `master_orchestrator.py` | — | 🟡 中 |
| Phase 3 | 12 个 prompt `.md` 文件 | — | 🟡 中 |
| Phase 4 | `schemas/schemas.py` | — | 🟡 中 |
| Phase 4 (下游验证) | `context_injector.py`, `gen_blueprint.py`, `e2e_solution_test.py` | — | 🟡 中 |

---

*审计完成。建议在实施前将 4 个遗漏修改点纳入方案，并优先完成 P0 测试清单。*
