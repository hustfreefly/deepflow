## Prompt 体系视角补充

> 评审日期：2026-06-01
> 评审范围：`domains/solution_pro/prompts/` 目录下全部 35 个 `.md` 文件
> 评审人：Prompt 工程 + 多 Agent 协作系统专家

---

# Solution Pro Prompt 体系评审报告

## 一、文件清单与版本标识合规

### 1.1 YAML Front Matter 覆盖率

| 文件数 | 有 Front Matter | 缺少 Front Matter |
|:---:|:---:|:---:|
| 35 | 35 | 0 |

**结论**：全部 35 个文件都有 YAML Front Matter，✅ 合规。

### 1.2 版本号分布

| 版本 | 文件数 | 文件列表 |
|:---|:---:|:---|
| 1.0.0 | 18 | worker_* (7个), architect, consolidator, fixer, fixer_expert, researcher, researcher_v2_harness(误标), summarizer, data_collection(误标), cron_watcher, harness_v3, pipeline_execution_guide, solution_planner_pro |
| 2.0.0 | 6 | planner, auditor, designer, fixer, deliver, researcher_template |
| 2.1.0 | 8 | 全部 `*_v2_harness` (planner/researcher/auditor/consolidator/fixer/fixer_expert/reviewer/summarizer) |
| 3.0.0 | 2 | pipeline_orchestrator_v3, pro_pipeline_orchestrator_v3 |
| 4.0.0 | 1 | pipeline_orchestrator_v4 |

**⚠️ 问题发现**：
- `researcher_v2_harness.md` 标注 version `2.1.0` 但 id 为 `solution/researcher_v2_harness`，文件命名和版本一致 ✅
- `data_collection.md` 标注 version `2.0.0` 但 id 为 `solution/data_collection`，不符合命名规则但本身无大碍
- **版本编号规则不统一**：`_v2_harness` 文件全部 2.1.0，但 `v3` orchestrator 却是 3.0.0

---

## 二、重复和冲突分析（严重问题区）

### 2.1 同一角色的 v1/v2 双版本共存

这是体系中最严重的结构问题。**每一个核心角色都存在 v1（worker_*）和 v2（*_v2_harness）两套 prompt**：

| 角色 | v1 Worker Prompt | v2 Harness Prompt | 基础版 Prompt |
|:---|:---|:---|:---|
| Planner | `worker_planner.md` | `planner_v2_harness.md` | `planner.md` |
| Researcher | `worker_researcher.md` | `researcher_v2_harness.md` | `researcher.md`, `researcher_template.md` |
| Auditor | `worker_auditor.md` | `auditor_v2_harness.md` | `auditor.md` |
| Reviewer | `worker_reviewer.md` | `reviewer_v2_harness.md` | 无基础版 |
| Fixer | `worker_fixer.md` | `fixer_v2_harness.md` | `fixer.md` |
| Fixer Expert | (同 worker_fixer) | `fixer_expert_v2_harness.md` | `fixer_expert.md` |
| Consolidator | `worker_consolidator.md` | `consolidator_v2_harness.md` | `consolidator.md` |
| Summarizer | `worker_summarizer.md` | `summarizer_v2_harness.md` | `summarizer.md` |

**判定**：
- `worker_*.md`（v1 风格）= 精简版，无 Harness 自评，直接写入 Blackboard
- `*_v2_harness.md` = 增强版，包含 Harness 自评 + Layer 2 约束注入点
- 无 v2 后缀的基础版（如 `planner.md`, `auditor.md`）= 最详细版本，有完整角色定义和评分标准

**⚠️ task_builder.py 实际使用的是 v2_harness 版本**：
```python
# domains/solution_pro/task_builder.py 中的引用
"planner"     → "solution/planner_v2_harness"
"researcher"  → "solution/researcher_v2_harness"
"auditor"     → "solution/auditor_v2_harness"
"fixer"       → "solution/fixer_v2_harness"
"consolidator"→ "solution/consolidator_v2_harness"
"reviewer"    → "solution/reviewer_v2_harness"
"summarizer"  → "solution/summarizer_v2_harness"
"fixer_expert"→ "solution/fixer_expert_v2_harness"
```

**worker_* 和基础版文件全部未被 task_builder.py 引用**，是死文件。

### 2.2 Pipeline Orchestrator 三版本共存

| 文件 | 版本 | 阶段数 | 状态 |
|:---|:---:|:---:|:---|
| `pipeline_orchestrator.md` | 2.0.0 | 8 阶段 | ❌ 废弃，无引用 |
| `pipeline_orchestrator_v3.md` | 3.0.0 | 10 阶段 | ❌ 与 v4 重复 |
| `pipeline_orchestrator_v4.md` | 4.0.0 | 10 阶段 | ✅ 当前活跃 |
| `pro_pipeline_orchestrator_v3.md` | 3.0.0 | 8 阶段+Harness | ❌ 旧架构 |

**v3 vs v4 关键差异**：
- v3 有详细的进度推送 JSON 格式，v4 没有
- v3 Stage 6 (Audit) 是 **并行 ×3**，v4 Stage 6 是 **串行**（⚠️ 行为差异）
- v4 新增了 `.completed` 标记文件写入，v3 没有
- v3 有 progress.json 追踪，v4 没有

**⚠️ 建议**：删除 `pipeline_orchestrator.md`、`pipeline_orchestrator_v3.md`、`pro_pipeline_orchestrator_v3.md`，仅保留 `pipeline_orchestrator_v4.md`。

### 2.3 researcher_template.md 的定位模糊

`researcher_template.md` (v2.0.0) 是一个 **模板 prompt**，使用 `{{ expert.name }}`、`{{ expert.angle }}` 等模板变量。但 `researcher_v2_harness.md` 也是研究者 prompt，且 task_builder.py 用的是 v2_harness 版。

**冲突点**：
- `researcher_template.md` 用模板变量 `{{ expert.angle }}`、`{{ expert.reason }}`
- `researcher_v2_harness.md` 也用 `{{ expert.angle }}`、`{{ expert.reason }}`
- 两者功能重叠，但 template 版还包含 Layer 2 约束验证清单

**判定**：`researcher_template.md` 可能是 `researcher_v2_harness.md` 的前身，两者都应保留其中一个。

### 2.4 architect.md 无对应 v2_harness

