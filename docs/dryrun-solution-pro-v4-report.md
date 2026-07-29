# Agent DryRun 报告 — Solution Pro V4.0 (post ADR-009)

## 综合判定: 🟡 CONDITIONAL

| 维度 | 状态 | 摘要 |
|------|------|------|
| 🔑 Prompt 主线 | ⚠️ | MD-first 交付物引用正确 ✅，但 `_shared_subagent_rules.md` API 文档与 ADR-009 矛盾（声称 write_stage 不接收 str） |
| 🔴 人 | ✅ | 约束强制 96% 强约束（23/24），Agent 行为契约完整 |
| 🟡 料 | ✅ | frozen_living_md + solution_living_md round-trip 100%，测试覆盖充分（31 tests） |
| 🔵 法 | ✅ | 全链路数据流闭合，MD-first 跨域消费正确（Ship Pro 读 MD） |
| 🟣 环 | ✅ | 所有引用的 API/类均真实存在，无幽灵引用 |
| ⚫ 系统 | ⚠️ | Spawn task 使用文件引用模式 ✅，但 master_state.json 双源共存、research_digest 未注册契约层 |

---

## BLOCKER 汇总（4 项，必须修复）

| # | 问题 | 来源 | 影响 | 修复方向 |
|---|------|------|------|---------|
| B1 | `_shared_subagent_rules.md:59-60` API 文档错误：声称 write_stage 不接收 str、read_stage 只返回 dict。ADR-009 后 write_stage 接受 `Union[Dict, str]`，read_stage 对 .md 返回 str | Agent C | 所有 Worker Agent 被误导，可能不敢传 str 写 MD | 更新 API 快速参考，说明 write_stage 接受 str（写 .md）、read_stage 对 .md 返回 str |
| B2 | `research_expert_base.md:165-166` 完整复制了 B1 的错误规则 | Agent C | Research Expert 被误导 | 同步更新，或改为引用 `_shared_subagent_rules.md` |
| B3 | `summary_json_extractor.md` Prompt 示例中 `semantic_anchors` 字段名 (`anchor_id`/`concept`/`doc_section`) 与 Schema 定义 (`name`/`category`/`constraint`) 完全不一致 | Agent A | LLM 按 Prompt 产出错误字段名 → render 出空值 → 信息流断裂 | 修正 Prompt 示例字段名为 `name`/`category`/`constraint` |
| B4 | `post_validator.py:191,256` 硬编码 `bb.read_json("data/frozen_spec.json")` 而非使用 `read_stage` 的 MD-first 路径 | Agent B | 绕过 MD-first 架构，直接读 JSON | 改为 `bb.read_stage("data/frozen_spec")` 或先尝试 MD |

---

## 技术债汇总（12 项，可延后）

