# 专家 5 报告：简约主义倡导者（反过度工程视角）

> **日期**: 2026-06-18
> **角色**: 简约主义软件工程师 — KISS / YAGNI / Unix 哲学
> **立场**: 挑战一切复杂性，追问"这真的必要吗？"

---

## 〇、理论武器库

在分析之前，先亮出我的理论依据：

| 原则 | 核心主张 | 对 DeepFlow 的启示 |
|------|---------|-------------------|
| **KISS** | 最简方案往往是最好的 | 14,573 行代码的管线，是不是太复杂了？ |
| **YAGNI** | 不为假设的未来需求编码 | "以后可能支持更多执行引擎" ≠ 现在就要抽象 |
| **Gall's Law** | 工作的复杂系统都从简单系统演化而来 | 从零设计一个 4 层管线 = 必死 |
| **Worse is Better** | 实现的简单性 > 接口的完美性 | 一个"够用"的 JSON > 一个"完美"的 Blueprint 体系 |
| **Rule of Three** | 出现 3 次再抽象 | 只有 1 个执行引擎（Hermes），抽象"通用接口"是 premature |
| **Premature Abstraction** | 过早抽象是万恶之源 | Ship Pro 的"通用中间层"角色 = 为不存在的未来编码 |

---

## 一、必要性审计：逐条审判

### 当前产物链（10 个 Blackboard 文件）

| # | 文件 | 大小 | 我的判决 | 理由 |
|---|------|------|---------|------|
| 1 | `spec.json`（Spec Pro 输出） | — | ✅ **保留** | 需求收集是真正必要的。没有需求就没有方案。 |
| 2 | `execution_plan.json` | 3.6KB | ❌ **砍掉** | Solution Pro 内部执行计划，是"10 阶段管线"的脚手架。用户不关心你内部怎么编排。 |
| 3 | `control_contract.json` | 15.3KB | ❌ **砍掉** | Solution Pro 内部契约，"harness scoring" 机制的产物。对外部消费者无意义。 |
| 4 | `tasks.json` | 166.1KB | ❌ **砍掉** | Solution Pro 内部任务数据。166KB 的内部数据 = 过度工程的铁证。 |
| 5 | `final_result.json` | 21.4KB | ✅ **保留** | 这是 Solution Pro 的**真正输出**——最丰富、信息密度最高。 |
| 6 | `living_blueprint.json` | 36.8KB | ❌ **砍掉** | "活版本"蓝图——一个在生命周期中从未被消费过的中间产物。 |
| 7 | `frozen_blueprint.json` | 44.5KB | ❌ **砍掉（或彻底重新定义）** | 信息比 final_result 少，却是 Ship Pro 的输入。这是一个**信息损耗的中间层**。 |
| 8 | `requirements_traceability_matrix.json` | 16.4KB | ⚠️ **降级为内部产物** | 需求追溯是好实践，但不应该是 blackboard 的一等公民。 |
| 9 | `ship_package.json` | 17.5KB | ⚠️ **保留但大幅简化** | 执行任务单是必要的，但不需要 17.5KB 的 JSON 来表达。 |
| 10 | `ship_review_data.json` / `domain_config.json` | 32.1KB | ❌ **砍掉** | Ship Pro 的辅助数据。domain_config 是"LLM 预扫描"的产物——又一个中间层。 |

### 当前模块链

| 模块 | 代码量 | 判决 | 分析 |
|------|--------|------|------|
| **Spec Pro** | 4,214 行 / 12 文件 | ⚠️ **大幅精简** | 需求收集本身必要，但 4,214 行？`coordinator.py` 1,340 行、`schemas.py` 426 行、`response_normalizer.py` 390 行——这是在"理解需求"还是在"工程化理解需求"？ |
| **Solution Pro** | 8,602 行 / 21 文件 | 🔴 **严重过度工程** | `task_builder.py` 1,922 行、`blueprint_compiler.py` 1,500 行、`orchestrator_agent.py` 927 行。一个"方案设计"模块需要 8,602 行代码吗？这是 Inner Platform Effect 的典型案例。 |
| **Ship Pro** | 1,757 行 / 10 文件 | 🔴 **premature abstraction** | 只有 1 个执行引擎（Hermes），却有一个"通用中间层"。1,757 行代码做的核心事情是：`module.name → WP.title`。 |
| **Super Loop** | 未实现 | ✅ **必要** | 实际执行代码的循环。这是唯一真正"做事"的环节。 |

