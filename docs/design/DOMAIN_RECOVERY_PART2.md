# DeepFlow 按功能模块开发恢复手册 — Part 2: Solution Pro

---

## 2. Solution Pro（方案设计管线）

### 2.1 概述

**10阶段LLM管线**，从Living Spec生成完整解决方案（final_result.json）。

```
管线流程:
EntryHarness → Planning → Reviewer×3(并行) → Research×3(并行) → Consolidator → Audit → Fix → FixerExpert → HarnessFinal → Summarizer
```

**Harness V3 评分**: 完整性35% / 必要性25% / 目标一致性40%
**数据传递**: Blackboard JSON（blackboard/{session_id}/stages/）
**红绿灯评分**: 定性 green/yellow/red，禁止0-1数值分

### 2.2 新建文件（4个）

| 文件 | 说明 |
|:---|:---|
| `domains/solution_pro/prompts/REQ_DEDUP_DESIGN.md` | 需求去重设计文档 |
| `domains/solution_pro/reviews/review_edge_cases.md` | 边界情况评审 |
| `domains/solution_pro/reviews/review_execution_reliability.md` | 执行可靠性评审 |
| `domains/solution_pro/reviews/review_simplicity.md` | 简洁性评审 |
| `domains/solution_pro/scripts/validate_req_dedup.py` | 需求去重验证脚本 |
| `skills/solution-pro/orchestrator_prompt_v2.md` | Solution Pro编排器Prompt V2 |
| `tests/golden/verify_golden_case.py` | Golden Case验证脚本 |

### 2.3 修改文件（19个）

#### prompts/ — Agent Prompts

| 文件 | 改动摘要 |
|:---|:---|
| `prompts/summarizer.md` | **v5.4.0→v5.5.0** — 输出从3文件→1文件(final_result.json)；新增铁律6/7: covered_req_ids和requirement_evidence必须传播；删除Markdown文档结构要求 |
| `prompts/planner.md` | 新增implementation_readiness字段(D7治本)；知识框架字段从4个扩展到6个 |
| `prompts/consolidator.md` | 版本升至5.4.1；输出格式和角色定义微调 |
| `prompts/reviewer.md` | 版本升至5.4.1；输出格式调整；**新增REQ去重指令** |
| `prompts/pipeline_orchestrator.md` | 添加YAML frontmatter (id/version/component) |
| `prompts/orchestrator_completion.md` | summarizer输出从final_solution.md改为final_result.json |

#### Python代码

| 文件 | 改动摘要 |
|:---|:---|
| `blackboard.py` | STAGE_PATH_REGISTRY v2.1.0→**v3.0.0**；summarizer路径改为final_result.json；目录创建加solution/前缀 |
| `completion_handler.py` | REQUIRED_SOLUTION_FINAL_ARTIFACTS删除final_solution.md |
| `orchestrator_agent.py` | V2.4归一化：success_metrics/users统一为dict格式 |
| `task_builder.py` | 多处改动：pain_points/success_metrics/users格式化；harness_final.md模板变量；format_metrics_list使用；输出文件要求从3个→1个 |
| `frozen_spec.py` | success_metrics归一化逻辑修改；import路径修正 |
| `normalize.py` | metric归一化函数改进 |
| `check_contract.py` | 合同文件名更新（planner_v2_harness→planner等） |

#### eval/

| 文件 | 改动摘要 |
|:---|:---|
| `eval/propagation_checker.py` | final输出路径固定为final_result.json（移除summarizer.json降级） |
| `eval/test_v6_improvements.py` | 测试路径从final_solution.json改为final_result.json |
| `eval/CONTRACT_SUMMARIZER_SINGLE_FILE.md` | 状态标记为 ✅ verified |

#### 其他

| 文件 | 改动摘要 |
|:---|:---|
| `SKILL.md` | Cron Watcher→Pipeline Watcher V2架构升级；Python脚本替代cron agent |
| `QUALITY_GUIDE.md` | Prompt文件索引更新（pipeline_orchestrator_v6→pipeline_orchestrator） |
| `__init__.py` | Prompt路径从pipeline_orchestrator_v6.md改为pipeline_orchestrator.md |

### 2.4 关键决策

#### D1: Summarizer单文件输出改造（6/21）

**问题**: Summarizer写final_result.json时没有传播covered_req_ids和requirement_evidence，导致Ship Pro Architect在"信息荒漠"中工作

**根因链（3级）**:
```
L1（直接原因）: Summarizer写final_result.json时没传播covered_req_ids和requirement_evidence
L2（设计原因）: Summarizer prompt v5.4.0的输出契约只规定了结构字段名，没规定"必须传播哪些数据字段"
L3（系统原因）: 2026-06-19退役Frozen Blueprint后，final_result.json成为唯一交接文件。
               但Schema用oneOf支持4种格式变体，covered_req_ids是optional → 没有强制校验
```

