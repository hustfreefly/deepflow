# 分布式系统架构师评审报告

> **评审人**: Expert 1 — 分布式系统架构师
> **日期**: 2026-06-23
> **评审对象**: DeepFlow 架构复盘 + Contract Layer 提案
> **模型**: bailian2/deepseek-v4-pro

---

## 零、核心判断（TL;DR）

**诊断大致准确，但根因不止一个。** "缺少合同层"抓住了问题的一个维度（数据契约），但忽略了至少两个同等重要的维度：**编排权力集中化**（谁有权力执行 Agent）和**状态源单一化**（谁有权力更新状态）。把三个维度的问题归约为一个"Contract Layer"，会导致方案覆盖面不足。

**建议的修改方向**：将"Contract Layer"扩展为**三层架构加固**——

| 现有方案 | 扩展建议 |
|:---|:---|
| Contract Registry（数据契约） | ✅ 保留，但缩小范围到"输出 Schema 自动生成" |
| 单一执行引擎（流程契约） | ✅ 保留，但需要明确"capability vs. permission" |
| 跨域合同（交接契约） | ✅ 保留 |
| **缺失：状态单源化** | 🔴 新增：集中式状态机 + 单一写路径 |
| **缺失：Gate 与 Prompt 静态绑定** | 🔴 新增：编译期 Gate→Prompt 一致性检查 |

---

## 一、状态管理：比"缺少合同"更根本的问题

### 1.1 三状态文件 = 三写入者 = 拜占庭问题

当前系统有三个独立的状态文件，各有独立的写入者：

| 状态文件 | 写入者 | 更新时机 |
|:---|:---|:---|
| `pipeline_status.json` | `run_pipeline.py` 的 `_save_status()` | Agent 状态变更时 |
| `.completed.json` | `completion_handler.py` 的 `write_completion_marker()` | Pipeline 完成时 |
| `.stage_progress.json` | 主 Agent 手动写入 | 阶段进度更新时 |

**这是分布式系统中最经典的"脑裂"场景**：多个写入者各自维护自己对"系统状态"的理解，没有共识协议，没有版本向量，没有单写者（single-writer）约束。

> **类比**: 三个数据库副本各自接受写入，没有 leader election，没有 quorum，没有 CRDT。不一致不是"bug"，是架构的必然结果。

### 1.2 Contract Layer 能解决这个问题吗？

**不能，因为这个问题的本质不是"合同不清晰"，而是"写入者太多"。**

Contract Layer 回答的是"输出应该长什么样"（What），但这个问题的本质是"谁有权更新状态"（Who）和"状态何时变化"（When）。合同可以定义状态文件的 schema，但无法约束"谁在什么条件下可以写入"——这是编排模型的问题，不是数据模型的问题。

### 1.3 建议：集中式状态机 + 单一写入路径

```
┌─────────────────────────────────────────────────┐
│              PipelineStateMachine                │
│                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Pipeline  │───▶│  Agent   │───▶│ Pipeline  │  │
│  │  State    │    │  State   │    │  State    │  │
│  │  (宏观)   │    │  (微观)   │    │  (宏观)   │  │
│  └──────────┘    └──────────┘    └──────────┘  │
│                                                 │
│  Single Writer: PipelineStateMachine.put(event)  │
│  Single Reader: PipelineStateMachine.get()       │
└─────────────────────────────────────────────────┘
```

**具体做法**：

1. **合并三个状态文件为一个** `pipeline_state.json`，包含所有状态信息
2. **只允许 `PipelineStateMachine` 类写入**，其他所有组件（包括主 Agent、completion_handler、run_pipeline.py）只读
3. **状态变更通过事件驱动**：`PSM.emit(event)` → 状态机内部转换 → 原子写入
4. **事件溯源**：保留事件日志（`.pipeline_events.jsonl`），状态文件可从事务日志重建

```python
# 伪代码
class PipelineStateMachine:
    def emit(self, event: PipelineEvent):
        self._validate_transition(event)  # 拒绝非法状态转换
        self._apply(event)                # 更新内存状态
        self._write_checkpoint()          # 原子写入状态文件
        self._append_event_log(event)     # 事件日志（可重建状态）
```

**为什么这比 Contract Layer 更根本**：因为 10 个问题中，P1-3 和 P1-4 是状态一致性问题，P1-1 和 P1-2 是数据契约问题。先修状态机（修 2 个），再修合同（修 2 个），顺序不能颠倒。

---

