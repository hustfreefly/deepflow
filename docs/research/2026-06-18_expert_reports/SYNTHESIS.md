# DeepFlow 架构重设计 — 6 专家综合决策报告

> **日期**: 2026-06-18
> **参与专家**: 系统架构师 / AI Agent 编排 / SE 方法论 / 产品经理 / 简约主义 / 信息架构师
> **总报告量**: ~160KB（2646 行分析）

---

## 一、6 位专家对 Q1-Q4 的投票汇总

### Q1: Blueprint 层是否保留？

| 选项 | 票数 | 投票者 |
|------|------|--------|
| **A: 保留 frozen_blueprint，修复信息丢失** | 0 | — |
| **B: 砍掉 frozen_blueprint** | **4** | Agent编排 / SE方法论 / 产品经理 / 简约主义 |
| **C: 重新设计 Blueprint 格式** | **2** | 系统架构师 / 信息架构师 |

**共识**：❌ **没有人选 A**。frozen_blueprint 作为信息损耗器，必须淘汰。
**分歧**：B（砍掉直连）vs C（重设计）。分歧本质是——是否需要一个"正式输出契约"。

### Q2: Solution Pro 应该输出什么？

| 专家 | 建议 |
|------|------|
| 系统架构师 | 2 个文件：final_result（内部）+ design_blueprint（外部 Published Language） |
| Agent 编排 | 1 个文件：solution.json（final_result 改名） |
| SE 方法论 | Architecture Description Package（C4 Model 多层视图） |
| 产品经理 | solution.json + plan_summary.md（人类可读摘要） |
| 简约主义 | 1 个文件：plan.json |
| 信息架构师 | solution_core.json（SSOT）+ solution_blueprint.json（视图） |

**共识**：✅ **至少一个核心 JSON 文件作为 SSOT**（Single Source of Truth）。
**分歧**：是否需要额外的"视图"文件（plan_summary.md / blueprint 视图）。

### Q3: Ship Pro 应该做什么？

| 专家 | 核心观点 |
|------|---------|
| 系统架构师 | 升级为"执行规划引擎"：任务分解 + 工时估算 + 集成检查点 |
| Agent 编排 | 升级为"执行规划器"，借鉴 Factory.ai Coordinator-Droid 模式 |
| SE 方法论 | 升级为"设计细化器"：做 Design → Implementation Plan 的细化 |
| 产品经理 | 真正的"项目经理"：任务分解、依赖排序、具体验收标准 |
| 简约主义 | **砍掉独立模块**，合并到 Architect 里（30 行代码搞定依赖排序） |
| 信息架构师 | 升级为"施工规划器"（前提是给它足够的信息输入） |

**共识**：✅ **5/6 认为 Ship Pro 需要升级为"执行规划器"**，而不是格式转换器。
**异议**：简约主义认为只有 1 个执行引擎时不需要独立模块。

### Q4: 最优数据流

| 专家 | 推荐层数 | 数据流 |
|------|---------|--------|
| 系统架构师 | 3 层 + 2 ACL | Spec → Blueprint(Published Language) → Ship Package |
| Agent 编排 | 3 文件 | requirements → solution → ship_package |
| SE 方法论 | 3 层 | Architecture Description → Design Package → Execution Package |
| 产品经理 | 3 文件 | requirements → solution → ship_package（用户只看 plan_summary.md） |
| 简约主义 | **2 文件** | spec → plan（合并 Solution+Ship 为 Architect） |
| 信息架构师 | 3 层 + SSOT | Spec → Solution Core + Blueprint View → Execution Package |

**共识**：✅ **大多数推荐 3 层**（Spec → Solution → Ship），简约主义推荐 2 层。

---

## 二、6 位专家的一致结论（100% 共识）

以下 6 点，**所有专家完全一致**：

