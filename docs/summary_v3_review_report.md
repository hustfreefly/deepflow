# 质量与对抗审查报告 — Summary 模块 V3.3 草案

**评审人**：质量与对抗审查专家（expert_quality_adversarial）  
**评审日期**：2026-07-26  
**评审对象**：V3.3 流程重排草案  
**裁决**：**CONDITIONAL**

---

## 一、总体评价

V3.3 草案方向正确——把 V3.1 静默删除的 Fix Judge 和 Harness Check 装回来，砍掉重复的串行 Review Layer B，限制 Analyzer 数量上限。这三步同时解决了"无裁判导致方案膨胀"和"无终检导致自报覆盖"两个核心质量问题，且预估从 83min 降到 65-70min。

**但草案存在 2 个必须修复的质量漏洞和 2 个值得考虑的优化点。** 以下逐项展开。

---

## 二、逐项评审

### 2.1 质量保障链完整性

#### ✅ 成立的部分

| 环节 | V3.0 设计 | V3.1 实现 | V3.3 草案 | 评价 |
|------|----------|----------|----------|------|
| Fix Judge 裁判 | 有 | 删除 | 装回 | ✅ 解决"7 份矛盾建议无人裁决" |
| Harness Check 终检 | 有 | 删除 | 装回 | ✅ 解决"45/45 UC 自报" |
| Review Layer B 重复 | 1 次（并行） | 2 次（并行+串行） | 1 次（并行） | ✅ 砍掉纯浪费 |
| 5a/5b 顺序 | 先文档后 JSON | 颠倒 | 调正 | ✅ |

**"质量从自报升级为独立终检背书"这个声称成立。** Harness Check 独立于 Refiner，读 `refined_solution` + `planning_convergence` + `frozen_spec`，输出结构化 `verification_result` JSON（含逐条证据），这是真正的独立终检，不是自报。

#### 🔴 漏洞 1：Harness Check FAIL 硬上限 1 轮 — 不够

草案写："FAIL → 回 4b 修一轮，硬上限 1 轮"。

**问题**：如果 1 轮回修后 Harness Check 仍然 FAIL，怎么办？草案没有定义出口条件。

- 如果直接放行 → 那 Harness Check 的 FAIL 就没有强制力，"独立终检背书"名存实亡
- 如果无限循环 → 时间预算不可控
- 如果直接报错终止 → 用户拿到一个半成品，体验更差

**这是质量保障链最关键的断裂点。** Harness Check 是最后一道质量门，它的 FAIL 出口条件必须明确定义。

**必须修复**：定义 1 轮回修后仍 FAIL 的处置策略。建议方案：

```
Harness Check FAIL → 回 4b 修一轮 → 再次 Harness Check
  → 如果仍 FAIL：
    → 输出 verification_result 标记 overall_verdict = "FAIL"
    → 在 refined_solution 中附带未通过项清单 + 具体失败证据
    → 继续推进到 Phase 6（不阻塞流程）
    → 域级 adversarial reviewer 会捕获这个 FAIL 信号
```

理由：不阻塞流程（避免死循环），但把 FAIL 信号显式传递给下游（域级 adversarial），让对抗 Agent 看到并处理。这是"质量信号不丢失"的最低保障。

#### ⚠️ 漏洞 2：Fix Judge 自身判断质量缺乏显式保障

Fix Judge 是裁判——它决定采纳/拒绝/折中哪些建议。但谁来审 Fix Judge？

草案没有显式的 Fix Judge meta-review。V3.0 设计文档说"Phase 3 的建议站在各自角度都对，但全局来看可能互相矛盾"，所以 Fix Judge 做全局判断。但如果 Fix Judge 的全局判断本身是错的呢？

**风险评估**：
- Fix Judge 的判断错误 → Refiner 只修采纳项 → Harness Check 可能发现（如果错误导致约束违反）
- 但如果 Fix Judge 错误地拒绝了一个关键修复建议 → Harness Check 的 P0 覆盖率检查应该能捕获
- 所以 Harness Check 间接覆盖了 Fix Judge 的部分盲区

**但有一个缺口**：Fix Judge 可能"采纳了错误理由"或"折中方案两头不靠"，这种语义层面的判断错误 Harness Check 的结构化检查（UC 覆盖、约束一致）不一定能发现。

**可选优化**：在域级 adversarial reviewer 的审查清单中显式加一条："审视 Fix Judge 的 fix_plan，判断是否有被错误拒绝的关键建议"。这不需要新增 Agent，只需扩展域级 adversarial 的 prompt。

### 2.2 对抗 Agent 卡位分析

#### 当前卡位（V3.3 草案 + V3.1 域级）

```
模块内对抗：
  Phase 3: Analyzers（含 Review Layer B 5 维对抗）→ 发现问题
  Phase 4a: Fix Judge → 独立判断（采纳/拒绝/折中）
  Phase 4c: Harness Check → 独立终检（结构化验证）

域级对抗（V3.1 引入，在 Orchestrator 层）：
  adversarial_quality_reviewer → 审最终产物
  cross_module_consistency_checker → 跨模块一致性
```

#### 分工是否有缺口？

**有一个时间差缺口**：Harness Check 审的是 `refined_solution`（Phase 4c），Document Writer 把它写成 `solution_document`（Phase 6a）。这两步之间可能有信息损失或表述偏差——比如 Refiner 的修复在 refined_solution 中是正确的，但 Document Writer 在组织文档时无意弱化或遗漏了某些修复细节。

**但这个缺口不需要新增 Agent**。域级 adversarial reviewer 审的是最终产物（solution_document），它会覆盖这个缺口。只需确保 adversarial reviewer 的 prompt 包含对 refined_solution → solution_document 一致性的检查。