## 二、编排模式：三条执行路径的根因不是"缺少合同"

### 2.1 三条路径的本质分析

| 执行路径 | 角色 | 执行者 | 问题 |
|:---|:---|:---|:---|
| SKILL.md | 自然语言指令 | 主 Agent（LLM 解释执行） | 不可靠——LLM 可能"理解偏差" |
| run_pipeline.py | 确定性 CLI | 主 Agent 调用（或 cron） | 可靠——但主 Agent 可以选择不调用 |
| orchestrator_agent.py | Agent 脚本 | 主 Agent 直接 spawn | 绕过了 run_pipeline 的状态管理 |

**在分布式编排系统中，这相当于同时存在三个调度器：**
- 一个写在工作文档里（SKILL.md）
- 一个实现在代码里（run_pipeline.py）
- 一个是运行时决策器（主 Agent 的"自由意志"）

这在 Airflow/Argo/Temporal 中是不可想象的——你不可能让 DAG 定义、Scheduler 代码、和 Operator 的"自主决定"同时存在且互相矛盾。

### 2.2 为什么会出现这种情况？

**根因是 LLM Agent 系统的特殊性**：主 Agent 既是"用户"，又是"调度器"，还是"执行器"。

在一个标准的分布式编排系统中：
- **用户**提交任务 → **Scheduler** 调度 → **Worker** 执行

在 DeepFlow 中：
- **用户**提交需求 → **主 Agent** 决定怎么执行 → 可能走 SKILL.md 的指令，可能走 run_pipeline.py，可能自己 spawn

**主 Agent 拥有"终极权力"——它可以无视任何规则。**

### 2.3 解决方案：capability ≠ permission

Contract Layer 的"单一执行引擎"方案是对的，但只解决了"capability"（提供能力），没有解决"permission"（限制权力）。

**建议**：

1. **run_pipeline.py 升级为唯一执行入口**（同意提案）
2. **SKILL.md 降级为"人类可读文档"**，不再作为执行指令
3. **主 Agent 通过 run_pipeline.py 的 CLI 接口操作**，不直接 spawn Agent
4. **新增权限边界**：如果主 Agent 直接 spawn 子 Agent，Gate 直接 FAIL（因为输出文件路径不在 STAGE_PATH_REGISTRY 中，Schema 验证会失败）

但这里有一个根本矛盾：**主 Agent 是 LLM，LLM 天然不遵守"你不能直接执行"的规则。** 这是 LLM Agent 编排与确定性编排的最大区别。

**更现实的方案**：不是"消灭"主 Agent 的直接执行能力，而是让"通过 run_pipeline.py"变得比"直接执行"更简单、更可靠。类似 Temporal 的哲学——不是因为强制，而是因为"这样做更省心"。

```python
# 让主 Agent 的选择更简单
# 之前：3 条路径，主 Agent 需要判断走哪条
# 之后：1 条路径，无脑走
result = run_pipeline("ship_pro", input_data, session_id)
# 如果主 Agent 直接 spawn，输出会失败（输出路径不在 registry 中）
```

---

## 三、数据契约：Protobuf/gRPC 的 Schema Registry 模式

### 3.1 当前问题在分布式系统中的类比

```
Prompt (Markdown)  ──→ LLM  ──→ 输出 JSON  ──→ Gate (Python)  ──→ Schema (JSON)
     ↑                                                                    │
     └──────────────── 没有反馈回路 ────────────────────────────────────┘
```

这在传统的 gRPC 生态中对应的就是 **Schema Registry 断裂**：

| 分布式系统概念 | DeepFlow 对应 |
|:---|:---|
| `.proto` 文件 | `architect.md` prompt |
| protoc 编译器 | LLM（将 prompt 编译为输出） |
| 服务端 Stub（反序列化+校验） | `gate_architect()` |
| Schema Registry | ❌ 不存在 |
| 编译期类型检查 | ❌ 不存在 |

**在 gRPC 中，如果 `.proto` 定义了 `string name = 1;`，但服务端期望 `string full_name = 2;`，编译就失败了。** 在 DeepFlow 中，prompt 和 gate 不一致不会导致"编译失败"——它会在运行时表现为 CONDITIONAL，然后主 Agent 忽略它。

### 3.2 Protobuf 模式的适用性

**部分适用，但需要改造。**

Protobuf 的 Schema Registry 模式有两个关键特性：
1. **编译期检查**：protoc 编译时就能发现字段不匹配
2. **向后兼容**：新增字段不影响旧版本消费者

