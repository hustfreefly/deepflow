# DeepFlow 按功能模块开发恢复手册 — Part 6: Pipeline Watcher + Core + Eval

---

## 6. Pipeline Watcher（管线监控）

### 6.1 概述

监控Solution Pro和Ship Pro管线运行状态，推送进度通知。

旧版: Cron Agent（LLM驱动）巡检 — 不稳定，经常发错误推送
新版V2: Python脚本(pipeline_watcher.py) + 薄wrapper prompt

### 6.2 改动文件

| 文件 | 改动 |
|:---|:---|
| scripts/pipeline_watcher.py | 大量重构：scan_all方法；cron_id自动发现；V2配置；排序/时间修复 |
| scripts/pipeline_progress_notify.py | 修复parse_args()调用；project_short_name→project_name重构 |
| contracts/shared/pipeline_watcher_design.md | 设计文档（新建） |
| contracts/shared/pipeline_watcher_v2_design.md | V2设计文档（新建） |

### 6.3 V2架构

两阶段采集 + 三层best-effort防线 + CloudEvents信封
SQLite存储模型：5表设计 + WAL模式 + 幂等写入

### 6.4 发现的12个问题

**🔴 当前Bug（4个，已全部修复）**:
1. Solution Pro __init__.py清理清单不完整（只清理3个文件，缺6个）→ 修复为9个
2. OrchestratorHeartbeat字段名不匹配（current_stage vs current_phase）→ 兼容层
3. CompletionChecker时区不一致（本地时区 vs UTC）→ 容错解析
4. Solution Pro的stages/和data/子目录不清理 → 新增清理

**🟡 隐患（5个，3个已修复）**:
5. emit()调sys.exit(0)但调用者不知道 — 未修复
6. lock file在emit时未关闭 → ✅ 已修复
7. StageDetector对Solution Pro的merge_group进度溢出(13/10) → ✅ 已修复
8. RunCounter.increment()读-改-写非原子 — 未修复
9. WRAPPER_PROMPT里{cron_job_id}没被替换 — 未修复

**🔵 设计弱点（3个）**:
10. orchestrator写.stage_progress.json靠LLM遵守prompt（随机性）
11. 没有watcher自检机制
12. 主Agent兜底清理没有代码保证

### 6.5 关键决策

#### D1: Cron路由修复
旧: 主Agent硬编码飞书open_id
新: 创建Cron时设delivery.mode="announce"，让系统自动路由

#### D2: 统一进度通知格式
设计: ⚡/✅/⚠️ + Unicode进度条 + 项目身份 + 紧凑/详细双模式
手机适配: 项目名完整显示不截断；短别名方案（4字以内）

---

## 7. Core 基础设施

### 7.1 path_config.py — V2 Blackboard方法

新增方法:
- get_projects_dir() — projects根目录
- get_research_dir() — research根目录
- get_project_path(slug) — 项目目录
- get_run_path(slug, run_id) — 运行目录
- get_domain_path(slug, run_id, domain) — 域目录
- generate_slug(topic, existing_slugs) — 人类可读slug
- generate_run_id(ts) — 时间戳格式运行ID
- is_v2_session_id(session_id) — V2格式判断
- parse_v2_session_id(session_id) — 解析V2 session_id
- get_blackboard_path_v2(slug, run_id, domain) — V2入口

新增imports: hashlib, unicodedata, datetime, Set

### 7.2 UnifiedEntry — Research Pro注册

core/unified_entry.py: 注册research_pro领域
domains: ['solution', 'code', 'general', 'research_pro']

---

## 8. 评估/质量体系

### 8.1 QUALITY_GUIDE.md — 全链路质量评估方法论

新建文件，覆盖Spec Pro → Solution Pro → Ship Pro端到端追溯
位置: 项目根目录QUALITY_GUIDE.md + domains/solution/QUALITY_GUIDE.md

### 8.2 Golden Case验证

tests/golden/verify_golden_case.py: 
- final_result.json检查（替代final_solution.md）
- 路径适配V2/V1双格式

### 8.3 Serenity Skills A股适配 — 全链路质量审查

发现: task_builder中success_metrics类型不匹配bug（list[dict] vs list[str]）
修复: orchestrator_agent.py V2.4归一化

### 8.4 需求去重验证

domains/solution/scripts/validate_req_dedup.py:
- 一致性检查
- 软性去重率警告
- 安全约束验证（POST /api/login vs /api/logout不误合并）
