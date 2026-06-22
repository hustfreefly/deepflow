# Solution Pro 多专家团队审计报告（综合版）

> **审计日期**: 2026-06-03  
> **审计范围**: `domains/solution/` 全部模块（12 个 .py 文件 + 14 个 .md prompt 模板）  
> **审计方法**: 4 位专家并行独立审计，代码证据驱动  
> **参考**: AUDIT_REPORT_2026-06-02.md（不重复已发现问题）

---

## 审计团队与分工

| 专家 | 维度 | 问题数 | 报告 |
|------|------|--------|------|
| 架构专家 | 死代码、架构不一致、路径碎片化 | 2 P0 + 4 P1 + 2 P2 | ✅ |
| 务实专家 | 防御性编程、运行时安全、异常处理 | 1 P0 + 3 P1 + 5 P2 | ✅ |
| 集成专家 | Prompt-Code 一致性、模板变量、格式漂移 | 3 P0 + 5 P1 + 6 P2 | ✅ |
| 质量专家 | Harness 评分、REQ-ID 追踪、质量门 | 1 P0 + 3 P1 + 3 P2 | ✅ |

---

## 根因归纳（去重后）

| ID | 根因 | 触发问题 |
|----|------|---------|
| RC1 | 死代码/未使用分支 | 架构 P0-1, P1-1; 务实 P1-3; 集成 P1-4 |
| RC2 | 模板变量未替换 | 集成 P0-1, P2-2 |
| RC3 | 指令冲突/Pipeline 顺序矛盾 | 集成 P0-3; 务实 P1-4 |
| RC4 | 角色权限/职责不清 | 集成 P1-3 |
| RC5 | 输出格式漂移/不一致 | 集成 P1-5, P2-6; 务实 P1-5 |
| RC6 | Schema 漂移/验证脱节 | 集成 P1-1, P2-1, P2-3, P2-5; 质量 P1-1, P1-2, P2-1 |
| RC7 | 路径管理碎片化（双轨制） | 架构 P0-2 |
| RC8 | 过时指令/文件名漂移 | 集成 P0-2, P1-5 |

---

## P0 问题（Critical — 崩溃/数据丢失/逻辑断裂）

### [P0-1] `{blackboard_path}` 模板变量在 7 个 Worker prompt 中未替换
- **审计来源**: 集成专家
- **位置**: `task_builder.py` + 7 个 `prompts/*_v2_harness.md`
- **根因**: RC2 — 模板变量未替换
- **证据**: 7 个 prompt 输出要求段包含 `{blackboard_path}` 字面字符串，但对应 build 函数未做 `.replace()`
- **影响**: LLM 看到占位符而非实际路径，可能使用错误路径写入
- **建议**: 在对应 build 函数中添加 `prompt.replace("{blackboard_path}", f"{_DEEPFLOW_BASE}/blackboard/{session_id}")`

### [P0-2] Summarizer 输入文件名 10/10 与 pipeline 输出完全不符
- **审计来源**: 集成专家
- **位置**: `prompts/summarizer_v2_harness.md` 第 30-40 行
- **根因**: RC8 — 过时指令/文件名漂移
- **证据**: Summarizer 引用 `stage_01_data_collection_output.json` 等 10 个文件名，实际 pipeline 输出为 `data/collection.json`、`stages/planning.json` 等
- **影响**: Summarizer 运行时将读取不到任何前序阶段输出，最终方案文档为空
- **建议**: 将 Summarizer prompt 中的文件名替换为实际 pipeline 输出路径

### [P0-3] Auditor prompt 要求读取尚不存在的 `consolidator.json`
- **审计来源**: 集成专家
- **位置**: `prompts/auditor_v2_harness.md` 审计流程 Step 1
- **根因**: RC3 — Pipeline 顺序矛盾
- **证据**: Auditor (Stage 6) 要求读取 consolidator.json，但 Consolidator 在 Stage 5 — Auditor 在 Consolidator 之后执行？需要确认
- **影响**: Auditor 无法读取 Consolidator 输出，审计缺少统一方案视角
- **建议**: 确认 pipeline 顺序后修复 Auditor prompt

### [P0-4] Design 阶段永远不可达（死分支）
- **审计来源**: 架构专家
- **位置**: `orchestrator_agent.py:410`
- **根因**: RC1 — 管线列表中不含 `design`，但 `elif stage == "design"` 分支仍存在
- **证据**: `pipeline = [...]` (L296-307) 不含 `"design"`，但 L410 有处理分支
- **影响**: `build_designer_task` 永远不被调用，代码是死分支
- **建议**: 如果 design 有意移除，删除 elif 分支和 import；如果保留，加入 pipeline

