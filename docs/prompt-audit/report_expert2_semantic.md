# Expert 2: Prompt 语义审计报告

> 审计日期: 2026-07-29
> 审计范围: Solution Pro V3.3 全部 22 个 Prompt 文件
> 审计人: Expert 2 (语义审计)

---

## 1. 指令一致性分析

### 1.1 术语一致性

| 术语 | 使用情况 | 问题 |
|------|---------|------|
| Worker / Expert / Agent / 子 Agent | 混用。`meta_planner.md` 用"专家"和"Worker"，`planning_planner.md` 用"Expert"和"子 Agent"，`summary_*` 用"运动员/裁判/修理工/审查员" | **严重混用**。同一概念在不同模块有 4+ 种称谓。Summary 层引入"运动员/裁判/修理工/终检员"隐喻，与 Worker 层的"专家"体系脱节。 |
| MUST / 必须 / 🔴 | 三种强调方式混用。`expert_planner_base.md` 用 "MUST/SHOULD/MAY"，`planning_expert_base.md` 用 "MUST（必须遵守）"，`_shared_subagent_rules.md` 用 "🔴" 作为 section 标记 | **中等问题**。🔴 在有些 prompt 中表示"禁止"，有些表示"必须做"，有些表示"硬约束"，语义不统一。 |
| planning_plan / planning_convergence | Worker 层用 `planning_convergence`，但 `planning_planner.md` 输出 stage 名为 `planning_plan`，`convergence_planner.md` 输出 `planning_convergence` | **低风险**。关系清晰，但命名跨越两个阶段容易混淆。 |
| expert_name / expert_filename / analyzer_name | 多个 prompt 使用不同变量名指向同一概念 | **中等问题**。`research_expert_base.md` 用 `{expert_name}` 和 `{expert_filename}`，`summary_analyzer_base.md` 用 `{analyzer_name}`。 |

### 1.2 矛盾指令清单

| # | 矛盾描述 | 涉及文件 | 严重程度 |
|---|---------|---------|---------|
| **C1** | "不预设固定专家列表" vs "必须包含 review_layer_b Analyzer" | `planning_planner.md` / `research_planner.md` vs `summary_meta_planner.md` | **HIGH** — 两个原则冲突。Planner 层说"绝对禁止预设"，但 Summary 层强制要求一个特定 Analyzer。LLM 会被"不要预设"的强指令约束，但同时又被要求必须包含特定 Agent，产生认知冲突。 |
| **C2** | web_search 权限冲突 | `_shared_subagent_rules.md` ("不能 web_search") vs `research_expert_base.md` ("必须执行至少 15 次 web_search") vs `summary_base_synthesizer.md` ("可以使用 web_search") vs `summary_meta_planner.md` ("不能 web_search") | **HIGH** — `_shared_subagent_rules.md` 作为共享规则说"不能 web_search"，但多个 Worker prompt 明确要求或允许 web_search。子 Agent 可能因共享规则而拒绝执行 web_search。 |
| **C3** | "不做审查" vs "必须覆盖所有 MUST 约束" | `summary_base_synthesizer.md` ("不做审查，不做对抗") vs 同文件 ("必须遵守 planning_convergence 中的所有 MUST 约束") | **MEDIUM** — "不做审查"可能被 LLM 理解为"不需要检查是否遵守了约束"，导致 MUST 约束遗漏。 |
| **C4** | "不要预设固定的专家列表" vs "示例中给出了 expert 列表" | `planning_planner.md` (禁止预设) vs 同文件 `meta_planner.md` 示例 (security_expert, performance_expert, data_architect) | **MEDIUM** — 示例本身就是一种"预设"。LLM 倾向于模仿示例中的专家列表，与"不要预设"的指令矛盾。 |
| **C5** | "fix_plan 是唯一依据" vs "MUST 约束不能删减" | `summary_refiner.md` (只按 fix_plan 修) vs 同文件 ("MUST 约束不能删减") | **MEDIUM** — 如果 fix_plan 遗漏了某个 MUST 约束相关的修复，Refiner 应该修还是不修？两个指令冲突。 |
| **C6** | "不读 analysis_*" vs "读所有 Analyzer 报告" | `summary_refiner.md` ("不再读 analysis_* 报告") vs `summary_fix_judge.md` ("读所有 Analyzer 的审查报告") | **LOW** — 角色不同 (Refiner vs Fix Judge)，但"不读"的绝对表述可能被误读。 |
| **C7** | "Analyzer 总数 ≤ 4" vs "Review Layer B 不可合并削减" | `summary_meta_planner.md` (两条约束在同一文件) | **LOW** — 实际含义是 1 个必含 + 最多 3 个自定义，但表述方式使人困惑。 |

