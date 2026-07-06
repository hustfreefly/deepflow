# 专家 13：AI Native 架构师 — Ship Pro 多 Agent 协作架构设计

> **日期**: 2026-06-18
> **角色**: AI Native 架构师（多 Agent 协作设计）
> **评审对象**: Ship Pro 从"确定性编译器"重构为"多 Agent 协作系统"

---

## 一、问题诊断：为什么当前方案不是 AI Native

### 1.1 当前架构的本质问题

当前 Ship Pro（`ship_compiler.py`，~1048 行 Python）是一个**确定性状态机**：

```
frozen_blueprint.json → 字段映射 → Work Packages → 模板填充 → ship_package.json
```

即使加入了 `domain_config.json`（LLM 预扫描），它仍然是**LLM 做了一部分 + 确定性代码兜底**的混合体：
- LLM 预扫描生成 `domain_config.json`（模块→阶段映射）
- 确定性 Python 代码做 WP 分解、AC 生成、风险契约

**核心矛盾**：`final_result.json` 有 5+ 种格式变体，每增加一种变体，确定性代码就需要新的 `if-else` 分支。这是**穷举式适配**，不是理解式适配。

### 1.2 实际格式多样性（从真实案例观察）

| 案例 | 架构信息位置 | 实施计划 | 需求信息 |
|------|-------------|---------|---------|
| 跨境算力中转站 | `architecture.core_components` | ✅ `implementation_plan`（phases+tasks） | 无（在 RTM 里） |
| 智能简历系统 | `final_solution.detailed_solution.architecture.components` | ❌ 无独立计划 | `covered_req_ids` |
| 智能客服系统 | `architecture.components` | ✅ `implementation_plan` | `requirements.items` |
| 电商订单系统 | `architecture`（16 个技术组件字段） | ❌ 无 | `req_coverage` |
| Serenity Skills | `final_solution.detailed_solution.architecture.components` | ❌ 无 | `covered_req_ids` |

**关键洞察**：信息都在，但**藏在哪、叫什么、怎么组织**完全不同。这正是 LLM 擅长的"理解"问题，不是确定性代码擅长的"映射"问题。

---

## 二、推荐架构：三 Agent 流水线 + 共享状态

### 2.1 设计原则

基于 2025-2026 多 Agent 系统的最佳实践（参考 Anthropic Agent Teams、OpenAI Agents SDK Handoffs、MetaGPT SOP 模式），结合 DeepFlow 的实际约束：

| 原则 | 说明 |
|------|------|
| **专精分工** | 每个 Agent 只做一件事，做到极致 |
| **结构化契约** | Agent 间传递 JSON Schema 约束的结构化数据，不是自然语言 |
| **渐进式质量门控** | 每个 Agent 输出经过验证才传递给下一个 |
| **最小上下文原则** | 每个 Agent 只接收它需要的信息，不传全量 |
| **可重试可降级** | 单 Agent 失败可独立重试，不污染全局状态 |

### 2.2 三 Agent 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Ship Pro Pipeline                            │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  Extractor   │───▶│  Architect   │───▶│  Assembler   │          │
│  │  (提取Agent)  │    │  (规划Agent)  │    │  (组装Agent)  │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
│         │                   │                   │                   │
│    SolutionIR          WorkPlanIR          ShipPackage             │
│    (理解契约)          (规划契约)           (输出契约)               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Quality Gate (LLM-as-Judge)                     │   │
│  │         每个 Agent 输出后独立验证，失败则重试                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 Agent 职责定义

#### Agent 1: Extractor（提取 Agent）

**职责**：从任意格式的 `final_result.json` + `RTM` + `execution_plan` 中提取统一的 `SolutionIR`。

**输入**：
- `final_result.json`（任意格式变体）
- `requirements_traceability_matrix.json`
- `execution_plan.json`
- （可选）`living_blueprint.json` 的 `design_decisions`

**输出**：`SolutionIR`（标准化中间表示）

```json
{
  "project_name": "跨境AI算力中转站平台",
  "objective": "...",
  "constraints": {
    "budget": "<$3000",
    "timeline": "15天MVP",
    "team": "1人兼职",
    "tech_preference": "Vibe Coding + 成熟开源"
  },
  "components": [
    {
      "id": "COMP-01",
      "name": "API网关层",
      "technology": "New API",
      "role": "多供应商聚合、智能路由、自动故障切换<3s",
      "deployment": "Docker on Railway",
      "tier": "T1",
      "dependencies": [],
      "complexity": "medium"
    }
  ],
  "requirements": [
    {
      "id": "REQ-001",
      "description": "...",
      "priority": "P0",
      "status": "covered"
    }
  ],
  "implementation_hints": {
    "phases": [...],
    "critical_path": [...],
    "budget_breakdown": {...}
  },
  "risks": [...],
  "design_decisions": {
    "tradeoffs": [...],
    "rejected_alternatives": [...]
  }
}
```

