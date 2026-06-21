# Phase 0 评审：架构可行性

> **评审视角**: AI Native 架构审计  
> **评审日期**: 2026-06-18  
> **评审对象**: Ship Pro V3 — 5 Agent 分工 + sessions_send 反馈闭环  
> **核心问题**: 在实际执行中会遇到什么问题？

---

## 评审结论：PASS_WITH_CONCERNS

架构整体方向正确，5 Agent 拆分合理，sessions_send 持续对话是关键优势。但存在 4 个需要解决的设计风险，其中 2 个可能影响系统可用性。

---

## Agent 分工评估

| Agent | 职责清晰度 | 复杂度 | 风险 |
|-------|-----------|--------|------|
| **Architect** | ⭐⭐⭐⭐⭐ 高 | 高（需处理 4 种输入格式） | 输入格式多样性导致 prompt 不稳定 |
| **Decomposer** | ⭐⭐⭐⭐ 较高 | 中（拆分 + 依赖排序） | 拆分粒度难以标准化 |
| **Specifier** | ⭐⭐⭐⭐ 较高 | 高（AC 质量是核心） | AC 质量高度依赖 prompt 迭代 |
| **Reviewer** | ⭐⭐⭐⭐⭐ 高 | 高（审核 + 结构化反馈） | 与生产 Agent "共谋"风险 |
| **Packager** | ⭐⭐⭐ 中 | 低（组装 + summary） | 职责太轻，ROI 存疑 |

### 分工详细分析

**Architect Agent — 职责清晰，但负载最重**
- ✅ 输入理解 + 格式归一化是合理的第一步
- ⚠️ 需要处理 4 种格式变体（A/B/C/D），prompt 中 5 种 few-shot 示例会占用大量 token
- ⚠️ 输出 blueprint.json 包含 modules/dependencies/requirements/risks/implementation_hints — 这是 5 个子任务打包在一个 Agent 里
- **建议**: 考虑将"格式识别+提取"和"依赖推导+需求映射"拆成两个子步骤（不一定拆成两个 Agent，至少 prompt 内分阶段）

**Decomposer Agent — 职责合理，粒度是难点**
- ✅ 模块→WP 拆分 + 依赖排序，职责单一
- ⚠️ 拆分粒度没有客观标准 — "大模块拆成多个 WP"，多大算大？
- ⚠️ 依赖推导完全依赖 LLM 理解，没有 code-based 校验（拓扑排序只检测环，不检测遗漏）
- **建议**: 在 prompt 中嵌入明确的拆分规则（如"每个 WP 对应一个可独立部署/测试的单元"），而非让 LLM 自由判断

**Specifier Agent — 职责核心，质量风险最高**
- ✅ AC 生成 + 技术约束 + 交付物，逻辑上是独立步骤
- ⚠️ AC 质量是整个系统的核心价值，但 LLM 生成 AC 的稳定性存疑
- ⚠️ AC 可验证性 Rubric（L1-L4）很好，但嵌入 prompt 后 LLM 能否稳定执行 4 级区分？
- **建议**: Phase 1 重点测试 Specifier，如果 AC 质量不达标，考虑增加"AC 模板库"（按 complexity 分级）

**Reviewer Agent — 职责清晰，共谋风险需缓解**
- ✅ 只审核不修改，职责边界明确
- ⚠️ **共谋风险**: Reviewer 和生产 Agent 用同系列模型时，可能"自己审自己"
- ⚠️ 结构化反馈格式（action/target_path/target_agent/value）对 LLM 来说约束较强
- **建议**: Reviewer 必须用不同模型（设计中已提到），且反馈格式应简化为自然语言 + 结构化混合

**Packager Agent — 职责过轻，ROI 最低**
- ⚠️ 组装 ship_package.json 本质是"读所有文件 → 填模板"，确定性代码可以做
- ⚠️ summary.md 生成是唯一需要 LLM 的部分，但一个轻量 prompt 即可
- ✅ 设计文档明确说"必选"，理由是"与 Ship 隐喻形成完整叙事"
- **建议**: 保留但降低期望 — Packager prompt 应该极简（<500 tokens），不要让它做额外的一致性审核（那是 Reviewer 的事）

---

## 关键风险

### 风险 1: 反馈闭环收敛性不确定 🔴 高

**问题**: 5 轮 sessions_send 反馈闭环能否收敛？

