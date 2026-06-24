# AI Native Loop 架构研讨纪要

> **日期**: 2026-06-25  
> **参与者**: 8 位 AI Native 专家（分三轮研讨）  
> **主持人**: 小满（OpenClaw Agent）  
> **决策者**: 姬忠礼  
> **状态**: 方案讨论阶段（未进入开发）

---

## 一、研讨背景

### 1.1 目标

建立一套 AI Native 的 Loop Engineering 体系，让 Agent 能够自主、长时间、可靠地执行复杂任务。

Loop Engineering 是 2026 年 5-6 月业界最前沿的方向（Claude Code /goal、OpenAI Codex Subagents、Google A2A 协议等均已落地），核心思想是：**人类定义目标，AI 决定路径，AI 自我验证，AI 自我进化。**

### 1.2 技术生态

| 工具 | 定位 | 说明 |
|------|------|------|
| **OpenClaw** | 主 Loop 控制器 | 决策中枢，有 memory、cron、sessions_spawn、message 等 |
| **Codex CLI** | 编码执行者 | 打工者角色，Full Auto 模式，沙箱执行 |
| **Hermes Agent** | 协作伙伴 | Nous Research 开源 AI Agent，有自己的 Loop、记忆、Skill |
| **Claude Code** | 审查 / 长任务 | 代码审查和复杂长任务执行 |
| **飞书/邮件/GitHub** | 通信 + 代码托管 | 人在环、多渠道通知 |

### 1.3 关键约束（忠礼决策）

1. **一步到位**：不要分阶段演进，直接做全 AI Native
2. **基于当前平台能力**：OpenClaw 现在能支持什么就做什么，不考虑未来升级
3. **AI Native 纯粹性**：Python 不做控制流，LLM 做所有决策
4. **不要问我技术实现细节**：自己调研，不懂就 web search

---

## 二、专家阵容

### 第一轮：4 位专家（基础研讨）

| # | 角色 | 核心主张 |
|---|------|---------|
| 1 | **Loop Engineering 原语设计师** | /goal 是契约不是检查器；三种 Loop 模式（Burst/Heartbeat/Event）；Goal 可嵌套、可演化、可优先级竞争 |
| 2 | **Self-Evolving Agent 架构师** | Agent 不仅执行任务，还要自我进化；三层架构（执行→进化→Meta）；基因式技能进化 |
| 3 | **Multi-Agent Swarm 设计师** | 编舞式（Choreography）替代编排式（Orchestration）；无控制器黑板架构；信息素衰减 |
| 4 | **OpenClaw Loop 平台架构师** | 分形 Loop（外/中/内三层）；间歇式心跳；文件即状态、目录即 Loop |

### 第二轮：3 位专家（聚焦分歧 + 面向未来）

| # | 角色 | 核心主张 |
|---|------|---------|
| 5 | **激进 AI Native 纯粹主义者** | 面向 2027 模型能力设计；Python 控制层从一开始就不应该有；三层演进路线（过渡→桥接→原生） |
| 6 | **面向未来系统架构师** | 当前 33% 成功率是设计失败不是 LLM 失败；架构应随模型升级自然解锁更多能力 |
| 7 | **多工具 AI 生态架构师** | 监督式自治（Supervised Autonomy）；异步事件+文件契约；任务黑板+能力拍卖 |

### 第三轮：1 位专家（一步到位可行性分析）

| # | 角色 | 核心主张 |
|---|------|---------|
| 8 | **全 AI Native 一步到位实践者** | 没有不可逾越的障碍；5 个真实挑战全部可创造性绕过；Hermes 是协作伙伴不是子 Agent |

---

## 三、业界调研发现

### 3.1 Loop Engineering 是当前最前沿方向

2026 年 5-6 月最热概念。核心三件套：
- **/goal**：可验证的终止条件（自然语言，不是代码）
- **/loop**：迭代执行循环（Reason → Act → Observe → Repeat）
- **/routines**：定时/事件触发的自动任务

Claude Code 和 OpenAI Codex 都已实现这套原语。

### 3.2 协议标准已成熟

| 协议 | 发起方 | 版本 | 作用 | 治理 |
|------|--------|------|------|------|
| **A2A** (Agent-to-Agent) | Google | v1.0 | Agent↔Agent 通信标准 | Linux Foundation |
| **MCP** (Model Context Protocol) | Anthropic | 已 GA | Agent↔工具标准接口 | Agentic AI Foundation |

A2A + MCP 互补：MCP 管 Agent 怎么用工具，A2A 管 Agent 之间怎么通信。已有 150+ 组织在生产环境使用 A2A。

