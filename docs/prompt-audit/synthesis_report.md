# Solution Pro Prompt 系统综合诊断报告

> 诊断日期：2026-07-29
> 诊断方法：3 专家并行审计（结构层 + 语义层 + 契约层）
> 审计范围：30 个活跃 prompt + 41 个 registry 条目 + 13 个归档文件 + 历史 memory 记录

---

## 综合评分

| 专家 | 维度 | 评分 | 核心问题 |
|------|------|------|---------|
| Expert 1 | 结构层 | **C+** | Registry 全量失准，代码嵌入 61.6%，架构版本矛盾 |
| Expert 2 | 语义层 | **B- (72/100)** | 72% 约束无代码保障，7 处矛盾指令，Examples 最弱 |
| Expert 3 | 契约层 | **D (68/100)** | 版本管理 F，18 个伪契约，28 天未更新 |
| **综合** | **全维度** | **C+ (70/100)** | 能跑但不健康，核心问题是"信任落差" |

---

## 🔴 P0 阻塞级问题（6 项）

### 1. Registry 全面失准（3 位专家一致）
- **版本号**：Registry 全部标记 `2.0.0`，实际 `1.0.0`~`4.0.0`（orchestrator 差距 2 major）
- **变量声明**：全部为空，实际使用 `session_id`、`deepflow_root`、`run_id` 等 6 个变量
- **changelog**：全部为 `"Auto-registered from disk"`，24 天未更新
- **幽灵条目**：13 个指向 `_archive` 的条目未标记 deprecated，1 个（harness_agent）指向不存在文件

### 2. 架构版本矛盾（Expert 1）
- Orchestrator V4.0 说"移除 Step 4 后置验证"
- planning_module V3.3 仍包含 reviewer_meta + reviewer_convergence 步骤
- 两个核心文件描述的不是同一套流程

### 3. web_search 权限冲突（Expert 2 — HIGH）
- `_shared_subagent_rules.md`："不能 web_search"
- `research_expert_base.md`："必须执行至少 15 次 web_search"
- `summary_base_synthesizer.md`："可以使用 web_search"
- 子 Agent 可能因共享规则拒绝执行 web_search

### 4. "不预设" vs "必含 review_layer_b" 矛盾（Expert 2 — HIGH）
- Planner 层 "绝对禁止预设固定专家列表"
- Summary 层 "必须包含 review_layer_b Analyzer"
- 两个原则冲突，LLM 产生认知矛盾

### 5. P0 REQ 100% 覆盖无代码验证（3 位专家一致）
- meta_planner.md 中声明为"硬约束"
- 实际完全依赖 LLM 自检（违反概率 40-60%）
- 无代码穷举验证

### 6. "禁止 yield/禁止文字" 是伪契约（Expert 3）
- 历史事故已证明这些约束不可靠（07-26 三次事故）
- 纯 prompt 文本，无代码级状态机锁
- LLM 本能在长等待时 poll/生成文字

---

## 🟡 P1 高优先级问题（5 项）

| # | 问题 | 来源 |
|---|------|------|
| 1 | 术语体系分裂：Worker 层 "专家/Worker/子 Agent" vs Summary 层 "运动员/裁判/修理工/终检员" | Expert 2 |
| 2 | 8 个"架空约束"（"必须"但无代码保障）：web_search 次数、Finding 字数、expert 数量上限、merge_ratio 等 | Expert 2 |
| 3 | 跨模块依赖无版本校验：planning → research → summary 的数据传递基于文件约定 | Expert 1 |
| 4 | 认知基底注入不可靠：ai_native_cognitive_base.md 依赖代码层注入，prompt 中无引用标记 | Expert 2 |
| 5 | 6 个文件存在但未注册：adversarial_quality_reviewer、solution_pulse 等 | Expert 1 |

---

## 关键数据统计

| 指标 | 数值 |
|------|------|
| 活跃 Prompt 文件 | 30 |
| Registry 条目 | 41（14 个指向 _archive） |
| 总 Prompt 量 | ~28K tokens |
| 代码嵌入比例（Module Agent 层） | 61.6%（summary_module 最高 76.9%） |
| 代码强约束 | 12（8%） |
| 纯指令约束 | 105（72%） |
| 建议约束 | 28（20%） |
| 伪契约 | 18 |
| 矛盾指令 | 7（2 处 HIGH） |
| Prompt 5 要素平均分 | 3.8/5（Examples 最弱 0.52） |
| 已知失败模式 | 8 个（3 个重复出现） |

---

## 根因分析

**核心问题：信任落差**

prompt 文本声称了 105 条"必须"约束，但只有 12 条有代码级保障。在 07-26 的三次事故中，正是这种落差导致了系统故障。

**信任落差的三层表现**：
1. **设计层**：以为写了"禁止"LLM 就会遵守 → 实际不会
2. **管理层**：以为 Registry 会同步更新 → 实际 24 天未更新
3. **认知层**：以为术语统一 → 实际 4+ 种称谓混用

---

## 改进路径

### 立即（本周）
1. 修复 Registry 版本号（同步到实际 frontmatter）
2. 清理 13 个幽灵 registry 条目（标记 deprecated）
3. 修复 web_search 权限冲突
4. 修复"不预设" vs "必含"矛盾

### 短期（2 周）
1. 为 P0 REQ 覆盖增加代码穷举验证
2. 统一术语体系
3. 为 8 个架空约束增加代码验证
4. 补全 Registry 缺失条目

### 中期（1 月）
1. 构建 Prompt Doctor Skill（基于六维框架）
2. 建立 CI hook 自动同步 Registry
3. 添加 prompt I/O 日志
4. 降低 Module Agent 层代码嵌入比例

---

*生成时间：2026-07-29 04:00 GMT+8 | 综合 3 份专家报告*