**Prompt 设计要点**：
- 不预设字段路径，而是描述"需要提取什么"
- 给出 2-3 个格式变体的例子，让 LLM 理解多样性
- 要求输出严格遵循 SolutionIR Schema
- 对缺失字段标记 `null` 而非编造

**为什么用 LLM 而不是代码**：5+ 种格式变体，每种嵌套路径不同。LLM 天然擅长"在不同格式中找到相同语义"，确定性代码需要为每种格式写一套映射。

---

#### Agent 2: Architect（规划 Agent）

**职责**：将 `SolutionIR` 转化为可执行的 `WorkPlanIR`（工作包规划）。

**输入**：`SolutionIR`

**输出**：`WorkPlanIR`

```json
{
  "work_packages": [
    {
      "id": "WP-001",
      "title": "API网关层 - 多供应商聚合与智能路由",
      "phase": 1,
      "phase_name": "核心基础设施",
      "estimated_hours": 40,
      "estimated_complexity": "medium",
      "dependencies": [],
      "component_refs": ["COMP-01"],
      "requirement_refs": ["REQ-001", "REQ-007", "REQ-009"],
      "deliverables": [
        "src/gateway/router.ts — 智能路由核心",
        "src/gateway/providers/ — 供应商适配器",
        "tests/integration/gateway.test.ts"
      ],
      "acceptance_criteria": [
        {
          "criterion": "支持至少3家AI供应商的API接入",
          "verification": "集成测试：对每个供应商发送相同请求，验证响应格式一致",
          "priority": "P0"
        }
      ],
      "technical_constraints": [
        "使用 New API（MIT License），Docker 部署在 Railway",
        "故障切换时间 < 3 秒"
      ],
      "integration_checkpoints": [
        { "after": "WP-003", "check": "API网关 + 支付系统集成验证" }
      ]
    }
  ],
  "execution_order": ["WP-001", "WP-002", "WP-003"],
  "parallel_groups": [["WP-001", "WP-004"]],
  "total_estimated_hours": 180,
  "critical_path": ["WP-001", "WP-003", "WP-005"]
}
```

**Prompt 设计要点**：
- 输入是标准化的 SolutionIR，不需要处理格式多样性
- 核心任务是**智能拆分**：哪些组件应该合并到一个 WP，哪些应该独立
- 考虑依赖关系、并行可能性、关键路径
- 工时估算基于组件复杂度和依赖深度
- AC 从需求证据中推导，不是凭空生成

**为什么拆成独立 Agent**：规划需要"理解项目全貌后做决策"，这和"从混乱格式中提取信息"是两种完全不同的认知任务。分开后每个 Agent 的 prompt 更聚焦，输出质量更高。

---

#### Agent 3: Assembler（组装 Agent）

**职责**：将 `WorkPlanIR` 组装为最终的 `ship_package.json`，补充工程细节。

**输入**：`WorkPlanIR` + `SolutionIR`（用于交叉验证）

**输出**：`ship_package.json`（最终格式）

**具体工作**：
- 为每个 WP 补充具体的文件路径、模块名
- 生成 Harmony Brief（执行上下文摘要）
- 生成 Risk Contract（从 SolutionIR 的风险信息推导）
- 生成 Acceptance Contract（从 WP 的 AC 汇总）
- 计算 Contracts、Delivery、Traceability 元数据

**Prompt 设计要点**：
- 接收的是已规划好的 WorkPlanIR，不需要做决策
- 主要是**格式化 + 补全 + 交叉验证**
- 确保所有 REQ 都有对应的 AC
- 确保所有 WP 的依赖关系无环

**为什么需要这个 Agent**：Assembler 可以做"全局一致性检查"——这是 Architect 做不到的（Architect 关注拆分，Assembler 关注整体一致性）。

---

### 2.4 Quality Gate（LLM-as-Judge）

每个 Agent 输出后，由一个轻量级 Judge Agent 验证：

```
Agent 输出 → Quality Gate → 通过 → 下一个 Agent
                           → 不通过 → 反馈 + 重试（最多 2 次）
```

**Judge 验证规则**：

| Agent | 验证项 |
|-------|--------|
| Extractor | SolutionIR 是否包含所有必需字段？components 数量是否合理？是否有遗漏的关键信息？ |
| Architect | WorkPlanIR 的 WP 是否覆盖了所有 components？依赖关系是否有环？AC 是否可验证？ |
| Assembler | ship_package.json 是否符合 Schema？所有 REQ 是否有 AC？所有 WP 是否有 deliverables？ |

