# AI Coding 消费者需求诊断

> **分析日期**: 2026-06-19
> **视角**: AI Coding Agent（Codex / Claude Code / Cursor）使用者
> **分析对象**: Ship Pro V3 Schema + 跨境案例真实产出
> **核心问题**: 一个 AI Coding Agent 真正需要从 ship_package 中获取什么？V3 定义的字段对不对？

---

## 核心结论：AI Coding Agent 真正需要什么

**一句话**: AI Coding Agent 需要的是一个**可执行的施工指令**，不是一份**可读的需求描述**。

Ship Pro V3 产出的是后者——一份人类可读、结构清晰的工作包描述。但 Codex/Claude Code 不是人类。它不需要"理解背景"，它需要**精确知道：读什么文件 → 改/写什么 → 跑什么验证 → 失败了怎么办**。

### 三个层次的诊断

| 层次 | Ship Pro V3 做到了吗 | 对 AI Agent 的影响 |
|------|:---:|------|
| **L1: 知道做什么** (objective + AC) | ✅ 做得好 | Agent 能理解目标，但无法直接执行 |
| **L2: 知道怎么开始** (context_files + outputs) | ❌ 全空 | Agent 不知道从哪下手，必须自己探索代码库 |
| **L3: 知道怎么跑** (budget + model + retry + tests) | ❌ 全空/null | Agent 无法被自动化调度，必须人工介入 |

**根本问题**: Ship Pro V3 的 Schema 字段**定义是对的**（字段选择合理），但 **Specifier Agent 没有填充它们**。这不是 Schema 设计问题，是 **Pipeline 执行问题**。

然而，深入分析后发现：**即使 Specifier 尽力填，某些字段在当前 Pipeline 架构下根本填不了**。这才是真正的问题。

---

## 字段需求分析

### 从 Codex 视角逐字段审视

假设我是 Codex，拿到 WP-002（API网关核心引擎部署），我要开始工作：

| 字段 | AI Agent 需要吗 | 需要程度 | 当前状态 | 诊断 |
|------|:---:|:---:|:---:|------|
| `id` | ✅ 必须 | 🔴 | ✅ `WP-002` | 正常。用于依赖追踪和日志 |
| `title` | ✅ 必须 | 🔴 | ✅ `API网关核心引擎部署` | 正常。Agent 用来快速定位任务 |
| `objective` | ✅ 必须 | 🔴 | ✅ 有值但太短 | **问题**: objective 只是 title 的重复（"API网关核心引擎部署"），没有说明具体要做什么。应该是"部署 New API 到 Railway，配置 PostgreSQL，实现 OpenAI 兼容的 /v1/chat/completions 端点" |
| `acceptance_criteria` | ✅ 必须 | 🔴 | ✅ 10 条详细 AC | **最大亮点**。AC 质量 73/100，有量化条件。但格式是自然语言，不是可执行命令 |
| `dependencies` | ✅ 必须 | 🔴 | ✅ `["WP-001"]` | 正常。Agent 知道要先等 WP-001 完成 |
| `context_files` | ✅ 必须 | 🔴 | ❌ `[]` | **关键缺失**。Agent 不知道读什么文件。但见下文"能不能填"分析 |
| `outputs` | ✅ 必须 | 🔴 | ❌ `[]` | **关键缺失**。Agent 不知道产出什么。Schema 要求 minItems=1 但实际为空=Schema 违规 |
| `budget.tokens` | ✅ 重要 | 🟠 | ❌ `null` | Agent 不知道 token 上限，可能过度消耗或过早停止 |
| `budget.time_minutes` | ⚠️ 有用 | 🟡 | ❌ `null` | 对 Codex 意义不大（它不按时间计费），但对调度器重要 |
| `budget.max_retries` | ✅ 重要 | 🟠 | ❌ `null` | Agent 不知道失败后能重试几次 |
| `complexity` | ✅ 重要 | 🟠 | ❌ `null` | 影响 Agent 选择策略（简单→直接写，复杂→先规划） |
| `model_tier` | ⚠️ 有用 | 🟡 | ❌ `null` | 对 Codex 无意义（它不能切换自己的模型），但对**调度器选择哪个 Agent** 有意义 |
| `acceptance_tests` | ✅ 必须 | 🔴 | ❌ `[]` | **关键缺失**。AC 是自然语言，tests 应该是可执行命令。Agent 需要跑命令来验证自己是否完成 |
| `retry_policy` | ⚠️ 有用 | 🟡 | ❌ `null` | 失败后 abort/retry/skip？对自动化调度重要 |
| `requires_human_approval` | ✅ 重要 | 🟠 | 未设置(默认false) | 某些 WP（如支付集成）可能需要人工审批 |
| `tags` | ⚠️ 有用 | 🟡 | ❌ `[]` | 分类标签，帮助 Agent 选择处理策略 |
| `constraints` | ✅ 必须 | 🟠 | ✅ 有值 | 非 Schema 标准字段但实际输出了，包含集成检查点和跨 WP 约束 |
| `source_modules` | ⚠️ 追溯用 | 🟡 | ✅ 有值 | 非 Schema 标准字段，用于追溯来源 |

