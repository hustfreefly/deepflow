# STEP 3: Worker Agent 调度

## 任务目标
在 STEP 1（数据采集）和 STEP 2（统一搜索）完成后，按 `domains/investment.yaml` 配置顺序 spawn Worker Agent。

---

## 前置条件检查

**只有在以下验证通过后，才能开始 spawn Worker：**

- [ ] `blackboard/{session_id}/data/INDEX.json` 存在
- [ ] `blackboard/{session_id}/data/05_supplement/` 至少 3 个文件
- [ ] 数据采集验证通过

---

## Worker Agent 映射表

| Stage | 角色 | Prompt 文件 | Label |
|-------|------|------------|-------|
| planner | 规划师 | `prompts/investment/workers/planner.md` | `"planner"` |
| researcher_finance | 财务研究 | `prompts/investment/workers/researcher_finance.md` | `"researcher_finance"` |
| researcher_tech | 技术研究 | `prompts/investment/workers/researcher_tech.md` | `"researcher_tech"` |
| researcher_market | 市场研究 | `prompts/investment/workers/researcher_market.md` | `"researcher_market"` |
| researcher_macro_chain | 宏观/政策/产业链 | `prompts/investment/workers/researcher_macro_chain.md` | `"researcher_macro_chain"` |
| researcher_management | 管理层/治理 | `prompts/investment/workers/researcher_management.md` | `"researcher_management"` |
| researcher_sentiment | 舆情/事件驱动 | `prompts/investment/workers/researcher_sentiment.md` | `"researcher_sentiment"` |
| financial | 财务分析 | `prompts/investment/workers/financial.md` | `"financial"` |
| market | 市场分析 | `prompts/investment/workers/market.md` | `"market"` |
| risk | 风险评估 | `prompts/investment/workers/risk.md` | `"risk"` |
| auditor_factual | 事实审计 | `prompts/investment/workers/auditor_factual.md` | `"auditor_factual"` |
| auditor_upside | 上行风险审计 | `prompts/investment/workers/auditor_upside.md` | `"auditor_upside"` |
| auditor_downside | 下行风险审计 | `prompts/investment/workers/auditor_downside.md` | `"auditor_downside"` |
| fixer | 修复师 | `prompts/investment/workers/fixer.md` | `"fixer"` |
| verifier | 验证师 | `prompts/investment/workers/verifier.md` | `"verifier"` |
| summarizer | 汇总师 | `prompts/investment/workers/summarizer.md` | `"summarizer"` |

---

## 关键执行规则

### 1. Researcher 必须 6 个并行
```python
# ✅ 正确：6 个 researcher 并行
sessions_spawn(label="researcher_finance", ...)
sessions_spawn(label="researcher_tech", ...)
sessions_spawn(label="researcher_market", ...)
sessions_spawn(label="researcher_macro_chain", ...)
sessions_spawn(label="researcher_management", ...)
sessions_spawn(label="researcher_sentiment", ...)

# ❌ 错误：只跑 1 个
sessions_spawn(label="researcher_finance", ...)
```

### 2. Auditor 必须 3 个并行
```python
# ✅ 正确：3 个 auditor 并行
sessions_spawn(label="auditor_factual", ...)
sessions_spawn(label="auditor_upside", ...)
sessions_spawn(label="auditor_downside", ...)

# ❌ 错误：只跑 1 个或串行
```

### 3. Fixer 必须基于审计意见
传入 auditor 的输出作为 fixer 的输入：
```python
auditor_outputs = [...]  # 3 个 auditor 的输出
fixer_task = f"""
基于以下审计意见修正预测：
{json.dumps(auditor_outputs, ensure_ascii=False)}
"""
sessions_spawn(label="fixer", task=fixer_task, ...)
```

### 4. Verifier 必须验证 Fixer 的结果
不得跳过 verifier 阶段。

### 5. 收敛检测必须跑够 2 轮
- target_score: 0.92
- 连续 2 轮提升 < 0.02 才收敛
- 禁止单轮即收敛（除非分数 ≥ 0.95 且所有 P0/P1 已修复）

### 6. Summarizer 必须最后执行
收敛后才能执行 summarizer 汇总最终报告。

---

## 完整管线流程

```
1. planner → 制定研究计划
2. researcher × 6 并行 → 4 大维度 + 2 小维度
   - research_finance: 财务研究（大维度，深度）
   - research_tech: 技术研究（大维度，深度）
   - research_market: 市场研究（大维度，深度）
   - research_macro_chain: 宏观/政策/产业链（大维度，深度）
   - research_management: 管理层/治理（小维度，轻量）
   - research_sentiment: 舆情/事件驱动（小维度，轻量）
3. financial → 财务分析与预测
4. market → 市场分析
5. risk → 风险评估
6. auditor × 3 并行审计 → 挑战前面所有结论
   - auditor_1: 财务合规审计
   - auditor_2: 风险逻辑审计
   - auditor_3: 市场数据审计
7. fixer → 根据审计意见修正预测
8. verifier → 验证修正后的结果
9. 收敛检测 → 达标？
   ├── 是 → summarizer 汇总
   └── 否 → 回到步骤 2（researcher）
10. summarizer → 汇总最终报告
```

---

## 每个 Worker Agent 的 Task 必须包含

- 角色定义 + 任务目标
- 股票代码和公司名称
- 当前股价（如有）
- **数据请求指引**：告知 Worker 可以从 Blackboard/data/ 读取数据
- 如需补充数据，写入 `blackboard/{session_id}/data_requests.json`

---

## ❌ 禁止行为

| 禁止 | 原因 | 正确做法 |
|------|------|----------|
| 跳过数据采集直接 spawn Worker | 缺少基础数据 | 先完成 STEP 1 + STEP 2 |
| researcher 只跑 1 个 | 覆盖不全 | 必须 6 个并行 |
| auditor 只跑 1 个 | 审计视角单一 | 必须 3 个并行 |
| fixer 不传 auditor 输出 | 无法针对性修复 | 传入 auditor 输出 |
| 跳过 verifier | 无法验证修复效果 | 必须执行 verifier |
| 单轮即收敛 | 未充分迭代 | 至少 2 轮 |
| 未收敛就执行 summarizer | 结果不可靠 | 收敛后才汇总 |