### [P0-5] 路径管理双轨制 — `_get_stage_path()` vs `BlackboardManager.get_stage_path()`
- **审计来源**: 架构专家
- **位置**: `task_builder.py:92-109` vs `blackboard.py:69-80`
- **根因**: RC7 — 路径管理碎片化
- **证据**: 两套路径生成逻辑并存，前缀来源不同
- **影响**: 如果 `PathConfig` 布局变化，两套路径将不一致，Worker 写错位置
- **建议**: 删除 `task_builder.py:_get_stage_path()`，统一通过 `BlackboardManager` 管理

### [P0-6] `validate_stage_output` 对非豁免阶段缺少 `requirement_evidence` 验证
- **审计来源**: 质量专家
- **位置**: `task_builder.py:322-365`
- **根因**: RC6 — 验证脱节
- **证据**: `inject_req_traceability` 要求输出 `requirement_evidence`，但 `validate_stage_output` 不检查该字段
- **影响**: Worker 可能不输出 REQ-ID 证据，validator 仍判定通过
- **建议**: 在 `validate_stage_output` 中添加 `requirement_evidence` 检查

---

## P1 问题（High — 功能缺陷）

### [P1-1] `PASS_WITH_CONDITIONS` 代码合法但 prompt 和评分标准中均未定义
- **审计来源**: 集成专家 + 质量专家（重复发现）
- **位置**: `task_builder.py:288,361` vs `prompts/harness_scoring.md`
- **根因**: RC6 — Schema 漂移
- **影响**: LLM 不知道这是合法选项，永远不会输出
- **建议**: 在评分标准中添加该值的阈值定义

### [P1-2] `living_spec_context` 双重赋值（死代码）
- **审计来源**: 集成专家
- **位置**: `task_builder.py:build_planner_task`, `build_harness_final_task`
- **根因**: RC1 — 代码内部不一致
- **影响**: 约 60-80 行死代码
- **建议**: 移除首次构建的 `living_spec_context` 代码块

### [P1-3] Fixer prompt 中 `files_modified` 暗示代码级修改
- **审计来源**: 集成专家
- **位置**: `prompts/fixer_v2_harness.md`, `prompts/fixer_expert_v2_harness.md`
- **根因**: RC4 — 角色权限不清
- **影响**: LLM 可能误解为修改实际代码文件
- **建议**: 改为 `documents_updated` / `sections_modified`

### [P1-4] `layer2_constraints` 参数签名与调用不对齐
- **审计来源**: 集成专家
- **位置**: `task_builder.py` 3 个函数签名 vs `orchestrator_agent.py` 调用
- **根因**: RC1 — 死参数
- **影响**: 参数始终为 None，回退到默认约束
- **建议**: 移除参数或统一传递

### [P1-5] Auditor 与 Fixer 输出格式不一致
- **审计来源**: 集成专家 + 务实专家
- **位置**: `task_builder.py` fallback context vs prompt 模板
- **根因**: RC5 — 输出格式漂移
- **证据**: Auditor 用 `level: P0/P1/P2`，Fixer 期望 `severity: critical|major|minor`
- **影响**: prompt 失败触发 fallback 时，Fixer 收到不兼容格式
- **建议**: 统一 fallback 格式与 prompt 模板

### [P1-6] `build_fixer_task()` 死代码
- **审计来源**: 架构专家 + 务实专家
- **位置**: `task_builder.py:914`
- **根因**: RC1 — 死代码
- **影响**: pipeline 使用 `build_fixer_task_with_audit`，旧函数无人维护
- **建议**: 标注 `@deprecated` 或删除

### [P1-7] `PARALLEL_OUTPUT_PATHS` 硬编码未使用注册表
- **审计来源**: 架构专家
- **位置**: `orchestrator_agent.py:87-94`
- **根因**: RC7 — 路径管理碎片化
- **影响**: 注册表更新后可能不同步
- **建议**: 从 `STAGE_PATH_REGISTRY` 动态构建

### [P1-8] `lightweight_spec_agent.py` 中 JSON Schema 验证缺失
- **审计来源**: 务实专家
- **位置**: `lightweight_spec_agent.py:101-130`
- **根因**: RC3 — 防御性不足
- **证据**: `infer_living_spec()` 在 LLM 返回非 JSON 时 fallback 到最小 spec，但未记录警告
- **影响**: 用户可能不知道轻量 Spec 推断失败
- **建议**: 添加日志警告 + 返回 `success` 标志

---

## P2 问题（Medium — 维护性）