**阻止收敛的因素**:
1. **Reviewer 标准漂移**: 每轮 Reviewer 可能用不同标准审核（LLM 输出不稳定），导致"改了 A 又发现 B"
2. **级联修改**: Reviewer 指出 Decomposer 的 WP 拆分问题 → Decomposer 修改 → Specifier 的 AC 全部失效 → 需要 Specifier 也改 → 两轮过去了
3. **反馈信息损失**: sessions_send 传 ~2KB 反馈，但 Agent 可能需要更多上下文才能正确修改
4. **Agent 间理解不一致**: Decomposer 对"拆分粒度"的理解和 Reviewer 不同 → 反复修改

**最坏情况**: 5 轮全部用于 Decomposer+Specifier 的来回修改，Packager 永远没机会执行。

**建议**:
- 增加"反馈路由"逻辑：Orchestrator 分析反馈，如果同一 Agent 连续 2 轮被标记，强制 Orchestrator 介入调整策略
- 设定每 Agent 最大修改次数（如每个 Agent 最多被 send 3 次）
- 第 3 轮后如果还没 PASS，降级为"输出当前最佳 + 附带 review_report 作为 warning"

### 风险 2: Token 预算紧张 🟡 中

**问题**: 100K token 够不够？

**粗略估算**:
| 阶段 | Token 消耗 |
|------|-----------|
| Architect 首次 spawn | ~15K（输入 ~8K + 输出 ~3K + prompt ~4K）|
| Decomposer 首次 spawn | ~10K |
| Specifier 首次 spawn | ~15K（每个 WP 的 AC 很长）|
| Packager 首次 spawn | ~8K |
| Reviewer 首次 spawn | ~12K |
| 反馈闭环（每轮）| ~8-15K（取决于修改范围）|
| **总计（首次 + 3 轮反馈）**| **~90-120K** |

**结论**: 100K 在 3 轮反馈内可行，5 轮大概率超支。

**建议**:
- 将 token 预算提高到 150K，或
- 动态预算：首次执行分配 60K，反馈闭环分配 40K（严格控制）
- 每个 Agent 设置独立 token 上限（Architect 20K, Specifier 25K, 其他 15K）

### 风险 3: Architect Agent 的 prompt 复杂度 🟡 中

**问题**: Architect 需要处理 4 种输入格式 + 输出统一 blueprint.json

**分析**:
- 4 种格式的路径提取逻辑不同（Format A 从 `final_solution.detailed_solution.architecture`，Format B 从 `architecture.components`...）
- Prompt 中需要嵌入 4 种格式的识别规则 + 提取路径 + few-shot 示例
- 预估 prompt 长度：~3000-4000 tokens（含 few-shot）
- 这是所有 Agent 中最复杂的 prompt，也是最容易出错的

**建议**:
- 在 Orchestrator 层增加"格式预检测"（确定性代码，<10 行），识别 Format A/B/C/D 后在 prompt 中只嵌入对应格式的提取规则
- 这样 Architect prompt 从"处理 4 种格式"简化为"处理 1 种已知格式"

### 风险 4: blackboard 文件传递的隐式依赖 🟢 低

**问题**: Agent 间通过文件系统传递数据，有没有隐式依赖？

**分析**:
- Architect → blueprint.json → Decomposer/Specifier/Reviewer：显式依赖，设计已覆盖
- Decomposer → wp_structure.json → Specifier：显式依赖
- Reviewer → review_report.json → Orchestrator → 目标 Agent：显式依赖
- ⚠️ **隐式依赖**: Specifier 需要 blueprint.json 中的技术约束来生成 AC，但 blueprint.json 的技术约束质量取决于 Architect 的理解 — 如果 Architect 漏掉了某个技术约束，Specifier 无法补救

**建议**:
- 在 Specifier prompt 中增加"如果发现 blueprint 中技术约束不足，在 wp_specs.json 中标注 `[CONSTRAINT_GAP]`"
- Reviewer 审核时检查 `[CONSTRAINT_GAP]` 标记

---

## 具体建议

### 建议 1: 简化反馈格式（高优先级）

当前设计的结构化反馈格式（action/target_path/target_agent/value）对 LLM 约束过强。建议改为：

```json
{
  "verdict": "FAIL",
  "issues": [
    {
      "target_agent": "specifier",
      "severity": "high",
      "description": "WP-003 的 AC 过于空泛，'功能实现完成'不可验证",
      "suggestion": "改为具体的测试命令和预期结果"
    }
  ]
}
```

