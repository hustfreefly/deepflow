# Summary Module V3 架构设计

> **版本**: V3.0.0 | **日期**: 2026-06-30 | **状态**: 已确认
> **设计原则**: 收敛流程（从发散到聚焦），不是发散流程

---

## 核心设计理念

1. **收敛而非发散**：Research/Planning 是从一个点展开（发散），Summary 是从大量知识收拢成最优方案（收敛）
2. **先建后审**：Phase 1 先产出完整基础方案，Phase 3 才有东西可审。不是上来就分段写再拼凑
3. **运动员 ≠ 裁判**：Base Synthesis 产出方案，Meta Summary Planner 审视方案并规划审查，独立视角
4. **动态规划**：Meta Summary Planner 根据基础方案的实际内容决定审查策略，不预设固定模板
5. **输出分离**：文档和 JSON 分两个 Agent 写，避免 LLM token 上限导致截断

---

## 三模块整体定位

```
Planning（发散：从需求 → 约束体系）→ planning_convergence
    ↓
Research（发散：从约束 → 深度研究）→ research_report + research_metadata
    ↓
Summary（收敛：从知识 → 最优方案）→ final_solution + solution_document
```

| 模块 | 方向 | 比喻 | 输出 |
|------|------|------|------|
| Planning | 发散 | 画边界 | 结构化约束 JSON |
| Research | 发散 | 填知识 | 自由 markdown 报告 |
| Summary | 收敛 | 炼方案 | JSON + 方案文档 |

---

## Summary V3 内部 5+1 Phase 架构

> **从旧版 ReviewQC 继承的角色**：Review Layer B（5 维度对抗检查）、Harness Check（业务验证）
> **不继承的角色**：Schema Validator（上游质量由上游保证）、Reviewer Meta（Phase 3 自然检验）、QC Convergence（Harness Check 已够）

### Phase 1: Base Synthesis（运动员）

- **目的**：吸收所有上游知识，产出一份完整的、详细的基础方案
- **输入**：
  - `planning_convergence`（统一约束 + 验证清单）
  - `research_report`（完整研究报告，含所有 Expert + Gap + Devil's Advocate）
  - `research_metadata`（研究元数据）
  - `data/frozen_spec`（原始需求）
- **职责**：
  1. 完整吸收 Research 的所有发现（不遗漏）
  2. 在 Planning 约束框架内综合方案
  3. 产出一份可直接审视的完整基础方案
- **输出**：`base_solution` stage（markdown）
- **关键约束**：
  - 必须覆盖 research_report 中的所有重要 finding
  - 必须遵守 planning_convergence 中的 MUST 约束
  - 不做审查，不做对抗——只管产出最好的基础方案

### Phase 2: Meta Summary Planner（裁判 + 导演）

- **目的**：审视基础方案，动态规划 Phase 3-5 的审查和收敛策略
- **输入**：
  - `base_solution`（Phase 1 产出）
  - `planning_convergence`（约束体系）
  - `research_report`（研究知识）
- **职责**：
  1. 分析基础方案的强弱项（哪些 section 详细？哪些薄弱？有没有遗漏？）
  2. 决定 Phase 3 需要哪些分析 Agent（不固定，根据基础方案动态决定）
  3. 为每个分析 Agent 定义审查焦点和具体问题
  4. 为 Phase 4 定义修复优先级和验证标准
  5. 为 Phase 5 定义最终收敛的文档结构
  6. **为下游 Agent 写定制化的 prompt**（不是读固定模板）
- **输出**：`summary_plan` stage（markdown + 最小结构化 schema）

  > 🔴 **Analyzer 面板部分必须使用固定格式**（确保 Module Agent 可解析）

  ```markdown
  # Summary Plan

  ## 基础方案评估
  - 强项：...
  - 弱项：...
  - 遗漏：...

  ## 分析面板（Phase 3）

  <!-- 🔴 以下格式必须严格遵守，Module Agent 用 "## Analyzer:" 分割提取 -->

  ## Analyzer: [角色名]
  - focus: [审查焦点，一句话]
  - questions:
    1. [具体问题 1]
    2. [具体问题 2]
    3. [具体问题 3]
  - target_sections: [section_1, section_2]

  ## Analyzer: [角色名]
  - focus: ...
  - questions:
    1. ...
  - target_sections: [...]

  ## 修复优先级（Phase 4）
  - 高优先级修复方向：...
  - 验证标准：...

  ## 文档结构（Phase 5）
  - 方案文档建议结构：...
  ```