### 3.3 Hermes Agent（Nous Research）

开源 AI Agent，2026 年 2 月发布。核心能力：
- 持久记忆 + 学习循环（自动创建可复用 Skill）
- 多平台网关（Telegram/Discord/Slack/WhatsApp/Signal/CLI）
- 执行环境（本地/Docker/SSH/Serverless）
- 浏览器自动化（搜索、点击、截图）
- 并行子 Agent
- 模型无关（OpenAI/Anthropic/Google/200+ 模型）
- 定时自动化（内置 cron）
- MLOps + AI 训练平台

**定位**：完整的 AI Agent，不是 API 工具。有自己的 Loop、记忆、Skill。

### 3.4 OpenAI Codex CLI

开源编码 Agent（v0.120.0），核心特征：
- 在终端中运行，有完整文件系统和 git 访问
- 三种模式：Suggest / Auto Edit / Full Auto
- 在沙箱目录中运行
- 支持 GPT-5 系列 + 开源模型（通过 Ollama）
- Codex Subagents GA：Manager + Explorer（只读扫描）+ Worker（写权限+沙箱）

### 3.5 Codex Subagents 框架

2026 年 3 月 GA。三层架构：
- **Manager Agent**：理解高层目标，编排执行
- **Explorer Subagent**：扫描代码库，构建上下文地图（只读）
- **Worker Subagent**：实现变更（写权限，沙箱执行）

支持 worktree 并行：多个 Agent 在同一仓库的不同 worktree 上并发工作。

---

## 四、全体共识（8/8 同意）

### 共识 1：Loop 三大原语

```
/goal  — 声明式目标（自然语言 + 结构化约束），不是 pass/fail 检查器
/loop  — 支持间歇式（不是 while True 死循环），可跨 Session 恢复
/routines — 自适应调度器（不是 cron），根据历史表现动态调整频率
```

### 共识 2：分形 Goal 嵌套

```
主 Goal（项目级）
├── 子 Goal（域级）
│   ├── 孙 Goal（Phase 级）
│   └── 孙 Goal
└── 子 Goal
```

每层有独立 Agent 负责、独立验证逻辑。子 Goal 可以反向修改父 Goal 的约束（执行中发现新约束时向上冒泡）。

### 共识 3：Dream Loop（空闲时自我反思）

Agent 空闲时自动执行：
- 回顾执行历史 → 提取成功/失败模式
- 生成改进策略 → 写入 memory
- 下次执行时自动应用
- 4 位专家独立提出此概念

### 共识 4：Meta-Loop（Loop 的 Loop）

一个高阶 Loop 监控所有 Loop 的表现：
- 自动调参（超时、重试次数、唤醒频率、Worker 模型选择）
- A/B 测试：新策略 vs 旧策略对比
- 持续优化，无需人工干预

### 共识 5：Memory 是 Loop 的灵魂

没有持久记忆的 Loop 是无状态的。跨 Session、跨时间的 Loop 必须靠 memory 维持连续性。

### 共识 6：OpenClaw 做主 Loop 控制器

