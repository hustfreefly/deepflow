# 专家 4 报告：产品经理视角（用户体验 + 工作流）

> **作者**: 专家 4 — AI 产品经理（Developer Tool / AI Agent 产品方向）
> **日期**: 2026-06-18
> **任务**: 从用户工作流和渐进式交付角度，评判 DeepFlow 架构重设计

---

## 一、用户工作流分析：忠礼真正需要看到什么？

### 1.1 忠礼的实际心智模型

忠礼的工作流极其简洁：

```
想法 → "帮我做XX" → 看方案 → "确认/调整" → 看结果 → "满意/迭代"
```

这是一个 **两步确认** 模型：
1. **方案确认**（Plan Review）：AI 理解了我的需求吗？方案合理吗？
2. **结果确认**（Result Review）：做出来了吗？符合预期吗？

### 1.2 当前系统的问题：中间产物爆炸

当前系统在一次运行中产出 **10 个 JSON 文件**：

| 文件 | 大小 | 用户是否需要看？ |
|------|------|:---:|
| final_result.json | 21.4KB | ⚠️ 可能需要（方案摘要） |
| living_blueprint.json | 36.8KB | ❌ 不需要 |
| frozen_blueprint.json | 44.5KB | ❌ 不需要 |
| ship_package.json | 17.5KB | ⚠️ 可能需要（任务列表） |
| requirements_traceability_matrix.json | 16.4KB | ❌ 不需要 |
| control_contract.json | 15.3KB | ❌ 不需要 |
| ship_review_data.json | 19.1KB | ❌ 不需要 |
| domain_config.json | 13.0KB | ❌ 不需要 |
| execution_plan.json | 3.6KB | ❌ 不需要 |
| tasks.json | 166.1KB | ❌ 不需要 |

**核心发现**：10 个文件中，用户真正可能需要的只有 1-2 个。其余 8-9 个是 AI 系统的内部实现细节。

### 1.3 业界标杆对比

| 产品 | 用户看到的中间产物 | 设计哲学 |
|------|:---:|:---|
| **GitHub Copilot Workspace** | 1 个 Plan（自然语言） | "Describe → Plan → Implement"，Plan 是唯一需要确认的 |
| **Cursor Composer** | 0 个中间产物 | 直接描述需求 → 出代码，无中间步骤 |
| **Notion AI** | 0 个中间产物 | 对话式交互，结果即文档 |
| **Linear** | 1 个 Issue/Ticket | 极简任务模型，依赖关系内隐 |
| **Manus Agent** | 1 个 Plan 文件 | Plan-driven，但 Plan 是人类可读的 |

**结论**：业界最佳实践是 **0-1 个中间产物**。DeepFlow 当前是 10 个。

---

## 二、对 Q1-Q4 的明确建议

### Q1: Blueprint 层是否保留？

**建议：选项 B — 砍掉 frozen_blueprint，Ship Pro 直接消费 final_result**

理由：
1. **信息损耗不可接受**：frozen_blueprint 丢失了组件技术栈、部署方式、许可证、执行计划等关键信息。修复这个"损耗器"的成本 > 收益。
2. **用户不需要 Blueprint**：忠礼不需要看一个 30KB 的 JSON 来确认方案。他需要一个 **人类可读的方案摘要**（500 字以内），而不是一个机器格式。
3. **final_result 已经足够丰富**：它包含 implementation_plan、modules、tech_stack 等所有 Ship Pro 需要的信息。
4. **living_blueprint 也无存在必要**：它是 Solution Pro 内部的状态追踪文件，不应暴露给用户。

**具体做法**：
- Solution Pro 只输出 `final_result.json`（重命名为 `solution.json`）
- Ship Pro 直接消费 `solution.json`
- 所有 Blueprint 文件降级为 Solution Pro 的内部调试产物，不进 blackboard 主目录

### Q2: Solution Pro 应该输出什么？

**建议：输出一个 `solution.json` + 一个人类可读的 `plan_summary.md`**

