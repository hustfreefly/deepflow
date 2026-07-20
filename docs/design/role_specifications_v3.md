# Solution Pro V3 — 全角色规格说明书

> **版本**: V1.0.0 | **日期**: 2026-06-30 | **状态**: 已确认
> **覆盖模块**: Orchestrator / Research V3 / Planning V3 / Summary V3

---

## 目录

- [一、角色总览](#一角色总览)
- [二、Orchestrator](#二orchestrator)
- [三、Deep Analysis Engine 通用角色（Research + Planning 共享）](#三deep-analysis-engine-通用角色research--planning-共享)
- [四、Research 专属角色](#四research-专属角色)
- [五、Planning 专属角色](#五planning-专属角色)
- [六、Summary V3 角色](#六summary-v3-角色)
- [七、调度经验教训](#七调度经验教训)
- [八、Prompt 编写规范](#八prompt-编写规范)

---

## 一、角色总览

### 1.1 模块架构对比

| 模块 | 方向 | Phase 数 | 角色数 |
|------|------|---------|--------|
| Orchestrator | 调度 | 3 步 | 1 |
| Research | 发散 | 5 Phase | 6 |
| Planning | 发散 | 5 Phase | 6 |
| Summary | 收敛 | 5+1 Phase | 7 |

### 1.2 角色清单

| 模块 | 角色 | 类型 | 职责一句话 |
|------|------|------|-----------|
| **Orchestrator** | Orchestrator | 调度器 | 按顺序 spawn Planning → Research → Summary，验证完成 |
| **Research/Planning** | Module Agent | 模块编排器 | 管理模块内 Phase 0-5 的 spawn/yield/verify 循环 |
| **Research/Planning** | Knowledge Freshness Agent | Worker | web_search 最新技术信息 |
| **Research/Planning** | Planner (Research/Planning) | Worker | 分析上游，动态规划专家面板 |
| **Research/Planning** | Expert × N | Worker | 从指定视角做深度分析，输出自由 markdown |
| **Research/Planning** | Gap Analyst | Worker | 审查 Expert 输出，web_search 验证缺失 |
| **Research/Planning** | Devil's Advocate | Worker | 挑战 Expert 结论，web_search 找反面证据 |
| **Research/Planning** | Supplementary Expert × N | Worker | 针对性补充研究 |
| **Summary** | Base Synthesizer | Worker | 吸收所有知识，产出基础方案 |
| **Summary** | Meta Summary Planner | Worker | 审视基础方案，规划 Phase 3-5 策略 |
| **Summary** | Analyzer × N | Worker | 从指定角度审查基础方案 |
| **Summary** | Fix Judge | Worker | 综合判断哪些建议采纳/拒绝/折中 |
| **Summary** | Fix Agent | Worker | 执行定向修复 |
| **Summary** | Verification Agent | Worker | 执行 verification_checklist |
| **Summary** | Document Generator | Worker | 产出完整方案文档 |
| **Summary** | JSON Extractor | Worker | 从文档中提取结构化元数据 |

---

## 二、Orchestrator

### Orchestrator（调度器）

| 属性 | 值 |
|------|-----|
| **类型** | 调度器（depth-1） |
| **职责** | 按顺序执行 Planning → Research → Summary 三个模块 |
| **Prompt 文件** | `prompts/v2_orchestrator.md` |

**输入（可读）**：
- `living_spec`（MD source of truth，JSON fallback）— 原始需求
- Blackboard 各 stage（验证用）

**权限**：
- ✅ spawn Planning/Research/Summary 模块 Agent
- ✅ sessions_yield 等待模块完成
- ✅ 读 Blackboard 验证输出
- ✅ 写 `.stage_progress` 和 `master_state.json`
- ✅ 写 `.failed` 文件终止 pipeline
- ❌ 不能自己生成模块输出
- ❌ 不能修改 living_spec

**输出**：
- `master_state.json` — pipeline 状态
- `.stage_progress` — 阶段进度
- `.completed` — 完成标记（所有模块完成后）
- `.failed` — 失败标记（任何模块失败时）

**依赖关系**：
```
Orchestrator
  ├── spawn → Planning Module Agent
  ├── spawn → Research Module Agent（等 Planning 完成后）
  └── spawn → Summary Module Agent（等 Research 完成后）
```

**调度逻辑**：
```
Step 1: spawn Planning → yield → 验证 planning_convergence
  → PASS → Step 2
  → FAIL → 写 .failed，终止

Step 2: spawn Research → yield → 验证 research_report + research_metadata
  → PASS → Step 3
  → FAIL → 写 .failed，终止

Step 3: spawn Summary → yield → 验证 final_solution + solution_document
  → PASS → 写 .completed
  → FAIL → 写 .failed，终止
```

---

## 三、Deep Analysis Engine 通用角色（Research + Planning 共享）

> Research 和 Planning 共享相同的 Phase 0-5 编排架构。
> 以下角色规格对两者都适用，差异通过 `role` 参数区分。

### 3.1 Module Agent（模块编排器）

| 属性 | Research | Planning |
|------|----------|----------|
| **类型** | 模块编排器（depth-2） | 模块编排器（depth-2） |
| **Prompt 文件** | `prompts/v2_research_module.md` | `prompts/v2_planning_module.md` |
| **职责** | 管理 Research Phase 0-5 | 管理 Planning Phase 0-5 |

**输入（可读）**：
- `living_spec`（MD source of truth，JSON fallback）
- **Research**: `planning_convergence`（Planning 产出）
- **Planning**: 无上游模块依赖（Planning 是第一个模块）

**权限**：
- ✅ spawn Phase 0-5 的 Worker Agent
- ✅ sessions_yield 等待 Worker 完成
- ✅ 读 Blackboard 验证输出
- ✅ 写 stage 文件
- ❌ 不能自己生成 Worker 输出
- ❌ 不能修改上游模块输出

**输出**：
- **Research**: `research_report`（markdown）+ `research_metadata`（JSON）
- **Planning**: `planning_convergence`（JSON）
- `research_completed` / `planning_completed` — 完成标记

**依赖关系**：
```
Module Agent
  ├── spawn → Knowledge Freshness Agent (Phase 0)
  ├── spawn → Planner (Phase 1)
  ├── spawn → Expert × N (Phase 2)
  ├── spawn → Gap Analyst (Phase 3a)
  ├── spawn → Devil's Advocate (Phase 3b)
  ├── spawn → Supplementary Expert × N (Phase 4)
  └── 写 → convergence stage (Phase 5)
```

**调度逻辑**：
```
Phase 0: spawn Knowledge Freshness → yield → 验证 knowledge_freshness
Phase 1: spawn Planner → yield → 验证 research_plan / planning_plan
Phase 2: spawn Expert × N（并行）→ yield → 验证所有 expert 输出
Phase 3a: spawn Gap Analyst → yield → 验证 gap_analysis
Phase 3b: spawn Devil's Advocate → yield → 验证 devil_advocate
Phase 4: spawn Supplementary Expert × N → yield → 验证补充输出
Phase 5: 写 convergence stage
```

---

### 3.2 Knowledge Freshness Agent（Phase 0）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-3） |
| **职责** | 搜索上游输入涉及的技术领域的最新进展 |

**输入（可读）**：
- `living_spec`（MD source of truth，JSON fallback）— 提取需要搜索的技术领域

**权限**：
- ✅ `web_search` 搜索最新技术信息
- ✅ 写 Blackboard stage
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改 living_spec

**输出**：
- **stage 名称**: `knowledge_freshness`
- **格式**: 自由 markdown
- **内容**: 每个搜索主题的发现、与需求的关联分析、source URL

---

### 3.3 Planner（Phase 1）

| 属性 | Research Planner | Planning Planner |
|------|-----------------|-----------------|
| **类型** | Worker（depth-3） | Worker（depth-3） |
| **Prompt 文件** | `prompts/research_planner.md` | `prompts/planning_planner.md`（待创建） |
| **职责** | 规划研究专家面板 | 规划分析专家面板 |

**输入（可读）**：
- `living_spec`（MD source of truth，JSON fallback）
- `knowledge_freshness`（Phase 0 产出）
- **Research**: `planning_convergence`（Planning 产出）
- **Planning**: 无上游模块依赖

**权限**：
- ✅ 读 Blackboard
- ✅ 写 Blackboard stage
- ❌ 不能 spawn 子 Agent
- ❌ 不能 `web_search`
- ❌ 不能修改上游输出

**输出**：
- **stage 名称**: `research_plan` / `planning_plan`
- **格式**: markdown
- **必须包含**：
  1. 领域分析（问题特征、复杂度）
  2. 专家面板（每个专家：角色、research_questions、focus_req_ids、期望深度）
  3. 质量标准（什么算"分析到位"）
  4. ~~对抗配置~~（Devil's Advocate 已改为必做，不需要配置）

---

### 3.4 Expert（Phase 2）× N

| 属性 | Research Expert | Planning Expert |
|------|----------------|-----------------|
| **类型** | Worker（depth-3） | Worker（depth-3） |
| **Prompt 文件** | `prompts/research_expert_base.md` | `prompts/planning_expert_base.md`（待创建） |
| **职责** | 深度研究 findings | 深度分析约束 |

**输入（可读）**：
- `living_spec`（MD source of truth，JSON fallback）
- `knowledge_freshness`
- `research_plan` / `planning_plan`（找到自己的 research_questions）
- **Research**: `planning_convergence`（约束对齐）
- **Planning**: 无上游模块依赖

**权限**：
- ✅ `web_search` 搜索最新信息
- ✅ 读 Blackboard
- ✅ 写 Blackboard stage
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改上游输出

**输出**：
- **stage 名称**: `research_experts/[name].md` / `planning_experts/[name].md`
- **格式**: 自由 markdown
- **必须包含**：
  1. 研究范围（从 plan 中提取的 research_questions）
  2. 发现与分析（每个 Finding ≥ 200 字，含 evidence）
  3. 技术推荐（如有，含对比评估）
  4. 风险识别
  5. 开放问题
  6. `covered_req_ids` 列表
- **禁止**：浅层结论、无 evidence 的声称

---

### 3.5 Gap Analyst（Phase 3a）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-3） |
| **Prompt 文件** | `prompts/gap_analyst.md`（通用，Research/Planning 共享） |
| **职责** | 审查 Expert 输出，找出缺失和问题，web_search 验证 |

**输入（可读）**：
- `research_experts/` 或 `planning_experts/` — 所有 Expert 报告
- `research_plan` / `planning_plan` — 质量标准
- `living_spec`（MD source of truth，JSON fallback）
- **Research**: `planning_convergence`

**权限**：
- ✅ `web_search` 验证 Expert finding、补充 evidence
- ✅ 读 Blackboard
- ✅ 写 Blackboard stage
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改 Expert 输出

**输出**：
- **stage 名称**: `gap_analysis`
- **格式**: markdown
- **必须包含**：
  1. 覆盖度检查（需求覆盖情况）
  2. 矛盾点（含 web_search 验证结果）
  3. 缺乏 evidence 的 finding（含补充搜索结果）
  4. 被忽略的维度
  5. 质量达标判定
  6. 补充研究建议（具体到可被 Phase 4 Expert 直接执行）

---

### 3.6 Devil's Advocate（Phase 3b）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-3） |
| **Prompt 文件** | `prompts/devil_advocate.md`（通用，Research/Planning 共享） |
| **职责** | 挑战 Expert 结论，web_search 找反面证据 |
| **必做** | 是，不是条件触发 |

**输入（可读）**：
- `research_experts/` 或 `planning_experts/` — 所有 Expert 报告
- `gap_analysis` — Gap Analyst 报告

**权限**：
- ✅ `web_search` 寻找反面证据、替代方案、失败案例
- ✅ 读 Blackboard
- ✅ 写 Blackboard stage
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改 Expert 输出

**输出**：
- **stage 名称**: `devil_advocate`
- **格式**: markdown
- **必须包含**：
  1. 每个挑战：原结论 + 反面证据 + 反面证据 URL + 严重程度 + 建议
- **关键约束**：用事实对抗（web_search 证据），不是逻辑对抗

---

### 3.7 Supplementary Expert（Phase 4）× N

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-3） |
| **Prompt 文件** | 复用 `research_expert_base.md` / `planning_expert_base.md` |
| **职责** | 针对 Gap Analyst / Devil's Advocate 的发现做补充研究 |
| **必做** | 是，固定 1 轮 |

**输入（可读）**：
- `gap_analysis` — 缺失清单
- `devil_advocate` — 挑战清单
- 所有 Expert 原始报告
- `living_spec`（MD source of truth，JSON fallback）

**权限**：
- ✅ `web_search`
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent

**输出**：
- **stage 名称**: `research_experts/supplementary_[name].md` / `planning_experts/supplementary_[name].md`
- **格式**: 同 Expert 输出格式

---

## 四、Research 专属角色

> Research 模块的 Phase 5 收敛是"不压缩，原文照搬"，由 Module Agent 直接执行，不需要独立 Worker。

### Phase 5 收敛（Module Agent 内执行）

**输入**：所有 Expert 报告 + gap_analysis + devil_advocate + 补充 Expert 报告

**输出**：
- `research_report`（markdown）：按主题分组，标记冲突，保留所有原始报告完整内容
- `research_metadata`（JSON）：
  ```json
  {
    "session_id": "...",
    "expert_count": N,
    "rounds": 2,
    "supplementary_rounds": 1,
    "covered_req_ids": [...],
    "uncovered_p0_req_ids": [],
    "expert_to_findings_map": {...},
    "conflict_count": M,
    "has_devil_advocate": true,
    "gap_analysis_verdict": "达标"
  }
  ```

---

## 五、Planning 专属角色

> Planning V3 与 Research V3 共享 Deep Analysis Engine 架构（Phase 0-5），差异仅在 prompt 内容和 Phase 5 收敛方式。

### Phase 5 收敛（结构化提取）

与 Research 的"不压缩"不同，Planning 的 Phase 5 从 Expert 自由分析中提取结构化约束。

**输入**：所有 Expert 报告 + gap_analysis + devil_advocate + 补充 Expert 报告

**输出**：
- `planning_convergence`（JSON）：
  ```json
  {
    "schema_version": "3.0.0",
    "unified_constraints": [
      {
        "constraint_id": "UC-001",
        "description": "...",
        "priority": "MUST|SHOULD|MAY",
        "source_experts": ["expert_a", "expert_b"],
        "covered_req_ids": ["REQ-001"],
        "rationale": "...",
        "conflicts_resolved": "..."
      }
    ],
    "verification_checklist": [
      {
        "check_id": "VC-001",
        "constraint_id": "UC-001",
        "verification_method": "...",
        "expected_result": "..."
      }
    ],
    "meta": {
      "total_expert_plans": N,
      "total_input_constraints": N,
      "total_output_constraints": N,
      "merge_ratio": 0.X
    },
    "covered_req_ids": [...]
  }
  ```

---

## 六、Summary V3 角色

### 6.1 Base Synthesizer（Phase 1）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **角色** | 运动员 |
| **职责** | 吸收所有上游知识，产出完整基础方案 |

**输入（可读）**：
- `planning_convergence`（约束体系）
- `research_report`（完整研究报告）
- `research_metadata`（研究元数据）
- `research_experts/`（各专家原始报告）
- `gap_analysis`（Gap Analyst 报告）
- `devil_advocate`（Devil's Advocate 报告）
- `living_spec`（MD source of truth，JSON fallback）

**权限**：
- ✅ `web_search`（搜索方案模板/行业案例）
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改上游输出

**输出**：
- **stage 名称**: `base_solution`
- **格式**: 自由 markdown
- **内容**：完整的基础方案，涵盖所有 Research 发现，遵守所有 Planning 约束
- **关键约束**：必须覆盖 research_report 中的所有重要 finding，必须遵守 MUST 约束

---

### 6.2 Meta Summary Planner（Phase 2）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **角色** | 裁判 + 导演 |
| **职责** | 审视基础方案，动态规划 Phase 3-5 策略，为下游写 prompt |

**输入（可读）**：
- `base_solution`（Phase 1 产出）
- `planning_convergence`（约束体系）
- `research_report`（研究知识）

**权限**：
- ✅ 读 Blackboard
- ✅ 写 Blackboard stage
- ❌ **不能修改 base_solution**（裁判不是运动员）
- ❌ 不能 spawn 子 Agent
- ❌ 不能 `web_search`

**输出**：
- **stage 名称**: `summary_plan`
- **格式**: markdown + 最小结构化 schema
- **必须包含**：
  1. 基础方案评估（强项、弱项、遗漏）
  2. 分析面板（Phase 3：每个 Analyzer 的角色、审查焦点、审查问题、重点关注 section）
  3. 修复优先级（Phase 4）
  4. 文档结构建议（Phase 5）
  5. **为每个下游 Agent 写的定制化 prompt 要点**
- **关键约束**：分析面板必须针对基础方案的实际弱点，不是预设模板

> 🔴 **Analyzer 面板部分必须使用固定格式**（确保 Module Agent 可解析）：
> ```markdown
> ## Analyzer: [角色名]
> - focus: [审查焦点，一句话]
> - questions:
>   1. [具体问题 1]
>   2. [具体问题 2]
> - target_sections: [section_1, section_2]
> ```
> Module Agent 用 `## Analyzer:` 分割提取。格式不一致会导致 spawn 失败。

---

### 6.3 Analyzer（Phase 3）× N

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **角色** | 审查员 |
| **职责** | 从指定角度审查基础方案 |

**输入（可读）**：
- `base_solution`（基础方案）
- `summary_plan`（获取审查焦点和问题）
- `planning_convergence`（约束参考）

**权限**：
- ✅ `web_search`（搜索最佳实践/案例来支撑审查）
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改 base_solution

**输出**：
- **stage 名称**: `analysis_[name]`
- **格式**: markdown
- **必须包含**：
  1. 审查范围（summary_plan 分配的问题）
  2. 发现（问题 + 严重程度 + 修复建议）
  3. 整体评价（维度得分 + 最关键改进点）
- **关键约束**：修复建议必须具体到可执行

#### 🔴 必含 Analyzer：Review Layer B（继承自旧版）

无论 Meta Summary Planner 如何规划，Phase 3 必须包含一个 Review Layer B Analyzer。

**职责**：5 维度对抗性质量检查

> 🔴 **确定性穷举任务必须用 Python 辅助，LLM 只做语义判断**（评审风险 4 修复）

| 维度 | 检查方法 | 判定标准 |
|------|---------|----------|
| 需求覆盖率 | 🔴 **Python** 从 living_spec.requirement_index 提取所有 P0 REQ-ID（语义化格式 REQ-OBJ-001）+ 在 base_solution 中搜索出现位置 → **LLM** 判断每个匹配是否语义对应 | 100% = PASS，< 100% = FAIL |
| 约束一致性 | 🔴 **Python** 遍历 unified_constraints 中所有 constraint_id + 在方案中搜索 → **LLM** 判断是否语义覆盖 | 缺失率 > 10% = FAIL |
| 来源追溯 | **LLM** 抽查 5+ 个关键决策，检查是否有 source_experts 追溯 | 无追溯 = WARNING |
| 逻辑一致性 | **LLM** 检查是否存在语义矛盾（同时要求 A 和 非A） | 存在矛盾 = FAIL |
| 可操作性 | 🔴 **Python** 提取所有验证项的 verification_method → **LLM** 判断是否为具体可执行命令 | 多数模糊 = FAIL |

**输出**：`analysis_review_layer_b` stage

---

### 6.4 Fix Judge（Phase 4 Step 1）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **角色** | 裁判 |
| **职责** | 综合判断所有 Analyzer 建议，决定采纳/拒绝/折中 |

**输入（可读）**：
- `base_solution`
- 所有 `analysis_[name]` 报告
- `planning_convergence`（约束参考）

**权限**：
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改 base_solution
- ❌ 不能 `web_search`

**输出**：
- **stage 名称**: `fix_plan`
- **格式**: markdown
- **必须包含**：
  1. 采纳的建议（列表 + 理由）
  2. 拒绝的建议（列表 + 理由：与其他建议冲突/全局影响不大）
  3. 折中的建议（列表 + 修改方案）
- **关键约束**：全局最优 > 局部最优

---

### 6.5 Fix Agent（Phase 4 Step 2）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **角色** | 修理工 |
| **职责** | 根据 fix_plan 执行定向修复 |

**输入（可读）**：
- `base_solution`
- `fix_plan`（裁判的判断结果）
- `planning_convergence`（约束参考）

**权限**：
- ✅ `web_search`（搜索修复所需的技术信息）
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent
- ❌ 只修 fix_plan 中采纳的修改

**输出**：
- **stage 名称**: `refined_solution`
- **格式**: 自由 markdown（基于 base_solution 修改后的完整方案）

---

### 6.6 Harness Check Agent（Phase 4 Step 3）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **角色** | 验证员（继承自旧版 Harness Agent） |
| **职责** | 两层验证：checklist 执行 + 业务验证 |

**输入（可读）**：
- `refined_solution`（修复后的方案）
- `planning_convergence`（含 verification_checklist）
- `living_spec`（MD source of truth，JSON fallback，用于 Harness 层）

**权限**：
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改 refined_solution

**输出**：
- **stage 名称**: `verification_result`
- **格式**: JSON（两层）
  ```json
  {
    "layer1_checklist": {
      "total_checks": N,
      "passed": N,
      "failed": N,
      "results": [{"check_id": "VC-001", "status": "PASS|FAIL", "evidence": "..."}]
    },
    "layer2_harness": {
      "p0_coverage_pct": 1.0,
      "missing_p0_reqs": [],
      "architecture_consistent": true,
      "guardrails_violated": [],
      "information_conservation": "PASS|FAIL",
      "overall_verdict": "PASS|CONDITIONAL|FAIL"
    }
  }
  ```

**Layer 2 Harness 业务验证细则**：

| 检查项 | 方法 | 判定 |
|--------|------|------|
| P0 REQ 覆盖率 | living_spec.requirement_index 中 P0 REQ 是否在方案中有对应实现 | < 100% = FAIL |
| 架构一致性 | 方案是否与 unified_constraints 体系一致 | 存在矛盾 = FAIL |
| Guardrails 遵守 | 是否违反 living_spec.confirmed.capabilities.never_do | 违反 = FAIL |
| 信息守恒 | 🔴 **Python** 从 living_spec.requirement_index 提取所有 P0 REQ-ID，检查每个 ID 是否在 refined_solution 中出现（语义覆盖而非字符串匹配） | P0 未全覆盖 = FAIL |

---

### 6.7 Document Generator（Phase 5a）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **职责** | 产出完整方案文档 |

**输入（可读）**：
- `refined_solution`
- 所有 `analysis_[name]` 报告
- `fix_plan`
- `verification_result`
- `summary_plan`（文档结构建议）

**权限**：
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent

**输出**：
- **stage 名称**: `solution_document`
- **格式**: 完整 markdown 文档
- **建议结构**：方案概述 → 架构设计 → 技术选型（含对比）→ 实施计划 → 风险缓解 → 约束覆盖追溯

---

### 6.8 JSON Extractor（Phase 5b）

| 属性 | 值 |
|------|-----|
| **类型** | Worker（depth-2） |
| **职责** | 从方案文档中提取结构化元数据 |

**输入（可读）**：
- `solution_document`（Phase 5a 已写完）
- `verification_result`

**权限**：
- ✅ 读/写 Blackboard
- ❌ 不能 spawn 子 Agent
- ❌ 不能重新生成方案内容

**输出**：
- **stage 名称**: `final_solution`
- **格式**: JSON（轻量元数据，不放完整内容）
  ```json
  {
    "schema_version": "3.0.0",
    "constraint_coverage": {"total": N, "covered": N, "ratio": 0.X, "uncovered": [...]},
    "key_decisions": [...],
    "implementation_phases": [...],
    "risk_summary": [...],
    "verification_status": {"passed": N, "failed": N},
    "document_ref": "solution_document"
  }
  ```

---

## 七、调度经验教训

> 来源：2026-06-30 开发过程中的实际踩坑记录。

### 7.1 sessions_yield 中断问题（最严重）

**现象**：Orchestrator 在 sessions_yield 后醒来时，生成文字而非 tool call，导致 session 终止。

**根因**：LLM 在 yield 后醒来时，倾向于生成"我继续..."之类的文字，而不是直接执行 exec 验证。

**解决方案**：
1. **Wake Response Protocol**：yield 唤醒后的第一个 action 必须是 exec tool call，禁止任何文字生成
2. **原子块**：将 spawn + yield + 验证合并为不可分割的步骤
3. **Yield Anchor**：yield 前的最后一条指令明确写"醒来后只做 exec 验证"

**Prompt 写法**：
```markdown
## ⚠️ Yield 唤醒规则（铁律）

sessions_yield 返回后：
1. 第一个 action **必须**是 exec 验证代码
2. **禁止**生成任何文字（包括"我继续"、"好的"、"现在检查"）
3. 验证完成后才能输出分析文字

违反此规则 = pipeline 中断 = 任务失败
```

### 7.2 Blackboard 路径双重嵌套 Bug

**现象**：write_stage('stages/xxx') 实际写入 stages/stages/xxx，导致读取失败。

**根因**：BlackboardManager.write_stage() 和 read_stage() 已自动添加 `stages/` 前缀，prompt 中再传 `stages/xxx` 导致双重嵌套。

**解决方案**：prompt 中传 stage 名称时**不加** `stages/` 前缀。
```python
# ✅ 正确
bb.write_stage('research_report', content)
bb.read_stage('research_report')

# ❌ 错误
bb.write_stage('stages/research_report', content)  # 实际写入 stages/stages/research_report
```

### 7.3 信息流断裂

**现象**：Research 模块不读 Planning 输出，导致研究与约束脱节。

**根因**：Research Expert prompt 中没有强制要求读 `planning_convergence`。

**解决方案**：在 Expert prompt 中加入铁律：
```markdown
## 🔴 强制输入（必须读）
你必须读取 `planning_convergence` stage，确保你的分析与约束对齐。
不读 planning_convergence = 输出无效。
```

### 7.4 JSON Schema 压缩导致信息丢失

**现象**：Expert 输出被强制 JSON schema 压缩（12 个结构化字段 → 1 个文本字段），信息保真率仅 ~65%。

**解决方案**：Expert 输出改为自由 markdown，收敛推迟到最后阶段。

### 7.5 LLM Token 上限导致输出截断

**现象**：大文档生成时 LLM 输出被截断，只写了 JSON 没写文档。

**解决方案**：大输出拆分为多个 Agent（如 Phase 5a 文档 + Phase 5b JSON）。

### 7.6 运动员 = 裁判 = 盲区

**现象**：同一个 Agent 既生成方案又审查方案，导致无法发现自己的问题。

**解决方案**：严格分离生成者和审查者角色。
- Base Synthesis（运动员）≠ Meta Summary Planner（裁判）
- Expert（运动员）≠ Gap Analyst / Devil's Advocate（裁判）

### 7.7 Prompt 内联 vs 独立文件

**现象**：模块 prompt 内联了精简版 Worker prompt，独立 prompt 文件更丰富但没被使用。

**解决方案**：模块 prompt 只负责编排逻辑，Worker prompt 使用独立文件（单一信息源）。

---

## 八、Prompt 编写规范

### 8.1 必须包含的元素

每个 Worker prompt 必须包含：

```markdown
---
id: solution/[role_name]
version: "X.X.X"
component: solution
role: [role_name]
---

# [角色名]

## 你的 session_id
`{session_id}`

## 执行环境（Preamble）
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "..."

## 输入（可读列表）
- 列出所有可读的 stage 和文件

## 职责
- 明确的职责列表

## 输出格式
- stage 名称
- 格式（markdown / JSON）
- 必须包含的字段

## 权限
- ✅ 可以做什么
- ❌ 不能做什么

## 完成验证
写入 Blackboard 后的验证代码

## 铁律
- yield 唤醒规则（如果涉及）
- 强制输入规则
- 输出质量规则
```

### 8.2 Prompt 编写禁忌

| 禁忌 | 原因 | 替代方案 |
|------|------|---------|
| 在 prompt 中嵌入大段 JSON 数据 | LLM 处理 token 有限 | 让 Worker 自己读 Blackboard |
| 用 `stages/` 前缀传 stage 名称 | API 已自动添加前缀 | 直接传名称 |
| 不指定 session_id | Worker 不知道读哪个 Blackboard | 必须传入 `{session_id}` |
| 不写 Preamble | Worker 的 Python import 会失败 | 每个 task 开头必须加 Preamble |
| 让 Worker spawn 子 Agent | depth 限制 | 只有编排器能 spawn |
| 输出格式只说"JSON" | LLM 可能省略字段 | 给出完整的 JSON schema 示例 |
| 不写验证代码 | 无法确认输出是否写入 | 必须包含写入后的验证代码 |

### 8.3 Spawn Task 模板

```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="[module]_[role]",  # 例：research_expert_architecture
    task=f"""
{PREAMBLE}

{read_prompt('[role_prompt_file]')}

## 你的 session_id
`{session_id}`
""",
    cwd="/Users/allen/.openclaw/workspace/.deepflow"
)
```

### 8.4 Yield 后验证模板

```python
# yield 返回后第一个 action 必须是 exec
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
result = bb.read_stage('[stage_name]')
if result:
    print('[STAGE]_OK')
    print(f'SIZE: {len(str(result))} chars')
else:
    print('[STAGE]_MISSING')
"
```

---

## ADR-009 变更说明（2026-07-12）

本文档中的 `frozen_spec.json` 引用已根据 ADR-009 Phase 3 更新：
- **数据源**: `frozen_spec.json` → `living_spec`（MD source of truth）
- **REQ-ID**: 从 `frozen_spec` 提取 → 从 `living_spec.requirement_index` 读取
- **REQ-ID 格式**: 语义化（REQ-OBJ-001），由 spec_pro/coordinator.py 原生生成
- **frozen_spec.py**: 已废弃（DEPRECATED），仅保留 fallback