### 关键发现

**14,573 行 Python 代码**，做的事情本质上是：

```
用户需求 → LLM 理解 → 方案设计 → 任务分解 → 代码执行
```

一个 5 步的流程，用了 4 个模块 + 10 个中间产物。这就是 Richard Gabriel 所说的 "The Right Thing" 陷阱——试图从一开始就设计一个完美的、通用的、可扩展的体系。

---

## 二、最简方案设计

### 核心论点：最少只需要 3 个模块

```
┌─────────────────────────────────────────────────────────┐
│                    最简架构（3 模块）                      │
│                                                         │
│  ┌───────────┐    ┌───────────────┐    ┌─────────────┐ │
│  │  Spec Pro  │───▶│   Architect   │───▶│ Super Loop  │ │
│  │ (需求收集)  │    │ (方案+任务单)  │    │  (执行)     │ │
│  └───────────┘    └───────────────┘    └─────────────┘ │
│       │                 │                    │          │
│       ▼                 ▼                    ▼          │
│   spec.json        plan.json           (代码输出)       │
│                    (≈合并 final_result                 │
│                     + ship_package)                   │
└─────────────────────────────────────────────────────────┘
```

**砍掉的模块/产物**：
1. ❌ `living_blueprint.json` — 从未被外部消费
2. ❌ `frozen_blueprint.json` — 信息损耗器
3. ❌ `execution_plan.json` — 内部脚手架
4. ❌ `control_contract.json` — 内部契约
5. ❌ `tasks.json` — 166KB 的内部任务数据
6. ❌ `domain_config.json` — LLM 预扫描中间产物
7. ❌ `ship_review_data.json` — 审查辅助数据
8. ❌ **Ship Pro 作为独立模块** — 合并进 Architect

**合并的核心逻辑**：

当前 Ship Pro 做的"真正有价值的事"（依赖关系推导 + phase 拓扑排序）完全可以作为 Solution Pro 的最后一步。不需要一个独立的 1,757 行模块来做格式转换。

### 最简数据流

```
Step 1: Spec Pro
  输入: 用户对话
  输出: spec.json（结构化需求）
  代码量: ~500 行（精简后）

Step 2: Architect（合并 Solution Pro + Ship Pro 的有价值部分）
  输入: spec.json
  输出: plan.json（方案蓝图 + 工作包 + 依赖关系 + 验收标准）
  代码量: ~1,500 行（精简后）

Step 3: Super Loop
  输入: plan.json
  输出: 可执行代码
  代码量: 待定
```

**总代码量**: ~2,000 行（vs 当前 14,573 行）

**plan.json 的结构**（一个文件，不是 10 个）：

```json
{
  "intent": { "project_name": "...", "description": "..." },
  "architecture": { "style": "...", "modules": [...] },
  "work_packages": [
    {
      "id": "WP-001",
      "title": "实现用户认证模块",
      "depends_on": [],
      "acceptance_criteria": ["..."],
      "technical_hints": ["..."]
    }
  ],
  "phases": [
    { "phase": 1, "work_packages": ["WP-001", "WP-002"] }
  ],
  "verification": {
    "integration_checks": ["..."],
    "definition_of_done": "..."
  }
}
```

---

## 三、对 Q1-Q4 的明确建议（偏简约方向）

### Q1: Blueprint 层是否保留？

**明确建议：选项 B — 砍掉 frozen_blueprint，Ship Pro 直接消费 final_result**

更进一步：连 living_blueprint 也砍掉。

**理由**：
- frozen_blueprint 比 final_result **信息更少**（这是已证实的事实）
- 它存在的唯一理由是"给 Ship Pro 一个稳定的输入格式"
- 但 Ship Pro 只有 1 个消费者，"稳定接口"的价值为零
- 这是 **Premature Abstraction** 的教科书案例：为 1 个使用场景设计"通用接口"

**Worse is Better 视角**：final_result 可能不"完美"，但它**信息最完整**。让下游直接消费它，比通过一个信息损耗的中间层要好得多。

### Q2: Solution Pro 应该输出什么？

**明确建议：只输出 1 个文件 — `plan.json`**

当前 Solution Pro 输出 3 个文件（final_result + living_blueprint + frozen_blueprint），加上 4 个内部产物。这是"Inner Platform Effect"——你在 Solution Pro 里面建了一个平台。