`solution.json` 应包含（从 final_result 提取）：
```
{
  "project_name": "...",
  "problem_statement": "...",
  "solution_overview": "...",        // 方案概述
  "modules": [...],                   // 模块设计（含技术栈、职责、依赖）
  "tech_stack": {...},                // 技术选型
  "architecture_decisions": [...],    // 关键架构决策（ADR 风格）
  "implementation_plan": {            // 实施计划（从 final_result 保留）
    "mvp_timeline": "...",
    "phases": [...]
  },
  "constraints": [...],               // 约束条件
  "risks": [...]                      // 风险点
}
```

`plan_summary.md` 是给忠礼看的：
```markdown
# 方案摘要：跨境AI算力中转站

## 一句话概述
...

## 核心模块（3个）
1. **API 转发层** — New API on Railway，负责...
2. **用户系统** — PostgreSQL + JWT，负责...
3. **管理后台** — React + Vite，负责...

## 技术选型
- 后端：New API + Node.js
- 数据库：PostgreSQL (Supabase)
- 部署：Railway

## 实施计划
- Phase 1（Day 1-5）：核心基础设施
- Phase 2（Day 6-10）：业务逻辑
- Phase 3（Day 11-15）：联调测试

## 关键决策
1. 选择 New API 而非 Kong，因为...
2. 选择 Railway 而非 AWS，因为...

## 风险
1. API 供应商审批时间不确定
2. ...
```

**关键原则**：Solution Pro 的输出边界是"架构方案"，不是"施工计划"。它告诉用户"做什么、为什么这么做"，不告诉用户"怎么做、分几步做"。

### Q3: Ship Pro 应该做什么？

**建议：Ship Pro 应该是真正的"项目经理"，输出可执行的 Ship Package**

当前 Ship Pro 的问题：
- 只是格式搬运（module → WP），没有增值
- 生成的 AC 是废话（"功能实现完成，满足设计规格"）
- constraints 是空话（"上游未提供具体约束"）

**Ship Pro 应该做的增值工作**：

1. **任务分解**：把 module 拆成可执行的 task（每个 task < 2 小时工作量）
2. **依赖排序**：确定 task 之间的执行顺序（拓扑排序）
3. **验收标准**：为每个 task 生成具体的、可验证的 AC（不是废话）
4. **技术约束**：从 solution.json 的 constraints 和 tech_stack 推导出每个 task 的具体约束
5. **集成检查点**：在关键节点设置"停下来验证"的检查点
6. **执行引擎适配**：根据目标引擎（Hermes/Codex/Claude Code）调整输出格式

**Ship Package 应该长这样**：
```
{
  "project": "跨境AI算力中转站",
  "executor": "hermes",              // 执行引擎
  "total_tasks": 23,
  "estimated_hours": 46,
  "phases": [
    {
      "name": "核心基础设施",
      "tasks": [
        {
          "id": "T001",
          "title": "注册域名并配置 DNS",
          "ac": [
            "域名 example.com 可访问",
            "DNS 解析指向 Railway 实例"
          ],
          "constraints": [
            "使用 Cloudflare 作为 DNS 提供商",
            "启用 HTTPS"
          ],
          "depends_on": [],
          "estimated_minutes": 30,
          "integration_checkpoint": false
        },
        ...
      ]
    }
  ],
  "integration_checkpoints": [
    {
      "after_task": "T005",
      "check": "API 转发链路端到端验证",
      "criteria": "curl 请求能正确转发并返回响应"
    }
  ]
}
```

### Q4: 三个模块的数据流最优设计是什么？

**建议**：