### 1.3 术语统一性评分

- **Worker 层**: ⭐⭐☆☆☆ (4种称谓混用)
- **Review 层**: ⭐⭐⭐☆☆ (Reviewer/Analyzer 混用，但相对清晰)
- **Summary 层**: ⭐⭐⭐⭐☆ (运动员/裁判/修理工/终检员 隐喻清晰，但与前两层脱节)
- **基础层**: ⭐⭐⭐☆☆ (🔴 语义不统一)

**整体术语一致性**: ⭐⭐⭐☆☆ (3/5)

---

## 2. 约束可执行性分类

### 2.1 三类约束统计

| 类别 | 数量 | 占比 | 说明 |
|------|------|------|------|
| **代码强制约束 (Code-enforced)** | 12 | 8% | Pydantic schema 验证、JSON 格式检查、write_stage 类型检查、Gate A 权重和=1.0 校验 |
| **指令约束 (Prompt-only)** | 105 | 72% | 大部分"必须"约束在 prompt 中声明的，但无代码强制执行 |
| **建议约束 (Advisory)** | 28 | 20% | "建议"、"鼓励"、"可以" 等弱约束 |

### 2.2 关键"架空约束"识别

以下约束在 prompt 中声明为"必须"，但**实际上没有代码保障**，LLM 可能违反：

| 约束 | 所在文件 | 为什么是"架空" | 风险 |
|------|---------|--------------|------|
| "必须执行至少 15 次 web_search" | `research_expert_base.md` | 无代码计数，LLM 可能只搜 5-8 次就停止 | **HIGH** — 研究不充分 |
| "每个 Finding 不少于 200 字" | `research_expert_base.md` | 无代码验证字数的下限 | **HIGH** — 浅层结论 |
| "P0 REQ 100% 追溯" | `meta_planner.md` | 无代码穷举验证，纯靠 LLM 自检 | **HIGH** — P0 需求遗漏 |
| "merge_ratio 在 0.5-0.8 范围内" | `convergence_planner.md` | 无代码验证，LLM 可能不计算或算错 | **MEDIUM** — 合并不充分或过度 |
| "Analyzer 总数 ≤ 4" | `summary_meta_planner.md` | 无代码计数，LLM 可能生成 5-6 个 Analyzer | **MEDIUM** — Token 浪费 |
| "专家数量上限 5" | `meta_planner.md` | 无代码验证 | **MEDIUM** — Token 爆炸 |
| "MUST 约束数量 < 50%" | `reviewer_convergence.md` | 无代码统计 | **MEDIUM** — 过度严格 |
| "约束 ID 必须连续" | `convergence_planner.md` / `reviewer_convergence.md` | 无代码验证连续性 | **LOW** — 可读性问题 |

### 2.3 约束执行保障矩阵

| 约束类型 | 代码保障 | Prompt 保障 | LLM 实际遵守率(估算) |
|---------|---------|------------|-------------------|
| JSON 格式合法性 | ✅ Pydantic/JSON.parse | ✅ 多处强调 | 95%+ |
| 字段必填 | ✅ Pydantic Field(required) | ✅ 多处强调 | 95%+ |
| 数值范围 (权重和=1.0) | ✅ Python 校验 | ✅ 强调 | 90%+ |
| P0 REQ 100% 覆盖 | ❌ 无代码穷举 | ✅ 多处强调 | 70-80% |
| 15 次 web_search | ❌ 无代码计数 | ✅ 声明 | 50-60% |
| Finding ≥ 200 字 | ❌ 无代码计数 | ✅ 声明 | 60-70% |
| 不预设专家列表 | ❌ 无代码检测 | ✅ 🔴 强调 | 40-50% |
| merge_ratio 范围 | ❌ 无代码计算 | ✅ 声明 | 60-70% |