1. **❌ frozen_blueprint 必须淘汰** — 信息保真度仅 32%，是系统最大的信息损耗器
2. **❌ living_blueprint 没有价值** — 从未被外部消费，膨胀且信息少于 final_result
3. **✅ Ship Pro 当前是"搬运工"** — 必须升级为"执行规划器"或合并到上游
4. **✅ final_result.json 是当前最丰富的输出** — 应该作为 SSOT 的基础
5. **✅ Solution Pro 的 delivery section 永远是空的** — 这是下游信息饥饿的根因
6. **⚠️ "通用型"定位是最大风险** — Solution Pro 如果要同时服务编码和非编码场景，输出会变成"最大公约数"

---

## 三、关键分歧点及建议

### 分歧 1：是否需要独立的 Blueprint 层？

| 立场 | 支持者 | 理由 |
|------|--------|------|
| **需要**（重设计为 Published Language） | 系统架构师、信息架构师 | DDD Anti-Corruption Layer、Contract-First Design |
| **不需要**（直连 final_result） | Agent 编排、SE 方法论、产品经理、简约主义 | 信息损耗、多余中间层、Manus/Hermes 都是单文件 |

**我的建议**：采纳多数意见，**砍掉独立 Blueprint 层**。理由：
- 我们不是在做微服务，不需要 Anti-Corruption Layer
- Solution Pro 和 Ship Pro 是同一个系统内的上下游，不是独立团队
- 4/6 专家认为直连更优

### 分歧 2：Ship Pro 是独立模块还是合并？

| 立场 | 支持者 | 理由 |
|------|--------|------|
| **独立模块**（升级职责） | 5/6 专家 | 忠礼明确说需要中间层适配 |
| **合并到 Architect** | 简约主义 | Rule of Three：只有 1 个执行引擎不值得抽象 |

**我的建议**：**保持 Ship Pro 独立模块**，但大幅升级职责。理由：
- 忠礼明确表达了"Solution Pro 是通用型，Ship Pro 是适配层"的定位
- 未来可能有多个执行引擎（Hermes/Codex/Claude Code）
- 但简约主义的风险值得记住：当有第 2 个执行引擎时再抽象

---

## 四、推荐架构方案

基于 6 位专家的共识和分歧，推荐以下方案：

### 数据流（3 文件管线）

```
用户想法
  ↓
Spec Pro → requirements.json
  ↓
Solution Pro → solution.json + plan_summary.md
  ↓                    （SSOT，替代 final_result + 所有 Blueprint）
Ship Pro → ship_package.json
  ↓                    （执行规划器，不是格式转换器）
Super Loop（Hermes+Codex）→ 代码
```

### 各模块职责

| 模块 | 角色 | 输入 | 输出 | 核心职责 |
|------|------|------|------|---------|
| **Spec Pro** | 需求分析师 | 用户对话 | requirements.json | 结构化需求 |
| **Solution Pro** | 架构师 | requirements.json | solution.json + plan_summary.md | 方案蓝图（架构+技术+约束+交付计划） |
| **Ship Pro** | 项目经理 | solution.json | ship_package.json | 执行规划（WP分解+工时+AC+依赖+集成检查点） |
| **Super Loop** | 施工队 | ship_package.json | 可运行代码 | 编排+编码+验证 |

### Solution Pro 输出（solution.json）必须包含

```json
{
  "meta": {},
  "intent": { "problem", "objective", "success_criteria" },
  "requirements": { "items": [...] },
  "architecture": {
    "modules": [{
      "id", "name", "summary",
      "tier": "T1/T2/T3",           // ← 当前为空，必须填
      "responsibilities": [...],     // ← 当前为空，必须填
      "interfaces": [...],           // ← 新增：模块间接口
      "technology": {                // ← 新增：从 final_result 搬过来
        "component": "New API",
        "deployment": "Docker on Railway",
        "license": "MIT"
      }
    }],
    "data_flows": [...],
    "technology_choices": [...],
    "decisions": [...]              // ← ADR 格式
  },
  "contracts": {                    // ← 当前全空，必须填
    "api": [...],
    "data": [...],
    "runtime": [...]
  },
  "delivery": {                     // ← 当前全空，必须填
    "phases": [...],
    "dependency_graph": [...],
    "milestones": [...],
    "timeline": "..."
  },
  "risks": { "register": [...], "forbidden_changes": [...] },
  "readiness": { "status": "PASS/FAIL", "blocking_issues": [] }
}
```