```
┌─────────────────────────────────────────────────────────────┐
│                    用户视角（忠礼看到的）                      │
│                                                             │
│  "帮我做XX" ──→ [方案摘要] ──→ "确认" ──→ [进度/结果] ──→ "OK" │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    系统视角（内部数据流）                       │
│                                                             │
│  Spec Pro                                                   │
│    │                                                        │
│    ▼                                                        │
│  requirements.json ──→ Solution Pro                         │
│                         │                                   │
│                         ▼                                   │
│                    solution.json ──→ Ship Pro               │
│                                         │                   │
│                                         ▼                   │
│                                    ship_package.json        │
│                                         │                   │
│                                         ▼                   │
│                                    Super Loop               │
│                                         │                   │
│                                         ▼                   │
│                                    代码产物 + 执行报告        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键设计决策**：
1. **三个 JSON 文件**：`requirements.json` → `solution.json` → `ship_package.json`，每个阶段一个，干净利落
2. **一个人类可读文件**：`plan_summary.md`，在 Solution Pro 完成后自动生成，是忠礼唯一需要看的中间产物
3. **内部文件不进 blackboard 主目录**：control_contract.json、execution_plan.json、tasks.json 等是 Solution Pro 的内部状态，放在 `.internal/` 子目录或 debug 日志中

---

## 三、推荐的用户可见 Artifact 清单（最少化）

### 3.1 忠礼需要看到的（必须可见）

| # | Artifact | 形式 | 时机 | 用途 |
|:-:|----------|------|------|------|
| 1 | **方案摘要** | Markdown（500字以内） | Solution Pro 完成后 | 忠礼确认方案 |
| 2 | **执行进度** | 实时文本更新 | Super Loop 执行中 | 忠礼了解进度 |
| 3 | **最终结果** | 文本 + 文件列表 | 全部完成后 | 忠礼验收 |

### 3.2 忠礼可能想看的（按需展开）

| # | Artifact | 形式 | 时机 | 用途 |
|:-:|----------|------|------|------|
| 4 | **任务列表** | 表格/清单 | Ship Pro 完成后 | 忠礼了解具体步骤 |
| 5 | **架构决策记录** | Markdown | 方案确认后 | 忠礼回顾为什么这么设计 |

### 3.3 忠礼不需要看到的（内部产物）

| Artifact | 原因 |
|----------|------|
| frozen_blueprint.json | 内部格式转换产物 |
| living_blueprint.json | Solution Pro 内部状态 |
| control_contract.json | Solution Pro 内部执行契约 |
| execution_plan.json | Solution Pro 内部计划 |
| tasks.json | Solution Pro 内部任务数据 |
| requirements_traceability_matrix.json | 质量追踪，内部使用 |
| ship_review_data.json | Ship Pro 内部审查 |
| domain_config.json | Ship Pro 内部配置 |

### 3.4 Progressive Disclosure 应用

借鉴 Progressive Disclosure 原则，信息分层展示：

```
第一层（始终可见）：方案摘要 → 进度 → 结果
第二层（点击展开）：任务列表、架构决策
第三层（调试模式）：完整 JSON 文件
```

**不要让用户在第三层信息中迷路。**

---

## 四、推荐的架构数据流图（从用户视角）

### 4.1 用户交互流

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  忠礼     │     │  DeepFlow │     │ 忠礼      │     │ DeepFlow  │
│  (想法)   │     │  (AI)    │     │ (确认)    │     │  (执行)   │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     │ "帮我做XX"     │                │                │
     ├───────────────→│                │                │
     │                │                │                │
     │                │ [收集需求...]   │                │
     │                │ [设计方案...]   │                │
     │                │                │                │
     │    ┌───────────┤                │                │
     │    │ 方案摘要   │                │                │
     │    │ (500字)   │                │                │
     │    └───────────┤                │                │
     │                │                │                │
     │                │ "方案如上，确认？"│                │
     │                ├───────────────→│                │
     │                │                │                │
     │                │         "确认，开始"              │
     │                │                ├───────────────→│
     │                │                │                │
     │                │                │   [执行中...]   │
     │                │                │   [Phase 1/3]  │
     │                │         ┌──────┤                │
     │                │         │进度更新│                │
     │                │         └──────┤                │
     │                │                │                │
     │                │         "完成了" │                │
     │                │         ┌──────┤                │
     │                │         │结果摘要│                │
     │                │         │+文件列表              │
     │                │         └──────┤                │
     │                │                │                │
```

### 4.2 系统内部数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                        DeepFlow Pipeline                        │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────┐    ┌────────┐│
│  │ Spec Pro │───→│ Solution Pro │───→│ Ship Pro │───→│ Super  ││
│  │          │    │  (架构师)     │    │(项目经理) │    │ Loop   ││
│  └──────────┘    └──────────────┘    └──────────┘    │(施工队) ││
│       │                │                 │            └────────┘│
│       ▼                ▼                 ▼                 │    │
│  requirements    solution.json     ship_package.json    代码产物 │
│      .json           │                 │                 │    │
│                      ▼                 ▼                 ▼    │
│               plan_summary.md    (内部调试文件)        执行报告  │
│               (给用户看的)                                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Blackboard 主目录（用户可见）：                            │   │
│  │   solution.json | ship_package.json | plan_summary.md   │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ Blackboard 内部目录（调试用）：                             │   │
│  │   .internal/control_contract.json                       │   │
│  │   .internal/execution_plan.json                         │   │
│  │   .internal/tasks.json                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 与业界对标

