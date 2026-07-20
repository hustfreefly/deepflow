---
id: solution/REQ_DEDUP_DESIGN
version: 2.0.0
description: REQ 语义去重规则设计，消除 Consolidator 输出中的语义重复需求
author: DeepFlow Team
created: 2026-06-18
updated: 2026-06-21
tags: [solution, prompt, dedup, requirements, design]
---

# REQ 语义去重规则设计

> **目标**：消除 Consolidator 输出中 ~30% 的语义重复 REQ，将 71 条 → ~45 条  
> **约束**：不新增字段、不改变输出 schema、不新增独立阶段  
> **状态**：设计稿 v1.0 | 2026-06-20

---

## 1. 问题分析

### 1.1 根因

当前 consolidator.md 的"方案整合"步骤中有一句：

> 消除重复内容

这条指令对**正文段落**有效，但对 `requirement_evidence[]` **无效**，原因：

1. **无 REQ 感知**：Consolidator 不知道每条 evidence 对应哪个 REQ-ID，无法判断两条 evidence 是否描述同一需求
2. **措辞差异**：不同阶段的 LLM 对同一需求用了不同表述（如"月固定$6-26" vs "预算<$50/月" vs "预算$3000以内"），简单文本去重无法捕获
3. **无聚合指令**：prompt 没有明确要求 Consolidator 对 `requirement_evidence[]` 做语义聚类

### 1.2 实际重复模式（v31_real_case 数据）

| 语义簇 | REQ-IDs | 条数 | 典型措辞差异 |
|:---|:---|:---:|:---|
| 预算约束 | 011, 013, 016, 030, 049, 068 | 6 | "首月<$50" / "月固定$6-26" / "预算$3000以内" |
| 供应商+通道 | 002, 012, 021, 045, 052 | 5 | "3家供应商" / "每家2-3通道" / "并行申请" |
| 自动化运维 | 005, 014, 017, 046, 070 | 5 | "每周<2h" / "全自动化" / "消除手动充值" |
| 支付降级 | 004, 022, 057 | 3 | "Paddle MoR" / "Stripe降级" / "Payment Links" |
| CDN/部署 | 024, 055, 061, 065 | 4 | "Cloudflare CDN" / "免ICP" / "全球边缘节点" |
| SLA 高可用 | 015, 037, 056, 066 | 4 | "99.9%" / "故障切换<3s" / "熔断器" |
| 技术栈友好 | 018, 047, 067 | 3 | "Vibe Coding友好" / "Go+React+PG" |
| 开源成熟 | 008, 043, 071 | 3 | "全部开源" / "MIT协议" / "成熟方案" |
| 15天MVP | 019, 041, 069 | 3 | "分3阶段" / "双重优化" / "buffer" |
| 社区文档 | 020, 042, 054 | 3 | "文档完善" / "社区活跃" / "AI训练数据" |

**结论**：重复不是精确文本重复，而是**同一需求的不同侧面/措辞**。需要语义级聚类。

---

## 2. 推荐方案：在"方案整合"步骤嵌入 REQ 去重子规则

### 2.1 设计决策

| 决策点 | 选择 | 理由 |
|:---|:---|:---|
| 去重放在哪？ | "方案整合"步骤的子规则 | 不新增阶段，避免 prompt 容量竞争 |
| 判断标准 | 同一需求的不同措辞/侧面 = 合并 | 简单可执行，不需要 LLM 做复杂推理 |
| 保留哪条？ | 信息最完整的那条 | 不丢失信息 |
| REQ-ID 处理 | `requirement_evidence[]` 保留最低 ID；`covered_req_ids[]` 保留全部原始 ID | 不改变 schema，下游可追溯 |
| 相似但不同侧重点？ | 保留独立条目 | 避免过度合并（如"首月<$50"和"月固定$6-26"是同一约束的不同表述→合并；但"预算约束"和"支付降级"是不同需求→不合并） |

### 2.2 Prompt 修改（嵌入 consolidator.md）

**修改位置**：在"3. 方案整合"下新增子项，替换原来的"消除重复内容"。

**原文**：
```markdown
3. **方案整合**
   - 合并各研究的建议
   - 消除重复内容
   - 确保逻辑连贯
```

**改为**：
```markdown
3. **方案整合**
   - 合并各研究的建议
   - 确保逻辑连贯
   - **REQ 语义去重**：对 `requirement_evidence[]` 执行语义聚类：
     - 判断标准：两条 evidence 是否在描述同一个需求约束（忽略措辞差异、侧重点互补视为同一需求）
     - 合并规则：同一语义簇只保留信息最完整的一条 evidence，使用最低 REQ-ID
     - `covered_req_ids[]` 保留全部原始 ID（不丢弃）
     - 不同需求即使措辞相似也不合并（如"预算约束"≠"支付降级"）
```

### 2.3 完整 Prompt 片段（可直接复制）

```markdown
   - **REQ 语义去重**：对 `requirement_evidence[]` 执行语义聚类：
     - 判断标准：两条 evidence 是否在描述同一个需求约束（忽略措辞差异、侧重点互补视为同一需求）
     - 合并规则：同一语义簇只保留信息最完整的一条 evidence，使用最低 REQ-ID
     - `covered_req_ids[]` 保留全部原始 ID（不丢弃）
     - 不同需求即使措辞相似也不合并（如"预算约束"≠"支付降级"）
```

---

## 3. 预期效果

### 3.1 数量变化