### 字段价值排序（AI Agent 视角）

```
必须有（没有就无法工作）:
  1. objective（做什么）         → ✅ 有但质量低
  2. acceptance_criteria（怎么验证）→ ✅ 有且质量尚可
  3. context_files（读什么）      → ❌ 空
  4. outputs（产出什么）          → ❌ 空
  5. acceptance_tests（跑什么验证） → ❌ 空

重要（影响效率和质量）:
  6. complexity（复杂度）         → ❌ null
  7. budget.tokens（token 预算）  → ❌ null
  8. dependencies（依赖关系）     → ✅ 有

有用但不紧急:
  9. model_tier（模型选择）       → ❌ null（对调度器有用，对 Agent 无用）
  10. retry_policy（失败策略）     → ❌ null
  11. budget.time_minutes         → ❌ null
```

---

## 关键问题分析

### 问题 1: context_files 在这个阶段能不能填？

**答案: 部分能，部分不能。**

当前 Pipeline 的信息流是：
```
用户需求 → Solution Pro（方案设计）→ Ship Pro（工作包拆解）→ AI Coding Agent（执行）
```

Ship Pro 阶段有两种场景：

| 场景 | 代码库状态 | context_files 能填吗 |
|------|-----------|:---:|
| **Brownfield**（已有代码库） | 代码存在 | ✅ 能。Solution Pro 可以分析代码库结构，Specifier 可以引用具体文件 |
| **Greenfield**（从零开始） | 代码不存在 | ❌ 不能。没有文件可引用 |

跨境案例是 **Greenfield**（"15天 MVP"、"Vibe Coding + 成熟开源"），代码库还不存在。所以 context_files 为空是**正确的**——没有文件可引用。

**但这暴露了更深层的问题**: Ship Pro Schema 没有区分 Greenfield 和 Brownfield。对于 Greenfield 项目，context_files 的语义应该是"参考文件/模板/文档"（比如 New API 的 GitHub 仓库地址、Railway 的部署文档），而不是"要修改的源代码文件"。

**建议**: 
- 将 `context_files` 拆分为 `source_files`（要读/改的代码）和 `reference_docs`（参考文档/URL）
- 对于 Greenfield 项目，`reference_docs` 应该包含技术选型对应的文档链接

### 问题 2: outputs 为什么是空？该填什么？

outputs 为空是 **Schema 违规**（minItems=1）+ **Specifier 执行缺失**的双重问题。

对于跨境案例，outputs 应该填什么？

| WP | 合理的 outputs |
|----|---------------|
| WP-001 CDN | `["cloudflare-config.md", "dns-records.txt"]` — 配置文档 |
| WP-002 网关 | `["docker-compose.yml", "railway.toml", "new-api/.env"]` — 部署配置 |
| WP-003 供应商 | `["supplier-channels-config.md", "api-test-results.json"]` — 配置和测试报告 |
| WP-004 用户 | `["user-service/config.md", "token-metering-spec.md"]` — 配置规格 |
| WP-005 支付 | `["payment-integration-spec.md", "webhook-config.md"]` — 集成规格 |
| WP-006 前端 | `["frontend/src/", "vercel.json"]` — 前端代码目录 |
| WP-007 监控 | `["monitoring-config.yml", "alert-rules.json", "status-page-config.md"]` — 监控配置 |

**但这里有个粒度问题**: 如果 outputs 是具体文件路径，那 Specifier 需要知道项目目录结构。如果项目还不存在（Greenfield），Specifier 需要**定义**目录结构。这超出了 Specifier 当前的职责范围。

**建议**: outputs 应该分两层：
- `output_artifacts`: 高层交付物描述（如 "Docker 部署配置"、"前端应用代码"）— Specifier 能填
- `output_files`: 具体文件路径 — 需要 Agent 在执行时确定