**实现方式**：
- Judge 是一个独立的 LLM 调用，prompt 中包含 Schema 和验证规则
- 输出结构化：`{ "pass": true/false, "issues": [...], "fix_instructions": "..." }`
- 不通过时，fix_instructions 作为 retry prompt 的一部分传回原 Agent

**为什么不用 JSON Schema 验证**：JSON Schema 只能验证结构（字段是否存在、类型是否正确），不能验证语义（WP 是否真的覆盖了组件的功能、AC 是否真的可验证）。语义验证需要 LLM。

---

## 三、Agent 间通信协议

### 3.1 为什么选择结构化 JSON 而非自然语言

基于 2025 年 Agent 间通信的研究共识：

| 方式 | 优势 | 劣势 | 适用场景 |
|------|------|------|---------|
| **结构化 JSON** | 可验证、可解析、零歧义 | 需要 Schema 约定 | ✅ Agent 间数据传递 |
| **自然语言** | 灵活、人类可读 | 歧义、不可验证、信息损失 | ❌ Agent 间协作 |
| **共享状态** | 解耦、可追溯 | 需要状态管理基础设施 | ✅ 与 Blackboard 结合 |

**决策**：Agent 间传递**结构化 JSON（受 Schema 约束）**，同时写入 Blackboard 作为共享状态。

### 3.2 通信流程

```
1. Extractor 读取 blackboard/ 下的输入文件
2. Extractor 输出 SolutionIR → 写入 blackboard/.internal/solution_ir.json
3. Quality Gate 1 验证 SolutionIR
4. Architect 读取 solution_ir.json
5. Architect 输出 WorkPlanIR → 写入 blackboard/.internal/work_plan_ir.json
6. Quality Gate 2 验证 WorkPlanIR
7. Assembler 读取 work_plan_ir.json + solution_ir.json
8. Assembler 输出 ship_package.json → 写入 blackboard/ship_package.json
9. Quality Gate 3 验证 ship_package.json
10. 通过 → 完成；不通过 → 回到对应 Agent 重试
```

### 3.3 为什么不直接传自然语言

当前方案中 `domain_config.json` 已经是 LLM 输出的结构化数据。但它只做了"模块→阶段"映射，没有充分利用结构化通信。

新方案中，每个 Agent 的输出都是**下游 Agent 的精确输入格式**：
- Extractor 知道 Architect 需要什么字段
- Architect 知道 Assembler 需要什么结构
- 每个 Agent 的 prompt 中可以精确描述输入/输出 Schema

---

## 四、与前一轮方案的对比分析

### 4.1 方案对比表

| 维度 | V2（LLM + 确定性 + 校验层） | V3（多 Agent 协作） |
|------|---------------------------|-------------------|
| **格式适配** | domain_config 预扫描 + 硬编码映射 | Extractor Agent 理解式提取 |
| **新增格式变体** | 需要修改 Python 代码 | 无需修改，LLM 天然适配 |
| **WP 拆分** | 规则：module → WP 1:1 映射 | Architect Agent 智能拆分 |
| **AC 生成** | 从全局 AC 匹配到 WP | Architect 从需求语义推导 |
| **质量保障** | JSON Schema + 规则校验 | LLM-as-Judge 语义验证 |
| **代码量** | ~1048 行 Python + 持续增长 | ~200 行编排代码 + prompts |
| **维护成本** | 每种新格式需要新代码 | Prompt 中加一个示例即可 |
| **可解释性** | 高（确定性代码可追踪） | 中（LLM 决策需要 trace 日志） |
| **成本** | 低（1 次 LLM 预扫描） | 中（3-5 次 LLM 调用） |
| **延迟** | 低（秒级） | 中（10-30 秒） |
| **鲁棒性** | 低（格式变化即崩溃） | 高（LLM 容忍格式变化） |

### 4.2 关键改进

1. **消除了格式适配的维护负担**：Extractor Agent 通过理解而非映射来处理格式多样性。新增变体无需修改代码。

2. **WP 拆分从"规则"升级为"决策"**：Architect Agent 可以考虑依赖关系、并行可能性、复杂度均衡，而不是简单的 1:1 映射。

3. **质量保障从"结构验证"升级为"语义验证"**：LLM-as-Judge 可以判断"这个 AC 是否真的可验证"、"这个 WP 是否真的覆盖了组件功能"。

4. **可重试粒度更细**：一个 Agent 失败只需重试该 Agent，不需要重跑整个管线。