- **关键约束**：
  - 不能修改 base_solution（它是裁判，不是运动员）
  - 分析面板必须针对基础方案的实际弱点（不是预设的安全/架构/性能三板斧）
  - 每个 Analyzer 必须有明确的审查问题（不是泛泛的"审查架构"）

### Phase 3: Parallel Analysis（多角度并行审视）

- **目的**：从多个角度对基础方案做压力测试
- **输入**：`base_solution` + `summary_plan`（获取审查焦点和问题）
- **执行**：根据 summary_plan 中的分析面板，并行 spawn 多个 Analyzer
- **🔴 必须包含的 Analyzer**：

  **Review Layer B Analyzer**（继承自旧版，5 维度对抗性检查）：
  1. **需求覆盖率**：P0 REQ 是否 100% 覆盖？逐一查找对应实现
  2. **约束一致性**：unified_constraints 是否完整保留？
  3. **来源追溯**：每条关键决策是否有 source_experts 追溯？
  4. **逻辑一致性**：方案中是否存在矛盾？
  5. **可操作性**：验证清单是否可执行（具体命令 vs 模糊描述）？

  其余 Analyzer 由 Meta Summary Planner 根据基础方案弱点动态决定。

- **每个 Analyzer 输出**：分析报告（markdown）
  ```markdown
  # [角色名] 审查报告

  ## 审查范围
  （summary_plan 中分配的审查问题）

  ## 发现
  ### 问题 1: [标题]
  [详细分析]
  **严重程度**：高/中/低
  **修复建议**：[具体修改方向]

  ### 问题 2: ...

  ## 整体评价
  - 基础方案在此维度的得分：X/10
  - 最关键的改进点：...
  ```
- **输出**：`analysis_[name]` stages（每个 Analyzer 一个）
- **关键约束**：
  - 每个 Analyzer 只审查 summary_plan 分配的焦点（不越界）
  - 修复建议必须具体到可执行（"修改 section 3，增加 X 机制"而非"加强安全性"）

### Phase 4: 裁判判断 → 定向修复 → Verification