`architect.md` (v1.0.0) 是架构师 prompt，但没有对应的 `architect_v2_harness.md`。也没有对应的 `worker_architect.md`。

**原因分析**：architect 似乎不在当前 8/10 阶段管线中运行，是遗留角色。

### 2.5 deliver.md 与 designer.md 功能重叠

| 文件 | 角色 | 功能 |
|:---|:---|:---|
| `designer.md` | 方案设计师 | "整合研究成果，产出方案文档" |
| `deliver.md` | 交付专家 | "整合研究成果，产出交付文档" |

两者描述几乎相同（"整合所有研究成果"），输出格式也类似（Markdown 文档 + 章节结构）。`deliver.md` 仅有 1KB，内容远少于 `designer.md` 的 2.4KB。

**判定**：功能重复，`deliver.md` 可合并到 `designer.md`。

---

## 三、Prompt 质量评估

### 3.1 角色定义清晰度

| 文件 | 角色定义 | 评分 | 问题 |
|:---|:---|:---:|:---|
| `architect.md` | ✅ 清晰 | 9/10 | 优秀，C4 模型要求明确 |
| `auditor.md` | ✅ 清晰 | 9/10 | P0-P3 分级、评分算法都明确 |
| `planner.md` | ✅ 清晰 | 9/10 | 动态 Agent 生成规则详细 |
| `planner_v2_harness.md` | ✅ 清晰 | 8/10 | 增加了 structured_requirements.json |
| `fixer.md` | ⚠️ 模糊 | 5/10 | 缺少具体修复策略 |
| `fixer_expert.md` | ✅ 清晰 | 8/10 | 深度 vs 表面对比清晰 |
| `researcher.md` | ⚠️ 模糊 | 6/10 | 研究维度泛化，不具体 |
| `researcher_template.md` | ✅ 清晰 | 8/10 | 模板结构好，含 Layer 2 验证 |
| `summarizer.md` | ✅ 清晰 | 8/10 | 8 阶段映射表清晰 |
| `worker_*.md` | ⚠️ 过于简略 | 4/10 | 仅 1KB 左右，角色定义单薄 |

### 3.2 输出格式明确性

**问题：v2_harness 和 worker_* 的输出格式不一致**

以 Auditor 为例：

`auditor.md` 输出格式：
```json
{ "audit_result": { "overall_score": 0.85, "verdict": "pass|...", "issues": [...] } }
```

`auditor_v2_harness.md` 输出格式：
```json
{ "status": "completed", "stage": "audit", "data": { "audit_findings": [...] }, "harness_self_assessment": {...} }
```

`worker_auditor.md` 输出格式：
```json
{ "role": "auditor_<type>", "session_id": "...", "audit": { "score": 0.88, "findings": [...] } }
```

**三个版本输出格式完全不同**。task_builder.py 中 build_auditor_task 期望的格式是另一个变体。

**⚠️ 高风险**：如果代码层期望 `data.issues` 但 prompt 要求 `data.audit_findings`，就会断裂。

### 3.3 模糊指令检测

| 文件 | 模糊指令 | 位置 |
|:---|:---|:---|:---|
| `researcher.md` | "快速执行 web search，收集行业信息" | 无具体搜索策略 |
| `consolidator.md` | "基于业务场景做出决策" | 未定义决策标准 |
| `solution_planner_pro.md` | "分析需求文档" | 未定义需求文档格式 |
| `pipeline_execution_guide.md` | "类似Stage 2，并行spawn..." | 省略了具体代码 |
| `pro_pipeline_orchestrator_v3.md` | 内嵌了大量 Python 代码 | Prompt 中嵌代码，违反 prompt 纯粹性原则 |

**特别注意**：`pro_pipeline_orchestrator_v3.md` 内嵌了完整的 Python `execute_completeness_check()` 调用，这不是一个 prompt 该做的事——prompt 应该定义角色行为，不应该内嵌执行代码。

---

## 四、跨 Agent 依赖与格式断裂风险

### 4.1 数据流断裂点分析

**完整数据流（v4 orchestrator 定义的 10 阶段）**：

```
Stage 1: Data Collection → data/collection.json
Stage 2: Planning → stages/planning.json
Stage 3: Reviewers ×3 → stages/review_*.json
Stage 4: Researchers ×3 → stages/research_*.json
Stage 5: Consolidator → stages/consolidator.json
Stage 6: Audit → stages/audit.json
Stage 7: Fix → stages/fix.json
Stage 8: Fixer Expert → stages/fixer_expert.json
Stage 9: Harness Final → stages/harness_final.json
Stage 10: Summarizer → final_solution.md + final_result.json
```

### 4.2 断裂点 #1：Planner → Researcher

**planner.md 输出**：
```json
{
  "analysis": { "core_problem": "...", "solution_type": "architecture", ... },
  "dimensions": { "performance": {...}, ... },
  "required_experts": [{ "name": "expert_name", "angle": "...", "reason": "..." }],
  "audit_strategy": "standard"
}
```

**task_builder.py 传递给 researcher_v2_harness 的变量**：
- `{{ expert.angle }}` ← 从 planner 的 required_experts 提取
- `{{ expert.reason }}` ← 从 planner 的 required_experts 提取
- `{{ topic }}` ← 原始 topic
- `{{ solution_type }}` ← 从 context 获取

**✅ 匹配情况**：task_builder.py 手动做了字段映射，不是自动对接。如果 planner 的 required_experts 结构变化，researcher 的 prompt 不会自动更新。

### 4.3 断裂点 #2：Researcher → Consolidator

**researcher_v2_harness 输出**：
```json
{ "status": "completed", "stage": "research", "data": { "findings": {...}, "risks": [...], "recommendations": [...] } }
```

**consolidator_v2_harness 期望输入**：
- `{{ research_outputs }}` — 一个 JSON 字符串，包含所有研究者输出

**⚠️ 风险**：consolidator 用 `{{ research_outputs }}` 变量接收，这个变量在 task_builder.py 中被替换为 `json.dumps(research_outputs)`。但 `research_outputs` 是 list of dict，不是直接从 Blackboard 读取。这意味着 **consolidator 的输入依赖 task_builder.py 手动组装，不是自动从 Blackboard 读取**。

### 4.4 断裂点 #3：Auditor → Fixer

