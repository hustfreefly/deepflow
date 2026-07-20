> **版本**: V2.2.0 | **最后更新**: 2026-07-12 | **MD-First 架构迁移**

# DeepFlow 架构文档

> 多 Agent 管线框架，运行在 OpenClaw 之上。  
> 将模糊需求转化为可交付工作包：**Spec Pro → Solution Pro → Ship Pro → Deliver Pro**。

---

## Part 1: 系统架构

### 1.1 定位

DeepFlow 不是一个 Agent，而是 **Agent 的编排框架**。它在 OpenClaw 的 `sessions_spawn` 原语之上构建了：

- **域（Domain）**：独立的能力单元，每个域有自己的入口、prompts、测试
- **管线（Pipeline）**：域间协作，上游输出自动成为下游输入
- **统一 Blackboard**：基于文件系统的跨域状态共享（`.deepflow/blackboard/{project}/`）
- **全链路追踪**：跨域 `trace_id`，从需求到交付包可追溯

### 1.2 五域架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           DeepFlow V2.2.0                                    │
│                                                                              │
│  ┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌───────────────┐
│  │  Spec Pro    │──▶│  Solution Pro    │──▶│   Ship Pro       │──▶│ Deliver Pro   │
│  │  V2.2.0      │   │  V2.1.1          │   │   V2.0.0         │   │ V1.0.0        │
│  │              │   │                  │   │                  │   │               │
│  │  需求梳理引擎 │   │  方案设计引擎     │   │   交付包生成引擎  │   │  执行交付引擎  │
│  │  Living Spec │   │  DomainProfile   │   │   ShipPackage    │   │  Work Package │
│  └──────────────┘   └──────────────────┘   └──────────────────┘   └───────────────┘
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────────────────────────────────┐    │
│  │  Research Pro    │    │  Core Infrastructure                         │    │
│  │  V2.0.0          │    │  • Blackboard Manager (MD-First)             │    │
│  │  深度研究引擎     │    │  • Cage (契约笼子) Validator                  │    │
│  │                  │    │  • Quality Gate                              │    │
│  │  DDGS + 来源分级  │    │  • Trace (全链路追踪)                         │    │
│  │  + 引用验证       │    │  • Prompt Registry                           │    │
│  └──────────────────┘    └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 数据流（MD-First）

```
用户输入（自然语言）
    │
    ▼
┌─────────────┐  living_spec.md + spec_track.json  ┌─────────────────┐
│  Spec Pro   │ ─────────────────────────────────▶ │  Solution Pro   │
│  多轮对话    │   (MD source of truth + derivative)│  DomainProfile   │
│  苏格拉底式  │                                    │  + 三模块方案     │
└─────────────┘                                    └────────┬────────┘
                                                            │
                                frozen_spec.md + frozen_spec.json
                                (MD source of truth + simplified JSON)
                                                            │
                                                            ▼
                                                   ┌─────────────────┐
                                                   │    Ship Pro     │
                                                   │  PipelineDesign │
                                                   │  + Worker 产出   │
                                                   └────────┬────────┘
                                                            │
                                ship_package.md + ship_package.json
                                (MD source of truth + derivative)
                                                            │
                                                            ▼
                                                   ┌─────────────────┐
                                                   │  Deliver Pro    │
                                                   │  5-Phase 流水线  │
                                                   │  → 可交付产物     │
                                                   └─────────────────┘
```

> **MD-First 原则**: Markdown 是 source of truth，JSON 是 derivative（仅用于 Gate 质量检查等确定性消费场景）。

### 1.4 AI Native 设计原则

| 原则 | 实现 |
|:-----|:-----|
| **代码做确定性粗筛** | Pydantic Schema 验证字段存在性、类型、格式 |
| **LLM 做语义判断** | Judge Agent 评估质量、完整性、一致性 |
| **契约笼子** | Pydantic + Gate + LLM Judge 三层约束 |
| **域自推断** | LLM 动态推断领域特征，零配置接入新领域 |
| **信息守恒** | 跨模块传递时追踪约束/需求的保留率 |

### 1.5 代码规模（已验证）