### 问题 3: WP 粒度是否合适？

**7 个 WP，每个 7-10 条 AC。对 AI Agent 来说粒度偏大。**

| 粒度问题 | 分析 |
|---------|------|
| **WP-001（CDN 配置）** | 对 Codex 来说，这是 30 分钟的工作。一个 WP 合适 |
| **WP-002（网关部署）** | 包含 Docker 部署 + DB 配置 + API 兼容性 + SSE + 路由 + 熔断 + ZDR + 计量 = **至少 8 个子任务**。太大了 |
| **WP-006（前端）** | Landing + Dashboard + API 文档 + 登录 + 充值 + 合规文档 + 响应式 = **至少 6 个独立页面/功能**。太大了 |

**核心问题**: WP 的粒度是按**人类团队的任务包**设计的（一个人负责一个 WP），不是按 **AI Agent 的单次执行**设计的。

AI Agent 的最佳工作粒度：
- **单次 session**: 1 个具体功能（如"实现 /v1/chat/completions 端点"），30-60 分钟完成
- **单个 WP**: 应该对应 1-3 个 session

**建议**: 
- WP-002 应该拆成 WP-002a（Docker 部署 + DB）、WP-002b（API 兼容性 + SSE）、WP-002c（路由 + 熔断 + ZDR）
- WP-006 应该拆成 WP-006a（Landing + 静态页面）、WP-006b（Dashboard + 用户功能）、WP-006c（支付页面 + 集成）
- 或者引入 `sub_tasks` 字段，WP 内部可以有子任务

### 问题 4: model_tier 对谁有用？

`model_tier` 对 **Codex 本身无用**——Codex 不能切换自己的模型。

它对**调度器**有用：调度器根据 model_tier 决定把 WP 分配给 Codex（opus）还是 Cursor（sonnet）还是 Haiku。

**但这暴露了架构假设问题**: Ship Pro 假设有一个中央调度器读取 ship_package 并分配任务。在实际使用中：
- 如果用户手动操作 Codex，model_tier 是噪音
- 如果有自动化调度器，model_tier 是必须的

**建议**: 保留 model_tier，但明确标注为"调度器指令，非 Agent 消费"。或者移到 `meta` 级别，不在 WP 级别。

### 问题 5: budget.tokens 有意义吗？

**有，但当前阶段填不了。**

token 预算取决于：
1. 代码库大小（context_files 决定）
2. 模型选择（model_tier 决定）
3. 任务复杂度（complexity 决定）

这三个都是 null/空，所以 budget.tokens 也必然是 null。

**更深层问题**: AI Coding Agent 的 token 消耗不像 API 调用那样可预测。一个 WP 可能消耗 50K tokens（简单修改）也可能消耗 500K tokens（需要大量探索）。预算更像是"软限制 + 告警阈值"，不是"硬上限"。

**建议**: 
- `budget.tokens` 改为 `budget.token_warning_threshold`（超过此值告警但不中断）
- 增加 `budget.token_hard_limit`（超过此值强制停止）
- 或者干脆去掉 token 预算，改为 `budget.max_turns`（最大对话轮次），这更可预测

---

## Schema 改进建议

### 建议 1: 修复 objective 字段——从 title 重复变为可执行指令

**当前**: `objective: "API网关核心引擎部署"` （就是 title 的重复）

**应该**: objective 是一段完整的技术指令，包含：
- 要部署什么（New API）
- 部署到哪（Railway 新加坡/东京）
- 关键技术要求（OpenAI 兼容、SSE、PostgreSQL）
- 关键约束（Docker 容器化、ZDR 架构）

**Schema 修改**: 给 objective 增加 minLength 约束（如 ≥100 字符），强制 Specifier 写清楚。

### 建议 2: 区分 Greenfield 和 Brownfield 的 context 语义

**新增字段**:
```json
{
  "project_type": {
    "type": "string",
    "enum": ["greenfield", "brownfield"],
    "description": "Whether this is a new project or existing codebase"
  }
}
```

**修改 context_files 语义**:
- Brownfield: 要读/改的源代码文件路径
- Greenfield: 参考文档 URL、模板仓库地址、API 文档链接

**或者更好的方案**: 拆分为两个字段：
```json
{
  "source_files": { "type": "array", "items": { "type": "string" } },
  "reference_docs": { "type": "array", "items": { "type": "string", "format": "uri" } }
}
```

