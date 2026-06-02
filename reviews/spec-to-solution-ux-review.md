# 产品体验评审：Spec Pro → Solution Pro 链路中的用户视角问题

## 执行摘要

**问题定性（已部分修复 2026-06-03）**：Spec Pro 产出的 rich living_spec 在经过 `frozen_spec.py` 扁平化为 REQ-ID 列表后，~~虽然字段没有丢失，但**语义关系和用户叙事的上下文丢失**~~ → **已修复**：frozen_spec V2.0 现已全量提取 17 种 category（98 条 REQ），包括 constraints 全量遍历 + guardrails.resolved + inferred。但叙事感问题（层级 1-3）仍待实施。

---

## 1. 从用户角度看，信息丢失会带来什么影响？

### 1.1 方案"正确但冰冷"

用户经历了一个多轮对话的 Spec Pro 过程，花了 5 轮、表达了自己的痛点、场景、约束。最终 Solution Pro 产出的方案：

- ✅ **功能覆盖正确** — 每个 REQ-ID 都有覆盖
- ❌ **没有叙事感** — 方案像是"需求清单的机械翻译"，而非"针对这个用户痛点的定制化方案"

**用户感知**："这个方案放在任何简历工具上都适用，没有针对我的场景做深度思考。"

### 1.2 痛点与解决方案之间缺少因果链

以 `living_spec.json` 中的真实数据为例：

| Living Spec 原始信息 | Frozen Spec 中变成了什么 | 丢失了什么 |
|---|---|---|
| `pain_points: ["每次针对不同岗位需手动调整简历内容", "难以保证简历与JD的高度贴合和专业呈现"]` | `REQ-043: "每次针对不同岗位需手动调整简历内容"` (category: pain_point) | ⚠️ 痛点与解决方案的映射关系仍待加强（executive_summary.why 已注入，但 worker 不一定利用） |
| `users: [{"role": "半导体封装全领域求职者", "key_needs": "针对不同猎头推送的职位信息快速生成定向优化简历"}]` | `REQ-049: "半导体封装领域求职者"` | ✅ 已修复：executive_summary.for_whom 包含完整 role + key_needs，注入到 worker prompt |
| `success_metrics: [{"metric": "JD贴合度", "target": "与目标JD高度贴合"}]` | `REQ-045: "JD贴合度"` | ✅ 已修复：executive_summary.success_criteria 包含完整 "metric: target" 对，注入到 worker prompt |
| `key_scenarios: ["收到猎头职位信息（文字或图片）→ 输入职位信息和公司信息 → 系统产出定制化PDF简历"]` | `REQ-051: "用户提供固定基础简历 + 目标岗位JD + 公司信息 → 系统生成定制化PDF简历"` | ⚠️ 保留了，但变成了"又一条需求"而非"用户旅程的核心叙事"（待层级 1-3 改进） |

### 1.3 优先级失真

Living Spec 中用户明确说了：
- **"这是个人工具，不是企业级产品"** — 设计哲学是"优雅简洁"
- **"不要引入不必要的企业级架构复杂度"** — 反复强调 3 次

但 frozen_spec 中，这些被平铺成 7 条 prohibition/guardrail + 7 条 design_decision。~~worker 看到它们时，不会感受到用户反复强调的**焦虑程度**~~ → **部分修复**：executive_summary 和 guardrails 已透传到 frozen_spec.json，spec_context.py 注入到 worker prompt。但焦虑程度的量化传达（如"强调 3 次"）仍待改进。

### 1.4 场景之间的先后关系和权重被抹平

Living Spec 中的 3 个 key_scenarios 有不同的重要性：
- 场景1（用户提供基础简历+JD+公司信息）是**核心流程**
- 场景2（收到猎头职位信息→输入→产出）是**高频触发**
- 场景3（针对特定岗位方向侧重表述）是**差异化能力**

Frozen Spec 中它们变成 REQ-051/052/053，权重完全平等。

---

## 2. 用户期望 Solution Pro 的方案能体现哪些信息？

按重要性排序：

### ⭐ 必体现（用户会明显感知缺失）

| 信息类型 | 用户期望体现在方案中 | 示例 |
|---|---|---|
| **核心痛点** | 方案设计要直接回应"为什么做这个" | 如果痛点是"每次手动调整"，方案应该有"自动适配 JD"的核心能力描述 |
| **用户画像 + key_needs** | 方案要针对"谁在用"，不只是"功能列表" | "半导体封装求职者"→ 方案应体现行业专业性，不是一般化的简历工具 |
| **设计哲学/约束** | 方案的架构选型要和用户预期一致 | 用户反复说"不要过度工程化"，方案就不能给出微服务+K8s 架构 |
| **关键场景** | 方案的核心流程要覆盖用户最重要的使用场景 | 用户最在意的场景应该在方案的"核心流程设计"中被重点描述 |

### ✅ 应该体现（用户会注意到但不一定不满）