所有专家一致认为 OpenClaw 是最佳主 Loop 控制器，独有优势：
- 跨 Session 持久化
- 多渠道通信（飞书/邮件/Telegram/iMessage）
- 定时调度（cron 原生支持）
- 子 Agent 管理（sessions_spawn + yield + auto-announce）
- 持久记忆（MEMORY.md + memory/*.md）
- Skill Workshop（Agent 可创建/更新/应用技能）

### 共识 7：间歇式心跳架构

```
快脉冲（3min）→ 检查 Worker 完成状态
慢脉搏（1h）  → 检查项目进度、调整策略
深呼吸（日）  → Dream Loop：反思 + 优化 + 记忆整理
长冥想（周）  → Meta-Loop：调整目标、进化 Skill
```

### 共识 8：一步到位做全 AI Native

没有不可逾越的技术障碍。所有挑战都可以用 OpenClaw 当前能力 + 创造性设计来解决。

---

## 五、分歧与裁决

### 分歧 1：编排式 vs 编舞式

| 维度 | 编排式（主 Loop 分配任务） | 编舞式（Agent 自主涌现协作） |
|------|--------------------------|---------------------------|
| 主张者 | 专家 1/4/6/7 | 专家 3/5 |
| 优势 | 可控、可预测、易调试 | 灵活、无瓶颈、自适应 |

**裁决**：分层混合
- 外 Loop（项目级）= 编排式（主 Loop 做决策）
- 内 Loop（Phase 级）= 编舞式（Worker 可动态请求帮助）

### 分歧 2：Agent 自我修改的边界

| 维度 | 保守派（只改参数） | 激进派（改 Skill/行为文件） |
|------|-------------------|--------------------------|
| 主张者 | 专家 4 | 专家 2/5 |

**裁决（忠礼决策）**：一步到位，Agent 可以修改自己的 Skill（通过 Skill Workshop），安全规则 Zone 0 不可改。

### 分歧 3：确定性控制 vs 全 LLM 控制

| 维度 | 保留 Python 控制层 | 全 LLM 控制 |
|------|-------------------|-------------|
| 主张者 | 专家 4 | 专家 5/8 |

**裁决（忠礼决策）**：全 LLM 控制。Python 不做控制流。`loop_runner.py` 废弃（忠礼判定：10 分钟速成产物，无参考性）。

### 分歧 4：Codex 集成模式

| 维度 | 子 Agent | 对等协作 |
|------|---------|---------|
| 主张者 | 专家 7 | 专家 5 |

**裁决**：监督式自治（Supervised Autonomy）
- OpenClaw 通过 sessions_spawn 启动 Codex
- Codex 在执行期间完全自治（Full Auto 模式）
- 完成后 auto-announce → OpenClaw 验证结果
- 失败 → OpenClaw 分析原因，重试或切换 Claude Code

### 分歧 5：Swarm 必要性

**裁决**：核心管线用编排式（确定性流程），探索性任务用 Swarm（涌现式协作）。

### 分歧 6：Hermes 角色

**裁决（专家8 + 调研确认）**：协作伙伴，不是子 Agent。
- Hermes 有自己的 Loop、记忆、Skill、学习循环
- 当子 Agent 浪费了它的独立学习能力
- 分工：OpenClaw = 主编排 + cron + heartbeat；Hermes = 多平台通信 + 独立调研 + 持续学习任务
- 协作方式：共享 memory 文件 + sessions_send

---

## 六、全 AI Native Loop 架构设计

### 6.1 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                   Main Loop (LLM 完全控制)               │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Goal Parser  │  │Phase Selector│  │Worker Alloc. │  │
│  │   (LLM)      │  │   (LLM)      │  │   (LLM)      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │Error Analyzer│  │ Dream Loop   │  │ Meta-Loop    │  │
│  │   (LLM)      │  │   (cron)     │  │(Skill Shop)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  State: memory/loops/ (JSON) + workspace/shared/        │
└─────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
   sessions_spawn       sessions_spawn       sessions_spawn
          │                    │                    │
          ▼                    ▼                    ▼
   ┌────────────┐      ┌────────────┐      ┌────────────┐
   │ Codex CLI  │      │  Hermes    │      │ Claude Code│
   │ (编码执行) │      │ (调研协作) │      │ (审查长任) │
   │ Full Auto  │      │ 独立 Agent │      │ Full Auto  │
   └────────────┘      └────────────┘      └────────────┘
```

### 6.2 核心组件

#### Goal Parser（目标解析器）

**输入**：自然语言目标  
**输出**：结构化任务 DAG（存入 memory/loops/task_dag.json）

```json
{
  "goal": "完成用户认证模块的设计、实现和部署",
  "tasks": [
    {"id": "t1", "name": "需求分析", "depends_on": [], "status": "pending", "assigned_to": null},
    {"id": "t2", "name": "架构设计", "depends_on": ["t1"], "status": "pending", "assigned_to": null},
    {"id": "t3", "name": "代码实现", "depends_on": ["t2"], "status": "pending", "assigned_to": null},
    {"id": "t4", "name": "测试验证", "depends_on": ["t3"], "status": "pending", "assigned_to": null},
    {"id": "t5", "name": "部署上线", "depends_on": ["t4"], "status": "pending", "assigned_to": null}
  ]
}
```

#### Phase Selector（阶段选择器）

LLM 动态选择下一个可执行任务（所有依赖已完成的任务），不是预定义顺序。

#### Worker Allocator（Worker 分配器）

LLM 根据任务类型分配给合适的工具：
- 编码任务 → Codex CLI
- 调研任务 → Hermes Agent
- 审查任务 → Claude Code
- 简单任务 → OpenClaw 子 Agent

#### Error Analyzer（错误分析器）

子 Agent 失败时，LLM 分析结构化错误报告 → 选择恢复策略：
- 超时 → 拆分任务，重新 spawn
- 测试失败 → 附带错误信息，重试
- 能力不足 → 切换更强模型
- 三次失败 → 上报用户

### 6.3 主 Loop 执行流程

```
用户: "完成用户认证模块"
  │
  ▼
[LLM] Goal Parser → 生成任务 DAG → 写入 memory/loops/
  │
  ▼
[LLM] Phase Selector → 选择 t1（需求分析，无依赖）
  │
  ▼
[LLM] Worker Allocator → spawn Hermes（调研认证方案最佳实践）
  │
  ▼
sessions_yield() → 等待 Hermes 完成
  │
  ▼
[Hermes] auto-announce → 返回调研结果
  │
  ▼
[LLM] 评估结果 → t1 完成 → 更新 DAG
  │
  ▼
[LLM] Phase Selector → 选择 t2（架构设计，t1 已完成）
  │
  ▼
...（循环直到所有任务完成）
  │
  ▼
[LLM] Goal Judge → 验证 Goal 是否满足 → 通知用户
```

### 6.4 状态管理

```
memory/loops/
├── {loop_id}/
│   ├── config.json       # Loop 配置（goal, tools, routines）
│   ├── state.json        # Loop 状态（running/paused/completed）
│   ├── task_dag.json     # 任务依赖图
│   ├── history.jsonl     # 迭代历史（每轮一次 append）
│   ├── errors.jsonl      # 错误记录
│   └── checkpoints/      # 断点文件（支持恢复）
```

**关键设计**：文件即状态，目录即 Loop。LLM 读写文件管理状态，不需要 Python 控制流。

### 6.5 Dream Loop（空闲时自我反思）

```
触发: cron 每日凌晨 / heartbeat 空闲时
  │
  ▼
[LLM] 读取 memory/loops/*/history.jsonl
  │
  ▼
