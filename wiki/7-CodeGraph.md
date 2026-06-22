# DeepFlow Code Graph

> 核心函数的调用关系图  
> 最后更新：2026-06-22

---

## 调用关系总览

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Spec Pro                                                        │
│                                                                  │
│  SpecProCoordinator                                              │
│    ├── init_session()                                            │
│    │     └── build_round_task()                                  │
│    │           └── load_prompt("parse_response.md")             │
│    │                                                              │
│    ├── build_next_round_task()                                   │
│    │     └── build_round_task()                                  │
│    │           └── load_prompt("structure.md")                   │
│    │                                                              │
│    └── build_confirmation_task()                                 │
│          └── load_prompt("assess.md")                            │
│                                                                  │
│  merge_spec.py                                                   │
│    ├── merge_spec()                                              │
│    │     ├── merge_confirmed()                                   │
│    │     ├── merge_conversation_digest() ←──────────────┐       │
│    │     │     └── 去重 + 上限 20 条                      │       │
│    │     └── update meta.version                         │       │
│    │                                                      │       │
│    └── apply_revisions()                                  │       │
│          └── 更新 confirmed 层                            │       │
│                                                           │       │
│  eval/harness.py                                          │       │
│    ├── run_harness_v2() ─────────────────────────────────┤       │
│    │     └── run_harness()                               │       │
│    │           └── evaluate_living_spec()                │       │
│    │                 ├── SemanticGate                    │       │
│    │                 │     ├── check_clarity()           │       │
│    │                 │     ├── check_completeness()      │       │
│    │                 │     ├── check_executability()     │       │
│    │                 │     ├── check_consistency()       │       │
│    │                 │     └── check_fitness()           │       │
│    │                 ├── InferenceAuditGate              │       │
│    │                 │     └── check()                   │       │
│    │                 └── TrajectoryAuditGate             │       │
│    │                       └── check()                   │       │
│    └── HarnessReport                                     │       │
│          └── to_dict()                                   │       │
│                                                           │       │
└───────────────────────────────────────────────────────────┼───────┘
                                                            │
                                                            ▼
┌───────────────────────────────────────────────────────────┼───────┐
│  Solution Pro                                              │       │
│                                                            │       │
│  spec_context.py ◄─────────────────────────────────────────┘       │
│    ├── build_living_spec_context()                                 │
│    │     └── 提取 user_directives + inferred + hints               │
│    │                                                                │
│    ├── build_conversation_digest_for_prompt()                      │
│    │     └── 生成 "## 需求概述" + "## 用户关键表达"                  │
│    │                                                                │
│    └── build_worker_context_section()                              │
│          └── 组合 user_directives + hints + guardrails + digest    │
│                                                                        │
│  orchestrator_agent.py                                                │
│    └── get_all_tasks()                                                │
│          ├── Stage 1: load_prompt("planner_v2_harness.md")           │
│          ├── Stage 2: load_prompt("reviewer_v2_harness.md")          │
│          ├── Stage 3: load_prompt("fixer_v2_harness.md")             │
│          ├── Stage 4: load_prompt("researcher_v2_harness.md")        │
│          ├── Stage 5: load_prompt("consolidator_v2_harness.md")      │
│          ├── Stage 6: load_prompt("auditor_v2_harness.md")           │
│          ├── Stage 7: load_prompt("fixer_expert_v2_harness.md")      │
│          ├── Stage 8: load_prompt("harness_v3.md")                   │
│          ├── Stage 9: load_prompt("fixer_v2_harness.md") [条件]      │
│          └── Stage 10: load_prompt("summarizer_v2_harness.md")       │
│                                                                        │
│  task_builder.py                                                       │
│    └── build_task()                                                    │
│          ├── 注入 LivingSpec 上下文                                    │
│          ├── 注入 conversation_digest                                  │
│          └── 注入 guardrails                                           │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Ship Pro                                                               │
│                                                                         │
│  scripts/orchestrator.py                                                │
│    └── run_pipeline()                                                   │
│          ├── Stage 1: load_prompt("architect.md")                      │
│          │     └── gates.gate_architect() ← 质量门控                    │
│          │                                                              │
│          ├── Stage 2: load_prompt("specifier.md")                      │
│          │     └── gates.gate_specifier() ← 质量门控                    │
│          │                                                              │
│          ├── Stage 3: load_prompt("decomposer.md")                     │
│          │     └── gates.gate_decomposer() ← 质量门控                   │
│          │                                                              │
│          ├── Stage 4: load_prompt("packager.md")                       │
│          │     └── gates.gate_packager() ← 质量门控                     │
│          │                                                              │
│          └── Stage 5: load_prompt("reviewer.md")                       │
│                └── gates.gate_reviewer() ← 质量门控                     │
│                                                                         │
│  eval/gates.py                                                          │
│    ├── gate_architect() → GateResult                                    │
│    ├── gate_specifier() → GateResult                                    │
│    ├── gate_decomposer() → GateResult                                   │
│    ├── gate_packager() → GateResult                                     │
│    └── gate_reviewer() → GateResult                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 核心函数签名

### Spec Pro