| 信息类型 | 用户期望体现在方案中 |
|---|---|
| **成功指标** | 方案应包含可量化的验收标准 |
| **风险和假设** | 方案的风险缓解策略应覆盖用户已识别的风险 |
| **对标产品** | 如果用户提到过对标对象，方案应对比分析 |

### 💡 加分项（用户会惊喜）

| 信息类型 | 用户期望体现在方案中 |
|---|---|
| **对话中的反复强调点** | Spec Pro 多轮对话中用户反复提及的点，应在方案中给予更高权重 |
| **用户明确拒绝的方向** | 用户说"不要 XXX"的地方，方案应明确说明"为什么不采用 XXX" |
| **质量轨迹** | 哪些维度是用户最难表达的（低分维度），方案应给予更多关注 |

---

## 3. 如何在不增加用户操作的情况下传递上下文？

### 现状分析

当前链路：

```
Living Spec (rich, nested, 95分)
    ↓ frozen_spec.py
Frozen Spec (flat REQ-ID list, 74条)
    ↓ data_collection 阶段（只做 web_search，不读 living_spec）
    ↓ Planning 阶段（只读 frozen_spec.json）
    ↓ Research/Design workers（只读 tasks.json 中的 task prompt）
```

**根本问题**：`frozen_spec.py` 把 rich context 拆成了扁平 REQ，但后续 worker 的 prompt 中**没有重新注入**这些上下文。

### 三个改进层级

---

```python
from domains.solution.frozen_spec import build_frozen_spec
# V2.0 (2026-06-03): 全量提取 17 种 category，98 条 REQ
frozen = build_frozen_spec(topic, living_spec=living_spec)
# frozen["executive_summary"] 包含完整 why/for_whom/success_criteria/constraints
# frozen["guardrails"] 透传 always_do/never_do/resolved
# frozen["solution_pro_hints"] 透传 focus_areas/layer2_hints/anti_patterns
```

**改动摘要**（2026-06-03）：
1. constraints 从硬编码 3 个 key → 遍历所有 key（11 条）
2. guardrails.resolved 新增提取（7 条 design_decision）
3. inferred 新增提取（10 条）
4. 信息保留率从 <5% → ~100%

---

#### 层级 1：最小改动（推荐优先实施）

**改动点**：在 `frozen_spec.py` 生成的 `frozen_spec.json` 中增加一个 `context_narrative` 字段。

```json
{
  "version": "1.0",
  "topic": "...",
  "requirements": [...],
  "context_narrative": {
    "user_story": "一段话描述：谁、什么痛点、期望什么结果",
    "design_philosophy": "用户强调的设计原则",
    "key_scenarios_summary": "2-3个核心场景的简要描述",
    "deal_breakers": "用户明确拒绝的方向",
    "quality_score": 95,
    "conversation_rounds": 5
  }
}
```

**注入时机**：在 pipeline orchestrator 的 `data_collection` 阶段 prompt 中，增加一段前置描述：

```markdown
## 项目背景（来自 Spec Pro 需求梳理）

**用户是谁**：{user_story}
**核心痛点**：{pain_points 摘要}
**设计原则**：{design_philosophy}
**用户明确拒绝的方向**：{deal_breakers}

这些不是功能需求，而是理解"为什么做"的上下文。请在设计中体现对这些痛点的回应。
```

**优势**：
- 0 用户操作
- 改动集中在 `frozen_spec.py` 和 data_collection prompt
- 所有 worker 都能通过 data_collection 的输出间接获得上下文

**工作量**：~2 小时

---

#### 层级 2：中等改动（推荐第二阶段实施）

**改动点**：在 Planning 阶段的 task prompt 中，注入 `living_spec_readable.md`（人类可读版本）。

当前 Spec Pro 已经生成了 `living_spec_readable.md`（在 `spec_spec_db44b60d/spec/` 下），但 Solution Pro 完全不读它。

**具体做法**：
1. 在 Solution Pro 启动时，如果有 `living_spec` 输入，除了生成 `frozen_spec.json`，同时生成一个 `spec/context_brief.md`
2. 这个文件包含：
   - 用户画像摘要（含 key_needs）
   - 痛点列表（按用户在对话中的强调程度排序）
   - 核心场景（带优先级标记）
   - 质量属性（含优先级和 target）
   - 用户反复强调的设计约束
   - 明确拒绝的方向
3. 在 Planning worker prompt 中增加 `## 用户上下文` 段落，指向这个文件

**优势**：
- Planner 是 Solution Pro 的"大脑"，如果 Planner 理解了上下文，它会通过 `required_experts` 和 `layer2_constraints` 把上下文传递给 downstream workers
- 利用了已有的 `living_spec_readable.md`，不需要额外生成

**工作量**：~4 小时

---

#### 层级 3：深度改进（长期方向）

**改动点**：在每个 worker 的 task prompt 中，基于该 worker 的 `covered_req_ids` 自动关联回 living_spec 的上下文。

