# Research Module V3 架构设计

> **版本**: V3.0.0 | **日期**: 2026-06-30 | **状态**: 已确认
> **设计原则**: Planning 决定下限,Research 决定上限

---

## 核心设计理念

1. **深度优先**:宁可每个 finding 写 500 字有 evidence 的分析,不要 50 个一句话的浅层结论
2. **自由输出**:Expert 用 markdown 研究报告,不强制 JSON schema。信息不被格式削掉
3. **内部循环**:不是一轮就完--有 Research Planner 规划、有 Gap Analyst 查缺、有 Devil's Advocate 对抗
4. **收敛推迟**:Research 内部只做轻量合并,结构化收敛推迟到 Summary 模块

---

## 三模块整体架构

```
Planning(粗规划,结构化 JSON)
  ↓ planning_convergence(统一约束 + 验证清单)
Research(重度研究,自由 markdown)
  ↓ research_report.md + research_metadata.json(完整、不压缩)
Summary(收敛 + 格式化 → final_solution JSON + markdown_document)
```

**Research 负责"宽进",Summary 负责"严出"。**

---

## Research 内部 5 Phase 架构

### Phase 0: 知识新鲜度检查
- **目的**:确保研究基于最新技术信息
- **方法**:web_search 每个 P0 需求涉及的技术领域
- **输出**:`knowledge_freshness` stage(自由 markdown)

### Phase 1: Research Planner(关键角色)
- **目的**:不预设固定专家列表,根据具体问题动态规划研究团队
- **输入**:planning_convergence + knowledge_freshness + frozen_spec
- **职责**:
  1. 分析问题的领域特征(架构密集?安全敏感?数据密集?)
  2. 决定需要哪些专家(不固定,动态生成)
  3. 决定专家数量(简单 2-3 个,复杂 5-6 个)
  4. 为每个专家定义 research_questions(具体问题)和 focus_req_ids
  5. 定义"研究到位"的质量标准
  6. ~~对抗配置~~（Devil's Advocate 已改为必做，不需要配置）
- **输出**：`research_plan` stage（markdown）

### Phase 2: 专家深度研究(并行)
- **目的**:每个 Expert 从自己的视角做深度研究
- **关键设计**:
  - Expert 数量由 Research Planner 决定(不固定)
  - Expert 输出是**自由 markdown**(不强制 JSON schema)
  - 每个 Expert 必须读 `planning_convergence`(确保研究与约束对齐)
  - 每个 Expert 必须回答 `research_plan` 中分配的 research_questions
- **输出**:每个 Expert 一份 markdown 研究报告,写入 `research_experts/` 目录

### Phase 3: 查缺补漏 + 对抗（串行，必做）
- **3a. Gap Analyst**（能做 web_search 验证）：
  - 读所有 Expert 报告 + planning_convergence + 质量标准
  - 🔴 可以使用 web_search 验证 Expert 的 finding（不是纸上谈兵）
  - 找出：未覆盖的需求（不限 P0）、Expert 间矛盾、缺乏 evidence 的 finding、被忽略的维度
  - 输出：`gap_analysis` stage
- **3b. Devil's Advocate**（必做，能做 web_search 对抗）：
  - 🔴 必做，不是条件触发。每一轮研究都必须经过对抗检验
  - 🔴 可以使用 web_search 寻找反面证据（用事实对抗，不是逻辑对抗）
  - 质疑技术推荐 → 搜索替代方案；质疑 finding → 搜索反例/失败案例
  - 输出：`devil_advocate` stage

### Phase 4: 补充研究（必做，固定 1 轮）
- 🔴 必做，不是可选。Gap Analyst 和 Devil's Advocate 一定会找到需要补充的点
- 编排器不需要分支判断——直接走 Phase 4
- 合并 gap_analysis + devil_advocate 的补充建议 → spawn 补充 Expert（1-3 个）
- 只跑 1 轮（不迭代，避免无限循环）
- **输出**：补充 Expert 报告，写入 `research_experts/` 目录，文件名前缀 `supplementary_`

### Phase 5: 轻量收敛
- **做的事**:按主题分组 + 标记冲突 + 附 metadata + **保留所有原始报告完整内容**
- **不做的事**:字段提取、JSON schema 映射、信息压缩
- **输出**:
  - `research_report` stage(完整 markdown,含所有 Expert 报告 + Gap 分析 + 对抗结果)
  - `research_metadata` stage(最小结构化 JSON:covered_req_ids, expert_count, rounds, conflicts)

---

## Expert 输出格式规范

