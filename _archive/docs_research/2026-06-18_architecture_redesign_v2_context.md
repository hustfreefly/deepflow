# DeepFlow 架构重设计 V2 — 第二轮专家评审输入

> **日期**: 2026-06-18
> **背景**: 第一轮 6 专家评审后，基于全量 8 个案例分析，形成了修正后的架构方案。本轮评审聚焦验证修正方案。

---

## 一、第一轮评审结论（6 专家共识）

1. ❌ frozen_blueprint 必须淘汰（信息保真度仅 32%）
2. ❌ living_blueprint 没有价值
3. ✅ Ship Pro 从"格式转换器"升级为"执行规划器"
4. ✅ final_result.json 是最丰富输出，作为 SSOT
5. ⚠️ "通用型"定位是最大风险

---

## 二、全量案例分析新发现

### 2.1 final_result.json 存在 5 种不同结构

| 案例 | 架构信息位置 | 实施计划 | 需求信息 |
|------|-------------|---------|---------|
| 跨境算力中转站 | `architecture.core_components` | ✅ `implementation_plan`（3 phases, 具体 tasks） | 无（在 RTM 里） |
| 智能简历系统 | `final_solution.detailed_solution.architecture.components` | ❌ 无 | `covered_req_ids` |
| 智能客服系统 | `architecture.components` | ✅ `implementation_plan` | `requirements.items` |
| 电商订单系统 | `architecture`（16 个技术组件字段） | ❌ 无 | `req_coverage` |
| Serenity Skills | `final_solution.detailed_solution.architecture.components` | ❌ 无 | `covered_req_ids` |

**关键发现**：
- **implementation_plan 只有 2/8 案例有**，不是必填字段
- **组件信息质量很高**（如简历系统的"三层匹配：关键词35%+语义45%+行业术语20%"）
- **技术栈信息散落在不同字段名中**（component/deployment/architecture 等）

### 2.2 Blackboard 文件价值审计

| 文件 | 跨案例稳定性 | 信息类型 | Ship Pro 需要？ |
|------|-------------|---------|:-:|
| **final_result.json** | ⚠️ 格式不统一 | 方案核心内容 | ✅ 必须 |
| **requirements_traceability_matrix.json** | ✅ 稳定 | 需求覆盖 + 验收证据链 | ✅ 必须 |
| **execution_plan.json** | ✅ 稳定 | 项目元数据（topic/constraints/stakeholders） | ✅ 应该读 |
| tasks.json | ✅ 稳定 | 10 阶段 prompt 文本（~120KB） | ❌ 不需要 |
| control_contract.json | ✅ 稳定 | Solution Pro 内部执行契约 | ❌ 不需要 |
| frozen_blueprint.json | ✅ 稳定 | 有损压缩（32% 保真度） | ❌ 不需要 |
| living_blueprint.json | ⚠️ 不稳定 | 另一视角的方案内容 | ⚠️ 可选（有 design_decisions） |
| ship_review_data.json | — | Ship Pro 自己的中间产物 | ❌ 不需要 |
| domain_config.json | — | Ship Pro 自己的中间产物 | ❌ 不需要 |

### 2.3 living_blueprint.json 的独有价值

虽然结构不稳定，但 living_blueprint 有一个 final_result 没有的字段：

```json
"design_decisions": {
  "tradeoffs": [...],
  "rejected_alternatives": [...],
  "reviewer_feedback": [...]
}
```

这个信息对 Ship Pro 理解"为什么这样设计"有价值。但结构不稳定，需要 LLM 解析。

---

## 三、修正后的架构方案（待评审）

### 3.1 数据流

```
Solution Pro
  输出到 blackboard/:
    ├── final_result.json          ← Ship Pro 读（主输入）
    ├── requirements_traceability_matrix.json ← Ship Pro 读（需求+验收证据）
    └── execution_plan.json        ← Ship Pro 读（元数据）
  
  输出到 blackboard/.internal/:
    ├── tasks.json                 ← 调试用
    └── control_contract.json      ← 调试用

Ship Pro（LLM 解析 + 补充，不是确定性编译器）
  读：final_result + RTM + execution_plan（~33KB）
  做：提取架构 → 拆 WP → 补工时/AC/依赖/集成检查点
  输出：ship_package.json

Super Loop（Hermes+Codex / 自建引擎）
  读：ship_package.json
  做：执行编码
```

### 3.2 Ship Pro 核心职责变更

| 维度 | 当前（V2） | 修正后 |
|------|-----------|--------|
| **实现方式** | 确定性编译器（Python） | LLM 引导编译器（LLM 解析 + 确定性组装） |
| **输入** | 只读 frozen_blueprint | 读 final_result + RTM + execution_plan |
| **核心工作** | module → WP（1:1 映射） | 提取 → 理解 → 拆分 → 补充 → 组装 |
| **新增能力** | 无 | 工时估算、具体 AC 生成、技术约束提取、集成检查点 |

### 3.3 Solution Pro 小改

不改输出格式（格式多样性是正常的），但：
1. 在 summarizer prompt 加 `_ship_pro_hints` 字段约定，指向关键数据位置
2. 确保 implementation_plan 在可能的情况下填充

### 3.4 砍掉的文件/步骤

- ❌ frozen_blueprint.json — 停止生成（blueprint freezing 步骤砍掉）
- ❌ living_blueprint.json — 停止生成
- ❌ ship_review_data.json — 停止持久化
- ❌ domain_config.json — 停止持久化
- ⚠️ tasks.json / control_contract.json — 移到 .internal/

### 3.5 Ship Package 输出目标格式

每个 WP 应该是：

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
      "criterion": "支持至少3家AI供应商的API接入",
      "verification": "集成测试：对每个供应商发送相同请求，验证响应格式一致",
      "priority": "P0"
    }
  ],
  "technical_constraints": [
    "使用 New API（MIT License），Docker 部署在 Railway（新加坡节点）",
    "故障切换时间 < 3 秒"
  ],
  "deliverables": [
    "src/gateway/router.ts",
    "tests/integration/gateway.test.ts"
  ],
  "integration_checkpoints": [
    { "after": "WP-003", "check": "API网关 + 支付系统集成验证" }
  ]
}
```

---

## 四、待评审的核心问题

### Q1: Ship Pro 用 LLM 还是确定性编译器？
修正方案用 LLM 解析不统一的 final_result 格式。这是否靠谱？是否需要额外的校验层？

### Q2: Ship Pro 应该读 3 个文件（final_result + RTM + execution_plan）还是更多？
living_blueprint 的 design_decisions 是否有必要读？

### Q3: `_ship_pro_hints` 约定是否可行？
让 Solution Pro 输出一个"导航字段"，指向关键数据位置。这是否增加了 Solution Pro 的脆弱性？

### Q4: 砍掉 blueprint freezing 步骤后，下游（Super Loop）的格式稳定性如何保证？

### Q5: 从确定性编译器（当前 1048 行 Python）切换到 LLM 引导编译器，代码量和维护成本的变化？

---

## 五、输出要求

1. 对 Q1-Q5 给出明确建议
2. 指出修正方案中的盲点或风险
3. 如果你认为有更好的方案，请提出
4. 给出"实施信心评分"（1-10）