在 DeepFlow 中，Contract Registry 提案的 `contract.yaml` → 自动生成 prompt schema 段落 + Gate 检查代码 + JSON Schema，本质上就是实现了一个穷人版的 protoc。

**但这里有一个 LLM 特有的问题**：protoc 生成的代码是确定性的，但 LLM 生成的输出是概率性的。即使 prompt 中明确写了"必须输出 `project_type` 字段"，LLM 仍然可能忘记。这是 Contract Layer 无法解决的——它只能保证"prompt 说了要输出这个字段"，不能保证"LLM 一定会输出这个字段"。

**所以 Contract Layer 的正确定位应该是**：消除"prompt 没说要输出"导致的 gate 失败，而不是消除所有 gate 失败。Gate 仍然会失败，但失败原因从"不知道该输出什么"变成了"知道但没输出"——后者是 LLM 的本质限制，不是架构问题。

### 3.3 建议：编译期一致性检查

在 Contract Registry 之上，增加一个**编译期检查**：

```bash
# 在修改任何 prompt 或 gate 之后运行
python3 scripts/check_contract_consistency.py
# 输出：
# ✅ architect: contract.yaml ↔ architect.md ↔ gate_architect() — 一致
# ❌ packager: contract.yaml 定义了 model_tier 枚举 [claude-opus, gpt-4o]
#    但 packager.md prompt 允许 [standard, premium]
#    但 gate_packager() 不检查 model_tier
```

这个检查应当在 CI/CD 中运行，在每次部署前发现不一致。

---

## 四、容错设计：Gate 失效是设计问题，不是实现问题

### 4.1 当前的 Gate 设计

Gate 的 Critical/Major/Minor 三层 + retry + skip 机制是**非常合理的容错设计**，类似于：

- **Critical = 硬约束**（必须满足，否则 FAIL）
- **Major = 软约束**（超过阈值 CONDITIONAL，否则 PASS）
- **Minor = 建议**（记录但不影响 PASS/FAIL）

这个设计本身是 sound 的。问题在于：

### 4.2 Gate 失效的根因层级

```
Layer 1: Prompt 没告诉 LLM 要输出什么字段
  └── 导致 LLM 输出缺少字段
  └── 导致 Gate 总是触发 CONDITIONAL/FAIL
  └── 导致 CONDITIONAL 变成常态（"狼来了"效应）
  └── 导致主 Agent 忽略 CONDITIONAL，直接跳过
  └── 导致 Gate 形同虚设
```

**所以 Gate 失效不是 Gate 的设计问题，而是 Gate 的输入（prompt）与 Gate 的检查逻辑不一致。** 这是**设计层面**的问题——Gate 是独立设计的，没有与 Prompt 绑定。

### 4.3 结论

> **这是设计问题，不是实现问题。** 实现是正确的（gate_architect 的代码逻辑清晰），但设计时没有建立 "Gate 检查的字段必须能在 Prompt 中找到对应描述" 的约束。

Contract Layer 的 `contract.yaml` 同时生成 prompt 段落和 gate 检查代码，可以解决这个问题。但要注意：**Gate 的检查逻辑可能比 contract.yaml 更复杂**（比如 `ac_score_70` 需要 NLP 评分），所以 contract.yaml 不能完全替代 Gate 代码，只能保证"contract 定义的字段在两个地方一致"。

---

## 五、Contract Layer 方案评估

### 5.1 架构上是否 sound？

**大体 sound，但需要调整范围和优先级。**

| 组件 | 评估 | 风险 |
|:---|:---|:---|
| Contract Registry (contract.yaml) | ✅ 正确的方向 | 可能过度工程化——对于 5 个 Agent 的系统，是否需要完整的 DSL？ |
| 自动生成 Prompt Schema 段落 | ✅ 解决 P1-2 类问题 | LLM 不一定遵守，但至少消除了"不知道"的不确定性 |
| 自动生成 Gate 检查代码 | ⚠️ 部分可行 | 复杂检查（如 AC 评分）无法自动生成 |
| 自动生成 JSON Schema | ✅ 解决 P1-1 类问题 | 但 schema 也需要人工维护（enum 值、业务逻辑） |
| 单一执行引擎 | ✅ 正确方向 | 需要解决"主 Agent 绕过"的问题 |
| 跨域合同 | ✅ 正确方向 | P2-2 类问题确实需要形式化 |

### 5.2 过度设计风险