| 模块 | Python 行数 | 测试数 | Prompts |
|:-----|----------:|-------:|--------:|
| Spec Pro | ~2,744 (核心文件) | 52 passed | 8 |
| Solution Pro | ~4,750 (orchestrators) | 127 passed, 10 skipped | 39 |
| Ship Pro | ~877 (单入口) | 19 passed | 1 |
| Deliver Pro | ~2,500+ (5-Phase) | 190+ passed | — |
| Research Pro | ~1,402 (orchestrator) | — | — |
| Core | ~9,534 | — | — |
| **总计** | **~49,000+** | **466 passed, 10 skipped** | **48+** |

---

## Part 2: Domain Adaptation Layer (DAL)

> V2.1.0 新增，V2.1.1 完善。解决"硬编码领域知识"的反模式。

### 2.1 架构总览

```
用户目标 (objective + context)
    │
    ▼
┌─────────────────────┐
│  domain_analysis.py │  ← LLM 语义推断领域特征
│  DomainProfile (10) │  ← Pydantic Schema
└──────────┬──────────┘
           │ DomainProfile
           ▼
┌─────────────────────┐
│ master_orchestrator │  ← 注入 DomainProfile 到全链路
│  (925 行)           │
└──────────┬──────────┘
           │
     ┌─────┼─────────────┐
     ▼     ▼             ▼
 Planning  Research   Summary
 (976行)  (2114行)   (737行)
     │     │             │
     └─────┼─────────────┘
           ▼
    task_builder.py  ← DomainProfile 注入 Prompt 构建
```

### 2.2 DomainProfile Schema

`domains/solution_pro/domain_analysis.py` (236 行)

```python
class DomainProfile(BaseModel):
    domain_id: str              # 领域标识（software, investment, hardware, medical...）
    domain_label: str           # 领域中文名
    description: str            # 领域简述（一句话）
    suggested_categories: list[str]    # 任务分类建议
    expert_roles: list[dict]           # 专家角色列表（name + lens）
    quality_dimensions: list[str]      # 质量评估维度
    seed_urls: list[str]               # 参考搜索方向
    output_structure: list[str]        # 方案文档结构
    review_dimensions: list[str]       # 评审维度
    harness_checks: list[str]          # Harness 检查项
```

**10 个字段**，全部由 LLM 动态生成，无硬编码领域映射。

### 2.3 Spec Pro 的域适配

Spec Pro 采用独立的域适配策略：

- **`prompts/parse.md`** — LLM 域自推断：从用户输入中推断领域，不依赖预定义配置
- **`domain_context.py`** (76 行) — `build_domain_context(domain_type)` 生成领域上下文注入字符串
- **`merge_spec.py`** (680 行) — 语义级合并：`merge_confirmed`, `merge_inferred`, `merge_guardrails`, `merge_semantic_anchors`, `check_contradictions`

### 2.4 Solution Pro 全链路透传

DomainProfile 在 Solution Pro 中的透传路径：

1. `domain_analysis.py` → LLM 生成 `DomainProfile`
2. `master_orchestrator.py` → 接收并存储 Profile
3. `planning_orchestrator.py` → Profile 注入专家规划 Prompt
4. `research_orchestrator.py` → Profile 注入研究专家 Prompt
5. `summary_orchestrator.py` → Profile 注入综合/评估 Prompt
6. `task_builder.py` → `build_data_collection_task(..., domain_profile=...)` 构建最终 Prompt

---

## Part 3: 三层门控架构

> 替代旧版 Harness 2.0.0 的单一评估模式。

### 3.1 架构