### 建议 3: outputs 分两层

```json
{
  "output_artifacts": {
    "type": "array",
    "items": { "type": "string" },
    "description": "High-level deliverables (Specifier fills this)",
    "minItems": 1
  },
  "output_files": {
    "type": "array",
    "items": { "type": "string" },
    "description": "Specific file paths (Agent fills this during execution)"
  }
}
```

### 建议 4: acceptance_tests 从"空数组"变为 AC 的机器可读映射

当前 AC 是自然语言，acceptance_tests 应该是从 AC 推导出的可执行命令。

**问题**: 这在 Specifier 阶段确实很难填（不知道代码结构、不知道测试框架）。

**替代方案**: 将 acceptance_tests 从 Specifier 的职责中移除，改为 **Agent 执行时自己生成**。Schema 中保留字段但标记为 `agent_filled: true`。

或者，Specifier 至少应该给出**测试方向**：
```json
{
  "acceptance_tests": [
    {
      "ac_id": "AC-002-03",
      "test_direction": "curl POST to /v1/chat/completions with OpenAI-format payload, verify response schema",
      "test_type": "integration",
      "suggested_tool": "curl + jq"
    }
  ]
}
```

### 建议 5: 增加 `environment` 字段

AI Agent 需要知道**运行环境**：
```json
{
  "environment": {
    "type": "object",
    "properties": {
      "runtime": { "type": "string", "description": "e.g. node:20, python:3.12" },
      "package_manager": { "type": "string", "description": "e.g. npm, pnpm, pip" },
      "deployment_target": { "type": "string", "description": "e.g. railway, vercel, aws" },
      "required_tools": { "type": "array", "items": { "type": "string" } },
      "env_vars_required": { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

跨境案例中，Agent 需要知道：用 Docker、部署到 Railway、需要 PostgreSQL、需要 New API 的 Docker 镜像。这些信息在 AC 中散落提及，但没有结构化。

### 建议 6: 增加 `sub_tasks` 字段（WP 内部拆分为可执行步骤）

```json
{
  "sub_tasks": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["step", "instruction"],
      "properties": {
        "step": { "type": "integer" },
        "instruction": { "type": "string" },
        "estimated_tokens": { "type": "integer" },
        "depends_on_steps": { "type": "array", "items": { "type": "integer" } }
      }
    }
  }
}
```

这解决了 WP 粒度太大的问题——WP 是逻辑分组，sub_tasks 是 Agent 实际执行的步骤。

---

## 被忽略的关键字段

### 1. `technology_stack`（技术栈声明）

**为什么需要**: Codex 开始写代码前，必须知道用什么语言/框架/库。当前这些信息散落在 AC 文本中（"Docker 容器"、"PostgreSQL"、"Next.js"），但没有结构化提取。

**建议**: 在 WP 级别增加：
```json
{
  "technology_stack": {
    "languages": ["python", "javascript"],
    "frameworks": ["next.js", "express"],
    "infrastructure": ["docker", "railway", "cloudflare"],
    "databases": ["postgresql"],
    "external_services": ["paddle", "stripple"]
  }
}
```

### 2. `definition_of_done`（完成的定义）

**为什么需要**: AI Agent 最容易犯的错误是"做多了"或"做少了"。需要明确定义：
- 什么算"做完"？（所有 AC 通过？测试覆盖？代码 review？）
- 什么"不需要做"？（MVP 不做性能优化？不做单元测试？）

**建议**:
```json
{
  "definition_of_done": {
    "type": "object",
    "properties": {
      "completion_criteria": { "type": "array", "items": { "type": "string" } },
      "out_of_scope": { "type": "array", "items": { "type": "string" } },
      "quality_bar": { "type": "string" }
    }
  }
}
```

### 3. `error_handling_guidance`（错误处理指导）

**为什么需要**: 当 Agent 遇到无法解决的问题时（如 API 返回未知错误、依赖版本冲突），它需要知道：
- 是自己尝试解决（最多尝试几次）？
- 还是跳过这个子任务继续下一个？
- 还是停下来报告？

`retry_policy` 只覆盖了 WP 级别的失败，但 Agent 在 WP 内部执行时也会遇到微观层面的错误。

**建议**:
```json
{
  "error_handling_guidance": {
    "type": "object",
    "properties": {
      "on_unknown_error": { "type": "string", "enum": ["retry", "skip", "abort", "ask_human"] },
      "max_self_recovery_attempts": { "type": "integer" },
      "escalation_condition": { "type": "string" }
    }
  }
}
```

### 4. `integration_points`（集成点声明）

**为什么需要**: 每个 WP 不是孤立的。Agent 需要知道自己的代码要和什么对接。

跨境案例中：
- WP-002（网关）要和 WP-001（CDN）对接 → Agent 需要知道 CDN 域名和路由规则
- WP-005（支付）要和 WP-004（用户）对接 → Agent 需要知道用户数据模型和 Token 计量接口

当前这些信息在 `dependencies` 和 `constraints` 中隐含，但没有显式声明**接口契约**。

**建议**:
```json
{
  "integration_points": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "depends_on_wp": { "type": "string" },
        "interface": { "type": "string", "description": "API endpoint or data contract" },
        "direction": { "type": "string", "enum": ["provides", "consumes"] }
      }
    }
  }
}
```

---

## 总结：Ship Pro V3 的核心矛盾

### 矛盾：Schema 设计 vs Pipeline 执行

| 维度 | Schema 设计 | Pipeline 执行 | 结论 |
|------|:---:|:---:|:---:|
| 字段选择 | ✅ 合理 | — | 字段定义覆盖了 AI Agent 需要的信息 |
| 字段填充 | — | ❌ 大面积空值 | Specifier Agent 没有填满字段 |
| 字段可填性 | — | — | ❌ **部分字段在 Specifier 阶段根本填不了** |

**核心发现**: 不是"Specifier 不够努力"，而是 **信息流架构决定了某些字段在 Specifier 阶段不可填**：

| 字段 | Specifier 能填吗 | 原因 |
|------|:---:|------|
| `context_files` | ❌ Greenfield 不能 | 代码不存在，没有文件可引用 |
| `outputs` (具体文件) | ❌ Greenfield 不能 | 目录结构未定义 |
| `acceptance_tests` (可执行命令) | ⚠️ 部分能 | 知道测试方向，但不知道测试框架/工具 |
| `budget.tokens` | ❌ 不能 | 依赖 context_files 和 model_tier |
| `complexity` | ⚠️ 能但没填 | 可以从 AC 数量和依赖深度推断 |
| `model_tier` | ⚠️ 能但没填 | 可以从 complexity 推断 |

### 改进优先级

| 优先级 | 改进项 | 预期收益 |
|:---:|------|---------|
| 🔴 P0 | 修复 objective：从 title 重复变为完整技术指令 | Agent 能直接理解任务，减少探索成本 |
| 🔴 P0 | outputs 改为 output_artifacts（高层描述），Specifier 必填 | Agent 知道要产出什么 |
| 🔴 P0 | 增加 technology_stack 字段 | Agent 立刻知道用什么技术 |
| 🟠 P1 | 区分 Greenfield/Brownfield，context_files 改为 reference_docs | Greenfield 项目有参考文档可看 |
| 🟠 P1 | 增加 sub_tasks 字段，WP 内部可拆分为执行步骤 | 解决 WP 粒度太大的问题 |
| 🟠 P1 | 增加 environment 字段 | Agent 知道运行环境 |
| 🟡 P2 | acceptance_tests 改为"测试方向"而非"可执行命令" | 降低 Specifier 填充难度 |
| 🟡 P2 | 增加 definition_of_done 字段 | 防止 Agent 做多了或做少了 |
| 🟡 P2 | 增加 integration_points 字段 | Agent 知道接口契约 |

### 最终判断

> **Ship Pro V3 的 Schema 字段选择是对的（80%），但字段定义粒度不够精确（60%），且 Pipeline 的信息流架构导致关键内容无法在 Specifier 阶段填充（40%）。**
>
> **修复方向**：
> 1. **Schema 层面**: 增加 technology_stack、environment、sub_tasks、integration_points
> 2. **Pipeline 层面**: 接受"有些字段 Agent 自己填"的现实，Schema 中标记 `specifier_filled` vs `agent_filled`
> 3. **Specifier Prompt 层面**: 强化 objective 质量、强制填充 output_artifacts、增加 complexity 推断逻辑
> 4. **粒度层面**: 引入 sub_tasks 或拆分过大的 WP（WP-002、WP-006）

---

*诊断完成: 2026-06-19*
*视角: AI Coding Agent 消费者（Codex/Claude Code/Cursor）*
*方法: 逐字段需求分析 + 信息流架构分析 + Pipeline 可填性评估*
