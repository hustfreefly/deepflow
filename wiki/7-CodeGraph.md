# DeepFlow Code Graph

> 核心函数的调用关系图  
> 最后更新: 2026-07-08

---

## 调用关系总览

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Spec Pro V2.2.0                                                │
│                                                                  │
│  SpecProCoordinator (coordinator.py, 22 functions)               │
│    ├── init_session()                                            │
│    │     └── build_round_task()                                  │
│    │           ├── load_prompt("parse.md")                       │
│    │           └── build_domain_context()                        │
│    │                                                              │
│    ├── build_next_round_task()                                   │
│    │     └── build_round_task()                                  │
│    │           ├── load_prompt("structure.md")                   │
│    │           └── load_prompt("guide.md")                       │
│    │                                                              │
│    └── build_confirmation_task()                                 │
│          └── load_prompt("assess.md")                            │
│                                                                  │
│  merge_spec.py                                                   │
│    ├── merge_spec()                                              │
│    │     ├── merge_confirmed()                                   │
│    │     ├── merge_conversation_digest()                         │
│    │     └── update meta.version                                 │
│    │                                                              │
│    └── apply_revisions()                                         │
│          └── 更新 confirmed 层                                   │
│                                                                  │
│  contracts/gate.py                                               │
│    ├── gate_living_spec_density() ─── Pydantic 验证              │
│    ├── gate_quality_report() ─────── 质量报告验证                │
│    └── gate_harness_decision() ───── L3 合并决策                 │
│                                                                  │
│  handoff.py                                                      │
│    ├── build_handoff_package()                                   │
│    └── save_handoff_package()                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Solution Pro V2.1.1                                             │
│                                                                  │
│  MasterOrchestrator (master_orchestrator.py, 29 functions)       │
│    ├── run() → 顺序调度三模块                                    │
│    │                                                              │
│    ├── PlanningOrchestrator (planning_orchestrator.py)           │
│    │     ├── MetaPlanner → meta_planner.md                      │
│    │     ├── Expert Agents (并行) → planning_expert_base.md     │
│    │     └── Convergence → convergence_planner.md               │
│    │                                                              │
│    ├── ResearchOrchestrator (research_orchestrator.py)           │
│    │     ├── ResearchPlanner → research_planner.md              │
│    │     └── Researcher Agents (并行) → research_expert_base.md │
│    │                                                              │
│    └── SummaryOrchestrator (summary_orchestrator.py)             │
│          └── 5+1 Phase:                                          │
│              ├── Analyzer (并行) → summary_analyzer_base.md     │
│              ├── BaseSynthesizer → summary_base_synthesizer.md  │
│              ├── Refiner → summary_refiner.md                   │
│              ├── MetaPlanner → summary_meta_planner.md          │
│              ├── JSONExtractor → summary_json_extractor.md      │
│              └── FixAgent (条件) → summary_fix_agent.md         │
│                                                                  │
│  domain_analysis.py                                              │
│    └── DomainProfile → LLM 推断 + 4 YAML few-shot               │
│                                                                  │
│  harness_scoring.py                                              │
│    └── Harness 评分 + 三层门控                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Ship Pro V2.0.0                                                 │
│                                                                  │
│  PipelineDesigner (pipeline_designer.py)                         │
│    ├── 分析 final_result.json                                    │
│    ├── 设计 Worker 拆分方案                                      │
│    ├── 裁剪 context.json (≤3KB)                                  │
│    └── 输出: PipelinePlan (Pydantic)                             │
│                                                                  │
│  Orchestrator (调度层)                                           │
│    └── Worker Agents (并行)                                      │
│                                                                  │
│  Consolidator (consolidator.md)                                  │
│    └── 合并 Worker 输出 → ship_package.json                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘


独立域:
┌─────────────────────────────────────────────────────────────────┐
│  Research Pro V2.0.0                                             │
│                                                                  │
│  Orchestrator (orchestrator.py)                                  │
│    ├── KeywordGenerator → keyword_generator.py                   │
│    ├── DDGS Client → ddgs_client.py                              │
│    ├── SafeFetcher → safe_fetcher.py                             │
│    ├── TierClassifier → tier_classifier.py                       │
│    └── CitationVerifier → citation_verifier.py                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core 基础设施调用关系

```
┌─────────────────────────────────────────────────────────────────┐
│  Core                                                            │
│                                                                  │
│  PathConfig (core/config/path_config.py)                         │
│    └── resolve() → 自动发现 .deepflow 根目录                     │
│                                                                  │
│  BlackboardManager (core/blackboard/blackboard_manager.py)       │
│    ├── read_json() / write_json()                                │
│    ├── read_text() / write_text()                                │
│    └── session_dir 管理                                          │
│                                                                  │
│  PromptRegistry (core/prompt_registry.py)                        │
│    └── load_prompt(name, domain) → 模板渲染                      │
│                                                                  │
│  Cage (core/cage/)                                               │
│    ├── cage_loader.py → 加载 YAML 契约                           │
│    ├── cage_validator.py → Pydantic 验证                         │
│    └── cage_checkpoint.py → 检查点管理                           │
│                                                                  │
│  Trace (core/trace.py)                                           │
│    ├── start_trace() → 创建跨域 trace_id                        │
│    ├── span() → 记录操作 span                                   │
│    └── save_to_blackboard() → 持久化追踪数据                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 关键 Pydantic 模型

| 模型 | 位置 | 用途 |
|:---|:---|:---|
| `LivingSpec` | `domains/spec_pro/contracts/living_spec.py` | Spec Pro 核心输出 |
| `RoundResult` | `domains/spec_pro/contracts/round_result.py` | 单轮对话结果 |
| `WorkerSpec` | `domains/ship_pro/pipeline_designer.py` | Ship Pro Worker 规格 |
| `PipelinePlan` | `domains/ship_pro/pipeline_designer.py` | Ship Pro 管线计划 |
| `DomainProfile` | `domains/solution_pro/domain_analysis.py` | DAL 域画像 |
| `PipelineState` | `domains/solution_pro/state_manager.py` | Solution Pro 状态 |