```
┌─────────────────────────────────────────────────────────┐
│                    三层门控                               │
│                                                         │
│  Layer 1: Python 确定性检查                              │
│  ├── Pydantic Schema 验证                                │
│  ├── 字段存在性 / 类型 / 格式                             │
│  ├── 无环依赖检查                                        │
│  └── 密度检查 (gate_living_spec_density)                 │
│          │                                              │
│          ▼                                              │
│  Layer 2: LLM 语义判断                                   │
│  ├── Judge Agent 评估质量/完整性/一致性                    │
│  ├── 多维度评分 (quality_dimensions)                     │
│  └── 独立视角（非执行者自身）                              │
│          │                                              │
│          ▼                                              │
│  Layer 3: Python 合并决策                                │
│  ├── gate_harness_decision(layer1_result, layer2_scores)│
│  ├── 合并 L1 + L2 → PASS / CONDITIONAL / FAIL           │
│  └── 确定性代码，非 LLM                                  │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Spec Pro 实例：`gate_harness_decision`

`domains/spec_pro/contracts/gate.py` (300 行)

```python
def gate_harness_decision(layer1_result: dict, layer2_scores: dict) -> dict:
    """合并 Layer 1 密度检查 + Layer 2 LLM 评估 → 最终决策"""
```

调用链：`coordinator.py:503 run_harness_decision()` → `gate_harness_decision(density_result, layer2_scores)`

相关 Gate 函数：
| 函数 | 作用 |
|:-----|:-----|
| `gate_living_spec(data)` | Pydantic 验证 LivingSpec |
| `gate_round_result(data)` | Pydantic 验证 RoundResult |
| `gate_quality_report(data)` | Pydantic 验证 QualityReport |
| `gate_living_spec_density(spec)` | Layer 1 密度检查 |
| `gate_harness_decision(l1, l2)` | Layer 3 合并决策 |

### 3.3 Ship Pro 实例：`CompletenessGate`

`domains/ship_pro/contracts/gates.py` (493 行)

```python
class CompletenessGate:
    """检查 Solution Pro 输出 → Ship Package 的需求覆盖完整性"""
    @staticmethod
    def check(solution_pro_output, ship_package) -> GateResult:
        ...
    @staticmethod
    def build_judge_prompt(solution_pro_output, ship_package) -> str:
        """Layer 2: 构建 LLM Judge Prompt"""
```

Ship Pro 的 Gate 体系：
| Gate | 层级 | 作用 |
|:-----|:----:|:-----|
| `PlannerGate.check()` | L1 | 验证 Planner 输出 Schema |
| `WorkerGate.check()` | L1+L2 | 验证 Worker 产出 + LLM Judge |
| `InformationConservationGate.check()` | L1 | 需求追踪完整性 |
| `CompletenessGate.check()` | L1+L2 | 端到端需求覆盖 |

### 3.4 Solution Pro 实例：ConvergenceLayer

`domains/solution_pro/convergence_layer.py` (978 行)

```python
class ConvergenceLayer:
    """Gate A + Gate B 评估"""
    def run_convergence(self) -> dict: ...
    def _validate_contract(self, compressed: dict): ...
    def _check_information_conservation(self, compressed: dict) -> dict: ...
```

- **Gate A**：模块级收敛评估（Planning/Research/Summary 各自是否收敛）
- **Gate B**：跨模块一致性评估（约束传播、需求覆盖、研究利用）
- 使用 `PlanningConvergenceSchema` / `ResearchConvergenceSchema` 做确定性验证

---

## Part 4: 各域架构（当前实际）

### 4.1 Spec Pro V2.2.0

> 需求梳理引擎 — 苏格拉底式对话，输出 Living Spec

**入口**: `SpecProCoordinator` (`coordinator.py`, 1010 行, 22 个方法)

#### 组件架构

```
SpecProCoordinator (1010 行)
    │
    ├── merge_spec.py (680 行)
    │   ├── merge_confirmed()      — 确认需求合并
    │   ├── merge_inferred()       — 推断需求合并
    │   ├── merge_guardrails()     — 护栏合并
    │   ├── merge_semantic_anchors() — 语义锚点合并
    │   └── check_contradictions() — 矛盾检测
    │
    ├── response_normalizer.py (391 行)
    │   ├── normalize_response()   — 响应标准化
    │   └── validate_response()    — 响应验证
    │
    ├── domain_context.py (76 行)
    │   └── build_domain_context() — 领域上下文构建
    │
    └── contracts/ (878 行, 8 文件)
        ├── living_spec.py    — LivingSpec (14 个 Pydantic 模型)
        ├── round_result.py   — RoundResult
        ├── quality_report.py — QualityReport
        ├── quality_trajectory.py — QualityTrajectory
        ├── gate.py           — 三层门控 (300 行)
        ├── conversation_log.py — ConversationLog
        └── transition_prompt.py — TransitionPrompt