[LLM] 分析模式: 哪些 prompt 模式导致成功？哪些导致失败？
  │
  ▼
[LLM] 提炼 pattern → 写入 memory/dreams/
  │
  ▼
[LLM] 生成改进策略 → 提交 Skill Workshop（action=create）
  │
  ▼
积累证据后 → skill_workshop(action=apply) → 成为正式 Skill
  │
  ▼
下次 Loop 自动加载这个 Skill → 表现更好
```

### 6.6 Meta-Loop（Loop 的 Loop）

```
触发: cron 每周
  │
  ▼
[LLM] 收集所有 Loop 的执行指标（成功率、耗时、token 消耗）
  │
  ▼
[LLM] 识别表现差的 Loop → 分析原因
  │
  ▼
[LLM] 调整参数（超时、重试次数、Worker 模型选择、并行度）
  │
  ▼
[LLM] A/B 测试：新参数 vs 旧参数 → 选择更优方案
  │
  ▼
更新 Loop 配置 → 记录到 memory/meta_loop/
```

---

## 七、多工具协作设计

### 7.1 工具角色矩阵

| 工具 | 角色 | 调用方式 | 交互模式 |
|------|------|---------|---------|
| **OpenClaw** | 主 Loop 控制器 | — | 决策中枢 |
| **Codex CLI** | 编码执行者 | sessions_spawn | 监督式自治（Full Auto） |
| **Hermes Agent** | 协作伙伴 | sessions_send / 共享 memory | 对等协作 |
| **Claude Code** | 审查+长任务 | sessions_spawn | 监督式自治 |
| **飞书/邮件** | 人类通信 | message | 人在环 |
| **GitHub** | 代码托管 | exec(gh cli) | 同步操作 |
| **Web Search** | 信息搜索 | web_search | 同步调用 |

### 7.2 Codex CLI 对接协议

```
OpenClaw 决定需要编码:
  1. 生成任务契约（JSON）:
     {
       "task_id": "fix-auth-bug",
       "context": {"repo": "...", "issue": "GitHub #123"},
       "constraints": {"max_files_changed": 5, "must_pass_tests": true},
       "completion_criteria": {"test_passes": true},
       "timeout_seconds": 600,
       "fallback": "escalate_to_claude"
     }
  2. sessions_spawn(task=任务描述, label="codex-worker")
  3. sessions_yield()
  4. Codex 在沙箱中自治执行（Full Auto）
  5. 完成后 auto-announce → OpenClaw 验证
  6. 验证通过 → 继续
  7. 验证失败 → 分析原因 → 重试或切换
```

### 7.3 Hermes Agent 协作协议

```
OpenClaw 需要 Hermes 协助:
  方式 A: sessions_send(message="请帮我调研 X")
  方式 B: 写入 workspace/shared/requests/req_001.json
          Hermes 检测到 → 执行 → 写入 responses/
  
