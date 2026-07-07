# DeepFlow Changelog

> 最后更新: 2026-07-08

---

## [V2.1.1] — 2026-07-08 — AI Native 反模式修复 + Wiki 更新

### 新增
- DAL (Domain Adaptation Layer) 架构 — 域推断从规则引擎改为 LLM 自推断
- 三层门控架构 (gate_harness_decision)
- Spec Pro 域上下文注入 (domain_context.py)
- Solution Pro DomainProfile 全链路透传
- 4 域 YAML 配置 (software/investment/hardware/business)

### 修复
- **P0 (5个)**: Gate B 关键词命中率、研究利用率子串匹配、硬编码语义分、正则代码检测、web_search 关键词匹配
- **P1 (10个)**: Cage F6/F7、VERDICT_MAP、harness 建议、conservation 参数化、domain_loader 精简、WP 阈值、状态机、Jaccard 去重、子串定位

### 变更
- 64 文件修改 (+5,165 / -989)
- 16+ Prompt 泛化（投资/硬件/商业多域示例）
- 测试: 179 passed, 10 skipped
- Wiki 全面更新

### AI Native 修复模式
代码做确定性粗筛（结构/标记/格式）→ LLM 做语义判断 → 代码合并决策

---

## [0.5.0] - 2026-06-23

### 🚀 Phase 0-3 架构加固

#### Phase 0: 止血
- 128 Schema 错 → 0
- contracts/generator.py CI 一致性检查

#### Phase 1: Pydantic 真相源 (Single Source of Truth)
- `contracts/architect.py` → ArchitectOutput Pydantic 模型
- `contracts/packager.py` → ShipPackage Pydantic 模型
- `contracts/generator.py` → 自动从模型生成 JSON Schema + Prompt 段落 + Gate 清单
- `gate_architect()` + `gate_packager()` → Pydantic 验证替代手写 `.get()`
- **效果**: 改一处 Pydantic 模型 → Schema/Gate/Prompt 自动对齐

#### Phase 2: 执行引擎化
- `scripts/orchestrator.py` → **DEPRECATED**（功能合并到 run_pipeline.py）
- `scripts/run_pipeline.py` → **唯一执行引擎** (prepare/task/gate/validate/status/update-status)
- `SKILL.md` 2.0.0 更新

#### Phase 3: 状态单一化
- `pipeline_state.json` → 唯一状态文件（基于 Pydantic PipelineState 模型）
- `pipeline_status.json` → **已删除**

### 📚 文档更新
- README.md → 四域架构，Ship Pro 加入
- SKILL.md → 2.0.0，四域架构
- docs/ARCHITECTURE.md → 2.0.0，Ship Pro 章节 + Phase 0-3 记录
- wiki/deepflow_overview.md → 更新架构图 + 版本说明

---

## [Unreleased] - 2026-06-21

### 🚀 New Features

#### Ship Pro 2.0.0 — 全新域
- 5-Agent 管线：Architect → Decomposer → Specifier → Reviewer → Packager
- 输入验证：Format A/B/C 自动检测 + 信息充足性评估
- 质量门禁：AC 质量验证 + 依赖合理性验证
- 修复流程：最多 2 轮修复循环
- 降级策略：超时自动降级

#### Summarizer 单文件输出改革
- 只保留 `final_result.json`，删除 `stages/summarizer.json` 和 `final_solution.md`
- REQ-ID 传播铁律：covered_req_ids 和 requirement_evidence 必须传播
- 12 个文件改动

#### Pipeline Watcher 2.0.0
- Python 脚本替代 cron agent（确定性逻辑）
- 两阶段采集 + 三层 best-effort 防线
- CloudEvents 信封 + SQLite WAL 存储
- 12 个问题发现并修复（4个 bug + 5个隐患 + 3个设计弱点）

#### Blackboard 2.0.0 目录结构（设计完成，待实施）
- `projects/{slug}/runs/{timestamp}/{spec,solution,ship}/` 三层结构
- 解决同 topic 重跑覆盖、Ship Pro 套娃、状态文件散落等问题
- path_config.py 2.0.0 方法：12个新方法已实现

### 🔧 Improvements

#### Solution Pro
- STAGE_PATH_REGISTRY v3.0.0：所有 stage 路径加 `solution/` 前缀
- task_builder.py：success_metrics 格式化简化
- SKILL.md：Pipeline Watcher 2.0.0 架构升级

#### Spec Pro 2.0.0
- constraints 权重分配变更：budget/timeline → platform/tech_stack/data_source
- eval/harness.py：SemanticGate 门控逻辑 + SC4→SC5 检查方法重命名
- QUALITY_GUIDE.md：新增 "Living Spec 数据结构参考" 章节

#### Core 基础设施
- path_config.py：新增 hashlib import + 路径哈希计算逻辑
- pipeline_orchestrator.py：summarizer 输出路径改为 final_result.json

#### Scripts
- pipeline_watcher.py：大量重构（scan_all、cron_id 自动发现、2.0.0 配置）
- start_solution_pro.py：delivery_config 输出字段调整
- pipeline_progress_notify.py：修复 parse_args() + project_name 重构

### 📚 Documentation

#### 新建文档
- `QUALITY_GUIDE.md`：全链路质量评估方法论
- `contracts/shared/pipeline_watcher_design.md`：Pipeline Watcher 设计文档
- `contracts/shared/pipeline_watcher_v2_design.md`：Pipeline Watcher 2.0.0 设计文档
- `super_loop/README.md`：Super Loop 说明文档
- `docs/design/blackboard_system_redesign.md`：Blackboard 系统重设计方案
- `docs/design/DOMAIN_RECOVERY_PART1-7.md`：7个模块恢复手册

#### 专家评审
- Blackboard 重构方案：3位专家评审（架构师、LLM工程师、实施专家）
- AI Native 重设计提案：16位专家评审 + 3份综合报告

### 🧪 Tests

- `tests/test_e2e_living_spec_v2.py`：Living Spec 2.0.0 E2E 测试（25KB）
- `tests/golden/verify_golden_case.py`：Golden Case 验证脚本

### 🐛 Bug Fixes

- **REQ 链路断裂**：Summarizer 写两个文件导致数据分裂 → 单文件输出改革
- **task_builder.py**：success_metrics 格式化简化（移除 isinstance 检查）
- **Pipeline Watcher**：12个问题修复（4个 bug + 5个隐患 + 3个设计弱点）

---

## [1.0.0] - 2026-06-11

### 🚀 Initial Release

#### Core Domains
- **Spec Pro**：需求收集与结构化引擎
- **Solution Pro**：方案设计与评审引擎（10阶段管线）
- **Research Pro**：深度研究引擎（四阶段状态机）

#### Infrastructure
- Blackboard 数据交换层
- Pipeline Orchestrator 管线编排器
- PathConfig 路径配置管理

#### Quality Assurance
- Harness 四维评分系统
- Multi-Reviewer 机制
- Golden Case 验证

---

## 版本说明

- **[0.5.0]**：2026-06-23 — Phase 0-3 架构加固 + Ship Pro 2.0.0
- **[Unreleased]**：6/11 到 6/22 之间的改动
- **[1.0.0]**：6/11 GitHub 基线版本

---

## 已知问题

1. **Blackboard 2.0.0 目录结构**：设计完成但尚未实施
2. **task_builder.py**：38个旧版本 edits 待清理
3. **端到端测试**：尚未验证所有恢复的代码

---

## 下一步计划

1. 运行端到端测试验证当前恢复状态
2. 实施 Blackboard 2.0.0 目录结构（待稳定后）
3. 清理 task_builder.py 旧版本 edits