**auditor_v2_harness 输出**：
```json
{ "data": { "audit_findings": [...], "summary": { "critical_count": 0, ... } } }
```

**task_builder.py 中 build_fixer_task 传入的 context**：
- 直接传入 `{ "audit_findings": [...] }` 的 context 字典

**⚠️ 风险**：fixer_v2_harness 期望 `{{ AUDIT_FINDINGS }}` 变量，但 build_fixer_task 并没有这个替换逻辑。build_fixer_task 用的是：
```python
prompt = prompt.replace("{{ TOPIC }}", topic)  # 没有 {{ AUDIT_FINDINGS }} 替换！
```

等等，再看一遍 `build_fixer_task`：
```python
def build_fixer_task(session_id, topic, context, layer2_constraints):
    base_prompt = read_prompt("solution/fixer_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "fixer", layer2_constraints or {})
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    ctx = f"## 修复主题\n{topic}\n\n## 问题清单\n{context_json}"
    return prompt + "\n" + ctx
```

fixer_v2_harness 定义了 `{{ TOPIC }}` 和 `{{ AUDIT_PATH }}` 变量，但 build_fixer_task 没有替换 `{{ AUDIT_PATH }}`，只追加了 context。build_fixer_task_with_audit 才是替换了 `{{ AUDIT_PATH }}` 的版本。

**结论：有两个 build_fixer 函数，功能不同但名称容易混淆。**

### 4.5 断裂点 #4：Fixer → Fixer Expert

**fixer_v2_harness 输出**：
```json
{ "data": { "fixes_applied": [...], "fixes_deferred": [...] } }
```

**fixer_expert_v2_harness 期望输入**：
- `{{ TOPIC }}`, `{{ SEVERITY }}`, `{{ AUDIT_FINDINGS }}`

**⚠️ 风险**：fixer_expert 直接消费 auditor 的输出，不是 fixer 的输出。这意味着 fixer 和 fixer_expert 是独立并行修正的关系，不是串行依赖。但 `pro_pipeline_orchestrator_v3.md` 中 Stage 7 Fixer Expert 的输入是 `stage_05_consolidator_output.json` + `stage_07_fixer_expert_output.json`，顺序混乱。

---

## 五、Harness 体系一致性

### 5.1 V2 vs V3 定义冲突

**Harness V2**（在 `*_v2_harness.md` 中）：
- 四维度自评：完整性(30%) + 必要性(20%) + 目标一致性(30%) + 全局影响(20%)
- 综合评级：green/yellow/red（平均分 ≥80 为 green）
- 每个 v2_harness prompt 末尾都有相同的自评标准

**Harness V3**（在 `harness_v3.md` 中）：
- 双维度检查：完整性(60%) + 适度性(40%)
- 评分规则：≥0.85 优秀，0.70-0.85 警告，<0.70 阻断
- 检查项完全不同（容错、数据流、测试、监控、成本、文档 vs 过度设计、过度审计、场景贴合）

**⚠️ 严重冲突**：V2 和 V3 是两套完全不同的质量门控体系。V2 是 Worker 自评（内嵌在每个 prompt 中），V3 是独立门禁（由 harness_v3.md 定义）。两者权重、维度、评分标准、阈值全部不同。

### 5.2 V2 自评模板的复制粘贴问题

所有 8 个 `*_v2_harness.md` 的 Harness V2 自我评估标准部分 **完全相同**，是复制粘贴的：

```
### 完整性 (30%)
- 90-100: 所有XXX已覆盖
- 70-89: 大部分XXX已覆盖，少数遗漏
...
```

每个角色只是改了 XXX 的具体内容（如"所有关键维度"→"所有研究成果"），但结构、权重、阈值完全一致。

**⚠️ 问题**：应该提取为一个公共的 Harness V2 自评模板，通过变量注入，而不是 8 个文件各自维护一份。

### 5.3 harness_v3.md 作为评分指南的角色

`harness_v3.md` 定义了双维度评分，但 `pro_pipeline_orchestrator_v3.md` 中内嵌了大量 Python 代码来执行这个评分（`execute_completeness_check()` 等）。这些函数名在 prompt 中引用，但没有实际定义——这意味着 orchestrator prompt 期望 AI 自己"执行"这些不存在的函数。

**⚠️ 严重问题**：`pro_pipeline_orchestrator_v3.md` 中的 Python 代码片段（如 `completeness_result = execute_completeness_check(fixer_output, completeness_checks)`）是伪代码，AI 无法真正"执行"。这会导致 AI 困惑或产生幻觉行为。

---

## 六、Prompt 与 task_builder.py 的耦合

### 6.1 引用映射表

| task_builder.py 函数 | 引用的 Prompt ID | 对应文件 | 存在？ |
|:---|:---|:---|:---:|
| build_data_collection_task | `solution/data_collection` | `data_collection.md` | ✅ |
| build_planner_task | `solution/planner_v2_harness` | `planner_v2_harness.md` | ✅ |
| build_researcher_task | `solution/researcher_v2_harness` | `researcher_v2_harness.md` | ✅ |
| build_designer_task | `solution/designer` | `designer.md` | ✅ |
| build_auditor_task | `solution/auditor_v2_harness` | `auditor_v2_harness.md` | ✅ |
| build_fixer_task | `solution/fixer_v2_harness` | `fixer_v2_harness.md` | ✅ |
| build_fixer_task_with_audit | `solution/fixer_v2_harness` | `fixer_v2_harness.md` | ✅ |
| build_deliver_task | `solution/deliver` | `deliver.md` | ✅ |
| build_reviewer_task | `solution/reviewer_v2_harness` | `reviewer_v2_harness.md` | ✅ |
| build_harness_v2_task | 多个 v2_harness | 多个 | ✅ |
| build_harness_final_task | `solution/harness_v3` | `harness_v3.md` | ✅ |
| build_harness_task | `solution/harness_v3` | `harness_v3.md` | ✅ |
| build_consolidator_task | `solution/consolidator_v2_harness` | `consolidator_v2_harness.md` | ✅ |
| build_fixer_expert_task | `solution/fixer_expert_v2_harness` | `fixer_expert_v2_harness.md` | ✅ |
| build_summarizer_task | `solution/summarizer_v2_harness` | `summarizer_v2_harness.md` | ✅ |

### 6.2 未被引用的 Prompt 文件（死文件）

