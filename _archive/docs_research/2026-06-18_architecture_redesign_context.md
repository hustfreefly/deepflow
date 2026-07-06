# DeepFlow 架构重设计 — 专家团输入上下文

> **日期**: 2026-06-18
> **任务**: 重新设计 Solution Pro → Ship Pro → Super Loop 的架构数据流
> **重要性**: 🔴 最高 — 这是 DeepFlow 的核心架构决策

---

## 一、当前架构

```
Spec Pro（需求收集）
  → spec.json

Solution Pro（方案设计，10阶段管线）
  → 内部中间产物：execution_plan.json, control_contract.json, tasks.json（~100KB）
  → final_result.json（19KB, 372 个有效字段）← 最丰富的输出
  → living_blueprint.json（30KB, 329 个有效字段）← 膨胀但信息变少
  → frozen_blueprint.json（35KB, 850 个字段但大量空值）← 最大但最空

Ship Pro（编译为 Ship Package）
  输入：只读 frozen_blueprint.json
  输出：ship_package.json

Super Loop（执行代码，Phase 1 用 Hermes+Codex）
  预期输入：ship_package.json
```

---

## 二、发现的核心问题

### 问题 1：Blueprint Freezing 是信息损耗器

**实际数据对比**（跨境AI算力中转站项目）：

| 信息 | final_result | frozen_blueprint | 状态 |
|------|-------------|-----------------|------|
| 组件技术栈 | `component: "New API"` | 丢了 | ❌ |
| 部署方式 | `deployment: "Docker on Railway"` | 丢了 | ❌ |
| 许可证 | `license: "MIT"` | 丢了 | ❌ |
| 执行计划 | 3 phases, 具体 tasks + milestones | `delivery` 全是空数组 | ❌ |
| 时间线 | `mvp_timeline: "15天"` | 丢了 | ❌ |
| 模块职责 | 详细的 role 描述 | 一句话 summary | ❌ |
| module.tier | N/A | 空的 | ❌ |
| module.responsibilities | N/A | 空的 | ❌ |

### 问题 2：Ship Pro 当前是"搬运工"而非"项目经理"

Ship Pro 的"转换"逻辑（1048行代码）：
- module.name → WP.title（加了"实现"二字）
- module.summary → WP.AC[1]（原文复制）
- 模板废话：每个 WP 都有 "功能实现完成，满足设计规格"
- constraints 每个 WP 都是 "上游未提供具体约束"
- 唯一有价值的：依赖关系推导 + phase 拓扑排序

### 问题 3：Solution Pro 的 delivery section 永远是空的

看了多个 Blueprint，delivery 永远是：
```json
"delivery": {
  "phases": [],
  "milestones": [],
  "suggested_work_slices": [],
  "dependency_hints": []
}
```

但 final_result.json 里**有** implementation_plan：
```json
{
  "mvp_timeline": "15天",
  "phases": [
    {
      "phase": 1,
      "name": "核心基础设施",
      "duration": "Day 1-5",
      "tasks": ["注册域名", "部署New API到Railway", "配置PostgreSQL..."],
      "milestones": ["Day 1: 供应商+支付并行申请", "Day 5: API转发链路验证"]
    }
  ]
}
```

---

## 三、已确定的设计原则

1. **Solution Pro = 架构师**：出方案蓝图，不管怎么施工。它是通用型模块，不限于编码场景。
2. **Ship Pro = 项目经理**：把蓝图翻译成施工任务单。可以针对不同执行引擎（Hermes/Codex/Claude Code）适配不同格式。
3. **Super Loop = 施工队**：消费 Ship Package，执行代码。

### 用户（忠礼）的核心观点

> "Solution Pro 是通用型的，它不一定是适用于编码，所以我们还是需要 Ship Pro 来做适配转换。Ship Pro 是一个中间层、通用接口的角色。"

---

## 四、待决策的核心问题

### Q1: Blueprint 层是否保留？

**选项 A**: 保留 frozen_blueprint，但修复信息丢失问题
**选项 B**: 砍掉 frozen_blueprint，Ship Pro 直接消费 final_result
**选项 C**: 重新设计 Blueprint 格式，使其包含完整信息

### Q2: Solution Pro 应该输出什么？

当前输出：final_result + living_blueprint + frozen_blueprint
应该输出什么？哪些信息是"方案设计"的边界？

### Q3: Ship Pro 应该做什么？

当前：格式转换（module → WP），质量差
应该：真正的"执行规划"——工时、步骤、验收标准、技术约束、集成检查点

### Q4: 三个模块的数据流最优设计是什么？

---

## 五、当前 Blackboard 文件清单（完整的一次运行）

```
blackboard/跨境AI算力中转站平台_architecture_e215c1bb/
├── frozen_blueprint.json      (44.5KB) — Ship Pro 的输入
├── living_blueprint.json      (36.8KB) — Blueprint 的"活"版本
├── final_result.json          (21.4KB) — Solution Pro 原始输出（最丰富）
├── requirements_traceability_matrix.json (16.4KB) — 需求追溯
├── control_contract.json      (15.3KB) — Solution Pro 内部执行契约
├── ship_package.json          (17.5KB) — Ship Pro 输出
├── ship_review_data.json      (19.1KB) — Ship Pro 审查数据
├── domain_config.json         (13.0KB) — Ship Pro 领域配置
├── execution_plan.json        (3.6KB) — Solution Pro 执行计划
└── tasks.json                 (166.1KB) — Solution Pro 内部任务数据
```

---

## 六、业界参考方向（请搜索最新信息）

- **Manus Agent** 的 Plan-driven 执行模式
- **Hermes Agent** 的 Iteration Budget + 显式 plan 文件
- **Claude Code** 的 Agent Harness 模式
- **Devin / Factory.ai / Cursor** 的编排模式
- **Software Engineering** 中 Blueprint → Implementation 的标准流程
- **Architecture Decision Records (ADR)** 的最佳实践
- **DDD（领域驱动设计）** 中 Bounded Context 的拆分原则

---

## 七、输出要求

1. 对 4 个核心问题给出明确建议（不是模糊的"都可以"）
2. 给出推荐的架构数据流图
3. 列出你认为最重要的 3 个设计决策及其理由
4. 指出当前方案中你看到的最大风险