```

#### Prompts (8 个)

| Prompt | 用途 |
|:-------|:-----|
| `parse.md` | 解析用户输入，推断领域 |
| `guide.md` | 生成苏格拉底式引导问题 |
| `assess.md` | 评估回答质量 |
| `structure.md` | 结构化需求 |
| `harness.md` | Layer 2 LLM 评估 |
| `orchestrator.md` | 编排决策 |
| `parse_response.md` | 解析响应标准化 |
| `assess_guide.md` | 评估引导问题质量 |

#### 测试: 52 passed

---

### 4.2 Solution Pro V2.1.1

> 领域自适应方案设计引擎 — 域自适应 + 三模块架构

**入口**: `run_solution_pro()` via `master_orchestrator.py` (925 行, 29 个方法)

#### 三模块架构

```
master_orchestrator.py (925 行)
    │
    ├── domain_analysis.py (236 行)
    │   ├── DomainProfile (10 字段 Pydantic)
    │   ├── build_domain_analysis_task()
    │   ├── parse_domain_profile()
    │   └── domain_profile_to_prompt_context()
    │
    ├── planning_orchestrator.py (976 行)
    │   ├── Meta-Planner → 并行专家 → Consolidator
    │   └── 约束提取 + 需求分解
    │
    ├── research_orchestrator.py (2114 行)
    │   ├── 多专家并行研究
    │   ├── FindingLedger (研究利用追踪)
    │   └── Digest → 收敛
    │
    ├── summary_orchestrator.py (737 行)
    │   ├── Base Synthesis → Refiner → Harness Check
    │   └── 5+1 Phase 收敛
    │
    ├── convergence_layer.py (978 行)
    │   ├── Gate A: 模块级收敛
    │   ├── Gate B: 跨模块一致性
    │   └── 语义压缩 + 契约验证
    │
    ├── information_conservation.py (327 行)
    │   ├── 需求覆盖追踪
    │   ├── 约束传播验证
    │   └── 来源可追溯性
    │
    └── task_builder.py
        ├── build_data_collection_task()
        ├── build_planner_task()
        ├── build_researcher_task()
        ├── build_designer_task()
        └── build_auditor_task()
```

#### 辅助组件

| 文件 | 行数 | 作用 |
|:-----|-----:|:-----|
| `ai_native_auditor.py` | 40 | AI Native 合规审计 |
| `compliance_checker.py` | 37 | 输出合规检查 |
| `harness_scorer.py` | — | Harness 评分 |
| `spec_context.py` | — | Spec 上下文注入 |
| `normalize.py` | — | 输出标准化 |
| `state_manager.py` | — | 状态管理 |
| `blackboard.py` | — | Blackboard 路径注册 |

#### 契约层

`contracts/` (301 行):
- `pipeline_state.py` (172 行) — `StageProgress`, `ConvergenceState`, `ModuleState`, `SolutionProPipelineState`
- `stage_contract.py` (110 行) — `StageContract`

#### Prompts (39 个)

核心 Prompt 分类：
- **Planning**: `meta_planner.md`, `expert_planner_base.md`, `planning_expert_base.md`, `planner_harness.md`, `planning_module.md`, `planning_planner.md`, `convergence_planner.md`
- **Research**: `research_expert_base.md`, `research_module.md`, `research_planner.md`, `researcher_harness.md`
- **Summary**: `summary_base_synthesizer.md`, `summary_analyzer_base.md`, `summary_meta_planner.md`, `summary_module.md`, `summary_summarizer.md`, `summarizer_harness.md`, `summary_refiner.md`, `summary_harness_check.md`, `summary_fix_agent.md`, `summary_fix_judge.md`, `summary_json_extractor.md`
- **Review**: `reviewer_harness.md`, `reviewer_meta.md`, `reviewer_convergence.md`, `review_layer_b.md`, `summary_review_layer_b.md`
- **Shared**: `orchestrator.md`, `harness_agent.md`, `auditor_harness.md`, `compliance_checker_base.md`, `ai_native_cognitive_base.md`, `fixer_harness.md`, `fixer_expert_harness.md`, `consolidator_harness.md`
- **Design**: `P0_CONSTRAINT_INJECTION_DESIGN.md`, `REQ_DEDUP_DESIGN.md`

#### 测试: 127 passed, 10 skipped

---

### 4.3 Ship Pro V2.0.0

> 交付包生成引擎 — PipelineDesigner + Orchestrator + Workers

**入口**: `run_ship_pro(project_name)` (`__init__.py`, 877 行)

#### 架构

```
run_ship_pro()
    │
    ├── design_pipeline()         — LLM 生成 PipelineDesign
    │
    ├── PipelineDesigner          — 管线设计（任务拆分 + 依赖图）
    │
    ├── ShipOrchestrator          — 编排 Worker 执行
    │   ├── _build_worker_prompts()  — 构建 Worker Prompt
    │   └── Workers (并行)          — 执行具体任务
    │
    └── Consolidator              — 合并产出 → ShipPackage
        └── _build_runner_prompt()   — 构建 Runner Prompt
