# Spec Pro 机制设计文档

> 本文档从 orchestrator.md 分离，供人类阅读和团队对齐。Orchestrator 运行时不需要这些解释性内容。

---

## v2.2 新增机制 (2026-05-31)

### 已问去重规则 (D1)

QuestionWorker 生成问题时，必须读取：
- `spec/conversation_log.json` — 检查历史 meta_directives
- `stages/round_XX_questions.json` — 检查上轮已问问题
- `stages/round_XX_response.json` — 检查用户回答和 meta_signals

**规则**：
- 用户明确说"不要再问 X"的维度 → 禁止提问
- 已问过且用户已回答的问题 → 不再重复
- `deliberately_omitted` 标记的维度 → 跳过

### 评分区分拒绝 (D2)

如果用户在某维度明确表达"不需要/不考虑"：
- ResponseWorker 提取 `deliberately_omitted` 字段到 `parsed_updates.user_directives`
- merge_spec 将其合并到 `living_spec.confirmed.user_directives`
- AssessWorker 评分时：该维度给默认分 50（不扣分），不出现在 top_missing 中

### 7 维分数展示 (D3)

round_result.json 的 `quality` 字段现在包含完整的 7 维度分数：
```json
{
  "quality": {
    "overall_score": 52,
    "level": "C",
    "dimension_scores": {
      "objective": {"score": 55, "delta": 15, "change": "up"},
      "users": {"score": 50, "delta": 0, "change": "flat"}
    },
    "top_improvements": [{"dimension": "integration", "delta": 50, "reason": "..."}],
    "top_missing": ["缺少 timeline", "未识别风险"]
  }
}
```

主 Agent 应将此格式化为表格展示给用户。

### 停滞检测 (D5)

如果满足以下**所有**条件，不再问问题，直接输出 Spec 草稿让用户确认：
1. `round_num >= 3`
2. 最近 2 轮 `delta` 绝对值都 < 3（质量停滞）
3. `overall_score >= 50`（至少有基础信息）

此时输出 `action: "proposal"`（不是 "questions"），包含 `stagnation_reason` 字段。

### 动态阈值 (D6)

质量阈值不再是固定值，而是动态计算：
- 基础阈值来自 MODE_CONFIG（standard: 75）
- 连续 2 轮 delta < 3 → 降 10 分（75 → 65）
- 连续 3 轮 delta < 3 → 降 15 分（75 → 60）
- 最低不低于 50 分

避免"用户不配合某维度 → 分数永远上不去 → 系统永远不结束"的死循环。

---

## Writer Protocol 设计说明

**为什么只有 Orchestrator 可以写 `spec/living_spec.json`**：

Living Spec 是多个 Worker 的合并产物。如果每个 Worker 都直接写，会出现：
- 并发写入导致数据丢失
- 合并逻辑散落在多个 Worker 中，难以维护
- 无法保证 confirmed/inferred/guardrails 三层的一致性

因此设计了 Writer Protocol：Worker 只写各自的增量文件（如 `stages/round_NN_response.json`），由 Orchestrator 通过 `merge_spec.py` 统一合并。

合并脚本自动处理：
- confirmed 层：追加新项，不删除已有项
- inferred 层：status=confirmed → 移入 confirmed；status=rejected → 标记 rejected；新增推断 → 追加
- guardrails：追加新项
- 矛盾处理：保留两者并标注 contradiction

---

## API 降级策略 — 为什么不能自行模拟

当 `spec_pro_api.py` 不存在时，Orchestrator 必须报错停止，不能自行模拟 API 行为。原因：

1. **质量不可控**：自行模拟跳过了 Worker 化流程，输出质量无法保证
2. **无可追溯日志**：模拟不会产生 Blackboard 文件，后续 Worker 无法工作
3. **违反设计原则**：Spec Pro 的核心架构是 Worker 化 + Blackboard 协作，自行模拟等于绕过了整个架构

---

*从 orchestrator.md v2.0.0 分离 | 2026-07-07*
