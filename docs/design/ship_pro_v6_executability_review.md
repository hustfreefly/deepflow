# 可执行性评审报告 — Ship Pro V6 AI Native 架构

**评审人**: 可执行性评审专家（Subagent）  
**评审日期**: 2026-07-03  
**评审对象**: `docs/design/ship_pro_v6_architecture.md`  
**参考资料**:
- `domains/solution_pro/summary_orchestrator.py`（Solution Pro 5+1 Phase 实现）
- `domains/solution_pro/module_orchestrator_base.py`（ModuleOrchestrator 基类）
- `domains/ship_pro/v5/contracts/v5_ship_package.py`（V5 数据模型）
- `domains/ship_pro/scripts/orchestrator.py`（V3 编排器，已废弃）

---

## 总体评分

**7.5/10**

架构设计方向正确，核心模式（继承 ModuleOrchestrator + 动态 DAG + 约束笼子）在现有代码库中有成熟先例。主要风险集中在 **Phase 1 Planner 输出解析的可靠性** 和 **信息守恒检查的实现细节未定义**。无重大缺陷，但有两个需要立即细化的设计缺口。

---

## 优点

1. **ModuleOrchestrator 基类高度可复用**
   - `_adapted_spawn`、`_execute_parallel`、checkpoint 管理、state 管理全部直接可用
   - SummaryOrchestrator 的 5+1 Phase 实现证明了基类的扩展能力，ShipOrchestrator 的模式几乎相同
   - 基类已有 P0 约束注入（`_load_p0_constraints_prompt_block`）和软约束（`_get_system_soft_constraints`），Ship Pro 可直接继承

2. **约束笼子设计务实**
   - 三层约束（任务边界 + 角色边界 + 输出边界）覆盖了发散的主要来源
   - `optional_suggestion` 标记机制是低成本高收益的设计——允许 LLM "发泄"创造性而不污染主流程
   - 约束注入方式与 Solution Pro 的 prompt 构建模式一致（参见 `_build_phase_task`）

3. **Phase 3 固定验证层方向正确**
   - 4 层验证（Pydantic → 信息守恒 → 完整性 → Harness）遵循了 "代码验证格式，LLM 验证语义" 的 AI Native 原则
   - 前 2 层纯代码检查可快速拦截结构性问题
   - 与 Solution Pro 的 Harness 模式（Gate A + Gate B）一脉相承

4. **输入契约严格**
   - 只接受 `final_solution.json` 一个格式，避免了 V3 的 `detect_format()` 多分支复杂度
   - 与 Solution Pro 的输出契约完美对接

5. **对称性设计降低认知负担**
   - Solution Pro: Planner → Researcher → Summarizer
   - Ship Pro: Analyzer → Planner → Workers → Summarizer
   - 团队已熟悉 Solution Pro 的模式，学习成本极低

---

## 优化建议

### 1. Planner 输出必须结构化，不能依赖正则解析

**问题**: 架构文档说 "LLM 动态生成 Worker Prompt"，但没有定义 Planner 的输出格式。参考 SummaryOrchestrator 的 `_extract_analyzers()`，它用正则 `## Analyzer:\s*(.+?)` 从自由文本中提取面板——这在实际运行中**脆弱且难以调试**。如果 Planner 输出的格式略有偏差（比如用 `### Analyzer` 而非 `## Analyzer`），解析就会失败。

**建议**: 
- Planner 的输出必须定义为 **Pydantic Schema**（如 `PlannerOutput`），包含 `workers: List[WorkerSpec]`
- 每个 `WorkerSpec` 包含：`role`, `task_description`, `required_inputs`, `expected_outputs`, `needs_web_search`
- Worker Prompt 由 Orchestrator 根据 `WorkerSpec` + 约束笼子模板 **程序化拼接**，而非让 LLM 直接生成完整 Prompt
- 这样 Planner 只需输出结构化决策，Orchestrator 负责 Prompt 组装