**存在过度设计风险，主要体现在：**

1. **contract.yaml DSL 的设计和维护成本**：对于 5 个 Agent 的系统，设计一个完整的 contract DSL 并维护它，可能比直接维护 5 个 prompt + 5 个 gate 函数更重

2. **自动生成代码的可靠性**：YAML → Python 代码生成看似优雅，但生成的代码需要调试、测试、维护。如果生成器有 bug，所有 Agent 的 Gate 都会出问题

3. **Phase 1-3 的整体范围**：三个阶段加起来，几乎等于重写整个系统。对于 10 个已知问题，是否有更轻量的方案？

### 5.3 更轻量的替代方案

**对于 10 个问题，建议分两步走，比 Contract Layer 的全部三个阶段更轻量：**

#### Step 1: 紧急修复（1-2 天）

| 问题 | 修复方式 | 工作量 |
|:---|:---|:---|
| P1-1: Schema 校验 128 错误 | 手动对齐 packager prompt 和 schema | 2h |
| P1-2: Architect Gate 断裂 | 在 architect.md 中增加 `project_type` 和 `mapped_components` 字段说明 | 30min |
| P1-3: 状态机失效 | 在主 Agent 手动 spawn 前，强制调用 `run_pipeline.py task` 而非直接 spawn | 1h |
| P1-4: 状态文件不一致 | 合并 `.completed.json` 和 `.stage_progress.json` 到 `pipeline_status.json` | 2h |
| P2-1: SKILL.md 版本不一致 | 将 SKILL.md 更新为 V3 流程描述 | 30min |
| P2-2: frozen_blueprint 缺失 | 在 completion_handler 中添加生成逻辑 | 1h |
| P2-3: final_solution.md 缺失 | 在 completion_handler 中添加生成逻辑 | 30min |
| P2-4: 占位符未替换 | 替换 reviewer.md 中的模板变量 | 15min |

**总计：约 1 个工作日。**

#### Step 2: 架构加固（1-2 周）

1. **集中式状态机**（替代三个状态文件）：2-3 天
2. **编译期一致性检查**（contract_consistency_check.py）：1-2 天
3. **单一执行入口**（SKILL.md 降级为文档，CLI 为唯一入口）：2-3 天
4. **Gate 与 Prompt 静态绑定**（contract.yaml 自动生成 prompt 字段说明 + gate 检查代码）：3-5 天

**总计：约 1-2 周，比 Phase 1-3 的完整 Contract Layer 轻量得多。**

### 5.4 什么情况下 Contract Layer 是必要的？

如果 DeepFlow 的 Agent 数量增长到 **20+ 个**，或者有**多个团队**各自维护 Agent 的 prompt 和 gate，那么 Contract Layer 的完整实现（含 DSL、代码生成、自动验证）是有价值的。对于当前 5 个 Agent 的系统，ROI 不高。

---

## 六、盲点：提案人没看到的问题

### 盲点 1: LLM 输出的概率性本质

Contract Layer 可以保证"prompt 说了要输出 X"，但不能保证"LLM 输出了 X"。在传统的分布式系统中，合同保证的是"双方都理解并同意接口定义"，但实现方（LLM）不是确定性的。

**这意味着**：即使 Contract Layer 完美实现，Gate 仍然会触发 CONDITIONAL/FAIL。系统需要接受这是 LLM Agent 管线的固有特性，而不是需要修复的 bug。

**建议**：在 Gate 的 CONDITIONAL 处理中，区分"LLM 不知道该输出什么"（可修复）和"LLM 知道但没输出好"（需要重试）。前者是 Contract Layer 解决的问题，后者是 LLM 的固有不确定性。

### 盲点 2: 可观测性

当前系统缺少分布式追踪。10 个问题的排查方式是"人工检查 5 个 Agent 的输出 + 3 个状态文件 + 2 个 prompt 文件"。如果有一个 OpenTelemetry 风格的 trace，每个 Agent 的执行作为一个 span，输入/输出作为 span attributes，问题排查会快 10 倍。

**建议**：在 Contract Layer 之前，先加入结构化日志（JSON 格式，包含 session_id、agent_name、stage、prompt_sha、output_schema_version、gate_decision）。

### 盲点 3: 版本管理

`run_pipeline.py` 中已经有了 `prompt_sha` 的概念（`_compute_prompt_sha()`），但：
- Gate 代码没有版本号
- Schema 文件没有版本号
- 没有机制确保 prompt_sha、gate 版本、schema 版本三者一致