```

#### 契约笼子

`contracts/` (809 行):

| 文件 | 行数 | 核心类 |
|:-----|-----:|:------|
| `gates.py` | 493 | `GateResult`, `PlannerGate`, `WorkerGate`, `InformationConservationGate`, `CompletenessGate` |
| `ship_package.py` | 73 | `ShipPackage(BaseModel)`, `DependencyGraph(BaseModel)` |
| `worker_deliverable.py` | 109 | Worker 产出 Schema |
| `planner_output.py` | 34 | Planner 输出 Schema |
| `repair_adapters.py` | 61 | 修复适配器 |

`contracts/schemas/`: JSON Schema 文件 (`ship_package.json`, `planner_output.json`, `worker_deliverable.json`)

#### 测试: 19 passed

---

### 4.4 Research Pro V2.0.0

> 深度研究引擎 — DDGS 搜索 + 来源分级 + 引用验证

**入口**: `run_research_pro()` via `orchestrator.py` (1,402 行)

#### 组件

| 文件 | 作用 |
|:-----|:-----|
| `orchestrator.py` (1402 行) | 主编排器 |
| `ddgs_client.py` | DuckDuckGo 搜索客户端 |
| `keyword_generator.py` | 关键词生成 |
| `tier_classifier.py` | 来源分级 |
| `safe_fetcher.py` | 安全网页抓取 |
| `citation_verifier.py` | 引用验证 |
| `source_registry.py` | 来源注册表 |
| `blackboard.py` | Blackboard 集成 |
| `url_utils.py` | URL 工具 |

#### 测试: 集成在 Solution Pro 测试中

---

### 4.5 Deliver Pro V1.0.0 — 执行交付域

**职责**: Work Package → 可交付产物（代码/报告/分析）

**5 Phase 流水线**:
1. **Analyze** — 解析 WP，生成执行计划（拓扑排序）
2. **Generate** — 并行 Worker Agent 执行（滑动窗口，max 5 并发）
3. **Integrate** — **Code-First Assembly (SmartAssembler)**，确定性拼接，零 LLM
4. **Validate** — LLM Judge 评分（6 维，≥3.5/5.0 通过）+ 单循环（max 5 轮）
5. **Package** — 最终交付物 + delivery_manifest.json

**核心设计**:
- **SmartAssembler**: Python 确定性拼接，保留率 ≥100%（解决 LLM 合并 84% 信息丢失问题）
- **统一输出 4 文件**: DELIVERABLE.md + EVIDENCE.md + ISSUES.md + MANIFEST.json
- **故障恢复**: LLM 端到端诊断（废除 F1-F8 查表法），上限 3 轮
- **E2E 验证**: 报告场景 4.15/5.0，编程场景 4.4/5.0 + 30/30 pytest passed

**模块**: `smart_assembler.py`, `orchestrator.py`, `blackboard.py`, `state_manager.py`, `failure_recovery.py`
**测试**: 190+ passed
**ADR**: ADR-010

---

## Part 5: 横切关注点

### 5.1 契约笼子模式 (Contract Cage)

DeepFlow 的核心约束机制，贯穿所有域：

```
┌─────────────────────────────────────┐
│           契约笼子                   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ Layer 1: Pydantic Schema    │   │
│  │ • 字段存在性                 │   │
│  │ • 类型验证                   │   │
│  │ • 格式校验                   │   │
│  │ • 无环依赖                   │   │
│  └──────────────┬──────────────┘   │
│                 │ PASS              │
│                 ▼                    │
│  ┌─────────────────────────────┐   │
│  │ Layer 2: LLM Judge          │   │
│  │ • 语义质量评估               │   │
│  │ • 完整性检查                 │   │
│  │ • 一致性验证                 │   │
│  │ • 独立视角（非执行者）        │   │
│  └──────────────┬──────────────┘   │
│                 │ scores            │
│                 ▼                    │
│  ┌─────────────────────────────┐   │
│  │ Layer 3: 合并决策            │   │
│  │ • 确定性代码（非 LLM）       │   │
│  │ • L1 + L2 → PASS/COND/FAIL  │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