**修复方案（Summarizer v5.5.0）**:
```markdown
## ⚠️ 数据传播铁律（新增）
final_result.json 必须包含以下字段（不可省略）：
1. covered_req_ids: 完整的REQ-ID列表
2. requirement_evidence: 完整的需求证据映射
3. final_solution.detailed_solution: 完整方案详情

禁止将final_result.json写成精简版。
```

**Schema加固**:
```json
{
  "required": ["status", "final_solution", "covered_req_ids"],
  "properties": {
    "covered_req_ids": {
      "type": "array",
      "minItems": 1
    }
  }
}
```

**完整改动文件**:
- `prompts/summarizer.md` — v5.5.0
- `prompts/orchestrator_completion.md` — 引用更新
- `prompts/task_builder.py` — 输出文件要求
- `blackboard.py` — STAGE_PATH_REGISTRY
- `completion_handler.py` — 删除final_solution.md检查
- `pipeline_orchestrator.py` — STAGE_PATHS
- `eval/propagation_checker.py` — 删除降级逻辑
- `scripts/golden_solution_pro_dry_run.py` — mock改动
- `tests/golden/verify_golden_case.py` — 检查改动

#### D2: REQ去重策略（6/19-21）

**问题**: 3个Reviewer各自输出54-122条REQ，大量重复

**分工**:
- **Reviewer层**: 领域内去重（同一维度内的重复REQ）
- **Consolidator层**: 跨域去重（跨维度的重复REQ）

**去重算法**: 三维检查法（主体+动作+约束），替代模糊的"语义相似度"
```
示例:
"系统应支持用户登录" vs "系统应支持用户注册"
→ 主体相同(系统)、动作不同(登录vs注册) → 不合并 ✅

"POST /api/login 应返回JWT token" vs "POST /api/login 应返回access_token"
→ 主体+动作相同、约束不同(JWT vs access_token) → 需进一步判断
```

**安全约束**: `POST /api/login` vs `POST /api/logout` 不能误合并

**ID保留规则**: `covered_req_ids[]` 保留全部原始ID（不丢弃），合并规则：保留最完整的一条，用最低REQ-ID

**验证脚本**: `validate_req_dedup.py` — 检查一致性+软性去重率警告

**去重效果**: 21个合并簇，从71个变成8个（忠礼对此表示惊讶）

**Prompt改动**:
- `prompts/reviewer.md` — 新增去重指令
- `prompts/consolidator.md` — 新增跨域去重指令

#### D3: Planner V6知识框架扩展（6/20）

**改动**: Planning阶段结构化字段从4个扩展到6个
- 新增 `implementation_readiness` 字段 (D7治本)
- 知识框架字段扩展

**Prompt改动**: `prompts/planner.md`

#### D4: success_metrics归一化（6/20）

**问题**: `list[dict]` vs `list[str]` 类型不匹配bug

**修复**:
- `orchestrator_agent.py` — V2.4归一化：success_metrics/users统一为dict格式
- `frozen_spec.py` — success_metrics归一化逻辑修改
- `normalize.py` — metric归一化函数改进
- `task_builder.py` — format_metrics_list使用

#### D5: Prompt YAML Frontmatter标准化（6/20）

**改动**: 所有prompt文件添加标准化YAML元数据
```yaml
---
id: summarizer
version: "5.5.0"
component: solution_pro
---
```

**影响文件**: `pipeline_orchestrator.md` 等全部prompt文件

#### D6: Pipeline Watcher兼容层改动（6/21）

**三方共识**: 先只改watcher兼容层，不动orchestrator prompt

**风险**: 改prompt可能导致管线卡住；工具切换（write→exec）混淆风险高

**已修复**: 7项低风险问题（详见Part 6 Pipeline Watcher章节）

### 2.5 Spec Pro→Solution Pro链路

| 文件 | 说明 |
|:---|:---|
| `docs/design/spec_pro_to_solution_pro_link_upgrade.md` | 链路升级设计 |
| `docs/design/spec_solution_link_v2.md` | 链路V2设计 |

**核心问题**: Living Spec的constraints字段从budget/timeline改为platform/tech_stack/data_source后，frozen_spec需要适配

**frozen_spec V2.0修复**:
- constraints全量遍历（从硬编码3个key→遍历confirmed_constraints.items()）
- guardrails.resolved提取（设计决策）
- inferred提取（AI推断）
- 信息保留率从<5%提升到~100%

### 2.6 待办

- [ ] final_result_v3.schema.json加固：covered_req_ids从optional→required
- [ ] Ship Pro Architect降级策略：当covered_req_ids缺失时，尝试读取stages/summarizer.json
- [ ] 交接文件统一化（长期）：final_result.json和stages/summarizer.json合并
- [ ] 去重率阈值验证：从71→8的去重率是否过于激进？需要更多案例验证
- [ ] Planner V6 implementation_readiness字段验证