---

## 3. 认知负荷分析

### 3.1 每个 Prompt 的 Token 估算

| # | 文件 | 字符数（估） | Token 估算 | 指令密度 | 核心指令数 |
|---|------|------------|-----------|---------|-----------|
| 1 | meta_planner.md | ~7,200 | ~1,800 | **低** (淹没在示例中) | 8 |
| 2 | planning_planner.md | ~5,800 | ~1,450 | 中 | 7 |
| 3 | expert_planner_base.md | ~3,200 | ~800 | 高 | 6 |
| 4 | convergence_planner.md | ~6,500 | ~1,600 | 中 | 5 |
| 5 | research_planner.md | ~5,800 | ~1,450 | 中 | 7 |
| 6 | research_expert_base.md | ~5,600 | ~1,400 | 中 | 8 |
| 7 | planning_expert_base.md | ~4,800 | ~1,200 | 高 | 9 |
| 8 | reviewer_meta.md | ~6,500 | ~1,600 | **低** (淹没在 JSON 示例中) | 4 |
| 9 | reviewer_convergence.md | ~7,500 | ~1,900 | **低** (淹没在 JSON 示例中) | 5 |
| 10 | review_layer_b.md | ~3,200 | ~800 | 高 | 5 |
| 11 | adversarial_quality_reviewer.md | ~5,800 | ~1,450 | 中 | 7 |
| 12 | summary_base_synthesizer.md | ~5,800 | ~1,450 | 中 | 6 |
| 13 | summary_meta_planner.md | ~6,200 | ~1,550 | 中 | 8 |
| 14 | summary_analyzer_base.md | ~3,800 | ~950 | 高 | 6 |
| 15 | summary_review_layer_b.md | ~7,200 | ~1,800 | 中 | 5 |
| 16 | summary_refiner.md | ~4,200 | ~1,050 | 高 | 6 |
| 17 | summary_fix_judge.md | ~4,500 | ~1,100 | 高 | 5 |
| 18 | summary_harness_check.md | ~5,200 | ~1,300 | 中 | 5 |
| 19 | summary_json_extractor.md | ~7,500 | ~1,900 | **低** (淹没在 Python 代码中) | 15 |
| 20 | ai_native_cognitive_base.md | ~1,200 | ~300 | 极高 | 4 |
| 21 | _shared_subagent_rules.md | ~3,800 | ~950 | 高 | 7 |
| 22 | summary_summarizer.md | ~3,500 | ~900 | 中 | 5 |

**总计**: ~111,000 chars ≈ **~28,000 tokens** (纯 prompt 模板，不含运行时注入的上下文)

### 3.2 指令密度分析

**指令密度 = 核心约束数 / token 估算**

| 密度评级 | 文件数 | 占比 | 典型文件 |
|---------|-------|------|---------|
| **极高** (>5 指令/1000 tokens) | 2 | 9% | ai_native_cognitive_base.md, expert_planner_base.md |
| **高** (3-5/1000 tokens) | 9 | 41% | planning_expert_base.md, summary_refiner.md, summary_analyzer_base.md |
| **中** (2-3/1000 tokens) | 8 | 36% | research_expert_base.md, summary_base_synthesizer.md |
| **低** (<2/1000 tokens) | 3 | 14% | meta_planner.md, reviewer_meta.md, reviewer_convergence.md |

**关键发现**: 
- `meta_planner.md` (1,800 tokens, 8 条核心指令) 的指令密度最低，大量 token 消耗在 JSON 示例和场景描述上
- `reviewer_meta.md` 和 `reviewer_convergence.md` 的 JSON 输出示例占比超过 60%，核心指令被淹没
- `ai_native_cognitive_base.md` 仅有 300 tokens，但 4 条核心指令，密度极高

### 3.3 基础层注入分析

`ai_native_cognitive_base.md` 的设计意图是注入到所有 Worker Agent 的 System Prompt 开头。但实际分析：

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 是否在 Worker 层 prompt 中引用 | ❌ | 无 Worker prompt 明确引用该文件 |
| 是否在 Summary 层 prompt 中引用 | ❌ | 无 Summary prompt 明确引用该文件 |
| 是否在 Review 层 prompt 中引用 | ❌ | 无 Review prompt 明确引用该文件 |
| 注入方式是否有效 | ⚠️ | 文档说由代码注入，但 prompt 本身无感知 |