**实例分布**:
- Spec Pro: `gate.py` — `gate_harness_decision`, `gate_living_spec_density`
- Solution Pro: `convergence_layer.py` — Gate A/B + `information_conservation.py`
- Ship Pro: `gates.py` — `PlannerGate`, `WorkerGate`, `CompletenessGate`
- Core: `core/quality/quality_gate.py`, `core/cage/cage_validator.py`

### 5.2 Blackboard 统一存储（MD-First）

```
.deepflow/blackboard/{project}/
    ├── spec_pro/               ← Living Spec 输出
    │   ├── living_spec.md          ← MD source of truth
    │   ├── spec_track.json         ← derivative (Gate 质量检查用)
    │   ├── quality_report.json
    │   └── conversation_log.json
    ├── solution_pro/           ← Solution 输出
    │   ├── frozen_spec.md          ← MD source of truth
    │   ├── frozen_spec.json        ← simplified derivative
    │   ├── stages/
    │   │   ├── planning/
    │   │   ├── research/
    │   │   └── summary/
    │   └── convergence/
    ├── ship_pro/               ← Ship 输出
    │   ├── ship_package.md         ← MD source of truth
    │   ├── ship_package.json       ← derivative
    │   ├── pipeline_design.json
    │   └── worker_outputs/
    └── deliver_pro/            ← Deliver 输出
        ├── DELIVERABLE.md
        ├── EVIDENCE.md
        ├── ISSUES.md
        └── MANIFEST.json
```

> **MD-First 存储原则**: 每个域的主输出为 `.md` 文件（source of truth），`.json` 文件为 derivative（仅用于 Gate 质量检查等确定性消费场景）。

**Core 支持**:
- `core/blackboard/blackboard_manager.py` — 统一读写 API
- `core/blackboard/blackboard_bridge.py` — 跨域桥接
- `core/blackboard/registry_base.py` — 路径注册基类 (`DomainRegistry`)
- `core/blackboard/context_injector.py` — 上下文注入
- `core/blackboard/session_id.py` — Session ID 管理

### 5.3 Core Infrastructure

`core/` (9,534 行):

| 模块 | 作用 |
|:-----|:-----|
| `core/cage/` | 契约笼子 — `cage_validator.py`, `cage_loader.py`, `cage_checkpoint.py` |
| `core/blackboard/` | Blackboard 管理 — 路径注册、读写、上下文注入 |
| `core/quality/` | 质量门控 — `quality_gate.py`, `entry_harness.py`, `observability.py` |
| `core/orchestrator/` | 编排基类 |
| `core/agents/` | Agent 基类 |
| `core/trace.py` | 全链路追踪 (102 行) |
| `core/unified_entry.py` | 统一入口 (187 行) |
| `core/prompt_registry.py` | Prompt 注册表 |
| `core/quality_judge.py` | LLM Judge 封装 |
| `core/checkpoint_manager.py` | 检查点管理 |
| `core/config_loader.py` | 配置加载 |
| `core/bootstrap.py` | 启动引导 |