### Ship Pro 输出（ship_package.json）应该是

每个 WP 不再是模板废话，而是：

```json
{
  "id": "WP-001",
  "title": "API网关层 - 多供应商聚合与智能路由",
  "phase": 1,
  "estimated_hours": 40,
  "dependencies": [],
  "acceptance_criteria": [
    {
      "id": "AC-001",
      "criterion": "支持至少3家AI供应商的API接入（DeepSeek/Qwen/Zhipu）",
      "verification": "集成测试：对每个供应商发送相同请求，验证响应格式一致",
      "priority": "P0"
    }
  ],
  "technical_constraints": [
    "使用 New API（MIT License），Docker 部署在 Railway（新加坡节点）",
    "故障切换时间 < 3 秒，用户无感知"
  ],
  "deliverables": [
    "src/gateway/router.ts — 智能路由引擎",
    "src/gateway/providers/ — 供应商适配器",
    "tests/integration/gateway.test.ts — 集成测试"
  ],
  "integration_checkpoints": [
    { "after": "WP-003", "check": "API网关 + 支付系统集成验证" }
  ]
}
```

### 砍掉的文件

| 文件 | 原因 |
|------|------|
| `frozen_blueprint.json` | 信息保真度 32%，信息损耗器 |
| `living_blueprint.json` | 从未被消费，膨胀冗余 |
| `ship_review_data.json` | Ship Pro 内部产物，不需要持久化 |
| `domain_config.json` | Ship Pro 内部产物 |
| `control_contract.json` | Solution Pro 内部产物 |

### 保留的内部文件（.internal/ 目录）

| 文件 | 原因 |
|------|------|
| `execution_plan.json` | Solution Pro 执行计划（调试用） |
| `tasks.json` | Solution Pro 任务数据（调试用） |
| `requirements_traceability_matrix.json` | 需求追溯（审计用） |

---

## 五、最大风险（6 位专家共识）

| 风险 | 严重度 | 缓解策略 |
|------|--------|---------|
| **Solution Pro 的"通用型"定位导致输出边界模糊** | 🔴 | 先只服务编码场景验证数据流，再扩展到其他场景 |
| **Solution Pro 的 delivery/contracts 仍然填不满** | 🔴 | 修改 prompts，增加强制输出约束；用真实项目验证 |
| **Ship Pro 升级后质量不达标** | 🟡 | 用 3 个真实项目做端到端验证 |
| **砍掉 Blueprint 后下游格式不稳定** | 🟡 | solution.json 用 JSON Schema 严格校验 |

---

## 六、实施路线建议

### Phase 1: 最小可行验证（1 周）

1. 修改 Solution Pro 的 prompts，强制填充 delivery + contracts + module.tier/responsibilities
2. 用 1 个真实项目运行，验证 solution.json 信息完整性
3. 手写一个 Ship Pro 的 LLM prompt（不用代码），消费 solution.json → 输出高质量 ship_package.json
4. 验证 Super Loop 能否消费 ship_package.json 执行编码

### Phase 2: 代码实现（2 周）

1. 定义 solution.json 的 JSON Schema
2. 重写 Ship Pro 的 ship_compiler.py（从确定性编译器 → LLM 引导编译器）
3. 砍掉 Blueprint freezing 步骤
4. 端到端验证 3 个项目

### Phase 3: 生产化（持续）

1. 建立 solution.json 的信息完整性校验（CI 级别）
2. Ship Pro 针对不同执行引擎适配（Hermes/Codex/Claude Code）
3. 积累执行数据，为方案 B 自建引擎做准备

---

*综合报告完毕。6 份专家原始报告存档于同目录。*