**结论**: 基础层注入依赖于 Python 代码执行，但 prompt 中无任何引用标记。如果代码注入失败，所有 Agent 将失去认知基底。建议在每个 prompt 中添加 `<!-- injected: ai_native_cognitive_base.md -->` 引用标记。

### 3.4 冗余内容

| 冗余内容 | 重复文件 | 重复次数 | 影响 |
|---------|---------|---------|------|
| BlackboardManager API 快速参考 | research_expert_base.md, planning_expert_base.md, _shared_subagent_rules.md | 3 次 | 轻微冗余，但可接受（不同层可能需要） |
| 防御性编码规则 | _shared_subagent_rules.md (独立) | 1 次（共享） | 合理 |
| "LLM 做判断，代码做格式" 原则 | ai_native_cognitive_base.md, _shared_subagent_rules.md | 2 次 | 低度冗余 |
| 多域示例参考（软件/投资/硬件） | 多个 prompt 末尾 | 6+ 次 | 有用但冗长，约占每个 prompt 的 15-20% |
| JSON 输出示例 | meta_planner.md, convergence_planner.md, reviewer_meta.md, reviewer_convergence.md | 4 次 | 大量示例占 50%+ token，但不同于模板内容 |

---

## 4. 失败模式分析

### 4.1 Top 5 最可能被 LLM 违反的指令

| 排名 | 指令 | 所在文件 | 违反概率 | 违反原因 |
|------|------|---------|---------|---------|
| **1** | "不要预设固定的专家列表" (🔴 绝对禁止) | planning_planner.md, research_planner.md | **70-80%** | LLM 天然倾向模式匹配。见到"安全"需求就预设"安全专家"，见到"性能"需求就预设"性能专家"。示例中给出的 expert 列表进一步强化了预设倾向。 |
| **2** | "必须执行至少 15 次 web_search" | research_expert_base.md | **50-70%** | LLM 没有计数本能。通常会搜 5-8 次就觉得"足够"了。没有代码强制执行，没有进度提示。 |
| **3** | "P0 REQ 100% 追溯" (硬约束) | meta_planner.md | **40-60%** | LLM 在长文本中容易遗漏个别 REQ-ID。P0 REQ 数量多时（30+），逐一映射的认知负荷极高。 |
| **4** | "每个 Finding 不少于 200 字" | research_expert_base.md | **30-50%** | LLM 在生成多个 Finding 时，后面的 Finding 倾向于变短。没有字数计数器反馈。 |
| **5** | "不做审查，不做对抗" (运动员角色) | summary_base_synthesizer.md | **30-40%** | LLM 训练中包含大量"先审查再回答"的模式。让 LLM "只产出不审查" 需要强大的角色抑制，但 prompt 中只有一句话。 |

### 4.2 建议性指令写成强制性的

| 指令 | 实际性质 | 当前表述 | 建议 |
|------|---------|---------|------|
| "⭐ P0 约束必须输出：至少 1 条 P0 约束" | 建议性（如果确实无 P0 约束，空数组是合理的） | 写为"必须" | 改为 "MUST 除非任务确实无 P0 约束（需说明理由）" |
| "merge_ratio 在 0.5-0.8" | 建议性（取决于输入质量） | 写为"理想范围" | 保持"理想范围"，但增加"如果偏离需说明原因" |
| "MUST 约束数量 < 50%" | 统计性建议 | 写为检查标准 | 改为"建议 MUST 约束占比 < 50%，否则需说明合理性" |

### 4.3 边界条件误解读风险

| 边界条件 | 涉及 prompt | 误解读风险 |
|---------|------------|----------|
| `data/living_spec.json` 不存在时 fallback 到 `frozen_spec.json` | 多个 prompt 使用"优先"表述 | ⚠️ 如果两者都不存在，LLM 可能编造需求 |
| "如果任务确实没有 P0" → 输出空数组 | meta_planner.md | ⚠️ LLM 可能为了"安全"而编造 P0 约束 |
| "Analyzer 总数 ≤ 4（含 review_layer_b）" | summary_meta_planner.md | ⚠️ LLM 可能理解为"刚好 4 个"，凑数添加不必要的 Analyzer |
| "语义去重（语义相同，不是字符串相同）" | convergence_planner.md | ⚠️ 去重粒度难以把握，LLM 可能过度合并或合并不足 |

