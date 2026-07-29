# MD-first JSON 技术债分析

> 用户提议：先清除 JSON 债 → 纯 MD 流转 → 再加 JSON tracking
> 分析时间：2026-07-29

---

## 当前 JSON 技术债全景

| 类别 | 数量 | 示例 | 性质 |
|------|:----:|------|------|
| **交付物 fallback** | 3 处 | frozen_spec.json, final_solution.json | ✅ 可清除 |
| **内部中间产物** | 29 种 | planning_convergence.json, expert_plans/*.json | ⚠️ 结构化数据 |
| **状态文件** | 5+ | master_state.json, pulse_state.json | ⚠️ 运行时状态 |
| **代码硬编码** | 36 处 | blackboard.py, control_contract.py | ✅ 可重构 |
| **Prompt 引用** | 120 处 | 各模块 prompt | ⚠️ 需评估 |

---

## 用户想法分析

### 思路核心

**先清除 JSON 债 → 纯 MD 流转 → 再加 JSON tracking**

**逻辑**：在干净的基础上建设，比在混乱基础上叠加更简单。

### 优点

1. 架构清晰，没有双源共存
2. 维护成本低
3. tracking 系统基础干净

### 问题：JSON 有不同的用途，不能一刀切

| 类型 | 是否适合改 MD | 理由 |
|------|:------------:|------|
| **交付物**（frozen_spec, final_solution） | ✅ 适合 | 人类可读，文档性质 |
| **内部中间产物**（expert_plans, convergence） | ❌ 不适合 | 结构化数据，Worker 间传递，需要 schema 验证 |
| **状态文件**（master_state, pulse_state） | ❌ 不适合 | 运行时状态，频繁读写，JSON 更高效 |
| **Tracking/审计** | ❌ 不适合 | 需要结构化查询，JSON 更合适 |

### 内部中间产物改 MD 的代价

29 种内部 JSON 文件，如果都改 MD：
- 需要写 29 个 render/parse 函数
- 需要更新所有 Prompt 的引用
- 需要更新所有 Schema 验证
- **收益是什么？** Worker 间传递结构化数据，MD 不如 JSON 直观

---

## 建议方案

### Phase 1: 清理"该清理的"（而不是"所有"）

| 清理项 | 动作 | 优先级 |
|--------|------|:------:|
| 交付物 JSON fallback | 删除 fallback 路径，纯 MD | P0 |
| master_state.json 双源 | 删除，统一用 .runs/*.run.json | P0 |
| 死代码（14 个函数） | 删除 | P1 |
| research_digest 未注册 | 注册到契约层 | P1 |

### Phase 2: 保留"该保留的"

| 保留项 | 理由 |
|--------|------|
| 内部中间产物（29 种 JSON） | 结构化数据，schema 验证，Worker 间传递 |
| 状态文件（pulse_state, run.json） | 运行时状态，频繁读写 |

### Phase 3: 明确 tracking 目标后再建设

先回答：
1. **tracking 的目标是什么？**（审计 / 变更追踪 / 执行追踪）
2. **tracking 的粒度是什么？**（文件级 / 字段级）
3. **tracking 的消费方是谁？**（人 / 系统 / 两者）

---

## 结论

**你的方向是对的**：先清理再建设，比在混乱基础上叠加更清晰。

**但"清除所有 JSON"需要修正**：
- ✅ 清除交付物的 JSON fallback
- ✅ 清除双源共存的状态文件
- ❌ 不清除内部中间产物（结构化数据）
- ❌ 不清除运行时状态文件

**建议的 Phase 顺序**：
1. **Phase 1**: 清理交付物 fallback + 双源状态（P0）
2. **Phase 2**: 明确 tracking 目标
3. **Phase 3**: 在干净的基础上建设 tracking 系统

---

## 待确认问题

**JSON tracking 系统的具体目标是什么？**

这决定了技术方案：
- 审计追踪 → git-style 日志
- 变更追踪 → 结构化 diff
- 执行追踪 → 结构化日志

---

*完整分析文件: `.deepflow/docs/md-first-json-debt-analysis.md`*