**plan.json 应该包含**：
1. 架构设计（模块划分、技术选型、依赖关系）
2. 工作包分解（每个 WP 有明确的验收标准）
3. 阶段规划（phase 划分 + 拓扑排序）
4. 验证策略（集成检查点 + 完成定义）

**不应该包含**：
- execution_plan（内部编排细节）
- control_contract（harness scoring 的中间产物）
- tasks.json（166KB 的内部任务数据——这是一个红旗🚩）

### Q3: Ship Pro 应该做什么？

**明确建议：Ship Pro 不应该作为独立模块存在**

当前 Ship Pro 的"有价值工作"：
1. 依赖关系推导 — 可以合并到 Architect 的最后一步
2. Phase 拓扑排序 — 同上，30 行代码搞定
3. 格式适配（module → WP）— 只有 1 个执行引擎，不需要"通用接口"

**如果未来有第 2 个执行引擎**（Rule of Three）：
- 到那时再抽取一个 `adapter` 层
- 基于 2-3 个真实案例来设计抽象，而不是为 1 个案例预设

**YAGNI**: "以后可能支持 Claude Code / Codex" 不是现在维持 1,757 行模块的理由。

### Q4: 三个模块的数据流最优设计？

**明确建议：2 个文件传递，不是 10 个**

```
用户 ──对话──▶ Spec Pro ──spec.json──▶ Architect ──plan.json──▶ Super Loop
                                          │
                                     (LLM 调用)
```

**Blackboard 上只留 2 个产物**：
1. `spec.json` — 需求
2. `plan.json` — 方案 + 任务

**不是 10 个**。10 个 blackboard 文件 = 你在用文件系统模拟一个消息队列。

---

## 四、推荐架构数据流图（最简版）

```
┌─────────────────────────────────────────────────────────────────┐
│                    DeepFlow 最简架构                              │
│                                                                 │
│  ┌──────────┐     ┌──────────────────────┐     ┌────────────┐  │
│  │ Spec Pro │     │      Architect       │     │ Super Loop │  │
│  │          │     │  (Solution Pro 精简)  │     │            │  │
│  │ 用户对话  │────▶│                      │────▶│  执行代码   │  │
│  │   ↓      │     │ spec.json            │     │   ↑        │  │
│  │ LLM 理解  │     │   ↓                  │     │ plan.json  │  │
│  │   ↓      │     │ LLM 方案设计          │     │   ↓        │  │
│  │ spec.json│     │   + 工作包分解         │     │ 代码输出    │  │
│  └──────────┘     │   + 依赖排序          │     └────────────┘  │
│                   │   + 验收标准          │                      │
│                   │   ↓                  │                      │
│                   │ plan.json            │                      │
│                   └──────────────────────┘                      │
│                                                                 │
│  产物数量: 2 个 (spec.json + plan.json)                          │
│  代码总量: ~2,500 行 (vs 当前 14,573 行)                         │
│  模块数量: 3 个 (vs 当前 4 个 + 10 个中间产物)                    │
└─────────────────────────────────────────────────────────────────┘
```

### 对比当前架构

| 维度 | 当前 | 最简版 | 削减比 |
|------|------|--------|--------|
| 模块数 | 4 (Spec/Solution/Ship/SuperLoop) | 3 (Spec/Architect/SuperLoop) | -25% |
| Blackboard 文件 | 10 | 2 | **-80%** |
| Python 代码 | 14,573 行 | ~2,500 行 | **-83%** |
| 中间 JSON 产物 | 8 个 | 0 个 | **-100%** |
| LLM 调用链 | Spec→Solution(10阶段)→Ship | Spec→Architect(1-2阶段) | **-75%** |

---

## 五、砍掉复杂性后的风险

### 风险 1：丢失"通用性"

**担忧**："如果未来需要支持多种执行引擎怎么办？"

**回应**：
- **Rule of Three** — 你现在只有 1 个执行引擎。为 1 个案例设计"通用接口"是 premature abstraction。
- 等到第 2、第 3 个执行引擎出现时，你会有**真实的案例**来指导抽象设计，而不是基于猜测。
- 到那时抽取 adapter 层的成本 << 现在维护 1,757 行 Ship Pro 的成本。

**缓解**：在 plan.json 中留一个 `engine_hints` 字段（5 行代码），未来扩展时够用。

### 风险 2：丢失"可追溯性"