以下文件 **未被 task_builder.py 任何函数引用**：

| 文件 | 大小 | 原因分析 |
|:---|:---:|:---|
| `architect.md` | 7.9KB | 架构师角色，可能被其他系统使用 |
| `worker_planner.md` | 2.6KB | v1 风格，已被 planner_v2_harness 取代 |
| `worker_researcher.md` | 1.2KB | v1 风格，已被 researcher_v2_harness 取代 |
| `worker_auditor.md` | 1.0KB | v1 风格，已被 auditor_v2_harness 取代 |
| `worker_reviewer.md` | 1.3KB | v1 风格，已被 reviewer_v2_harness 取代 |
| `worker_fixer.md` | 1.3KB | v1 风格，已被 fixer_v2_harness 取代 |
| `worker_consolidator.md` | 1.2KB | v1 风格，已被 consolidator_v2_harness 取代 |
| `worker_summarizer.md` | 1.2KB | v1 风格，已被 summarizer_v2_harness 取代 |
| `pipeline_orchestrator.md` | 2.8KB | v2 orchestrator，已被 v4 取代 |
| `pipeline_orchestrator_v3.md` | 4.8KB | v3 orchestrator，已被 v4 取代 |
| `pro_pipeline_orchestrator_v3.md` | 13KB | Pro v3 orchestrator，已被 v4 取代 |
| `pipeline_execution_guide.md` | 5.0KB | 执行指南，文档类文件 |
| `solution_planner_pro.md` | 6.7KB | Pro Planner，可能被 pipeline_orchestrator_v4 间接使用 |
| `researcher.md` | 2.5KB | 基础版 researcher，已被 v2_harness 取代 |
| `researcher_template.md` | 3.2KB | 研究者模板，与 v2_harness 重叠 |
| `researcher_v2_harness.md` 中的 `{{ mode }}` 变量 | - | 无对应替换逻辑 |
| `summarizer.md` | 4.9KB | 基础版 summarizer，已被 v2_harness 取代 |
| `consolidator.md` | 3.5KB | 基础版 consolidator，已被 v2_harness 取代 |
| `fixer.md` | 1.9KB | 基础版 fixer，已被 v2_harness 取代 |
| `fixer_expert.md` | 3.8KB | 基础版 fixer_expert，已被 v2_harness 取代 |
| `auditor.md` | 8.3KB | 基础版 auditor，已被 v2_harness 取代 |
| `planner.md` | 7.7KB | 基础版 planner，已被 v2_harness 取代 |
| `cron_watcher.md` | 4.0KB | Cron 巡检，被独立的 cron job 使用，不属于 task_builder |

### 6.3 task_builder.py 核心 issue/core/task_builder.py 对比

`core/task_builder.py` 是 **Investment 领域**的 task builder，引用的是 `investment/` 前缀的 prompt，与 Solution 领域无关。不在本次评审范围内。

### 6.4 模板变量替换不一致

| Prompt 变量 | build_planner_task | build_researcher_task | build_auditor_task | build_fixer_task |
|:---|:---:|:---:|:---:|:---:|
| `{{ TOPIC }}` | ❌ | ❌ | ❌ | ✅ |
| `{{ expert.angle }}` | - | ✅ | - | - |
| `{{ expert.reason }}` | - | ✅ | - | - |
| `{{ AUDIT_PATH }}` | - | - | - | ⚠️ 仅 build_fixer_task_with_audit |
| `{{ review_type }}` | - | - | - | - |
| `{{ review_focus }}` | - | - | - | - |

**⚠️ 问题**：`build_planner_task` 没有替换 planner_v2_harness 中可能存在的 `{{ TOPIC }}` 等变量，只做了 `inject_layer2_constraints` 追加。如果 planner_v2_harness 中有 `{{ }}` 模板变量未被替换，就会残留到最终 prompt 中。

---

## 七、废弃文件清理建议

### 7.1 立即删除（确认为废弃）

| 文件 | 理由 |
|:---|:---|
| `pipeline_orchestrator.md` | v2 版本，功能已被 v4 完全取代 |
| `pipeline_orchestrator_v3.md` | v3 版本，功能已被 v4 完全取代 |
| `pro_pipeline_orchestrator_v3.md` | Pro v3 版本，功能已被 v4 完全取代 |
| `worker_planner.md` | v1 风格，已被 planner_v2_harness 取代 |
| `worker_researcher.md` | v1 风格，已被 researcher_v2_harness 取代 |
| `worker_auditor.md` | v1 风格，已被 auditor_v2_harness 取代 |
| `worker_reviewer.md` | v1 风格，已被 reviewer_v2_harness 取代 |
| `worker_fixer.md` | v1 风格，已被 fixer_v2_harness 取代 |
| `worker_consolidator.md` | v1 风格，已被 consolidator_v2_harness 取代 |
| `worker_summarizer.md` | v1 风格，已被 summarizer_v2_harness 取代 |
| `deliver.md` | 与 designer.md 功能完全重叠，且内容只有 1KB |
| `pipeline_execution_guide.md` | 文档类文件，不应放在 prompts/ 目录 |

### 7.2 考虑删除（有保留价值但当前未使用）

| 文件 | 保留建议 |
|:---|:---|
| `architect.md` | 如果未来需要架构师角色则保留，否则删除。当前管线不使用 |
| `researcher.md` | 基础版，内容比 template 和 v2_harness 都少。建议删除 |
| `researcher_template.md` | 如果 v2_harness 已包含模板变量功能，可删除 |
| `planner.md` | 最详细的 planner prompt，但 v2_harness 已覆盖。建议归档 |
| `auditor.md` | 最详细的 auditor prompt（8.3KB），v2_harness 版简化了很多。建议保留作为参考 |
| `fixer.md` | 简化版，内容太少。建议删除 |
| `fixer_expert.md` | 与 v2_harness 版差异不大。建议删除 |
| `consolidator.md` | 与 v2_harness 版差异不大。建议删除 |
| `summarizer.md` | 与 v2_harness 版差异不大。建议删除 |
| `cron_watcher.md` | 被独立 cron job 使用，**保留** |

### 7.3 建议的目录重组