| # | 问题 | 来源 | 分类 | 修复方向 |
|---|------|------|------|---------|
| D1 | `research_digest` 未在 STAGE_PATH_REGISTRY / STAGE_CONTRACTS / STAGE_SCHEMA_MAP 注册 | Agent D | 残留引用 | 在三处注册表中添加 `research_digest` |
| D2 | `research_convergence` 是死契约（定义但零 Prompt 引用） | Agent D | 死代码 | 从 schemas.py / stage_contract.py 移除 |
| D3 | `master_state.json` 双源共存（orchestrator.md 声明废弃，__init__.py 仍写入） | Agent D | 状态管理 | 移除 __init__.py 中的写入，或更新文档 |
| D4 | `implementation_phases` Prompt 示例用旧字段名 (`name`/`duration`/`milestones`)，render 已兼容但 Prompt 应更新 | Agent A | 残留引用 | 修正 Prompt 示例为 `title`/`timeline`/`estimated_effort` |
| D5 | 8/11 Schema 无运行时强制（仅文档），包括 ExpertPlanSchema、ResearchExpertSchema 等 | Agent A | 死验证 | 评估是否需要运行时强制，或标记为 @deprecated |
| D6 | `task_builder.py:37` 本地重定义 `validate_stage_output()` 覆盖 schemas.py 的 Pydantic 版本 | Agent A | 架构不一致 | 统一使用 schemas.py 版本，或删除本地版本 |
| D7 | `planning_planner.md:130` "data 必须是 dict，不是 str" 过时 | Agent C | 残留引用 | 修正为 "data 接受 dict 或 str" |
| D8 | `summary_json_extractor.md` "source of truth 是 frozen_spec.md" 措辞不当 | Agent C | 措辞 | 改为 "living_spec.md 优先，frozen_spec.md 向后兼容" |
| D9 | `planning_module.md` 内 `bb`/`bm` 变量名混用 | Agent C | 一致性 | 统一为 `bb` |
| D10 | 14 个死代码函数（含整个 SolutionProPipelineState 类疑似 V3 遗留） | Agent B | 死代码 | 清理或标记 @deprecated |
| D11 | "生存铁律"/"Wake Response Protocol"/"生命周期协议" 在 planning_module.md 和 research_module.md 间 ~90% 重复（~75 行 × 2） | Agent C | 重复 | 提取到共享文件 |
| D12 | 跨域 MD 数据流缺少端到端集成测试（Solution Pro → Ship Pro） | Agent B | 测试覆盖 | 添加端到端测试 |

---

## 亮点（ADR-009 改造成果）

| 项目 | 状态 | 证据 |
|------|:----:|------|
| MD-first 代码落地 | ✅ | frozen_living_md + solution_living_md round-trip 100%，blackboard_manager 支持 str/dict 双模式 |
| 防回归测试 | ✅ | 17/17 测试通过，覆盖 write MD / read MD 优先 / JSON fallback / MD precedence / registry |
| 跨域数据流 | ✅ | Ship Pro 优先读 final_solution.md + parse_final_solution_md()，frozen_spec.md 被 pipeline_designer 消费 |
| Spawn Task 大小 | ✅ | Orchestrator ~350 chars（文件引用模式），V3.4 修复记录完整 |
| 约束强制 | ✅ | 96% 强约束（23/24 Pydantic raise ValueError） |
| 全链路数据流 | ✅ | Planning → Research → Summary → Ship Pro 无断裂 |

---

## 测试统计

| 指标 | 数值 |
|------|------|
| pytest passed | 150 |
| pytest failed | 1 (pre-existing: test_completion_marker_is_lightweight) |
| pytest skipped | 10 (需要真实 session 数据) |
| 防回归测试 | 17/17 ✅ |
| 约束强制率 | 96% (23/24 强约束) |

---

## 修复优先级建议

### P0（立即修复，阻断正确性）
1. **B1+B2**: 更新 `_shared_subagent_rules.md` + `research_expert_base.md` 的 write_stage/read_stage API 文档
2. **B3**: 修正 `summary_json_extractor.md` 的 semantic_anchors 字段名
3. **B4**: `post_validator.py` 改用 `read_stage` 的 MD-first 路径

### P1（近期修复，维护性）
4. **D1-D3**: 注册 research_digest、清理死契约、统一状态管理
5. **D4**: 修正 implementation_phases Prompt 示例字段名
6. **D7-D9**: 修正过时文档和变量名不一致

### P2（维护窗口清理）
7. **D5-D6**: 评估 Schema 运行时强制必要性、统一 validate_stage_output
8. **D10-D12**: 清理死代码、消除重复、添加端到端测试

---

## GO 条件

修复 B1-B4（4 个 BLOCKER）后可升级为 🟢 GO。
技术债不阻断执行，可在后续维护窗口处理。

---

*报告生成时间: 2026-07-29*
*体检框架: AgentDryRun V3.7*
*审计 Agent: 4 并行（A 代码+约束 / B 测试+扫描 / C Prompt 语义 / D 契约+系统）*
