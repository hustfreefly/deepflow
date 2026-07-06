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
python3 -c "from core.bootstrap import get_deepflow_root; print('DeepFlow root:', get_deepflow_root())"
# 应输出: DeepFlow root: /path/to/.deepflow
```

---

## 四大核心域

DeepFlow 有四个核心域，每个都有 `/命令` 快捷入口：

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

多阶段自动化管线，产出系统级架构方案。

```
你: /solution-pro 设计一个支持10000并发的实时推荐系统
AI: 🏗️ Solution Pro · 方案设计引擎
    正在生成执行计划...
    [自动执行多阶段管线]
    ✅ 方案已生成: blackboard/{project}/solution_document.md
```

**产出**: 完整架构方案（业务+架构+技术 三层设计）

---

### 3. Ship Pro — 交付编译引擎

```
/ship-pro
```

消费 Solution Pro 输出，拆分为可执行工作包（AI Coding 就绪）。

```
你: /ship-pro
AI: 🚢 Ship Pro · 交付编译引擎
    读取 Solution Pro 输出...
    [Designer → Workers → Consolidator]
    ✅ 交付包已生成: blackboard/{project}/ship_pro/stages/ship_package.json
```

**产出**: ShipPackage（工作包 + 依赖图 + 统计信息）

---

### 4. Research Pro — 深度研究引擎

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

## 四个域的协作流程

```
描述想法        梳理需求        设计方案        交付编译        深度研究
  │              │              │              │              │
  ▼              ▼              ▼              ▼              ▼
/spec-pro ───→ /solution-pro ─→ /ship-pro ─→ Research Pro
(想法→需求)    (需求→方案)     (方案→工作包)  (方案→调研报告)
```

也可以单独使用任何一个域。

---

## 目录结构说明

```
.deepflow/
├── README.md              # 项目整体说明
├── CHANGELOG.md           # 版本历史
├── CONTRACTS.md           # 契约定义
├── SKILL.md               # OpenClaw Skill 入口
│
├── core/                  # 核心框架
│   ├── master_orchestrator.py  # 主编排器
│   ├── quality/           #   质量门 + EntryHarness
│   ├── blackboard/        #   统一 Blackboard
│   ├── cage/              #   契约笼子
│   └── config/            #   配置管理
│
├── domains/               # 四个域（代码实现）
│   ├── spec_pro/          #   Spec Pro 代码
│   ├── solution_pro/      #   Solution Pro 代码
│   ├── ship_pro/          #   Ship Pro 代码
│   └── research_pro/      #   Research Pro 代码
│
├── contracts/             # 共享契约（Pydantic Schema）
│
├── docs/                  # 文档
│   └── guides/            #   上手指南（你在这里）
│
└── _archive/              # 归档文件（不影响使用）
```

**统一 Blackboard**：所有域的产出写入 `.deepflow/blackboard/{project_name}/`，跨域信息流靠文件路径约定。

---

## 完整触发列表

| 域 | 触发命令 | 说明 |
|------|------|------|
| Spec Pro | `/spec-pro` | 需求梳理 |
| Solution Pro | `/solution-pro` | 方案设计 |
| Ship Pro | `/ship-pro` | 交付编译 |
| Research Pro | `/research-pro` | 深度研究 |

> 💡 **查看所有 Skills**: 浏览 `skills/` 目录，每个子目录的 `SKILL.md` 的 `description:` 字段列出了触发方式。

---

## 常见问题

**Q: 必须用 OpenClaw 吗？能独立运行吗？**  
A: 目前核心编排依赖 OpenClaw 的 `sessions_spawn` / `sessions_yield`。独立运行在路线图中。

**Q: 搜索功能需要什么配置？**  
A: 配置 OpenClaw 的 `web.search.provider`（推荐 Brave Search）。Research Pro 也内置 DuckDuckGo 作为降级方案。

**Q: 怎么自定义研究维度或数据源？**  
A: 编辑 `domains/research_pro/config/` 下的 JSON 配置文件。

---

*DeepFlow v2.0.0 | 2026-07-06*