#### 分工是否有重叠？

**Harness Check vs 域级 adversarial reviewer 不重叠**：
- Harness Check：结构化验证（UC 覆盖、约束一致、信息守恒），输出 JSON，是"合规检查"
- 域级 adversarial：语义对抗（方案是否真的解决了问题、有没有逻辑漏洞、技术选型是否合理），是"质量挑战"

两者互补，不重叠。**卡位正确。**

### 2.3 Analyzer 上限 4 的合理性

#### 分析

V3.0 设计要求 Review Layer B 必须保留（5 维对抗检查），这是硬性的。剩余 3 个动态位由 Meta Planner 根据基础方案弱点分配。

**V3.1 实测 7 个 Analyzer 有重合**（供应链/团队组织两个维度重合），说明边际收益确实递减。

**4 个上限是否削弱对抗性？**

对抗性来源不只是 Analyzer 数量：
1. Review Layer B（5 维对抗）→ 保留 ✓
2. Fix Judge 的独立判断 → 装回 ✓
3. Harness Check 的独立终检 → 装回 ✓
4. 域级 adversarial reviewer → 存在 ✓

**4 个 Analyzer 不会削弱对抗性**，因为对抗性来自多层独立视角，不是单层的 Agent 数量。7 个 Analyzer 中有 3 个是噪音，砍掉反而让信号更清晰。

#### ⚠️ 但有一个风险

Meta Planner 现在有"Analyzer ≤4、相似维度必须合并"的硬约束。如果 Meta Planner 把"安全性"和"可操作性"合并成一个 Analyzer（因为"相似"），可能丢失对抗粒度。

**建议**：在硬约束中补充一条例外——"Review Layer B 的 5 个维度不可合并，必须作为独立 Analyzer 或独立检查清单保留"。实际上 Review Layer B 已经是 1 个 Analyzer 做 5 维检查（不是 5 个 Analyzer），所以这条应该自然满足，但显式声明更安全。

### 2.4 精简机会

草案已经砍掉了主要的浪费点（串行重复 Review Layer B、冗余 Analyzer）。**没有明显的进一步精简机会**——每个保留的 Agent 都有独立职责，不可再合并。

Fix Judge 和 Harness Check **不该合并**（草案主张正确）：
- Fix Judge 是修复前的选择题（"该不该修"）
- Harness Check 是修复后的判断题（"修对没有"）
- 合并 = 运动员兼裁判 = V3.1 的教训

---

## 三、裁决

### **CONDITIONAL — 附 2 项必须修改 + 2 项可选优化**

### 必须修改项

| # | 修改项 | 理由 | 修改建议 |
|---|--------|------|----------|
| M1 | 定义 Harness Check 1 轮回修后仍 FAIL 的出口策略 | 质量保障链断裂点：FAIL 无强制力则"独立终检背书"名存实亡 | FAIL 信号显式传递到域级 adversarial reviewer，不阻塞流程但不可静默吞掉 |
| M2 | 在域级 adversarial reviewer 的 prompt 中显式加入：审视 fix_plan 是否有被错误拒绝的关键建议 + 检查 refined_solution → solution_document 一致性 | Fix Judge 判断质量缺乏显式保障；Document Writer 可能引入信息损失 | 扩展域级 adversarial 的审查清单，覆盖这两个缺口 |

### 可选优化项

| # | 优化项 | 理由 |
|---|--------|------|
| O1 | Meta Planner 硬约束中显式声明"Review Layer B 的 5 维检查不可被合并削减" | 防止"相似维度必须合并"约束误伤 Review Layer B 的对抗粒度 |
| O2 | Harness Check 的 verification_result 中增加 `fix_plan_adherence` 字段：检查 Refiner 是否只修了采纳项、是否引入了 fix_plan 之外的改动 | 防止 Refiner "过度修复"（V3.1 实测 Refiner 膨胀 75%，部分原因可能是修了不该修的）|

---

## 四、回答 Briefing 第五节的 6 个问题

1. **V3.3 是否满足"极高质量 + 对抗 Agent + 精简"？**  
   基本满足，但有 1 个质量漏洞需补（M1）。对抗 Agent 多层覆盖充分。精简到位。

2. **Fix Judge 和 Harness Check 该不该合并？**  
   **不该合并。** 草案论证正确：前者是修复前选择题，后者是修复后判断题。合并 = 运动员兼裁判。

3. **Analyzer 上限 4 是否合理？**  
   合理。对抗性来自多层独立视角（Analyzer + Fix Judge + Harness + 域级 adversarial），不是单层 Agent 数量。动态 2-5 机制增加了编排复杂度但收益不大（Meta Planner 已经有动态规划能力，硬上限 4 足够约束）。

4. **有没有遗漏的质量风险或精简机会？**  
   质量风险：M1（FAIL 出口）、M2（Fix Judge 元审查 + Document Writer 一致性）。精简机会：已无明显空间。

5. **对抗 Agent 卡位是否正确？**  
   正确。模块内 Harness Check（合规检查）vs 域级 adversarial（语义对抗）互补不重叠。唯一缺口是 refined_solution → solution_document 的转换阶段，由域级 adversarial 覆盖即可（M2）。

6. **有没有更好的替代编排？**  
   没有。V3.3 的 Phase 1→2→3→4a→4b→4c→6a→6b 线性链已经是最优编排。唯一的改进方向是 M1/M2 的补强，不是结构重排。

---

**总结**：V3.3 草案方向正确、架构合理，补上 M1（FAIL 出口策略）和 M2（域级 adversarial 审查清单扩展）后即可进入实施。