| 维度 | Copilot Workspace | Cursor | DeepFlow（推荐后） |
|------|:---:|:---:|:---:|
| 用户可见中间产物 | 1（Plan） | 0 | 1（plan_summary.md） |
| 确认点 | 1（Plan review） | 0 | 1（方案确认） |
| 内部 JSON 文件 | 不暴露 | 不暴露 | 不暴露（.internal/） |
| 从想法到代码的步骤 | 3（Describe→Plan→Code） | 2（Describe→Code） | 3（Idea→Plan→Execute） |

DeepFlow 推荐方案与 Copilot Workspace 对齐：**1 个确认点 + 1 个中间产物**。

---

## 五、最大风险

### 风险 1：Solution Pro 的"通用性"导致 Ship Pro 信息不足

**风险描述**：Solution Pro 被定位为"通用型模块，不限于编码场景"。但 Ship Pro 需要的是**可执行的架构方案**。如果 Solution Pro 过于通用，它可能不会输出 Ship Pro 需要的具体技术细节（如具体框架版本、API 接口定义、数据模型 schema）。

**缓解措施**：
- 在 solution.json 的 schema 中定义"编码场景必填字段"
- 当检测到场景是编码时，Solution Pro 的 prompt 增加技术细节要求
- Ship Pro 有权向 Solution Pro 发起"信息补充请求"（但这会增加复杂度）

**建议**：先不处理。让 Solution Pro 保持通用，但在 final_result 中通过 prompt engineering 引导它输出足够的技术细节。如果后续发现信息不足，再增加场景检测逻辑。

### 风险 2：砍掉 Blueprint 后失去"方案演化"能力

**风险描述**：living_blueprint → frozen_blueprint 的设计初衷是支持"方案演化"——用户可以在 Blueprint 上修改，然后重新执行。砍掉后，如果用户想"调整方案再执行"，没有中间态可以修改。

**缓解措施**：
- plan_summary.md 可以作为修改的锚点（用户说"把模块 2 改成 Redis"，AI 理解后修改 solution.json）
- solution.json 本身是可修改的（它是标准 JSON，可以被程序化编辑）
- 如果需要更正式的"方案版本管理"，可以在 solution.json 上加 version 字段

**建议**：这个风险是可控的。当前 Blueprint 的"方案演化"能力从未被实际使用（frozen_blueprint 信息丢失就是证据）。先简化，等真正需要时再加回来。

### 风险 3：plan_summary.md 的生成质量

**风险描述**：plan_summary.md 是用户唯一看到的中间产物。如果它的质量差（信息遗漏、表述不清、过于冗长），用户会失去对方案的判断力，导致确认了错误方案或反复修改。

**缓解措施**：
- 定义严格的模板（500 字以内，固定 5 个 section）
- 用 LLM 从 solution.json 生成，而不是手写逻辑
- 生成后做"信息完整性检查"：确保每个 module 都有对应描述

**建议**：这是最关键的质量关卡。plan_summary.md 的生成逻辑应该是 Solution Pro 的"一等公民输出"，而不是事后附加的格式化脚本。

---

## 六、总结：三个最重要的设计决策

| # | 决策 | 理由 |
|:-:|------|------|
| 1 | **砍掉 Blueprint 层，Ship Pro 直接消费 solution.json** | 消除信息损耗，减少 50% 的文件产出，简化数据流 |
| 2 | **用户只看到 plan_summary.md 一个中间产物** | Progressive Disclosure，降低认知负荷，对齐业界最佳实践 |
| 3 | **Ship Pro 从"格式搬运"升级为"真正的执行规划"** | 这是整个系统价值的核心——没有好的执行规划，执行引擎再强也没用 |

---

## 七、一句话总结

> **用户不需要看 10 个 JSON 文件。他需要一个 500 字的方案摘要，然后说"开始"。**
> 
> **DeepFlow 的架构应该围绕"一个确认点"设计，而不是"十个中间文件"。**

---

*报告完成。2026-06-18。*