### 5.4 AI Native 反模式修复 (V2.1.1)

V2.1.1 新增的反模式修复（基于 AGENTS.md Zone 4 审计）：

| 修复类型 | 数量 | 示例 |
|:---------|:----:|:-----|
| P0 — 架构级 | 3 | 硬编码域映射 → LLM 自推断；单一 Gate → 三层门控；串行执行 → 并行 spawn |
| P1 — 实现级 | 6 | 正则分类 → LLM 判断；无 Layer 2 → 补 LLM Judge；信息丢失 → 信息守恒追踪 |
| **总计** | **9** | |

修复覆盖：
- `domain_analysis.py` — 域自推断替代硬编码
- `convergence_layer.py` — 三层门控替代单一评估
- `information_conservation.py` — 信息守恒追踪
- `task_builder.py` — DomainProfile 全链路注入

---

## Part 6: 与 V2.0.0 的差异

> V2.0.0 (2026-06-23) → V2.1.1 (2026-07-08) 的架构演进

### 6.1 新增 Domain Adaptation Layer (DAL)

| 维度 | V2.0.0 | V2.1.1 |
|:-----|:-------|:-------|
| 领域知识 | 硬编码 YAML 配置 | LLM 动态推断 (`domain_analysis.py`) |
| 新领域接入 | 需编写新配置文件 | 零配置，LLM 自推断 |
| 域信息传递 | 隐式/无 | `DomainProfile` 全链路透传 |

### 6.2 三层门控替代旧 Harness

| 维度 | V2.0.0 Harness | V2.1.1 三层门控 |
|:-----|:--------------|:---------------|
| 验证 | 单一 LLM 评估 | L1 确定性 + L2 LLM + L3 合并 |
| 决策 | 模糊分数 | PASS / CONDITIONAL / FAIL |
| 可追溯性 | 无 | 每层独立记录 |

### 6.3 Solution Pro 架构重构

| 维度 | V2.0.0 | V2.1.1 |
|:-----|:-------|:-------|
| 结构 | 10 阶段固定管线 | 3 模块 (Planning + Research + Summary) |
| 收敛 | 阶段间串行传递 | `ConvergenceLayer` Gate A/B 评估 |
| 信息追踪 | 无 | `information_conservation.py` |
| 域适配 | 无 | `DomainProfile` 全链路注入 |

### 6.4 Spec Pro 演进

| 维度 | V2.0.0 | V2.2.0 |
|:-----|:-------|:-------|
| 合并逻辑 | 简单 JSON merge | `merge_spec.py` (680 行) 语义级合并 |
| 响应处理 | 直接解析 | `response_normalizer.py` (391 行) 标准化 |
| 门控 | 基础验证 | `gate.py` (300 行) 三层门控 |
| 域适配 | 无 | `domain_context.py` + `parse.md` LLM 域自推断 |

### 6.5 Ship Pro 定型

| 维度 | V1.x | V2.0.0 |
|:-----|:-----|:-------|
| 架构 | 多入口分散 | 单入口 `run_ship_pro()` |
| 契约 | 松散 dict | Pydantic `ShipPackage` + `gates.py` (493 行) |
| 门控 | 无 | 4 个 Gate 类 (`PlannerGate`, `WorkerGate`, `InformationConservationGate`, `CompletenessGate`) |

### 6.6 测试覆盖演进

| 域 | V2.0.0 | V2.1.1 | 变化 |
|:---|-------:|-------:|:-----|
| Spec Pro | ~30 | 52 | +22 |
| Solution Pro | ~80 | 127 (+10 skipped) | +47 |
| Ship Pro | 0 | 19 | +19 (新增) |
| **总计** | ~110 | **466** | **+356** |

---

## 附录 A: 文件索引

### 域入口文件