**预期收益**: 
- 解析可靠性从 ~80% 提升到 ~99%
- Worker Prompt 质量更稳定（模板保证约束注入不遗漏）
- 调试时可直接检查 `WorkerSpec` 而非分析 LLM 的自由文本

---

### 2. 信息守恒检查需要明确的算法定义

**问题**: 架构文档提到 "Solution Pro 的 MUST 约束在产出中有对应"，但没有定义：
- "MUST 约束" 从哪里提取？（`final_solution.json` 中没有 `must_constraints` 字段）
- "对应" 的判定标准是什么？（关键词匹配？语义相似度？LLM 判断？）
- 检查失败时的处理策略？（FAIL？CONDITIONAL？）

**建议**: 
- 在 Solution Pro 的输出契约中增加 `key_constraints: List[str]` 字段（或在 `key_design_decisions` 中标记 `critical: bool`）
- 信息守恒检查分两层：
  - **L1 代码检查**: 提取 Solution Pro 中的 `key_design_decisions` 列表，检查 Ship Pro 产出的 `work_packages` 是否每个 decision 都有对应的 module/WP
  - **L2 LLM 检查**: 用 LLM-as-Judge 判断语义一致性（"Solution Pro 说用微服务，Ship Pro 的 WP 是否体现了微服务拆分？"）
- 失败策略：L1 失败 → FAIL；L2 失败 → CONDITIONAL（附 LLM 判断理由）

**预期收益**: 
- 信息守恒从"概念"变成可实现的检查项
- 避免 Phase 3 验证层沦为摆设

---

### 3. 动态 Worker 数量的上限控制

**问题**: 架构说 "spawn N 个 Worker Agent（动态数量）"，但没有上限。如果 Planner 判断需要 10 个 Worker，并行执行可能导致：
- API 并发限制
- 总超时不可控（`PHASE_TIMEOUT = 900s` 可能不够）
- Token 消耗爆炸

**建议**: 
- 设置 Worker 数量上限（建议 3-5 个），超过上限时 Planner 必须合并 Worker
- 在 Planner Prompt 中明确注入上限约束：`最多生成 N 个 Worker`
- 添加 `MAX_WORKERS` 常量到 `ShipOrchestrator`

**预期收益**: 
- 执行时间可预测
- 成本可控
- 避免资源争抢导致的超时

---

### 4. 复用 V5 Pydantic 模型作为输出 Schema

**问题**: 架构文档提到 "每个阶段的输出必须符合 Pydantic Schema"，但没有定义具体的 Schema。V5 已有成熟的 `ShipPackage`、`WorkPackage`、`Module`、`Requirement` 等模型（见 `v5_ship_package.py`），重新设计会浪费已有工作。

**建议**: 
- Phase 3 的最终输出直接复用 `ShipPackage`（或 `ShipPackageExtras`）
- Phase 2 Worker 的输出定义 `WorkerDeliverable` 新模型（每个 Worker 产出的工作包片段）
- Phase 1 Planner 的输出定义 `PlannerOutput` 新模型（建议 1 中已提到）

**预期收益**: 
- 减少 ~1 人天的 Schema 设计工作
- V5 → V6 迁移更平滑
- 已有的 `check_contract` 验证逻辑可复用

---

### 5. Phase 0 Analyzer 可以简化

**问题**: Phase 0 的职责（"判断任务类型、复杂度、是否需要 web search"）相对简单，但架构给了它独立的 Phase 地位。参考 Solution Pro，没有等价的 "分析" Phase——Planning 模块直接处理输入。

**建议**: 
- 将 Phase 0 的分析逻辑**合并到 Phase 1 Planner 的 Prompt 前缀**中
- Planner 先做分析（1-2 句结论），然后基于分析结果做规划
- 如果分析结论需要 web search，Planner 在 Prompt 中注入搜索结果为上下文

**预期收益**: 
- 减少 1 个 Phase（4 Phase → 3 Phase），降低编排复杂度
- 减少 1 次 spawn 调用，节省 ~30-60s 执行时间
- 分析与规划在同一 LLM 调用中完成，上下文更完整

