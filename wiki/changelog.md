# DeepFlow Changelog

> 最后更新: 2026-07-08

---

## [V2.1.1] — 2026-07-08 — AI Native 反模式修复 + DAL 架构

### 版本基线

| 域 | 版本 | 测试数 | Prompts | Modules |
|:---|:---|:---|:---|:---|
| Spec Pro | V2.2.0 | 52 | 8 | 18 |
| Solution Pro | V2.1.1 | 137 | 39 | 26 |
| Ship Pro | V2.0.0 | 19 | 1 | 3 |
| Research Pro | V2.0.0 | 136 | 8 | 10 |
| Core + Integration | — | 187 | — | — |
| **Total** | — | **531** | **56** | **57** |

### 新增
- **DAL (Domain Adaptation Layer)** — 域推断从规则引擎改为 LLM 自推断
- **三层门控架构** — `gate_harness_decision()` = L1(代码) + L2(LLM) + L3(合并)
- Spec Pro 域上下文注入 (`domain_context.py`)
- Solution Pro DomainProfile 全链路透传
- 4 域 YAML 配置 (software/investment/hardware/business)
- Spec Pro V2.2.0: LLM 域自推断 + 三层门控 + Harness 2.0.0
- Solution Pro V2.1.1: 三模块串联 (Planning → Research → Summary)
- Ship Pro V2.0.0: PipelineDesigner + Orchestrator 镜像架构
- Research Pro V2.0.0: 独立深度研究引擎

### 修复
- **P0 (5个)**: Gate B 关键词命中率、研究利用率子串匹配、硬编码语义分、正则代码检测、web_search 关键词匹配
- **P1 (10个)**: Cage F6/F7、VERDICT_MAP、harness 建议、conservation 参数化、domain_loader 精简、WP 阈值、状态机、Jaccard 去重、子串定位

### 变更
- 64 文件修改 (+5,165 / -989)
- 16+ Prompt 泛化（投资/硬件/商业多域示例）
- Wiki 全面重写 (2026-07-08)

### AI Native 修复模式
代码做确定性粗筛（结构/标记/格式）→ LLM 做语义判断 → 代码合并决策

---

## [0.5.0] — 2026-06-23

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

## [Unreleased] — 2026-06-21

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

#### Pipeline Watcher 2.0.0
- Python 脚本替代 cron agent（确定性逻辑）
- 两阶段采集 + 三层 best-effort 防线
- CloudEvents 信封 + SQLite WAL 存储

#### Blackboard 2.0.0 目录结构（设计完成，待实施）
- `projects/{slug}/runs/{timestamp}/{spec,solution,ship}/` 三层结构
- path_config.py 2.0.0 方法：12 个新方法已实现

---

## [1.0.0] — 2026-06-11

### 🚀 Initial Release

#### Core Domains
- **Spec Pro**: 需求收集与结构化引擎
- **Solution Pro**: 方案设计与评审引擎（10 阶段管线）
- **Research Pro**: 深度研究引擎（四阶段状态机）

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

| 版本 | 日期 | 关键变更 |
|:---|:---|:---|
| V2.1.1 | 2026-07-08 | DAL + 三层门控 + AI Native 反模式修复 |
| 0.5.0 | 2026-06-23 | Phase 0-3 架构加固 + Ship Pro 2.0.0 |
| Unreleased | 2026-06-21 | Ship Pro 2.0.0 + Pipeline Watcher 2.0.0 |
| 1.0.0 | 2026-06-11 | GitHub 基线版本 |