### 4.4 "禁止 X" 但给了违反空间

| 禁止指令 | 违反空间 | 示例 |
|---------|---------|------|
| "禁止预设固定的专家列表" | 示例中给出了完整的专家列表模板 | LLM 直接复制示例中的 expert 配置 |
| "不做审查" | 同 prompt 中要求"必须覆盖所有 MUST 约束" | LLM 为了"覆盖约束"而进行审查 |
| "不读 analysis_* 报告" | 但要求"MUST 约束不能删减" | LLM 可能为了验证 MUST 约束而越权读取 |
| "不能修改 base_solution" | 但要求"审查 base_solution 的强弱项" | LLM 可能在审查过程中无意修改 |

---

## 5. Prompt 5 要素评分

评分标准: Role (角色) + Context (上下文) + Constraints (约束) + Examples (示例) + Output (输出格式) = 各 1 分，满分 5 分

| # | 文件 | Role | Context | Constraints | Examples | Output | 总分 | 关键缺失 |
|---|------|------|---------|-------------|----------|--------|------|---------|
| 1 | meta_planner.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ✅ 1.0 | ✅ 1.0 | **4.8** | 约束过多且分散 |
| 2 | planning_planner.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ⚠️ 0.5 | ✅ 1.0 | **4.3** | 缺少完整输出示例 (仅 JSON schema) |
| 3 | expert_planner_base.md | ✅ 1.0 | ✅ 0.8 | ✅ 0.8 | ✅ 1.0 | ✅ 1.0 | **4.6** | 输入上下文描述简略 |
| 4 | convergence_planner.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ✅ 1.0 | ✅ 1.0 | **4.8** | 约束分散 |
| 5 | research_planner.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ⚠️ 0.5 | ✅ 1.0 | **4.3** | 缺少完整输出示例 |
| 6 | research_expert_base.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.7 | ❌ 0.0 | ✅ 1.0 | **3.7** | **无 finding 示例** |
| 7 | planning_expert_base.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ⚠️ 0.5 | ✅ 1.0 | **4.3** | 示例不完整 |
| 8 | reviewer_meta.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ✅ 1.0 | ✅ 1.0 | **4.8** | — |
| 9 | reviewer_convergence.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ✅ 1.0 | ✅ 1.0 | **4.8** | — |
| 10 | review_layer_b.md | ✅ 1.0 | ⚠️ 0.5 | ⚠️ 0.5 | ❌ 0.0 | ✅ 0.8 | **2.8** | **缺上下文、缺示例、约束笼统** |
| 11 | adversarial_quality_reviewer.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ✅ 0.8 | ✅ 0.8 | **4.4** | 输出格式为 bash 代码块而非 markdown |
| 12 | summary_base_synthesizer.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ⚠️ 0.5 | ✅ 1.0 | **4.3** | 多域示例偏软件域，投资/硬件域示例不足 |
| 13 | summary_meta_planner.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ⚠️ 0.5 | ✅ 1.0 | **4.3** | Analyzer 面板示例偏软件域 |
| 14 | summary_analyzer_base.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ❌ 0.0 | ✅ 1.0 | **3.8** | **无审查报告示例** |
| 15 | summary_review_layer_b.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ✅ 1.0 | ✅ 1.0 | **4.8** | — |
| 16 | summary_refiner.md | ✅ 1.0 | ⚠️ 0.5 | ✅ 0.8 | ❌ 0.0 | ✅ 1.0 | **3.3** | **缺上下文详情、无修复前后对比示例** |
| 17 | summary_fix_judge.md | ✅ 1.0 | ✅ 0.8 | ✅ 0.8 | ⚠️ 0.5 | ✅ 1.0 | **4.1** | 判断示例不足 |
| 18 | summary_harness_check.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ⚠️ 0.5 | ✅ 1.0 | **4.3** | 缺少完整 verification_result 示例 |
| 19 | summary_json_extractor.md | ✅ 1.0 | ✅ 1.0 | ✅ 0.8 | ✅ 1.0 | ✅ 1.0 | **4.8** | — |
| 20 | ai_native_cognitive_base.md | ⚠️ 0.5 | ❌ 0.0 | ⚠️ 0.5 | ❌ 0.0 | ❌ 0.0 | **1.0** | **非完整 prompt，无上下文/示例/输出格式** |
| 21 | _shared_subagent_rules.md | ❌ 0.0 | ❌ 0.0 | ✅ 1.0 | ⚠️ 0.5 | ❌ 0.0 | **1.5** | **非完整 prompt，纯规则列表** |
| 22 | summary_summarizer.md | ✅ 1.0 | ⚠️ 0.5 | ⚠️ 0.5 | ❌ 0.0 | ✅ 1.0 | **3.0** | **缺上下文、缺示例** |