### 4.3 潜在风险

| 风险 | 缓解措施 |
|------|---------|
| LLM 提取遗漏关键信息 | Quality Gate 1 交叉验证 RTM 中的 REQ 数量 |
| Architect 拆分不合理 | Quality Gate 2 检查组件覆盖率 + 依赖无环 |
| 成本增加（3-5 次 LLM 调用） | Extractor/Assembler 用小模型，Architect 用大模型 |
| 延迟增加（10-30 秒） | 可接受范围（对比 Solution Pro 的 10 阶段管线） |
| LLM-as-Judge 误判 | 保守策略：有疑问时标记而非拒绝 |

---

## 五、实施信心评分

### 评分：8/10

**信心依据**：
1. ✅ 多 Agent 协作是 2025-2026 的行业共识方向（Gartner 预测 40% 企业应用将采用）
2. ✅ 结构化通信协议（A2A、MCP）已成熟，不需要从零设计
3. ✅ LLM-as-Judge 模式已被广泛验证（DeepEval、Langfuse 等框架）
4. ✅ 三个 Agent 的分工清晰，每个都是 LLM 擅长的认知任务
5. ✅ 渐进式迁移可行：可以先替换 Extractor，验证后再替换其他部分

**扣分原因**：
1. ⚠️ LLM 提取的稳定性需要实测验证（不同模型表现可能差异大）
2. ⚠️ Quality Gate 的误判率需要调优（太严会频繁重试，太松会放过错误）
3. ⚠️ 成本增加需要量化评估（3-5 次 LLM 调用的 token 消耗）

---

## 六、实施建议

### 6.1 分阶段迁移路径

```
Phase 1（1周）：Extractor Agent
  - 实现 Extractor prompt + SolutionIR Schema
  - 用 8 个现有案例测试提取准确率
  - 与 domain_config.json 对比验证

Phase 2（1周）：Architect Agent
  - 实现 Architect prompt + WorkPlanIR Schema
  - 用跨境算力中转站 + 智能简历系统两个极端案例测试
  - 对比当前 WP 分解结果

Phase 3（3天）：Assembler Agent
  - 实现 Assembler prompt + ship_package Schema
  - 确保输出与当前 ship_package.json 兼容

Phase 4（3天）：Quality Gate + 编排层
  - 实现 Judge prompt + 重试逻辑
  - 实现 Agent 间状态传递
  - 端到端测试
```

### 6.2 模型选择建议

| Agent | 推荐模型 | 理由 |
|-------|---------|------|
| Extractor | Claude Sonnet / Qwen-Plus | 需要处理格式多样性，中等推理能力 |
| Architect | Claude Opus / Qwen-Max | 需要深度理解和决策，最强推理 |
| Assembler | Claude Sonnet / Qwen-Plus | 主要是格式化和补全，中等能力即可 |
| Judge | Claude Haiku / Qwen-Turbo | 轻量验证，快速响应 |

### 6.3 与现有 Blackboard 架构的整合

```
blackboard/
├── final_result.json                    ← Extractor 读取
├── requirements_traceability_matrix.json ← Extractor 读取
├── execution_plan.json                  ← Extractor 读取
├── .internal/
│   ├── solution_ir.json                 ← Extractor 输出
│   ├── work_plan_ir.json                ← Architect 输出
│   └── quality_reports/                 ← Judge 输出
├── ship_package.json                    ← Assembler 输出（最终）
└── ship_package.md                      ← Assembler 输出（人类可读）
```

---

## 七、总结

**核心论点**：Ship Pro 的问题本质是"理解多样化的人类表达并转化为结构化工程计划"——这是 LLM 的核心能力，不是确定性代码的核心能力。

**推荐方案**：三 Agent 流水线（Extractor → Architect → Assembler）+ 结构化中间契约（SolutionIR / WorkPlanIR）+ LLM-as-Judge 质量门控。

**与 AI Native 原则的对齐**：
- ✅ LLM 做全部智能工作（提取、规划、验证）
- ✅ Agent 间通过结构化数据协作（不是自然语言）
- ✅ 每个 Agent 专精一个认知任务
- ✅ 质量保障用 LLM 而非代码规则
- ✅ 格式适应性通过理解而非穷举实现

> **"让 LLM 做 LLM 擅长的事，让代码做代码擅长的事。"**
> 
> 在这个场景中：LLM 擅长理解、推理、适配；代码擅长执行、存储、传输。
> 多 Agent 协作让每个 Agent 专注于一个认知任务，通过结构化契约协作，
> 比"LLM + 确定性代码"的混合体更纯粹、更可维护、更鲁棒。