| 语义簇 | 原始条数 | 去重后 | 保留 REQ-ID | 合并掉的 IDs |
|:---|:---:|:---:|:---|:---|
| 预算约束 | 6 | 1 | REQ-011 | 013, 016, 030, 049, 068 |
| 供应商+通道 | 5 | 1 | REQ-002 | 012, 021, 045, 052 |
| 自动化运维 | 5 | 1 | REQ-005 | 014, 017, 046, 070 |
| 支付降级 | 3 | 1 | REQ-004 | 022, 057 |
| CDN/部署 | 4 | 1 | REQ-024 | 055, 061, 065 |
| SLA 高可用 | 4 | 1 | REQ-015 | 037, 056, 066 |
| 技术栈友好 | 3 | 1 | REQ-018 | 047, 067 |
| 开源成熟 | 3 | 1 | REQ-008 | 043, 071 |
| 15天MVP | 3 | 1 | REQ-019 | 041, 069 |
| 社区文档 | 3 | 1 | REQ-020 | 042, 054 |
| **合计** | **39** | **10** | — | 29 条消除 |
| 非重复条目 | 32 | 32 | — | — |
| **总计** | **71** | **42** | — | — |

### 3.2 对下游 Ship Pro Architect 的影响

| 维度 | 去重前 | 去重后 | 影响 |
|:---|:---|:---|:---|
| `requirement_evidence[]` 长度 | 71 | ~42 | ✅ Architect 读取更快，信噪比提升 |
| `covered_req_ids[]` 长度 | 71 | 71（不变） | ✅ 追溯性完整，不丢失任何 REQ-ID |
| 证据质量 | 同一需求多条碎片 | 一条完整描述 | ✅ Architect 获得更完整的上下文 |
| REQ-ID 稳定性 | — | 保留最低 ID | ✅ 与 frozen_spec.json 的映射不断裂 |

### 3.3 边界情况处理

| 场景 | 处理方式 | 示例 |
|:---|:---|:---|
| 两条 REQ 相似但侧重点不同 | **保留独立** | "首月<$50 启动成本" vs "月固定$6-26 运营成本" → 合并（同一预算约束的不同表述）；但"预算约束" vs "支付降级方案" → 不合并（不同需求） |
| 合并后 REQ-ID 选择 | 取语义簇中**最小 ID** | {011, 013, 016} → REQ-011 |
| `covered_req_ids[]` 是否丢弃被合并的 ID | **不丢弃** | 全部保留，确保 frozen_spec 追溯完整 |
| 三条 evidence 中两条互补、一条冗余 | 合并互补内容为一条，丢弃纯冗余 | 002 说"3家供应商"、012 补充"每家2-3通道"、052 重复 002 → 保留 012（最完整） |

---

## 4. 验证方法

### 4.1 静态验证（Prompt 层面）

1. **检查 consolidator.md 是否包含去重指令**：
   ```bash
   grep -c "REQ 语义去重" prompts/v1/consolidator.md
   # 期望：1
   ```

2. **检查指令位置**：必须在"方案整合"步骤内，不是独立阶段

### 4.2 动态验证（输出层面）

运行一次完整的 Solution Pro 管线，检查 `final_result.json`：

```python
import json

with open("blackboard/final_result.json") as f:
    data = json.load(f)

evidence = data["requirement_evidence"]
covered = data["covered_req_ids"]

# 检查 1: evidence 数量减少
print(f"requirement_evidence: {len(evidence)} 条")
assert len(evidence) < 55, f"去重未生效，仍有 {len(evidence)} 条"

# 检查 2: covered_req_ids 不丢失
print(f"covered_req_ids: {len(covered)} 条")
assert len(covered) == 71, f"covered_req_ids 不应减少，当前 {len(covered)}"

# 检查 3: evidence 中的 req_id 都在 covered_req_ids 中
evidence_ids = {e["req_id"] for e in evidence}
assert evidence_ids.issubset(set(covered)), "evidence 中有 ID 不在 covered 中"

# 检查 4: 无明显的语义重复（人工抽检 top 5 高频主题）
print("✅ 验证通过")
```

### 4.3 信息完整性验证

对比去重前后的 evidence 内容，确认：
- 每个语义簇的合并条目包含簇内所有独特信息点
- `covered_req_ids` 长度不变（71 → 71）
- frozen_spec.json 中的每个 REQ-ID 仍可追溯到 evidence

### 4.4 A/B 对比验证

| 指标 | 基线（当前） | 目标 | 测量方法 |
|:---|:---|:---|:---|
| `requirement_evidence[]` 条数 | 71 | ≤ 45 | `len(evidence)` |
| `covered_req_ids[]` 条数 | 71 | 71（不变） | `len(covered)` |
| 语义重复率 | ~30% | < 5% | 人工抽检 10 对 |
| 信息丢失率 | 0% | 0% | 对比每个语义簇的独特信息点 |

---

## 5. 实施计划

1. **修改 consolidator.md**：将 §2.3 的 prompt 片段嵌入"方案整合"步骤
2. **运行一次完整管线**：使用 v31_real_case 的相同输入
3. **对比输出**：确认 71 → ≤45 且 covered_req_ids 不变
4. **回归检查**：确认 Ship Pro Architect 能正常消费去重后的 evidence

---

## 6. 风险与缓解

| 风险 | 概率 | 缓解 |
|:---|:---|:---|
| LLM 过度合并（把不同需求合并了） | 中 | prompt 中明确给出反例："预算约束"≠"支付降级" |
| LLM 忽略去重指令 | 低 | 指令放在"方案整合"核心步骤，不是附加说明 |
| 合并后证据丢失关键细节 | 低 | 规则要求"保留最完整的一条"，且 covered_req_ids 全部保留 |
| Prompt 容量竞争 | 低 | 新增 4 行，替换原有 1 行，净增 3 行 |