**注意**: 此建议属于"局部调优"，不改四阶段结构。如果团队认为 Phase 0 独立存在有利于调试和可观测性，保留也完全可以。

---

### 6. 端到端测试策略需要分层

**问题**: 架构文档提到 "端到端测试"，但没有具体策略。Ship Pro V6 涉及 4 个 Phase + 动态 Worker + LLM 验证，端到端测试的失败定位极其困难。

**建议**: 分三层测试：
- **L1 单元测试**: 每个 Phase 的 `_run_*` 方法可独立测试（mock spawn_fn，验证输入输出 Schema）
- **L2 集成测试**: 用固定的 `final_solution.json` fixture 跑完整 pipeline，验证 Phase 间数据传递
- **L3 端到端测试**: 真实 spawn Agent，验证最终 `ship_package.json` 质量（仅用于验收，不用于 CI）

**预期收益**: 
- L1+L2 可进 CI，快速迭代
- L3 仅在发版前跑，避免每次提交都消耗大量 Token

---

## 重大缺陷

**无重大缺陷。**

有两个需要立即细化的设计缺口（已在优化建议中覆盖）：
1. Planner 输出格式未定义 → 可能导致 Phase 1→2 的数据传递不可靠
2. 信息守恒检查算法未定义 → 可能导致 Phase 3 验证层无法实现

这两个缺口不影响架构方向，但需要在编码前完成设计细化，否则实现阶段会返工。

---

## 实现工作量估算

| 阶段 | 工作内容 | 人天 | 说明 |
|------|---------|------|------|
| **Phase 0 Analyzer** | 合并到 Planner 或独立实现 | 0.5-1 | 如果保留独立 Phase：1 天；如果合并到 Planner：0.5 天 |
| **Phase 1 Planner** | Pydantic Schema 设计 + Prompt 设计 + 输出解析逻辑 | 2 | 核心难点：PlannerOutput Schema + WorkerSpec 解析 + 约束注入 |
| **Phase 2 Workers** | Worker 执行引擎 + Prompt 组装 + web search 集成 | 1.5 | 复用 `_execute_parallel`，新增 Worker Prompt 模板 + search 权限控制 |
| **Phase 3 Summarizer** | 汇总逻辑 + 4 层验证实现 | 2.5 | Pydantic Gate（0.5d）+ 信息守恒检查（1d）+ 完整性检查（0.5d）+ Harness 适配（0.5d）|
| **Orchestrator 骨架** | ShipOrchestrator 类 + state 管理 + checkpoint | 1 | 继承 ModuleOrchestrator，参考 SummaryOrchestrator |
| **Pydantic Schema** | PlannerOutput + WorkerDeliverable + 复用 ShipPackage | 1 | 含单元测试 |
| **端到端测试** | L1 单元测试 + L2 集成测试 + fixture 准备 | 1.5 | 含 mock spawn_fn 测试 |
| **总计** | | **10-10.5** | |

**关键路径**: Phase 1 Planner Schema 设计 → Phase 2 Worker Prompt 模板 → Phase 3 信息守恒检查

**风险缓冲**: 建议预留 2-3 天缓冲（Planner 输出解析的调试、信息守恒检查的 LLM-as-Judge 调优）

---

## 总结

Ship Pro V6 架构在可执行性上**整体可行**，核心模式（ModuleOrchestrator 继承 + 动态 DAG + 约束笼子）有成熟的代码库支撑。主要风险不在架构层面，而在**两个设计缺口的细化**：

1. **Planner 输出必须结构化**（Pydantic Schema，不是自由文本）
2. **信息守恒检查必须有明确算法**（L1 代码 + L2 LLM，不是模糊概念）

细化这两点后，实现工作量约 10 人天，关键路径清晰，可并行开发的模块较多（Phase 2 Workers 和 Phase 3 验证层可并行准备）。
