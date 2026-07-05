# DeepFlow Overview

> 最后更新: 2026-06-23

---

## What is DeepFlow?

DeepFlow 是一个多 Agent 管线框架，运行在 OpenClaw 平台上。核心职责是将用户需求转化为可执行的方案。

### 管线架构 (2.0.0)

```
用户需求
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Spec Pro（需求收集与结构化）                            │
│  苏格拉底式对话 → Living Spec                          │
│  5维度 Output Guard 质量门禁                           │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Solution Pro（方案设计与评审）                          │
│  10阶段管线：Planning → Reviewers → Research →         │
│  Consolidator → Audit → Fix → Fixer Expert →           │
│  Harness Final → Summarizer                            │
│  4维度 Harness 评分 + Multi-Reviewer 机制              │
└─────────────────────────────────────────────────────────┘
    │ final_result.json 自动交接
    ▼
┌─────────────────────────────────────────────────────────┐
│ Ship Pro 2.0.0（执行交付）                               │
│  5-Agent 管线：Architect → Decomposer → Specifier →    │
│  Reviewer ↔ 反馈闭环 → Packager                       │
│  Pydantic 契约笼子 + run_pipeline.py 单一执行引擎      │
│  pipeline_state.json 唯一状态文件                      │
└─────────────────────────────────────────────────────────┘
```

### 辅助域

| 域 | 职责 | 与主链路关系 |
|:---|:---|:---|
| **Research Pro** | 深度研究与分析 | 独立域，不依赖主链路 |

---

## 核心组件

### Blackboard（数据交换层）

文件系统目录，每个运行产生一个目录，包含输入、阶段输出、状态文件、交付文件。

**当前结构（2.0.0）**：
```
blackboard/
└── {session_id}/
    ├── data/
    ├── stages/
    ├── final_result.json
    └── .completed, .cron_*, etc.
```

**计划结构（2.0.0，设计完成待实施）**：
```
blackboard/
├── projects/{slug}/runs/{timestamp}/
│   ├── spec/
│   ├── solution/
│   └── ship/
├── research/
└── archive/
```

### Pipeline Orchestrator（管线编排器）

LLM sub-agent，通过 `sessions_spawn` 启动。按固定阶段顺序执行管线。

### PathConfig（路径配置管理）

路径解析器，支持 2.0.0（`get_blackboard_path`）和 2.0.0（`get_blackboard_path_v2`）两种模式。

### Pipeline Watcher（管线监控）

Python 脚本 + 薄 LLM wrapper。监控管线运行状态，推送进度通知。

---

## 质量评估体系

### 全链路质量评估（QUALITY_GUIDE.md）

**双维度模型**：

1. **模块内质量（Intra-Module）**
   - Spec Pro: 5维度 Output Guard
   - Solution Pro: 4维度 Harness Scorer
   - Ship Pro: Quality Gate 2.0.0

2. **跨模块对齐（Cross-Module）**
   - 2A: 用户意图 → Solution Pro
   - 2B: Solution Pro → Ship Pro
   - 2C: 端到端追溯链

### 各域质量门禁

| 域 | 评估框架 | 决策阈值 |
|:---|:---|:---|
| Spec Pro | 5维度（清晰度/完整度/可执行度/一致度/适配度） | PASS ≥75 |
| Solution Pro | 4维度（完整性/必要性/目标一致性/全局影响） | PASS ≥0.85 |
| Ship Pro | 2项检查（AC质量 + 依赖合理性） | PASS = 0 issues |

---

## AI Native 原则

1. **确定性优先**：能用代码做的不用 LLM
2. **理解优于穷举**：用语义描述让 LLM 理解意图
3. **渐进交付**：分阶段实现
4. **不引入外部基础设施**：SQLite 存储
5. **Worker 零改动**：绝对红线
6. **代码的角色**：从"写代码"转变为"指导 AI、设计规范、验证结果"

---

## 技术栈

| 组件 | 技术 |
|:---|:---|
| 运行平台 | OpenClaw |
| 语言 | Python 3.9+ |
| 存储 | 文件系统（Blackboard）+ SQLite（Pipeline Watcher） |
| LLM 调用 | OpenClaw sessions_spawn / sessions_send |
| 通知 | 飞书 / Cron announce |

---

## 文件结构

```
.deepflow/
├── core/
│   ├── config/path_config.py          — 路径配置管理
│   └── orchestrator/
│       └── pipeline_orchestrator.py   — 管线编排器
├── domains/
│   ├── solution/                      — Solution Pro 域
│   ├── spec_pro/                      — Spec Pro 域
│   ├── ship_pro/                      — Ship Pro 域
│   └── research_pro/                  — Research Pro 域
├── scripts/
│   ├── start_solution_pro.py          — Solution Pro 启动脚本
│   ├── pipeline_watcher.py            — Pipeline Watcher 2.0.0
│   └── pipeline_progress_notify.py    — 进度通知
├── contracts/
│   └── shared/                        — 共享设计文档
├── docs/
│   ├── design/                        — 设计文档
│   └── research/                      — 研究文档
├── tests/                             — 测试文件
├── wiki/                              — 文档（本目录）
├── QUALITY_GUIDE.md                   — 全链路质量评估方法论
└── SKILL.md                           — DeepFlow 技能入口
```

---

## 版本历史

- **2026-06-23**：Phase 0-3 架构加固完成 — Pydantic 契约笼子 + 单一执行引擎 + 状态单一化；版本升至 2.0.0
- **2026-06-21**：Ship Pro 2.0.0 + Summarizer 单文件输出 + Pipeline Watcher 2.0.0 + Blackboard 2.0.0 设计
- **2026-06-11**：GitHub 基线版本（Spec Pro + Solution Pro + Research Pro 13项修复）

详见 [changelog.md](changelog.md)