```markdown
# [Expert 角色名] 研究报告

## 研究范围
(我负责回答的 research_questions)

## 发现与分析
### Finding 1: [标题]
[详细分析,200+ 字,包含具体技术名称+版本+量化数据]
**Evidence**: [具体来源/数据/案例/论文]

### Finding 2: [标题]
...

## 技术推荐(如果有)
对比评估:X vs Y vs Z
选择建议 + 理由

## 风险识别
(从我的视角发现的风险)

## 开放问题
(研究中遇到但未解决的问题)

## 覆盖需求
covered_req_ids: [REQ-001, REQ-005, ...]
```

---

## Research Planner 输出格式规范

```markdown
# Research Plan

## 1. 领域分析
- 核心领域:...
- 技术复杂度:高/中/低
- 约束分布:安全 X 条 / 架构 Y 条 / 性能 Z 条

## 2. 专家面板

### Expert 1: [角色名]
- **视角**:...
- **research_questions**:
  1. [具体问题 1]
  2. [具体问题 2]
- **focus_req_ids**:REQ-001, REQ-005
- **期望深度**:需要具体技术名称+版本+量化数据

### Expert N: [角色名]
- ...

## 3. 研究质量标准
- 每个 finding 必须有 evidence
- P0 需求必须被至少 1 个 Expert 深入分析
- 技术推荐必须有对比评估

## 4. 对抗配置
- Devil's Advocate: 是/否
- 触发条件:...
```

---

## 数据流全景

```
frozen_spec (需求)
    ↓
Planning Module → planning_convergence (约束体系,结构化 JSON)
    ↓
Research Module:
    Phase 0: knowledge_freshness (web search 结果,markdown)
    Phase 1: research_plan (专家面板规划,markdown)
    Phase 2: expert_1.md, expert_2.md, ..., expert_N.md (自由 markdown)
    Phase 3: gap_analysis.md + devil_advocate.md (markdown, 含 web_search 验证/对抗)
    Phase 4: supplementary_expert.md (必做，markdown)
    Phase 5: research_report.md (完整汇编) + research_metadata.json (最小结构化)
    ↓
Summary Module:
    读 research_report.md (完整内容,不压缩)
    读 planning_convergence (约束体系)
    → QC 验证 + 方案综合
    → final_solution (结构化 JSON) + markdown_document (最终文档)
```

---

## 与旧版(V2)对比

| 维度 | 旧版(V2) | 新版(V3) |
|------|-----------|-----------|
| 专家确定方式 | 固定列表 | Research Planner 动态决定 |
| 专家数量 | 固定 4-6 个 | 由问题复杂度决定(2-6 个) |
| 输出格式 | 强制 JSON schema | 自由 markdown 研究报告 |
| 对抗机制 | 无 | Gap Analyst（web_search验证） + Devil's Advocate（web_search对抗，必做） |
| 迭代轮数 | 1 轮 | 固定 2 轮（首轮研究 + 补充研究） |
| 收敛方式 | 结构化压缩 | 不压缩,原文照搬 |
| Planning→Research | 断裂 | 强制读取 planning_convergence |
| 收敛职责 | Research 内部 | 推迟到 Summary |
| 信息保真率 | ~65%(审计实测) | 目标 >90% |

---

## 业界参考

- **OpenAI Deep Research**:Scope → Research → Write 三阶段,多轮迭代,Debate 技术
- **Multi-agent Deep Research**(2025-2026):模块化架构,迭代反馈循环,多轮对抗测试
- **DeepFlow Research Pro**:多专家并行 + 知识新鲜度检查

---

## 决策记录

| 日期 | 决策 | 参与者 |
|------|------|--------|
| 2026-06-30 | Research 输出不强制 JSON schema,用自由 markdown | 忠礼 + 小满 |
| 2026-06-30 | 新增 Research Planner 角色,动态决定专家面板 | 忠礼 + 小满 |
| 2026-06-30 | 新增 Gap Analyst + Devil's Advocate 对抗机制 | 忠礼 + 小满 |
| 2026-06-30 | 收敛职责从 Research 推迟到 Summary | 忠礼 + 小满 |
| 2026-06-30 | 补充研究最多 1 轮（避免无限循环） | 忠礼 + 小满 |
| 2026-06-30 | Gap Analyst / Devil's Advocate 能用 web_search 做验证/对抗 | 忠礼 + 小满 |
| 2026-06-30 | Devil's Advocate 和 Phase 4 补充研究改为必做（非条件触发），简化编排 | 忠礼 + 小满 |