让 LLM 用自然语言描述问题和修改建议，Orchestrator 只解析 `target_agent` 做路由。

### 建议 2: 增加 Orchestrator 智能路由（高优先级）

当前设计是"Reviewer 说改谁就改谁"。建议 Orchestrator 增加一层分析：

```
Reviewer 反馈 → Orchestrator 分析:
  ├── 单 Agent 问题 → 直接 send
  ├── 多 Agent 问题 → 分析依赖顺序（先改 Architect → 再改 Specifier）
  └── 循环修改（同一 Agent 连续 2 轮被标记）→ 强制降级输出
```

### 建议 3: Packager prompt 极简设计（中优先级）

Packager 的 prompt 应该控制在 500 tokens 以内：
- 读所有 Agent 输出
- 按 ship_package_v3.schema.json 组装
- 生成 summary.md（3 段：概述、执行顺序、风险提示）
- 不做额外审核（那是 Reviewer 的工作）

### 建议 4: 格式预检测（中优先级）

在 Orchestrator 中增加 ~10 行确定性代码：

```python
def detect_input_format(final_result: dict) -> str:
    if "final_solution" in final_result:
        return "A"
    elif "project" in final_result:
        return "B"
    elif "pipeline_summary" in final_result:
        return "C"
    else:
        return "D"
```

然后在 Architect prompt 中只嵌入对应格式的规则。这将 Architect 的 prompt 复杂度降低 60%。

### 建议 5: Token 预算重新分配（中优先级）

| Agent | 建议预算 | 理由 |
|-------|---------|------|
| Architect | 20K | 输入最大（3 个文件），输出复杂 |
| Decomposer | 15K | 中等输入输出 |
| Specifier | 25K | AC 生成是核心，需要足够空间 |
| Reviewer | 15K | 审核 + 结构化反馈 |
| Packager | 10K | 组装 + summary，最轻 |
| 反馈闭环池 | 40K | ~3 轮反馈 |
| **总计** | **125K** | 略超 100K，建议提高上限 |

### 建议 6: 降级策略明确化（低优先级）

当前设计的降级策略是"token 预算用完 → 输出当前最佳"。建议细化：

| 触发条件 | 降级动作 |
|---------|---------|
| Reviewer 第 1 轮 PASS | 正常流程，Packager 组装 |
| Reviewer 第 3 轮仍 FAIL | 输出当前最佳 + review_report 作为 warning 附件 |
| Token 预算 > 80% | 停止反馈闭环，直接进入 Packager |
| 同一 Agent 连续 3 轮被标记 | 该 Agent 输出冻结，标注 `[REVIEW_UNRESOLVED]` |
| Architect 输出 confidence=low | 在 ship_package 中标注 `[LOW_CONFIDENCE]`，建议人工审核 |

---

## 正面评价（做得好的地方）

1. **blueprint.json 作为协作契约** — 这是关键设计决策，Agent 间有明确的数据接口，避免了隐式耦合
2. **sessions_send 持续对话** — 比"重新 spawn"节省 ~90% 的 token，且修改更精准
3. **三层质量评估** — L1 自检（<5s）→ L2 预检（<1s）→ L3 审核（~30s），分层过滤，设计合理
4. **WP 结构适配 AI Coding** — 删除工时/阶段，替换为 token/复杂度/重试，这是正确的方向
5. **版本快照 _meta** — run_id 贯穿所有 Agent 输出，可追溯性强
6. **AC 可验证性 Rubric** — L1-L4 四级量表，确定性可计算，这是系统的"质量锚点"

---

## 总结

| 维度 | 评估 | 说明 |
|------|:---:|------|
| Agent 分工合理性 | ✅ PASS | 5 Agent 拆分合理，边界基本清晰 |
| 数据流设计 | ✅ PASS | blueprint.json 契约 + blackboard 传递 |
| 反馈闭环可行性 | ⚠️ CONCERN | 收敛性不确定，需要 Orchestrator 智能路由 |
| Prompt 设计方向 | ⚠️ CONCERN | Architect prompt 过复杂，需要格式预检测 |
| Token 预算 | ⚠️ CONCERN | 100K 偏紧，建议 125-150K |
| 降级策略 | ✅ PASS | 有基本策略，建议细化触发条件 |

**总体**: 架构可行，建议的 6 个改进点中，建议 1（简化反馈格式）和建议 2（Orchestrator 智能路由）是 Phase 1 必须解决的，其他可以在 Phase 2/3 迭代。