```
prompts/
├── active/                      # 当前活跃使用的 prompt
│   ├── data_collection.md
│   ├── planner_v2_harness.md
│   ├── researcher_v2_harness.md
│   ├── researcher_template.md   # 如果保留
│   ├── reviewer_v2_harness.md
│   ├── consolidator_v2_harness.md
│   ├── auditor_v2_harness.md
│   ├── fixer_v2_harness.md
│   ├── fixer_expert_v2_harness.md
│   ├── summarizer_v2_harness.md
│   ├── harness_v3.md
│   ├── pipeline_orchestrator_v4.md
│   ├── solution_planner_pro.md
│   ├── designer.md
│   └── cron_watcher.md
├── archived/                    # 归档的废弃版本
│   ├── v1_workers/
│   ├── v2_base/
│   └── v3_orchestrators/
└── harness_v2_self_eval.md      # 提取公共自评模板
```

---

## 八、Prompt 依赖断裂风险评估

### 8.1 风险矩阵

| 断裂点 | 风险等级 | 说明 |
|:---|:---:|:---|
| Auditor → Fixer | 🔴 高 | build_fixer_task 未替换 `{{ AUDIT_PATH }}`，只有 build_fixer_task_with_audit 做了 |
| Fixer → Fixer Expert | 🟡 中 | fixer_expert 直接消费 auditor 输出，绕过了 fixer |
| Planner → Researcher | 🟡 中 | 手动字段映射，非自动对接 |
| Researcher → Consolidator | 🟡 中 | 依赖 task_builder.py 手动组装 input |
| Consolidator → Auditor | 🟢 低 | auditor_v2_harness 从 context 获取输入 |
| Fixer Expert → Summarizer | 🟢 低 | summarizer 从 Blackboard 读取所有 stage |

### 8.2 输出格式不一致的具体风险

**Auditor 输出格式断裂**：

- `auditor.md` 要求 `audit_result.overall_score` (0-1 浮点) + `verdict` (pass/conditional_pass/fail)
- `auditor_v2_harness.md` 要求 `data.audit_findings[]` + `summary.critical_count`
- `worker_auditor.md` 要求 `audit.score` (0-1) + `audit.findings[]`

**影响**：如果下游 Fixer/Consolidator 期望的字段名是 `issues`，但 auditor_v2_harness 输出的是 `audit_findings`，就会找不到数据。

**Fixer 输出格式断裂**：

- `fixer.md` 输出：`{ fixes: [...], modified_sections: [...] }`
- `fixer_v2_harness.md` 输出：`{ data: { fixes_applied: [...], fixes_deferred: [...] } }`

**影响**：如果 Fixer Expert 期望的审计发现字段名不一致，深度修正会找不到要修正的问题。

### 8.3 断裂点 #5：cron_watcher 与 pipeline_orchestrator_v4 的阶段映射冲突

`cron_watcher.md` 定义的阶段映射（10 个阶段）：

```
data/collection.json        → Stage 1
stages/planning.json        → Stage 2
stages/reviewer_*.json      → Stage 3
stages/research_expert_*.json → Stage 4
stages/consolidator.json    → Stage 5
stages/audit.json           → Stage 6
stages/fix.json             → Stage 7
stages/fixer_expert.json    → Stage 8
stages/harness_final.json   → Stage 9
final_solution.md           → Stage 10
```

`pipeline_orchestrator_v4.md` 定义的阶段（10 个阶段）：

```
Stage 1: Data Collection
Stage 2: Planning
Stage 3: Reviewers (×3)
Stage 4: Researchers (×3)
Stage 5: Consolidator
Stage 6: Audit
Stage 7: Fix
Stage 8: Fixer Expert
Stage 9: Harness Final
Stage 10: Summarizer
```

**✅ 两者一致**。

但 `pro_pipeline_orchestrator_v3.md` 定义的是 8 阶段 + 2 个 Harness 检查（Stage 3.5 和 7.5），阶段编号和文件命名完全不同。如果 cron_watcher 被用于监控 Pro v3 管线，就会完全错位。

### 8.4 Harness V2 自评的 harness_check 字段 vs task_builder.py 的 STAGE_OUTPUT_SCHEMA

`task_builder.py` 中的 `STAGE_OUTPUT_SCHEMA` 要求：
```json
"harness_check": {
  "completeness": { "score": 0.0-1.0, "level": "high/medium/low", "reasoning": "..." },
  "necessity": { ... },
  "alignment": { ... },
  "overall_score": 0.0-1.0,
  "decision": "PASS|WARNING|CRITICAL_WARNING|BLOCK_RECOMMENDATION"
}
```

但 `*_v2_harness.md` prompt 中的自评输出是：
```json
"harness_self_assessment": {
  "completeness_score": 85,  // 0-100 整数！
  "necessity_score": 90,
  "alignment_score": 88,
  "global_impact_score": 82,
  "overall": "green|yellow|red"  // 不是 PASS/WARNING！
}
```

**🔴 严重断裂**：
1. 分数范围：Schema 要求 0.0-1.0，prompt 要求 0-100
2. 字段名：Schema 用 `harness_check`，prompt 用 `harness_self_assessment`
3. 维度数：Schema 要求 3 维（completeness/necessity/alignment），prompt 要求 4 维（+global_impact）
4. 决策值：Schema 要求 PASS/WARNING/CRITICAL_WARNING/BLOCK_RECOMMENDATION，prompt 要求 green/yellow/red

**这是 P0 级别的不一致**。validate_stage_output() 会拒绝所有 v2_harness prompt 的输出。

---

## 九、总结与建议

### 9.1 P0 级别问题（必须修复）

1. **harness_check 字段断裂**：task_builder.py 的 STAGE_OUTPUT_SCHEMA 和所有 v2_harness prompt 的输出格式完全不兼容。分数范围、字段名、维度数、决策值全部不一致。

2. **build_fixer_task 缺少 `{{ AUDIT_PATH }}` 替换**：fixer_v2_harness 定义了 `{{ AUDIT_PATH }}` 模板变量，但 build_fixer_task 没有替换它。

3. **Auditor 输出格式三个版本不一致**：auditor.md / auditor_v2_harness.md / worker_auditor.md 的输出格式完全不同，下游消费者无法统一消费。

### 9.2 P1 级别问题（强烈建议修复）

4. **11 个废弃文件应清理**：pipeline_orchestrator ×3、worker_* ×7、deliver.md、pipeline_execution_guide.md。