```python
# domains/spec_pro/coordinator.py
class SpecProCoordinator:
    def __init__(self, scenario: str, mode: str)
    def init_session(self, user_input: str) -> dict
    def build_next_round_task(self, user_response: str) -> dict
    def build_confirmation_task(self, confirmation: dict) -> str
    def get_status(self) -> dict
    def is_done(self) -> bool

# domains/spec_pro/merge_spec.py
def merge_spec(response_path: str, living_spec_path: str) -> dict
def merge_conversation_digest(spec: dict, response: dict) -> None
def apply_revisions(confirmation_path: str, living_spec_path: str) -> dict

# domains/spec_pro/eval/harness.py
def run_harness_v2(spec_path: str) -> dict
def run_harness(living_spec: dict, quality_report: dict = None) -> HarnessReport
def evaluate_living_spec(living_spec: dict, quality_report: dict) -> HarnessReport

class SemanticGate:
    def check_clarity(self, living_spec: dict) -> DimensionScore
    def check_completeness(self, quality_report: dict) -> DimensionScore
    def check_executability(self, living_spec: dict) -> DimensionScore
    def check_consistency(self, living_spec: dict) -> DimensionScore
    def check_fitness(self, living_spec: dict) -> DimensionScore

class InferenceAuditGate:
    def check(self, living_spec: dict) -> GateResult

class TrajectoryAuditGate:
    def check(self, conversation_log: dict, quality_trajectory: dict) -> GateResult
```

### Solution Pro

```python
# domains/solution/spec_context.py
def build_living_spec_context(living_spec: dict) -> dict
def build_conversation_digest_for_prompt(digest: dict) -> str
def build_worker_context_section(living_spec: dict, role: str) -> str

# domains/solution/orchestrator_agent.py
class OrchestratorAgent:
    def get_all_tasks(self, blackboard_path: str) -> list[dict]

# domains/solution/task_builder.py
def build_task(blackboard_path: str, stage: int, role: str) -> dict
```

### Ship Pro

```python
# domains/ship_pro/scripts/orchestrator.py
def run_pipeline(blackboard_path: str) -> dict

# domains/ship_pro/eval/gates.py
def gate_architect(blueprint: dict) -> GateResult
def gate_specifier(wp_specs: dict) -> GateResult
def gate_decomposer(decomposed: dict) -> GateResult
def gate_packager(package: dict) -> GateResult
def gate_reviewer(review: dict) -> GateResult
```

---

## 数据流向

```
┌──────────────┐
│ 用户输入      │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  blackboard/spec_spec_XXX/                                    │
│    ├── input.md                                               │
│    ├── user_response_round_N.md                               │
│    ├── spec/                                                  │
│    │     ├── living_spec.json ◄── merge_spec()                │
│    │     └── harness_report.json ◄── run_harness_v2()         │
│    └── stages/                                                │
│          └── round_N_*.json                                   │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  blackboard/solution_XXX/                                     │
│    ├── input.json (LivingSpec)                                │
│    ├── stage_1_planner.json ◄── build_conversation_digest_   │
│    │                                    for_prompt()           │
│    ├── stage_2_reviewer.json                                  │
│    ├── ...                                                    │
│    └── final_result.json                                      │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  blackboard/ship_XXX/                                         │
│    ├── input.json (技术方案)                                   │
│    ├── architect_output.json ◄── gate_architect()             │
│    ├── specifier_output.json ◄── gate_specifier()             │
│    ├── decomposer_output.json ◄── gate_decomposer()           │
│    ├── packager_output.json ◄── gate_packager()               │
│    └── ship_package.json ◄── gate_reviewer()                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 依赖关系

### 核心依赖

```
Spec Pro
  ├── core/config/path_config.py (路径管理)
  ├── core/prompt_registry.py (Prompt 加载)
  └── domains/spec_pro/prompts/*.md (10 个 Prompt)

Solution Pro
  ├── core/config/path_config.py (路径管理)
  ├── core/prompt_registry.py (Prompt 加载)
  ├── domains/solution/spec_context.py (上下文注入) ◄── Spec Pro
  └── domains/solution/prompts/*.md (25 个 Prompt)

Ship Pro
  ├── core/config/path_config.py (路径管理)
  ├── core/prompt_registry.py (Prompt 加载)
  ├── domains/ship_pro/eval/gates.py (质量门控)
  └── domains/ship_pro/prompts/*.md (9 个 Prompt)
```

### 跨域依赖

```
Solution Pro ◄── Spec Pro
  spec_context.py 使用 LivingSpec + conversation_digest

Ship Pro ◄── Solution Pro
  orchestrator.py 读取 final_result.json
```

---

## 测试覆盖

```
tests/
├── test_path_config.py ──────────────────────► core/config/path_config.py
├── test_prompt_registry.py ──────────────────► core/prompt_registry.py
├── test_e2e_living_spec_v2.py ───────────────► domains/spec_pro/merge_spec.py
│                                               domains/spec_pro/eval/harness.py
│                                               domains/solution/spec_context.py
├── test_spec_pro_full.py ────────────────────► domains/spec_pro/ (全部)
├── contract/test_quality_gate.py ────────────► core/quality/quality_gate.py
├── e2e_solution_test.py ─────────────────────► domains/solution/ (全部)
└── domains/ship_pro/eval/
    ├── test_eval_checks.py ─────────────────► domains/ship_pro/eval/eval_code_checks.py
    └── test_gates.py ────────────────────────► domains/ship_pro/eval/gates.py
```

---

## 版本演进

```
v1.0 (2026-06-11)
  ├── Spec Pro 基础版
  ├── Solution Pro 5 阶段
  └── Ship Pro 3 Agent

v2.0 (2026-06-18)
  ├── Spec Pro: 新增 conversation_digest
  ├── Solution Pro: 扩展到 10 阶段
  ├── Ship Pro: 扩展到 5 Agent + 质量门控
  └── Harness V2: 新增 Layer 2 (SC1-SC2)

v2.1 (2026-06-22) ← 当前版本
  ├── merge_conversation_digest 累积逻辑
  ├── run_harness_v2 兼容 V1/V2
  ├── build_conversation_digest_for_prompt 格式化
  └── build_worker_context_section 完整上下文
```