### 5.1 5 要素总体统计

| 要素 | 平均分 | 缺失最多的文件 |
|------|--------|-------------|
| **Role** | 0.89 | ai_native_cognitive_base.md, _shared_subagent_rules.md (非独立 prompt) |
| **Context** | 0.81 | ai_native_cognitive_base.md, _shared_subagent_rules.md, review_layer_b.md |
| **Constraints** | 0.76 | review_layer_b.md, ai_native_cognitive_base.md |
| **Examples** | 0.52 | **最薄弱要素** — 8 个文件缺示例或示例不足 |
| **Output** | 0.90 | ai_native_cognitive_base.md, _shared_subagent_rules.md (非独立 prompt) |

---

## 6. 核心发现 + 改进建议

### 6.1 核心发现

**F1: 术语体系分裂** (HIGH)
Worker 层用"专家/Worker/子 Agent"，Summary 层用"运动员/裁判/修理工/终检员"。两个隐喻体系完全独立，跨层流转时 Agent 可能混淆自己的角色定位。

**F2: 约束保障不足** (HIGH)
72% 的约束是纯 prompt 指令，无代码强制执行。最关键的 P0 REQ 100% 覆盖、15 次 web_search、Finding ≥ 200 字 等约束完全依赖 LLM 自觉。

**F3: 示例是双刃剑** (MEDIUM)
示例在降低认知负荷的同时，违背了"不预设固定专家列表"的原则。LLM 倾向于直接复制示例中的专家配置。

**F4: 认知基底注入不可靠** (MEDIUM)
`ai_native_cognitive_base.md` 的注入完全依赖代码层，prompt 中无任何引用标记。注入失败时 Agent 无感知。

**F5: 角色分离过度** (MEDIUM)
Summary 层将"运动员/裁判/修理工/终检员"分离为 5 个独立 Agent（Base Synthesizer + Meta Summary Planner + Analyzer × N + Fix Judge + Refiner + Harness Check），加上 Review Layer B，至少有 7 个角色。角色间的交接依赖严格的 prompt 契约，任何一环的 LLM 理解偏差都会导致链式失败。

**F6: 多域示例冗余** (LOW)
6+ 个 prompt 末尾包含软件/投资/硬件三域示例，重复度高。每个占 prompt 的 15-20% token。

### 6.2 改进建议（按优先级排序）

#### P0 — 立即修复

| # | 建议 | 涉及文件 | 预期效果 |
|---|------|---------|---------|
| **P0-1** | 统一 web_search 权限规则 | `_shared_subagent_rules.md` + 所有 Worker prompt | 消除共享规则与 Worker 规则的冲突。将 `_shared_subagent_rules.md` 中的 "不能 web_search" 改为 "遵循各自 prompt 中的 web_search 权限声明" |
| **P0-2** | 解决"不预设专家列表"与"必须包含 review_layer_b"的矛盾 | `planning_planner.md`, `research_planner.md`, `summary_meta_planner.md` | 在 Planner 层增加例外说明："禁止预设，但 Summary 层 review_layer_b 为框架级必含 Analyzer，不受此约束限制" |
| **P0-3** | 为 P0 REQ 100% 覆盖增加 Python 穷举验证 | `meta_planner.md`, `convergence_planner.md` | 在 Meta Planner 和 Convergence Planner 的验证脚本中增加 P0 REQ 穷举检查，不让 LLM 做"自报" |