5. **Harness V2 自评模板应提取为公共文件**：8 个 v2_harness prompt 的自评部分完全相同，复制粘贴维护。

6. **pro_pipeline_orchestrator_v3.md 内嵌伪代码**：Python 函数调用在 prompt 中无实际定义，AI 无法执行。

7. **Fixer → Fixer Expert 依赖链断裂**：fixer_expert 直接消费 auditor 输出，跳过 fixer。管线阶段编号和依赖关系需要明确。

### 9.3 P2 级别问题（建议优化）

8. **版本编号规则不统一**：_v2_harness 是 2.1.0，_v3 是 3.0.0，_v4 是 4.0.0。建议统一规则。

9. **researcher 的 `{{ mode }}` 变量无替换逻辑**：researcher_v2_harness 中有 `{{ mode }}` 变量，但 build_researcher_task 只替换了部分变量。

10. **planner.md 比 planner_v2_harness.md 更详细**：基础版（7.7KB）比 v2_harness（7.1KB）包含更多角色定义细节。v2_harness 应包含基础版的所有内容。

### 9.4 文件清理清单

```
删除（11个）:
  pipeline_orchestrator.md
  pipeline_orchestrator_v3.md
  pro_pipeline_orchestrator_v3.md
  worker_planner.md
  worker_researcher.md
  worker_auditor.md
  worker_reviewer.md
  worker_fixer.md
  worker_consolidator.md
  worker_summarizer.md
  deliver.md

归档（可选）:
  pipeline_execution_guide.md → docs/
  researcher.md → archived/
  planner.md → archived/
  auditor.md → archived/（最详细版本，建议保留为参考）
  fixer.md → archived/
  fixer_expert.md → archived/
  consolidator.md → archived/
  summarizer.md → archived/
  researcher_template.md → 与 v2_harness 合并

保留:
  cron_watcher.md（cron job 使用）
  architect.md（未来可能使用）
  solution_planner_pro.md
  pipeline_orchestrator_v4.md（当前活跃）
  harness_v3.md
  所有 *_v2_harness.md（8个，当前活跃）
  data_collection.md
  designer.md
```

---

> *评审结束。建议优先修复 P0 #1（harness_check 断裂），这是运行时一定会触发的错误。*

---

## 契约与配置一致性视角补充

> **评审维度**: 契约文件 ↔ 代码 ↔ 配置 ↔ SKILL.md ↔ 版本控制契约
> **评审日期**: 2026-06-01
> **评审人**: Subagent (契约架构专家 + DevOps 架构师)

---

### 1. 契约与代码一致性

#### 1.1 Cage 数量声明 vs 实际文件数

| 声明 (solution_v1.0.yaml) | 实际 | 状态 |
|:---|---:|:---|
| "13 Python modules" | **14 个 .py 文件** | ⚠️ 差 1（`__init__.py` 是否计入需澄清） |
| "32 Prompts" | **35 个 .md 文件** | 🔴 不符，差 3 个 |
| "Harness V2/V3" | ✅ V2 + V3 代码都存在 | ✅ |
| "Cron 巡检" | ✅ `cron_watcher.md` + SKILL.md 描述 | ✅ |

**多出的 3 个 Prompt 文件**（不在 cage worker_agents 列表中）：
- `pipeline_execution_guide.md` — 文档型 prompt，非 worker
- `pro_pipeline_orchestrator_v3.md` — V3 变体
- `researcher_template.md` — 模板文件

此外，`data_collection.md`, `deliver.md`, `architect.md`, `designer.md`, `planner.md`, `researcher.md`, `auditor.md`, `fixer.md`, `summarizer.md`, `consolidator.md` 这些 prompt **有文件但不在 cage worker_agents 声明中**。Cage 列的 worker 角色使用的是 `worker_*.md` 系列。存在 **两套并行 prompt 体系**：

1. **worker_*.md 系列**（8 个）：被 V2 Harness 管线实际使用
2. **角色名直命名系列**（planner.md, researcher.md, auditor.md 等，10+ 个）：被 config/solution.yaml 声明但代码中未使用

**结论**：`32` 可能是只算 worker + v2_harness 系列的数量，但笼统说 "32 Prompts" 没有区分活跃/废弃/模板。**建议 cage 明确列出活跃 prompt 数量。**

#### 1.2 Cage 管线声明 vs config.py stages vs orchestrator_agent.py 实际执行

| 来源 | 阶段列表 | 阶段数 |
|:---|:---|---:|
| **cage 描述** | `data_collection → planning → reviewers×3 → research×3 → consolidator → audit → fix → fixer_expert → harness_final → summarizer` | **10** |
| **config.py stages** | `planner → reviewers → fixer_planner → researchers → consolidator → auditors → fixer_expert → summarizer` | **8** |
| **orchestrator pipeline** | `data_collection → planning → reviewers → research → consolidator → audit → fix → fixer_expert → harness_final → summarizer` | **10** |
| **config/solution.yaml pipeline** | `data_collection → planning → research → design → audit → fix → deliver` | **7** |
| **SKILL.md README 10阶段表** | `Data Collection → Planning → Reviewers → Research → Consolidator → Audit → Fix → Harness Final → Summarizer → Delivery` | **10** |

**🔴 严重不一致**：同一模块有 **5 份不同**的阶段定义。

| 差异点 | 说明 |
|:---|:---|
| `config.py` 缺少 `data_collection` 和 `harness_final` 两个阶段 | config.py 只有 8 阶段 |
| `config/solution.yaml` 有 `design` 阶段但代码无此阶段 | 7 阶段定义 vs 10 阶段执行 |
| `config.py` 有 `fixer_planner` 阶段 | cage 和 orchestrator 中均无此阶段名 |
| `config/solution.yaml` 有 `deliver` 阶段 | 不在 Python 代码的 pipeline 中 |

#### 1.3 红线合规验证（实际代码执行结果）