**担忧**："砍掉 control_contract、traceability_matrix，怎么追溯需求？"

**回应**：
- 需求追溯是好实践，但不需要 16.4KB 的独立 JSON 文件。
- 在 plan.json 的每个 work_package 里加一个 `source_requirements: ["REQ-001"]` 字段就够了。
- 追溯性应该是**数据结构的一个字段**，不是一个独立模块。

**缓解**：plan.json 中保留 `traceability` 内联字段。

### 风险 3：Solution Pro 的"10 阶段管线"被简化掉

**担忧**："10 阶段管线保证了方案质量，简化后质量会不会下降？"

**回应**：
- 10 个阶段 ≠ 10 个阶段都在做有用的事。
- 检查当前 10 个阶段的实际输出：有多少阶段的输出在后续阶段被消费了？
- 如果 `execution_plan.json` 和 `control_contract.json` 是某些阶段的"产出"，但这些产出从未被下游消费——那些阶段就是**死代码**。
- 质量来自 LLM 的能力 + prompt 的质量，不是管线的长度。

**缓解**：保留 2-3 个关键阶段（理解→设计→验证），砍掉纯内部编排的阶段。

### 风险 4：忠礼的"通用接口"论点

**担忧**：忠礼明确说 "Ship Pro 是一个中间层、通用接口的角色"。

**回应**：
- 这是整个设计中**最大的 premature abstraction 风险**。
- "通用接口"的价值取决于消费者的数量。1 个消费者 = 没有"通用"可言。
- 如果忠礼的愿景是"DeepFlow 未来支持 10 种执行引擎"，那是一个**产品战略决策**，不应该在架构层面用 1,757 行代码来预付成本。
- **建议**：先验证 DeepFlow 的核心价值（方案质量），再考虑扩展性。Gall's Law：先让它 work，再让它 grow。

**缓解**：在 Architect 模块的 prompt 中，输出格式已经天然适配 Hermes。如果未来需要其他引擎，修改 prompt 的输出格式比维护一个独立的"编译"模块简单 10 倍。

### 风险 5：过度精简导致调试困难

**担忧**："如果所有东西都合并了，出问题时怎么定位？"

**回应**：
- 2 个 JSON 文件（spec.json + plan.json）= 2 个调试检查点。
- 比 10 个文件中排查问题简单得多。
- 如果需要更细粒度的调试，加 logging（`structured_log` 已经存在），不需要保留中间产物文件。

---

## 六、总结：我的"砍刀清单"

### 立即砍掉（节省 ~12,000 行代码）

1. ❌ `living_blueprint.json` — 从未被外部消费
2. ❌ `frozen_blueprint.json` — 信息损耗器
3. ❌ `execution_plan.json` — 内部脚手架
4. ❌ `control_contract.json` — harness scoring 中间产物
5. ❌ `tasks.json` — 166KB 内部数据
6. ❌ `domain_config.json` — LLM 预扫描中间产物
7. ❌ `ship_review_data.json` — 审查辅助
8. ❌ **Ship Pro 作为独立模块** — 合并其有价值部分到 Architect

### 大幅精简

1. ⚠️ Solution Pro 从 8,602 行 → ~1,500 行（砍掉内部编排、harness scoring、多策略系统）
2. ⚠️ Spec Pro 从 4,214 行 → ~500 行（保留核心需求收集，砍掉 schema 验证、response normalization 的过度工程）

### 保留

1. ✅ spec.json — 需求（必要）
2. ✅ plan.json — 方案+任务（必要，合并 final_result + ship_package 的有价值部分）
3. ✅ Super Loop — 执行（必要）

---

## 七、一句话总结

> **当前 DeepFlow 有 14,573 行代码和 10 个中间产物，做的事情本质上是：理解需求 → 设计方案 → 执行代码。3 个模块、2 个文件、2,500 行代码就够了。剩下的 12,000 行是在为"假设的未来"编码。**

---

## 附录：理论引用

- **Gall's Law**: "A complex system that works is invariably found to have evolved from a simpler system that worked." — John Gall, *Systemantics* (1975)
- **Worse is Better**: "The design must be simple, both in implementation and interface. It is more important for the implementation to be simple than the interface." — Richard Gabriel (1989)
- **Rule of Three**: "Wait until you have three instances of business logic with a clear, recurring pattern before abstracting."
- **YAGNI**: "Always implement things when you actually need them, never when you just foresee them." — Ron Jeffries