- **目的**：有选择地修复，不是盲从所有建议
- **三步执行**：

  **Step 1: 综合判断（裁判）**
  - 读所有 Phase 3 分析报告
  - 判断哪些建议采纳、哪些拒绝、哪些折中
  - 理由：全局最优 > 局部最优
  - Phase 3 的建议"站在各自角度都对，但全局来看可能互相矛盾"
  - 输出：`fix_plan` stage（markdown）
    ```markdown
    # Fix Plan

    ## 采纳的建议
    - [Analyzer X 的问题 Y]：采纳，理由...
    ## 拒绝的建议
    - [Analyzer A 的问题 B]：拒绝，理由（与其他建议冲突/全局影响不大）
    ## 折中的建议
    - [Analyzer C 的问题 D]：部分采纳，修改为...
    ```

  **Step 2: 定向修复（修理工）**
  - 读 `base_solution` + `fix_plan`
  - 只修 fix_plan 中决定采纳的修改
  - 输出：`refined_solution` stage（markdown）

  **Step 3: Harness Check（继承自旧版 Harness Agent）**
  - 读 `refined_solution` + `planning_convergence` + `data/frozen_spec`
  - 执行两层验证：

    **Layer 1: Verification Checklist 执行**
    - 逐条执行 Planning 的 `verification_checklist`
    - 确保修改后仍然满足所有 MUST 约束

    **Layer 2: Harness 业务验证**
    - P0 REQ 覆盖率：frozen_spec 中 P0 需求是否在方案中有对应实现
    - 架构一致性：方案是否与 planning_convergence 的约束体系一致
    - Guardrails 遵守：是否违反 frozen_spec 中的 never_do
    - 信息守恒：Research 的关键 finding 是否在方案中体现

  - 输出：`verification_result` stage（JSON）
    ```json
    {
      "layer1_checklist": {
        "total_checks": N, "passed": N, "failed": N,
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

### Phase 5a: 文档生成

- **目的**：产出完整的方案文档
- **输入**：`refined_solution` + Phase 3 分析报告 + Phase 4 fix_plan
- **输出**：`solution_document` stage（markdown）
- **关键约束**：
  - 文档是大头，给足 token 空间
  - 包含完整方案细节、技术选型对比、实施计划、风险缓解

### Phase 5b: 结构化提取

- **目的**：从方案文档中提取结构化元数据
- **输入**：`solution_document`（Phase 5a 已写完）
- **输出**：`final_solution` stage（JSON）
  ```json
  {
    "schema_version": "3.0.0",
    "constraint_coverage": {
      "total": 32,
      "covered": 31,
      "ratio": 0.97,
      "uncovered": ["C-XXX"]
    },
    "key_decisions": [...],
    "implementation_phases": [...],
    "risk_summary": [...],
    "verification_status": {"passed": N, "failed": N},
    "document_ref": "solution_document"
  }
  ```
- **关键约束**：
  - JSON 只放元数据，不放完整方案内容
  - 从已写完的文档中提取，不重新生成

---

## 输出分离设计（解决 token 截断问题）

| 输出 | Agent | 大小估计 | 格式 |
|------|-------|---------|------|
| solution_document | Phase 5a Agent | 5000-10000 字 | 自由 markdown |
| final_solution | Phase 5b Agent | ~500 字 | 结构化 JSON |

**为什么分开**：
- 文档是大头，单独一个 Agent 给足 token 空间
- JSON 是轻量提取，不会超限
- 如果 5a 超时，5b 还能从 refined_solution 中提取

---

## 依赖关系图

```
Phase 1 (Base Synthesis)
  ↓ base_solution
Phase 2 (Meta Summary Planner)
  ↓ summary_plan
Phase 3 (Parallel Analysis × N)
  ↓ analysis_[name] × N
Phase 4 (判断 → 修复 → 验证)
  ↓ refined_solution + verification_result
Phase 5a (文档生成)
  ↓ solution_document
Phase 5b (结构化提取)
  ↓ final_solution
```

**严格线性链**：1 → 2 → 3 → 4 → 5a → 5b

---

## 质量双保障

| 目标 | 保障机制 |
|------|---------|
| 方案足够优秀 | Phase 3 多角度分析 + Phase 4 有选择修复 |
| 不偏离需求 | Phase 4 Verification 执行 Planning 的 verification_checklist |

---

## 与 Research/Planning 的对比

| 维度 | Research | Planning | Summary |
|------|----------|----------|---------|
| 方向 | 发散 | 发散 | **收敛** |
| Planner | Research Planner（Phase 1） | Meta-Planner（Layer 0） | Meta Summary Planner（Phase 2） |
| 并行 | N 个 Expert | N 个 Expert | N 个 Analyzer |
| 对抗 | Gap + Devil's（web_search） | Gap + Devil's（web_search） | 裁判判断 + Verification |
| 收敛 | 不压缩 | 结构化提取 | **文档 + JSON 分离** |
| 运动员/裁判 | 分离 | 分离 | **分离（Phase 1 ≠ Phase 2）** |

---

## 决策记录

| 日期 | 决策 | 理由 | 参与者 |
|------|------|------|--------|
| 2026-06-30 | Summary 不套 Research/Planning 模板 | Summary 是收敛流程，不是发散流程 | 忠礼 + 小满 |
| 2026-06-30 | Base Synthesis 先于 Meta Summary Planner | 裁判必须先看到方案才能规划审查 | 忠礼 + 小满 |
| 2026-06-30 | 不合并 Phase 1+2 | 运动员 ≠ 裁判，独立视角 | 忠礼 + 小满 |
| 2026-06-30 | Phase 4 有独立判断力 | 并行分析的建议可能互相矛盾，需全局判断 | 忠礼 + 小满 |
| 2026-06-30 | Phase 5 文档和 JSON 分离 | 解决 LLM token 上限导致截断问题 | 忠礼 + 小满 |