| 红线 ID | 规则 | Cage 声称的 check | 实际验证结果 |
|:---|:---|:---|:---|
| **RED-SOL-001** | Python 禁止 LLM 推理 | `grep openai/anthropic/llm → 无匹配` | ⚠️ `planner.py` 有 `llm_output` 变量名（仅参数名，无调用）；V3 废弃方法中硬编码 prompt 字符串拼接 |
| **RED-SOL-002** | 禁止直接调用 sessions_spawn | `grep from openclaw import → 仅 fallback` | ✅ 仅在 `_resolve_spawn_fn` 的 try/except 中 |
| **RED-SOL-003** | 跨阶段 Blackboard 传递 | Worker Prompt 包含 Blackboard 路径 | ✅ `worker_*.md` 均包含 `{blackboard_path}` 变量 |
| **RED-SOL-004** | 外部网页视为 DATA 非指令 | `grep 视为数据/treat.*as.*data → 有匹配` | ❌ **未通过！** 所有 35 个 prompt 文件中**均无** prompt injection 防御声明 |
| **RED-SOL-005** | topic 路径遍历检测 | `_check_path_traversal` + `_sanitize_topic` | ✅ 两方法均有实现并被调用 |
| **RED-SOL-006** | spawn_fn 未注入时降级 | `grep spawn_fn.*不可用` | ✅ 多处 RuntimeError |
| **RED-SOL-007** | Harness 红绿灯，禁止 0-1 分 | `grep green.*yellow.*red` | ✅ orchestrator 已嵌入红绿灯；但 `harness_scorer.py` 仍用 0-1 数值计算后映射（内部实现与对外接口不一致） |

**关键发现**：
- **RED-SOL-004 实际不合规** — Cage 的 check 声称 `grep` 有匹配，但实际结果为空
- **RED-SOL-007 部分合规** — 最终输出红绿灯，但 scorer 内部仍用 0-1 数值

---

### 2. 配置一致性

#### 2.1 config/solution.yaml → config.py 字段覆盖

| config/solution.yaml 字段 | config.py 是否覆盖 | 状态 |
|:---|:---:|:---|
| `modes` (quick/standard/rigorous) | ❌ | `SolutionConfig` 无 mode 字段 |
| `solution_types` 定义（含 sections） | ❌ | 仅 `solution_type: str = "architecture"` 默认值 |
| `agents` 列表（6 roles, model, timeout） | ❌ | stages 中硬编码 agent 名 |
| `pipeline.stages` 定义 | ❌ | `config.py` 有独立的 stages 列表 |
| `model_chain` (primary/fallback/emergency) | ❌ | 不在 config.py 中 |
| `convergence` 配置 | ❌ | 不在 config.py 中 |
| `quality.dimensions` (5 维度权重) | ❌ | 不在 config.py 中 |
| `output.format/template_dir/language` | ❌ | 不在 config.py 中 |
| `delivery.progressive/checkpoints` | ❌ | 不在 config.py 中 |
| `concurrency.max_parallel_workers` | ❌ | 不在 config.py 中 |
| `session_id` / `topic` / `constraints` / `stakeholders` | ✅ | `SolutionConfig` 仅有的运行时字段 |
| `blackboard_path` | ✅ | 通过 PathConfig 解析 |

**结论**：`config.py`（48 行）仅覆盖 **5 个运行时参数**，完全不加载 `config/solution.yaml`（200+ 行）。两者是**孤立的**——YAML 文件存在但 Python 代码不读取它。唯一引用在 `check_contract.py`（仅检查文件存在性）。

#### 2.2 config.py stages vs orchestrator pipeline

`config.py` 定义了 8 阶段，`orchestrator_agent.py` 的 `pipeline` 属性定义了 10 阶段。**两套定义完全独立，互不引用。** 实际执行使用 orchestrator 自己的 pipeline 列表。

#### 2.3 data_sources/solution.yaml 使用情况

**结论：完全没有被代码使用。**
- `grep 'data_sources' domains/solution_pro/*.py` → **零匹配**
- 定义了 tech_documentation/industry_reports/competitor_analysis 搜索源
- orchestrator 的 `_run_data_collection` 使用 `web_search` 工具，不参考此配置
- 这是一个 **死配置文件**

---

### 3. SKILL.md 准确性

#### 3.1 架构描述 vs 实际

| SKILL.md 声明 | 实际情况 | 状态 |
|:---|:---|:---|
| "V4.1 架构: LLM Orchestrator + Cron 巡检" | 与 cage 中 `llm_orchestrator` 执行模式匹配 | ✅ |
| "10 个阶段" | 实际 10 阶段（cage + orchestrator） | ✅ |
| 步骤 1: `run_solution_pro()` exec 生成计划 | `__init__.py` 导出 `run_solution_pro` | ✅ |
| 步骤 4: spawn orchestrator 子 Agent | `pipeline_orchestrator_v4.md` 存在 | ✅ |
| 步骤 5: 创建 Cron 巡检 Agent | `cron_watcher.md` 存在 | ✅ |
| 三层退出机制 | 代码中有完整状态文件处理 | ✅ |
| 结尾标注 "V4.2" | 开头标注 "V4.1" | ⚠️ 版本号自相矛盾 |

#### 3.2 SKILL.md vs README.md 架构差异

| 维度 | SKILL.md | README.md | 状态 |
|:---|:---|:---|:---|
| 入口 | `run_solution_pro()` exec + sessions_spawn | `sessions_spawn` dispatcher 模式 | ⚠️ 两套入口 |
| 层数 | 主 Agent → orchestrator → cron | 主 Agent → Dispatcher → Workers | 🔴 不同 |
| 架构描述 | LLM Orchestrator + Cron 巡检 | 三层调度架构（旧 Dispatcher 模式） | 🔴 README 过时 |
| 版本 | V4.1/V4.2 | V3.4 | 🔴 版本严重滞后 |

**⚠️ README.md 的架构描述是旧版 V3.4**（三层 Dispatcher 调度），而 SKILL.md 描述的是新版 V4（LLM Orchestrator + Cron 巡检 + 三层退出）。**README.md 没有更新。**

#### 3.3 run_solution_pro 返回值

SKILL.md Step 1 说返回 `{session_id, base_path, plan_path}`。实际 `__init__.py` 返回一致。✅

---

### 4. 版本标识合规（version_control.md 对照）

#### 4.1 文件类型版本头覆盖