Hermes 主动发现:
  Hermes 在自己的平台上发现有用信息
  → 写入 workspace/shared/signals/
  → OpenClaw 下次心跳时读取
```

### 7.4 失败恢复决策树

```
Worker 失败
  ├─ 超时 → 拆分任务，重新 spawn（更小粒度）
  ├─ 测试失败 → 附带错误信息，重试一次
  ├─ 能力不足 → 切换工具（Codex → Claude Code）
  ├─ 信息不足 → 请求 Hermes 补充调研
  ├─ 方向错误 → LLM 重新规划任务 DAG
  └─ 三次失败 → 通知用户（message 到飞书）→ 等待人类指导
```

---

## 八、创新机制汇总

### 8.1 Dream Loop（4 位专家共识）

Agent 空闲时自我反思 → 提取模式 → 生成改进策略 → 固化到 memory/Skill。

### 8.2 Goal 优先级竞争（专家1）

多个 Goal 冲突时，Agent 自主裁决资源分配：
- 安全优先 > 阻塞链上游优先 > 陈旧惩罚 > 资源上限

### 8.3 基因式技能进化（专家2）

Skill 有"适应度"评分：
- 低分 Skill → 淘汰
- 高分 Skill → 变异（生成变体）
- 两个高分 Skill → 交叉（组合新 Skill）

### 8.4 预测性失败建模（专家2）

Agent 建立"我可能在哪类任务上失败"的预测模型，提前准备应对策略。

### 8.5 信息素衰减（专家3）

蚁群式间接通信：Agent 在 memory 中留下"信息素"，信息素随时间衰减，确保 stale 区域被重新探索。

### 8.6 分形中断（专家4）

任何层级的 Loop 可被中断/暂停/恢复，中断沿分形结构传播，断点持久化到文件。

### 8.7 自适应 Routine Pipeline（专家1）

Routine A 输出 → Routine B 输入，形成日循环流水线。根据历史表现自动调整调度频率。

### 8.8 任务黑板 + 能力拍卖（专家7）

共享状态文件（黑板）+ Agent 根据能力竞争任务（拍卖），先做 PoC 再正式承诺。

### 8.9 Goal 演化（专家1）

Goal 不是写死的。执行过程中发现新约束时：
- 只能增加约束或放宽非关键约束
- 不能删除 hard 约束
- 每次演化都记录日志
- 超过 3 次演化自动通知人类

---

## 九、已废弃的结论（不再参考）

### 9.1 ~~"33% 成功率说明 LLM 不适合循环控制"~~

**废弃原因**：真实根因是并发限制（3任务×9子agent撞并发上限），不是 LLM 能力问题。

### 9.2 ~~loop_runner.py / Phase Worker 模式~~

**废弃原因**：忠礼判定为 10 分钟速成产物，无参考性。Python 做控制流是反 AI Native 的设计。新架构完全重建，不纳入。

### 9.3 ~~"分阶段演进"路线~~

**废弃原因**：忠礼明确要求一步到位做全 AI Native，不分阶段。没有不可逾越的技术障碍。

### 9.4 ~~"混合架构（Python 骨架 + LLM 肉）"~~

**废弃原因**：保守方案，基于错误的"LLM不可靠"前提。全 LLM 控制是正确方向。

---

## 十、参考文档索引

| 文档 | 内容 | 路径 |
|------|------|------|
| Loop 原语设计 | /goal + /loop + /routines 完整设计 | `loop-engineering-primitives.md` |
| OpenClaw Loop 架构 | 分形 Loop + 间歇式心跳 + 跨工具编排 | `.deepflow/docs/OPENCLAW_LOOP_ARCHITECTURE.md` |
| 7 位专家共识 | 第二轮整合文档 | `.deepflow/docs/AI_NATIVE_LOOP_CONSENSUS.md` |
| 本文档 | 完整研讨纪要（8 位专家） | `.deepflow/docs/AI_NATIVE_LOOP_STUDY.md` |

---

## 十一、下一步

1. **忠礼审阅本文档** — 确认共识和分歧裁决是否准确
2. **确定第一个实验项目** — 选一个小项目验证全 AI Native 架构
3. **开始设计 Skill** — 主 Loop 的行为规则定义为一个 Skill
4. **不写代码** — 方案定稿后再进入开发

---

*8 位专家、三轮研讨、三次业界调研。方案讨论阶段，不执行。*
*loop_runner.py 已废弃，不作为新架构参考。*