**示例**：
- 当 Research Worker 被分配覆盖 REQ-043 (pain_point: "每次针对不同岗位需手动调整简历内容") 时
- prompt 中自动附加："⚡ 这是一个用户痛点。你的研究应该重点关注自动化 JD 适配的业界方案。"
- 当 Research Worker 被分配覆盖 REQ-049 (user: "半导体封装领域求职者") 时
- prompt 中自动附加："👤 这是目标用户。你的研究应考虑半导体封装行业的特殊性。"

**实现方式**：在 `control_contract.py` 生成 task prompt 时，根据 `covered_req_ids` 查找对应 REQ 的 `category`，自动附加 category 对应的上下文模板。

**优势**：
- 最精准——每个 worker 只看到和它相关的上下文
- 不增加无关信息负担

**工作量**：~8 小时

---

## 4. 具体改进建议（按优先级排序）

### P0：修复 `frozen_spec.py` 中的数据丢失

**问题**：当前代码对 `user` 的处理只取了 `role` 字段，丢失了 `detail` 和 `key_needs`。

```python
# 当前代码（✅ 已修复 2026-06-03）
for item in confirmed.get("users", []) or []:
    if isinstance(item, dict):
        role = item.get("role", "") or item.get("description", "")
        # role 已保留，key_needs 通过 executive_summary.for_whom 注入到 worker prompt
```

> **状态**: ✅ 已实施。executive_summary.for_whom 包含完整 role + description，spec_context.py 的 `build_worker_context_section()` 注入到各 worker prompt。

**同理**：`success_metrics` 的 `target` 字段：

> **状态**: ✅ 已实施。executive_summary.success_criteria 以 `"metric: target"` 格式完整保留。

### P1：在 `data_collection` 阶段注入用户叙事

修改 `prompts/data_collection.md`，增加前置上下文段落：

```markdown
## 项目上下文（来自需求梳理阶段）

> **谁在用**：{{USER_STORY}}
> **为什么做**：{{PAIN_POINTS_SUMMARY}}
> **做对的标准**：{{SUCCESS_METRICS_SUMMARY}}
> **不要做什么**：{{DEAL_BREAKERS}}

这些上下文帮助你理解"为什么做"，而不仅仅是"做什么"。
请在行业调研中特别关注与这些痛点相关的解决方案。
```

其中变量由 pipeline orchestrator 在 spawn data_collection worker 前，从 `frozen_spec.json` 中提取并注入。

### P2：在 `final_solution.md` 中增加"用户需求回应"章节

当前 Summarizer 输出的是"需求覆盖度"（REQ-ID 覆盖矩阵），建议增加一个面向用户的章节：

```markdown
## 用户需求回应

| 用户痛点 | 方案设计如何回应 |
|---|---|
| 每次针对不同岗位需手动调整简历 | 设计了 JD 自动解析 + 内容智能适配模块，用户只需上传 JD 即可自动生成定制化内容 |
| 难以保证简历与 JD 的高度贴合 | 引入语义相似度评分机制，生成后自动评估贴合度并给出优化建议 |

| 用户核心场景 | 方案覆盖方式 |
|---|---|
| 收到猎头职位信息→输入→产出定制化简历 | 设计了快捷输入通道（文字/图片 OCR→自动解析→一键生成） |
```

这个章节让用户直观看到"我的痛点被理解并回应了"。

### P3：在 Harness 质量门禁中增加"灵魂检查"

当前 Harness Final 是 4 维评分（完整性/必要性/目标一致性/全局影响），建议增加一个维度：

| 维度 | 检查项 |
|---|---|
| **用户场景覆盖度** | 方案是否回应了 living_spec 中标注的每个 key_scenario 和 pain_point？ |
| **设计哲学对齐** | 方案的架构选型是否与用户强调的设计原则一致？（如"不要过度工程化"） |

这个维度可以命名为 **"User Empathy"** 或 **"Context Alignment"**。

---

## 总结

| 问题 | 影响 | 建议方案 | 工作量 |
|---|---|---|---|
| 用户画像信息丢失 | ~~方案不针对目标用户~~ → 已修复 | P0: ~~修复 frozen_spec.py 的字段提取~~ → ✅ 已完成 | ~~30min~~ |
| 成功指标 target 丢失 | ~~验收标准模糊~~ → 已修复 | P0: ~~保留 target 值~~ → ✅ 已完成 | ~~10min~~ |
| 上下文不传递给 worker | 方案缺少叙事感 | P1: data_collection 注入上下文 | 2h |
| 最终方案看不出对用户痛点的回应 | 用户感觉"方案正确但冰冷" | P2: 增加"用户需求回应"章节 | 1h |
| 质量门禁缺少用户视角检查 | 可能产出技术上正确但用户体验差的方案 | P3: Harness 增加灵魂检查 | 2h |

**核心观点**：用户不关心 REQ-ID 覆盖率是 95% 还是 100%。用户关心的是——"你理解我的痛点吗？你的方案能解决我的问题吗？"。当前的机制保证了前者（需求覆盖），但牺牲了后者（用户共情）。通过上述改进，可以在不增加用户操作的情况下，让 Solution Pro 的方案既有"正确性"也有"灵魂"。
