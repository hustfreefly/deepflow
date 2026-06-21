# DeepFlow Changelog

> 最后更新: 2026-06-21

---

## [Unreleased] - 2026-06-21

### 🚀 New Features

#### Ship Pro V3 — 全新域
- 5-Agent 管线：Architect → Decomposer → Specifier → Reviewer → Packager
- 输入验证：Format A/B/C 自动检测 + 信息充足性评估
- 质量门禁：AC 质量验证 + 依赖合理性验证
- 修复流程：最多 2 轮修复循环
- 降级策略：超时自动降级

#### Summarizer 单文件输出改革
- 只保留 `final_result.json`，删除 `stages/summarizer.json` 和 `final_solution.md`
- REQ-ID 传播铁律：covered_req_ids 和 requirement_evidence 必须传播
- 12 个文件改动

#### Pipeline Watcher V2
- Python 脚本替代 cron agent（确定性逻辑）
- 两阶段采集 + 三层 best-effort 防线
- CloudEvents 信封 + SQLite WAL 存储
- 12 个问题发现并修复（4个 bug + 5个隐患 + 3个设计弱点）

#### Blackboard V2 目录结构（设计完成，待实施）
- `projects/{slug}/runs/{timestamp}/{spec,solution,ship}/` 三层结构
- 解决同 topic 重跑覆盖、Ship Pro 套娃、状态文件散落等问题
- path_config.py V2 方法：12个新方法已实现

### 🔧 Improvements

#### Solution Pro
- STAGE_PATH_REGISTRY v3.0.0：所有 stage 路径加 `solution/` 前缀
- task_builder.py：success_metrics 格式化简化
- SKILL.md：Pipeline Watcher V2 架构升级

#### Spec Pro V4.1
- constraints 权重分配变更：budget/timeline → platform/tech_stack/data_source
- eval/harness.py：SemanticGate 门控逻辑 + SC4→SC5 检查方法重命名
- QUALITY_GUIDE.md：新增 "Living Spec 数据结构参考" 章节

#### Core 基础设施
- path_config.py：新增 hashlib import + 路径哈希计算逻辑
- pipeline_orchestrator.py：summarizer 输出路径改为 final_result.json

#### Scripts
- pipeline_watcher.py：大量重构（scan_all、cron_id 自动发现、V2 配置）
- start_solution_pro.py：delivery_config 输出字段调整
- pipeline_progress_notify.py：修复 parse_args() + project_name 重构

### 📚 Documentation

#### 新建文档
- `QUALITY_GUIDE.md`：全链路质量评估方法论
- `contracts/shared/pipeline_watcher_design.md`：Pipeline Watcher 设计文档
- `contracts/shared/pipeline_watcher_v2_design.md`：Pipeline Watcher V2 设计文档
- `super_loop/README.md`：Super Loop 说明文档
- `docs/design/blackboard_system_redesign.md`：Blackboard 系统重设计方案
- `docs/design/DOMAIN_RECOVERY_PART1-7.md`：7个模块恢复手册

#### 专家评审
- Blackboard 重构方案：3位专家评审（架构师、LLM工程师、实施专家）
- AI Native 重设计提案：16位专家评审 + 3份综合报告

### 🧪 Tests

- `tests/test_e2e_living_spec_v2.py`：Living Spec V2 E2E 测试（25KB）
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

- **[Unreleased]**：6/11 之后的所有改动（尚未发布到 GitHub）
- **[1.0.0]**：6/11 GitHub 基线版本

---

## 已知问题

1. **Blackboard V2 目录结构**：设计完成但尚未实施
2. **task_builder.py**：38个旧版本 edits 待清理
3. **端到端测试**：尚未验证所有恢复的代码

---

## 下一步计划

1. 运行端到端测试验证当前恢复状态
2. 实施 Blackboard V2 目录结构（待稳定后）
3. 清理 task_builder.py 旧版本 edits