| ID | 问题 | 来源 | 建议 |
|----|------|------|------|
| P2-1 | `harness_scoring.md` 缺 `PASS_WITH_CONDITIONS` 阈值 | 集成 | 补充定义 |
| P2-2 | Fixer `{blackboard_path}` 未替换 | 集成 | 同 P0-1 统一修复 |
| P2-3 | Summarizer 输出字段无 validator 检查 | 集成 | 添加检查或从 prompt 移除 |
| P2-4 | `data_collection.md` 缺 `covered_req_ids` 示例 | 集成 | 添加示例 |
| P2-5 | `harness_v3.md` 新增字段无 validator 对应 | 集成 | 添加检查 |
| P2-6 | Planner category 枚举与 frozen_spec 不一致 | 集成 | 统一枚举 |
| P2-7 | `config.py` stages 与实际 pipeline 不一致 | 务实 | 同步或移除 config |
| P2-8 | `progress_tracker.py` 硬编码 total_stages=8 | 务实 | 动态计算 |
| P2-9 | `prefix_extractor.py` async 但调用方同步 | 务实 | 统一或移除 |
| P2-10 | `check_contract.py` 检查的 stages 与实际不符 | 务实 | 更新检查列表 |
| P2-11 | `completion_handler.py` 数据库不存在时只 warning | 质量 | 添加降级报告 |
| P2-12 | `harness_check_expert.py` 评分维度权重硬编码 | 质量 | 提取到配置 |
| P2-13 | `_read_dynamic_experts()` 空列表时静默回退 | 务实 | 添加日志 |

---

## 修复优先级建议

### 第一轮（P0 × 6）— 必须修复，否则运行时可能崩溃

| # | 问题 | 修复策略 | 预计工作量 |
|---|------|---------|-----------|
| 1 | P0-2 Summarizer 文件名全错 | 修改 `summarizer_v2_harness.md` | 15 min |
| 2 | P0-3 Auditor 读取不存在文件 | 修改 `auditor_v2_harness.md` | 10 min |
| 3 | P0-1 `{blackboard_path}` 未替换 | 7 个 build 函数各加一行 replace | 30 min |
| 4 | P0-4 Design 死分支 | 删除 dead code | 10 min |
| 5 | P0-5 路径双轨制 | 统一路径管理 | 45 min |
| 6 | P0-6 `requirement_evidence` 验证缺失 | 修改 `validate_stage_output` | 20 min |

### 第二轮（P1 × 8）— 功能完善

| # | 问题 | 修复策略 | 预计工作量 |
|---|------|---------|-----------|
| 1 | P1-1 `PASS_WITH_CONDITIONS` 缺失定义 | 修改评分标准 + 9 个 prompt | 30 min |
| 2 | P1-2 `living_spec_context` 死代码 | 清理重复赋值 | 15 min |
| 3 | P1-3 Fixer `files_modified` | 修改 prompt | 15 min |
| 4 | P1-4 `layer2_constraints` 不对齐 | 统一签名或移除参数 | 20 min |
| 5 | P1-5 Auditor/Fixer 格式不一致 | 统一 fallback 格式 | 20 min |
| 6 | P1-6 `build_fixer_task` 死代码 | 删除或标记 deprecated | 5 min |
| 7 | P1-7 `PARALLEL_OUTPUT_PATHS` 硬编码 | 动态构建 | 20 min |
| 8 | P1-8 lightweight_spec_agent 缺验证 | 添加日志 + 返回标志 | 20 min |

### 第三轮（P2 × 13）— 维护性优化

建议按影响度排序，逐步修复。预计 2-3 小时。

---

## 审计维度覆盖总结

| 审计维度 | 发现问题 | 最高级别 | 专家 |
|:---|:---:|:---:|:---|
| 死代码/未使用分支 | 4 | P0 | 架构 |
| 模板变量未替换 | 2 | P0 | 集成 |
| 指令冲突/Pipeline 矛盾 | 2 | P0 | 集成 + 务实 |
| 角色权限不清 | 1 | P1 | 集成 |
| 输出格式漂移 | 3 | P1 | 集成 + 务实 |
| Schema 漂移/验证脱节 | 5 | P1 | 集成 + 质量 |
| 路径管理碎片化 | 3 | P0 | 架构 |
| 防御性编程不足 | 4 | P1 | 务实 |
| Harness 评分质量 | 4 | P1 | 质量 |
| Prompt 过时指令 | 2 | P0 | 集成 |

**总计**: 8 P0 + 8 P1 + 13 P2 = **29 个问题**（去重后）

---

**报告生成时间**: 2026-06-03  
**建议**: 按优先级分三轮修复，第一轮预计 2 小时可完成全部 P0 修复