| 域 | 入口文件 | 入口函数/类 |
|:---|:---------|:-----------|
| Spec Pro | `domains/spec_pro/coordinator.py` | `SpecProCoordinator` |
| Solution Pro | `domains/solution_pro/master_orchestrator.py` | `run_solution_pro()` |
| Ship Pro | `domains/ship_pro/__init__.py` | `run_ship_pro()` |
| Deliver Pro | `domains/deliver_pro/orchestrator.py` | `run_deliver_pro()` |
| Research Pro | `domains/research_pro/orchestrator.py` | `run_research_pro()` |

### 契约文件

| 域 | 路径 | 核心 Schema |
|:---|:-----|:-----------|
| Spec Pro | `domains/spec_pro/contracts/` | `LivingSpec`, `RoundResult`, `QualityReport`, `GateResult` |
| Solution Pro | `domains/solution_pro/contracts/` | `SolutionProPipelineState`, `StageContract` |
| Ship Pro | `domains/ship_pro/contracts/` | `ShipPackage`, `GateResult`, `DependencyGraph` |
| Deliver Pro | `domains/deliver_pro/contracts/` | `WorkPackage`, `DeliveryManifest`, `ValidationResult` |

### Prompt 文件

| 域 | 路径 | 数量 |
|:---|:-----|:----:|
| Spec Pro | `domains/spec_pro/prompts/` | 8 |
| Solution Pro | `domains/solution_pro/prompts/` | 39 |
| Ship Pro | `domains/ship_pro/prompts/` | 1 |
| Deliver Pro | `domains/deliver_pro/prompts/` | — |

---

## 附录 B: 关键设计决策

| # | 决策 | 理由 |
|:--|:-----|:-----|
| D1 | LLM 域自推断而非硬编码配置 | 零配置接入新领域，避免维护成本 |
| D2 | 三层门控而非单一 LLM 评估 | 确定性快筛 + 语义深检，兼顾速度和准确性 |
| D3 | 文件 Blackboard 而非数据库 | 与 OpenClaw 文件系统一致，可审计可回溯 |
| D4 | Pydantic 契约而非 JSON Schema 文件 | Python 原生类型安全，IDE 支持好 |
| D5 | 信息守恒追踪 | 防止跨模块传递时需求/约束丢失 |
| D6 | 单入口模式 (`run_xxx_pro()`) | 简化 Main Agent 调用，隐藏内部复杂度 |
| D7 | MD-First 架构（ADR-009） | Markdown 是 source of truth，JSON 降级为 derivative |
| D8 | Code-First Assembly（ADR-010） | 确定性拼接替代 LLM 合并，解决 84% 信息丢失 |

---

---

## Part 7: 架构决策记录 (ADR)

### ADR-009: MD-First 架构迁移（2026-07-12）

**核心变更**: Markdown 成为 source of truth，JSON 降级为 ~1KB track 元数据（仅用于 Gate 质量检查）

**影响范围**:
- **Spec Pro**: `living_spec.md` 原生输出，`spec_track.json` derivative
- **Solution Pro**: `frozen_spec.py` 废弃，`living_spec.requirement_index` 直读
- **Ship Pro**: `ship_package.md` sidecar + MD-first 读取
- **Deliver Pro**: 消费 MD-first 上游输入
- **Core**: `md_track_extractor.py`, `md_merge_validator.py`, `*_living_md.py` 系列

**语义化 REQ-ID**: `REQ-OBJ-001` 格式（category 前缀 + 分类内序号），由 `spec_pro/coordinator.py` 原生生成

**迁移状态**: ✅ 已完成

### ADR-010: Code-First Assembly (SmartAssembler)

**核心变更**: Deliver Pro 的 Integrate 阶段采用 Python 确定性拼接，零 LLM 参与

**动机**: LLM 合并导致 84% 信息丢失，确定性拼接保留率 ≥100%

**实现**: `smart_assembler.py` — 解析 Worker 产出结构，按依赖拓扑排序，确定性拼接

---

> **文档维护**: 本文档随代码演进而更新。修改架构后必须同步更新对应章节。  
> **验证方式**: 所有数据通过 `grep`/`wc`/`pytest` 实际验证，非估算值。