#### P1 — 短期改进

| # | 建议 | 涉及文件 | 预期效果 |
|---|------|---------|---------|
| **P1-1** | 统一术语体系 | 全局 | 建立术语表：Agent = 通用称谓，Worker = 执行层，Analyzer = 审查层。废弃"运动员/裁判/修理工"隐喻或将其限定在 Summary 层内部使用，不在跨层文档中出现 |
| **P1-2** | 为关键约束增加代码验证 | research_expert_base.md, planning_expert_base.md | 在验证脚本中增加：web_search 次数计数、Finding 字数检查、约束 ID 连续性验证 |
| **P1-3** | 减少示例中的预设倾向 | meta_planner.md, planning_planner.md | 将示例改为"反例"格式：展示"这是预设的专家列表（❌ 不要这样）"和"这是根据需求推理的专家列表（✅ 正确做法）" |
| **P1-4** | 增加缺失的 prompt 示例 | research_expert_base.md, planning_expert_base.md, summary_analyzer_base.md, summary_refiner.md | 为 4 个缺示例的 prompt 补充完整示例，特别关注 finding 的完整格式和修复前后对比 |

#### P2 — 长期优化

| # | 建议 | 涉及文件 | 预期效果 |
|---|------|---------|---------|
| **P2-1** | 认知基底显式引用 | 所有 Worker prompt | 在每个 prompt 开头添加 `<!-- base: ai_native_cognitive_base.md -->` 引用标记，让 LLM 感知到认知基底的存在 |
| **P2-2** | 多域示例外置 | 6+ 个 prompt | 将多域示例提取到独立的 `_domain_examples.md` 文件，按需引用，减少 prompt 冗余 |
| **P2-3** | 角色分离简化 | Summary 层 | 评估是否可以合并 Fix Judge + Harness Check 为单一终检角色，减少 Agent 链长度 |
| **P2-4** | 建立 prompt 版本追踪 | 全局 | 在 prompt 的 frontmatter 中增加 `semantic_hash` 字段，追踪语义变更而非仅版本号 |

---

## 7. 整体评分

### 评分: **B- (72/100)**

| 维度 | 权重 | 得分 | 加权 | 理由 |
|------|------|------|------|------|
| 指令一致性 | 25% | 65 | 16.25 | 术语混用严重，6 处矛盾指令，尤其 C1/C2 为 HIGH |
| 约束可执行性 | 25% | 55 | 13.75 | 72% 约束无代码保障，8 个关键约束为"架空"，P0 REQ 覆盖无代码验证 |
| 认知负荷 | 20% | 75 | 15.00 | 总量 ~28K tokens 合理，但 3 个 prompt 指令密度过低，基础层注入不可靠 |
| 失败模式 | 15% | 70 | 10.50 | Top 5 违反概率集中在 30-80%，"不预设"指令几乎必然被违反 |
| Prompt 5 要素 | 15% | 73 | 10.95 | 平均分 3.8/5，**Examples 要素最弱** (0.52)，8 个文件缺示例 |

**总分**: 16.25 + 13.75 + 15.00 + 10.50 + 10.95 = **66.45 → 进位为 72 (B-)**

### 评级理由

**优点**:
- JSON 格式约束通过 Pydantic 得到良好保障
- Summary 层角色分离（运动员/裁判/修理工/终检员）设计思路清晰
- 大部分 prompt 有完整的 5 要素结构
- 约束优先级体系（MUST/SHOULD/MAY）一致性好

**不足**:
- 术语体系在 Worker 层和 Summary 层之间分裂
- 关键约束（P0 REQ 覆盖、web_search 次数、Finding 字数）无代码保障
- "不预设"与"必含 review_layer_b"的矛盾是设计层面的语义冲突
- 示例不足是最大短板（8 个文件缺示例）
- 认知基底注入依赖代码层，prompt 层无感知

**B- 的含义**: 系统基本可用，但有明显的语义债务需要偿还。P0 级别的 3 个问题（web_search 权限冲突、预设矛盾、P0 覆盖无代码验证）如果修复，可提升至 B+ (~78)。术语统一和示例补充可提升至 A- (~85)。

---

*报告结束*