**建议**：在 contract.yaml 中定义一个 `version` 字段，三个产物（prompt、gate、schema）都携带这个 version。验证时检查三者 version 是否一致。

### 盲点 4: 主 Agent 的"绕过"能力

提案说"消灭 3 条执行路径，只留 run_pipeline.py CLI"。但 LLM 主 Agent 可以无视这个规则——它可以直接 spawn 子 Agent。在传统的分布式系统中，你可以通过权限控制来限制谁可以调度任务。在 LLM Agent 系统中，你无法限制主 Agent 的"自由意志"。

**建议**：不要试图"禁止"主 Agent 绕过，而是通过**激励机制**让它不绕过：
- 确保 `run_pipeline.py` 比直接 spawn 更简单
- 确保直接 spawn 的输出会失败（因为输出路径不在 STAGE_PATH_REGISTRY，Schema 验证会失败）
- 在 SKILL.md 中明确说明"使用 run_pipeline.py 是唯一正确的方式"

### 盲点 5: Sub-agent 与 Pipeline 的关系

当前 `PipelineOrchestrator` 类有一个 `_resolve_spawn_fn()` 方法，试图注入 `sessions_spawn`。但 `run_pipeline.py` 的 CLI 模式（`get_agent_task()` 返回 task 字符串，由主 Agent 去 spawn）和 `PipelineOrchestrator` 模式（在 Agent 内部 spawn）是两套不同的模型。

**这本身就是一个架构歧义**：Pipeline 应该由谁驱动？

- **模式 A**：Pipeline 由主 Agent 驱动（CLI 模式，run_pipeline.py 提供"下一步做什么"的信息）
- **模式 B**：Pipeline 由 Orchestrator 驱动（在 Agent 内部 spawn 子 Agent）

**建议**：明确选择一种模式，消灭另一种。从当前代码看，模式 A 是更现实的（因为 LLM 主 Agent 无法被限制），但 `PipelineOrchestrator` 类的存在表明历史上曾经尝试过模式 B。

---

## 七、总结与优先级建议

### 核心判断

| 诊断 | 准确性 | 说明 |
|:---|:---:|:---|
| "缺少合同层"是根因 | ⚠️ 部分正确 | 合同层解决的是数据契约问题，但状态一致性、编排权力、执行路径三个问题需要不同的解决方案 |
| 5 份文档独立维护 | ✅ 正确 | 这是 P1-1 和 P1-2 的根因 |
| 3 条执行路径 | ✅ 正确 | 但根因不是"缺少合同"，而是"主 Agent 有终极权力" |
| 打地鼠会无限循环 | ✅ 正确 | 没有系统性约束，每次修复都是一次性对齐 |

### 优先级建议

**在有限资源下，建议按以下顺序修复：**

| 优先级 | 修复内容 | 解决哪些问题 | 工作量 |
|:---|:---|:---|:---|
| 🔴 P0 | 集中式状态机（合并三个状态文件为单一状态源） | P1-3, P1-4 | 2-3 天 |
| 🔴 P0 | 手动对齐 prompt ↔ gate ↔ schema（一次性修复） | P1-1, P1-2, P2-4 | 0.5 天 |
| 🟡 P1 | 单一执行入口（SKILL.md 降级为文档） | P1-3, P2-1 | 2-3 天 |
| 🟡 P1 | 编译期一致性检查（contract_consistency_check.py） | P1-1, P1-2（防复发） | 1-2 天 |
| 🟢 P2 | 补齐 missing artifacts（frozen_blueprint, final_solution） | P2-2, P2-3 | 0.5 天 |
| 🟢 P2 | 结构化日志 + 分布式追踪 | 可观测性 | 1-2 天 |
| 🔵 P3 | Contract Registry（如果 Agent 数量增长到 20+） | 系统性防复发 | 1-2 周 |

### 一句话总结

> **"缺少合同层"是对的，但只解决了问题和方案的三分之一。另外三分之二是：状态必须单源化（只有一个写入者），编排必须集中化（只有一个执行路径）。三者合在一起，才构成一个完整的分布式编排系统。先修状态机，再对齐合同，最后统一入口——按这个顺序，10 个问题中 8 个可以在 1 周内解决。** 完整的 Contract Layer（含 DSL、代码生成、Phase 1-3）是 20+ Agent 规模的方案，对当前 5 Agent 系统属于过度设计。

---

*评审完成时间: 2026-06-23 18:38 GMT+8*