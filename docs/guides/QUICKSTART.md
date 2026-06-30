# DeepFlow — 5 分钟上手指南

> 从 GitHub 下载到跑通第一个任务

---

## 前提：安装 OpenClaw

DeepFlow 运行在 [OpenClaw](https://docs.openclaw.ai) 平台上。先装 OpenClaw：

```bash
npm install -g openclaw
openclaw init
```

配置搜索 provider（Research Pro 需要）：

```bash
openclaw config set web.search.provider brave
openclaw config set web.search.apiKey YOUR_API_KEY
```

---

## 安装 DeepFlow

```bash
cd ~/.openclaw/workspace
git clone https://github.com/deepflow/deepflow .deepflow
```

验证安装：

```bash
cd .deepflow
python3 -c "from core.unified_entry import UnifiedEntry; print(UnifiedEntry().list_domains())"
# 应输出: ['solution', 'code', 'general', 'research_pro']
```

---

## 三大核心模块

DeepFlow 有三个核心模块，每个都有 `/命令` 快捷入口：

### 1. Spec Pro — 需求梳理引擎

```
/spec-pro
```

苏格拉底式对话，帮你把模糊想法变成结构化需求规格书。

```
你: /spec-pro
AI: 🧠 Spec Pro · 需求梳理引擎
    说说你想做什么？

你: 我要做一个内部知识库，200人技术团队用
AI: 好的，让我帮你梳理...
```

**产出**: Living Spec（JSON 格式需求规格书）

---

### 2. Solution Pro — 方案设计引擎

```
/solution-pro 设计一个AI算力调度平台
```

10 阶段自动化管线，产出系统级架构方案。

```
你: /solution-pro 设计一个支持10000并发的实时推荐系统
AI: 🏗️ Solution Pro · 方案设计引擎
    正在生成执行计划...
    [自动执行 10 阶段管线]
    ✅ 方案已生成: blackboard/sol_xxx/final_solution.md
```

**产出**: 完整架构方案（业务+架构+技术 三层设计）

---

### 3. Research Pro — 深度研究引擎

```
/research-pro 分析AI芯片市场趋势
深度研究 贵州茅台2024年投资价值
```

多源搜索 + 引用验证 + 结构化研究报告。

```
你: /research-pro 分析2026年AI芯片市场
AI: 🔬 Research Pro · 深度研究引擎
    正在生成研究计划...
    [自动搜索 → 分析 → 生成报告]
    ✅ 报告已生成: blackboard/research_pro_xxx/report/final.md
```

**产出**: 带引用验证的深度研究报告

---

## 三个模块的协作流程

```
描述想法           梳理需求           设计方案           深度研究
  │                 │                 │                 │
  ▼                 ▼                 ▼                 ▼
/spec-pro  ──────→ /solution-pro ──→ Research Pro
(想法→需求)        (需求→方案)       (方案→调研报告)
```

也可以单独使用任何一个模块。

---

## 目录结构说明

```
.deepflow/
├── README.md          # 项目整体说明
├── QUICKSTART.md      # ← 你在看的文件
│
├── core/              # 核心框架（编排器、质量门、黑板）
│   ├── orchestrator/  #   PipelineOrchestrator
│   ├── quality/       #   EntryHarness + QualityGate
│   ├── blackboard/    #   状态持久化
│   └── cage/          #   契约笼子
│
├── domains/           # 三个领域（代码实现）
│   ├── solution/      #   Solution Pro 代码
│   ├── research_pro/  #   Research Pro 代码
│   └── code/          #   Code domain (规划中)
│
└── skills/            # OpenClaw Skill 入口（用户触发）
    ├── spec-pro/      #   /spec-pro 触发入口
    ├── solution-pro/  #   /solution-pro 触发入口
    ├── research-pro/  #   /research-pro 触发入口
    └── ...            #   80+ 其他 skills
```

**`domains/` vs `skills/` 的关系：**

| 目录 | 面向 | 内容 | 类比 |
|------|------|------|------|
| `domains/` | 开发者 / AI 内部 | Python 代码 + 执行指南 | 引擎 |
| `skills/` | OpenClaw 用户 | 触发入口 + 使用说明 | 方向盘 |

用户在 `skills/` 里触发 → AI 读取对应 `domains/` 里的代码来执行。

---

## 完整 Skill 列表

除了三大核心模块，DeepFlow 还提供 80+ 扩展 Skills：

### 核心三大（`/命令` 触发）
| Skill | 触发 | 说明 |
|-------|------|------|
| Spec Pro | `/spec-pro` | 需求梳理 |
| Solution Pro | `/solution-pro` | 方案设计 |
| Research Pro | `/research-pro` | 深度研究 |

### 统一入口
| Skill | 触发 | 说明 |
|-------|------|------|
| DeepFlow | `/deepflow` | 导航页，选择模块 |

### 投资分析
| Skill | 触发 | 说明 |
|-------|------|------|
| stock-analysis | "分析XX股票" | A股/港股分析 |
| us-stock-analysis | "分析XX美股" | 美股分析 |
| market-analysis-cn | "市场分析" | 市场环境分析 |

### 飞书工具
| Skill | 触发 | 说明 |
|-------|------|------|
| feishu-send-report | "发报告" | 飞书发送报告 |
| feishu-doc-manager | "创建飞书文档" | 飞书文档管理 |

> 💡 **查看所有 Skills**: 浏览 `skills/` 目录，每个子目录的 `SKILL.md` 的 `triggers:` 字段列出了触发方式。

---

## 常见问题

**Q: 必须用 OpenClaw 吗？能独立运行吗？**  
A: 目前核心编排依赖 OpenClaw 的 `sessions_spawn` / `sessions_yield`。独立运行在路线图中。

**Q: 搜索功能需要什么配置？**  
A: 配置 OpenClaw 的 `web.search.provider`（推荐 Brave Search）。Research Pro 也内置 DuckDuckGo 作为降级方案。

**Q: 怎么自定义研究维度或数据源？**  
A: 编辑 `domains/research_pro/config/` 下的 JSON 配置文件。

---

*DeepFlow v0.4.0 | 2026-06-11*