| 文件类型 | 数量 | 有版本头 | 无版本头 | 状态 |
|:---|---:|---:|---:|:---|
| Prompt .md | 35 | 35 ✅ | 0 | ✅ 全部有 Front Matter |
| Cage .yaml | 1 (`solution_v1.0.yaml`) | 1 ✅ | 0 | ✅ |
| Domain .yaml | 2 | 2 ✅ | 0 | ✅ |
| Contract .md | 1 | 1 ✅ | 0 | ✅ |
| Python .py | 14 | **0** ❌ | 14 | 🔴 全部缺失 |
| SKILL.md | 1 | **0** ❌ | 1 | 🔴 缺失 |
| README.md | 1 | **0** ❌ | 1 | ⚠️ 可选但建议 |

#### 4.2 Prompt 文件 Front Matter 字段完整性

根据 version_control.md §2.2，Prompt 必填字段：`id`, `version`, `component`, `updated`。

| 统计 | 数量 |
|:---|:---:|
| 缺少 `updated` 字段 | **27 个** Prompt 文件 |
| 缺少 `status` 字段 | **16 个** Prompt 文件 |
| 有 `requires` 依赖声明 | **0 个** |

**问题**：27 个 Prompt 文件缺少必填的 `updated` 字段。`version_control.md` 将其列为必填但大量文件未遵循。

#### 4.3 Cage 版本号内部冲突

`solution_v1.0.yaml`：
- `cage_version: "1.0.0"` — L2 图层级
- `version: "1.1"` — 文件内部声明

**两个版本号不一致**，且 `1.1` 不是三段式 SemVer。

---

### 5. Solution Pro 专属契约缺失

#### 5.1 与 Investment 对比

| 维度 | Investment | Solution Pro |
|:---|:---|:---|
| 专属 cage | ✅ `investment_v2.0.yaml` | ✅ `solution_v1.0.yaml` |
| Python 文件数 | ~10 | **14** |
| Prompt 文件数 | ~20 | **35** |
| 专属 contract 文件 | ✅ 有 | ❌ **无** |
| 配置运行时加载 | ✅ | ❌ config.py 不加载 config/solution.yaml |

#### 5.2 现有 solution_v1.0.yaml 的问题

现有 cage 文件已相当完整（redlines + interface + behavior + data + quality_gates），但存在：

1. **版本号不一致**：`cage_version: "1.0.0"` vs `version: "1.1"`
2. **stage 顺序与实际代码不一致**：cage 中 `reviewers` 在 `research` 之前，config/solution.yaml 中 `research` 在 `design` 之前
3. **缺失 data_collection worker**：`interface.worker_agents` 没有 data_collection，但 behavior/data 部分提到了它
4. **缺少对 config/solution.yaml 的引用**：cage 的 `data.config` 没有声明这些值必须与 YAML 同步

#### 5.3 建议

**不需要创建新的专属契约文件**。现有 `solution_v1.0.yaml` 已经足够全面，但需修复上述问题。

---

### 6. 不一致之处总结

| # | 不一致项 | 涉及文件 | 严重度 | 修复建议 |
|:---|:---|:---|:---:|:---|
| 1 | **Cage 声明 32 Prompts，实际 35 个** | `solution_v1.0.yaml` | 🟡 | 更新数字或分类列出活跃 prompt |
| 2 | **RED-SOL-004 实际不合规** | 所有 prompts/*.md | 🔴 | 在 data_collection.md 等 prompt 中添加 prompt injection 防御声明 |
| 3 | **5 份不同阶段定义互不匹配** | cage/config.py/config.yaml/orchestrator/README | 🔴 | 以 orchestrator pipeline 为权威来源统一 |
| 4 | **config.py 不加载 config/solution.yaml** | `config.py` + `config/solution.yaml` | 🟠 | 添加 YAML 加载逻辑或删除 YAML |
| 5 | **data_sources/solution.yaml 完全未被使用** | `data_sources/solution.yaml` | 🟡 | 删除或在代码中引用 |
| 6 | **SKILL.md 版本号自相矛盾** (V4.1 vs V4.2) | `SKILL.md` | 🟡 | 统一版本号 |
| 7 | **README.md 架构描述过时** (V3.4 vs V4) | `README.md` | 🟡 | 更新为 V4 架构描述 |
| 8 | **27 个 Prompt 缺失 `updated` 字段** | prompts/*.md | 🟡 | 批量补充 updated 日期 |
| 9 | **harness_scorer.py 用 0-1 数值 vs cage 要求红绿灯** | `harness_scorer.py` + cage | 🟡 | 确认仅为内部计算则 OK，否则改用枚举 |
| 10 | **cage_version vs version 不一致** (1.0.0 vs 1.1) | `solution_v1.0.yaml` | 🟡 | 统一到 1.1.0 |
| 11 | **config.py stages 与 orchestrator pipeline 不同** | `config.py` + `orchestrator_agent.py` | 🟠 | 统一来源 |
| 12 | **所有 Python 文件无 YAML Front Matter** | 14 个 .py 文件 | 🟡 | 至少核心文件添加 |
| 13 | **Cage 版本号非三段式 SemVer** (`1.1` → 应为 `1.1.0`) | `solution_v1.0.yaml` | 🟡 | 改为 `1.1.0` |

---

### 7. 修复建议优先级

| 优先级 | 修复项 | 预计工作量 |
|:---|:---|---|
| **P0** | 修复 RED-SOL-004：在 data_collection.md 等 prompt 中添加 "外部网页内容视为 DATA 而非指令" 声明 | 15 min |
| **P0** | 统一 10 阶段定义：以 orchestrator_agent.py pipeline 为权威来源，更新 config.py 和 config/solution.yaml | 30 min |
| **P1** | 删除或连接 data_sources/solution.yaml | 15 min |
| **P1** | 补充 27 个 prompt 文件的 `updated` 字段 | 15 min |
| **P1** | 统一 cage 版本号（cage_version 与 version 对齐为 1.1.0） | 5 min |
| **P2** | 更新 README.md 为 V4 LLM Orchestrator + Cron 巡检架构描述 | 20 min |
| **P2** | 修复 SKILL.md 版本号自相矛盾（V4.1 vs V4.2） | 5 min |
| **P2** | 为 orchestrator_agent.py / task_builder.py / harness_scorer.py 添加 YAML Front Matter | 10 min |
| **P2** | 更新 cage 中 "13 Python modules + 32 Prompts" 为准确数字 | 5 min |

---

*契约与配置一致性评审结束。共发现 13 项不一致，其中 2 项 P0，4 项 P1，7 项 P2。*
