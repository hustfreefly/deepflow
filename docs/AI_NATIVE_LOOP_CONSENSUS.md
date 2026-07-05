# AI Native Loop 架构设计 — 7 位专家共识与分歧

> **日期**: 2026-06-25  
> **状态**: 方案讨论阶段（不执行）  
> **专家总数**: 7 位（分两轮研讨）

---

## 一、专家阵容

### 第一轮（4 位）

| # | 角色 | 核心立场 | 完整文档 |
|---|------|---------|---------|
| 1 | Loop Engineering 原语设计师 | /goal + /loop + /routines 三原语 | `loop-engineering-primitives.md` |
| 2 | Self-Evolving Agent 架构师 | Agent 自己进化自己 | session history |
| 3 | Multi-Agent Swarm 设计师 | 编舞式涌现协作 | session history |
| 4 | OpenClaw Loop 平台架构师 | 分形 Loop + 间歇式心跳 | `OPENCLAW_LOOP_ARCHITECTURE.md` |

### 第二轮（3 位，基于"模型能力持续提高"假设）

| # | 角色 | 核心立场 |
|---|------|---------|
| 5 | 激进 AI Native 纯粹主义者 | 面向 2027 模型能力设计，不为当前局限打补丁 |
| 6 | 面向未来系统架构师 | 三层演进路线（过渡→桥接→原生） |
| 7 | 多工具 AI 生态架构师 | 监督式自治（Supervised Autonomy） |

---

## 二、全体共识（7/7 同意）

### 共识 1: Loop 三大原语

```
/goal  — 声明式目标（自然语言+结构化约束），不是 pass/fail 检查器
/loop  — 支持间歇式（不是 while True），可跨 Session 恢复
/routines — 自适应调度器（不是 cron），根据历史表现调整频率
```

### 共识 2: Goal 可以嵌套（分形目标）

```
主 Goal（项目级）
├── 子 Goal（域级: Spec Pro / Solution Pro / Ship Pro）
│   ├── 孙 Goal（Phase 级）
│   └── 孙 Goal
└── 子 Goal
```

每层有独立 Agent 负责、独立验证逻辑。子 Goal 可以反向修改父 Goal 的约束（执行中发现新约束时向上冒泡）。

### 共识 3: Dream Loop（空闲时自我反思）

Agent 空闲时自动执行：
- 回顾执行历史 → 提取模式 → 生成改进策略
- 写入 memory → 下次执行时自动应用
- 4 位专家独立提出此概念（不是抄的）

### 共识 4: Meta-Loop（Loop 的 Loop）

一个高阶 Loop 监控所有 Loop 的表现：
- 自动调参（超时、重试次数、唤醒频率）
- A/B 测试：新策略 vs 旧策略对比
- 持续优化，无需人工干预

### 共识 5: Memory 是 Loop 的灵魂

没有持久记忆的 Loop 是无状态的。跨 Session、跨时间的 Loop 必须靠 memory 维持连续性。

### 共识 6: OpenClaw 作为主 Loop 控制器

所有专家一致认为 OpenClaw 是最佳的主 Loop 控制器：
- 跨 Session 持久化
- 多渠道通信（飞书/邮件/Telegram）
- 定时调度（cron）
- 子 Agent 管理（sessions_spawn/yield）
- 持久记忆（memory）

### 共识 7: 间歇式心跳架构

```
快脉冲（3min）→ 检查 Worker 完成状态
慢脉搏（1h）  → 检查项目进度、调整策略
深呼吸（日）  → Dream Loop：反思+优化+记忆整理
长冥想（周）  → Meta-Loop：调整目标、进化 Skill
```

---

## 三、分歧与裁决（基于"模型能力持续提高"假设）

### 分歧 1: 编排式 vs 编舞式

| 维度 | 编排式（主 Loop 分配任务） | 编舞式（Agent 自主涌现协作） |
|------|--------------------------|---------------------------|
| 主张者 | 专家 1/4/6/7 | 专家 3/5 |
| 优势 | 可控、可预测、易调试 | 灵活、无瓶颈、自适应 |
| 劣势 | 中心化瓶颈 | 可能出现混沌 |

**激进派判断（专家5）**：编舞式是"模型不够强时的妥协"。当模型足够强时，**编排式+自适应**更优。

**裁决**：**分层混合**
- 外 Loop（项目级）= 编排式（主 Loop 做决策）
- 内 Loop（Phase 级）= 编舞式（Worker 可动态请求帮助）
- 理由：模型能力提高后，Worker 级的自主决策可靠度提升，但项目级的方向把控仍需中心化

### 分歧 2: Agent 自我修改的边界

| 维度 | 保守派（只改参数） | 激进派（改 Skill/行为文件） |
|------|-------------------|--------------------------|
| 主张者 | 专家 4 | 专家 2/5 |
| 安全边界 | 只调超时/重试次数 | 可修改 Skill，不可改安全规则 |

**激进派判断（专家5）**：未来模型足够强时，Agent 自我修改是**进化而非自毁**。关键是**安全分层**：

```
Zone 0 (不可改): 安全规则、权限边界
Zone 1 (可改，需验证): Skill 定义、prompt 模板
Zone 2 (自由改): 参数配置、执行策略、工具偏好
```

**裁决**：**分阶段开放**
- 2026 阶段：Agent 可改 Zone 2（参数）
- 2027 阶段：Agent 可改 Zone 1（Skill，通过 Skill Workshop 验证）
- 2028+：Agent 可改 Zone 1 全部（安全规则仍需人类确认）

### 分歧 3: 确定性控制 vs 全 LLM 控制

| 维度 | 保留 Python 控制层 | 渐进移除 Python 控制 |
|------|-------------------|---------------------|
| 主张者 | 专家 4/6 | 专家 5 |
| 代表 | loop_runner.py 做 phase 推进 | 主 Loop 直接用 LLM 决策 |

**激进派判断（专家5）**：Python 控制层从**一开始就不应该有**。但考虑到当前系统已在运行，建议**渐进移除**。

**未来架构师判断（专家6）**：三层演进
1. **过渡期（2026 H2）**：Python 保底 + LLM 增强
2. **桥接期（2027 H1）**：LLM 主导 + Python 熔断
3. **原生期（2027 H2+）**：全 LLM Loop，Python 只做工具执行

**裁决**：**渐进式路径**（与专家6的三层演进一致）

### 分歧 4: Codex 集成模式

| 维度 | 子 Agent | 对等协作 | 市场模式 |
|------|---------|---------|---------|
| 主张者 | 专家 7 | 专家 5 | 无人 |

**多工具专家判断（专家7）**：**监督式自治（Supervised Autonomy）**
- OpenClaw 通过 sessions_spawn 启动 Codex（子 Agent 模式）
- Codex 在执行期间完全自治（对等模式特征）
- 通信通过异步事件 + 文件契约
- Codex 完成 → auto-announce → OpenClaw 恢复

**激进派判断（专家5）**：未来通过 A2A 协议实现标准互操作。

**裁决**：**监督式自治 + A2A/MCP 协议**

### 分歧 5: Swarm 必要性

| 维度 | 需要 Swarm | 4 域管线够用 |
|------|-----------|-------------|
| 主张者 | 专家 3 | 专家 4/6 |

**激进派判断（专家5）**：2027 阶段引入 Swarm 有价值，但不用于核心管线。

**裁决**：**核心管线用编排式，探索性任务用 Swarm**
- Spec Pro → Solution Pro → Ship Pro = 编排式（确定性流程）
- 技术调研、竞品分析、创意探索 = Swarm（涌现式协作）

---

## 四、多工具协作架构（专家7 核心设计）

### 4.1 工具角色矩阵

```
┌─────────────────────────────────────────────────────────┐
│                 OpenClaw = 决策中枢                       │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Memory   │  │ Scheduler│  │ Router   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│         │              │              │                 │
│    ┌────┼────┐    ┌────┼────┐    ┌────┼────┐          │
│    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼          │
│  Codex  Hermes Claude  Web   exec  message            │
│  (编码) (信息) (审查)  (搜索)(计算) (通知)             │
└─────────────────────────────────────────────────────────┘
```

### 4.2 各工具角色

| 工具 | 角色 | 调用方式 | 交互模式 |
|------|------|---------|---------|
| **OpenClaw** | 主 Loop 控制器 | — | 决策中枢 |
| **Codex CLI** | 编码执行者 | sessions_spawn | 监督式自治 |
| **Hermes** | 信息专家 | web_search / exec | 同步查询 |
| **Claude Code** | 审查+长任务 | sessions_spawn | 监督式自治 |
| **飞书/邮件** | 人类通信 | message | 人在环 |
| **GitHub** | 代码托管 | exec(gh cli) | 同步操作 |

### 4.3 失败恢复决策树

```
Codex 失败 → OpenClaw 收到 completion event
  ├─ 超时 → 拆分任务，重新 spawn
  ├─ 测试失败 → 附带错误信息，重试一次
  ├─ 语法错误 → 切换 Claude Code（更强推理）
  └─ 三次失败 → 上报用户，请求人工介入
```

### 4.4 A2A/MCP 协议集成（未来）

```
┌──────────────────────────────────────────────────────┐
│                 协议层                                 │
│                                                      │
│  ┌──────────┐              ┌──────────┐              │
│  │   A2A    │              │   MCP    │              │
│  │ Agent↔   │              │ Agent↔   │              │
│  │ Agent    │              │ 工具     │              │
│  └──────────┘              └──────────┘              │
│                                                      │
│  Agent Card:                                         │
│  {                                                   │
│    "name": "codex-coder",                            │
│    "capabilities": ["code_fix", "test_write"],       │
│    "input_format": "task_contract",                  │
│    "output_format": "diff + test_results"            │
│  }                                                   │
└──────────────────────────────────────────────────────┘
```

---

## 五、三层演进路线（专家6 核心设计）

### 第一层：过渡期（2026 H2）

```
特征：Python 保底 + LLM 增强
架构：
  主 Loop = Python（loop_runner.py）
  + Goal Judge（LLM 验证目标满足度）
  + Compaction（LLM 压缩上下文）
  + Dream Loop（cron 触发反思）
  
确定性控制：phase 顺序、文件完整性、超时熔断
LLM 控制：phase 内决策、质量判断、恢复策略选择

对应 DeepFlow：现有的 loop_runner.py + Watcher
```

### 第二层：桥接期（2027 H1）

```
特征：LLM 主导 + Python 熔断
架构：
  主 Loop = LLM（理解 Goal + 动态规划）
  + Python 熔断器（预算超限 → 强制停止）
  + Agent Mesh（多 Agent 动态协作）
  
Python 角色：只做安全保底（预算、超时、权限检查）
LLM 角色：流程控制、phase 选择、Agent 分配

对应 OpenClaw：需要升级 sessions 管理、增加 Agent 通信协议
```

### 第三层：原生期（2027 H2+）

```
特征：全 AI Native
架构：
  主 Loop = LLM（完全自主）
  + Self-Evolving（Agent 修改自己的 Skill）
  + Fractal Loop（无限嵌套）
  + Swarm（涌现协作）
  
Python 角色：只做工具执行（exec）
LLM 角色：一切决策

对应 OpenClaw：需要原生 Loop 支持、Agent 互操作协议
```

---

## 六、创新机制汇总

### 6.1 Dream Loop（4 位专家共识）

Agent 空闲时自我反思 → 提取模式 → 生成改进策略 → 固化到 memory/Skill。

### 6.2 Goal 优先级竞争（专家1）

多个 Goal 冲突时，Agent 自主裁决资源分配。规则：安全优先 > 阻塞链上游优先 > 陈旧惩罚 > 资源上限。

### 6.3 基因式技能进化（专家2）

Skill 有"适应度"评分：
- 低分 Skill → 淘汰
- 高分 Skill → 变异（生成变体）
- 两个高分 Skill → 交叉（组合新 Skill）

### 6.4 预测性失败建模（专家2）

Agent 建立"我可能在哪类任务上失败"的预测模型，提前准备应对策略。

### 6.5 信息素衰减（专家3）

蚁群式间接通信：Agent 在 memory 中留下"信息素"，信息素随时间衰减，确保 stale 区域被重新探索。

### 6.6 分形中断（专家4）

任何层级的 Loop 可被中断/暂停/恢复，中断沿分形结构传播，断点持久化到文件。

### 6.7 自适应 Routine Pipeline（专家1）

Routine A 输出 → Routine B 输入，形成日循环流水线。根据历史表现自动调整调度频率。

### 6.8 任务黑板 + 能力拍卖（专家7）

共享状态文件（黑板）+ Agent 根据能力竞争任务（拍卖），先做 PoC 再正式承诺。

---

## 七、OpenClaw 独有优势（其他平台做不到）

| 优势 | 说明 | 如何利用 |
|------|------|---------|
| **跨 Session 持久化** | memory 跨 Session 存活 | Heartbeat Loop、Dream Loop |
| **多渠道通信** | 飞书/邮件/Telegram/iMessage | 人在环、进度通知 |
| **定时调度** | cron 原生支持 | 间歇式 Loop、Routine |
| **子 Agent 管理** | sessions_spawn + yield + auto-announce | 编码任务委派给 Codex |
| **Skill Workshop** | Agent 可创建/更新 Skill | 自我进化 |
| **文件即状态** | 目录结构 = Loop 实体 | 分形中断、断点恢复 |

---

## 八、核心参考文档

| 文档 | 内容 | 路径 |
|------|------|------|
| Loop 原语设计 | /goal + /loop + /routines 完整设计 | `loop-engineering-primitives.md` |
| OpenClaw Loop 架构 | 分形 Loop + 间歇式心跳 + 跨工具编排 | `.deepflow/docs/OPENCLAW_LOOP_ARCHITECTURE.md` |
| AI Native Loop 2.0.0 | 七层混合架构设计（第一轮） | `.deepflow/docs/AI_NATIVE_LOOP_DESIGN.md` |
| 本文档 | 7 位专家共识与分歧 | `.deepflow/docs/AI_NATIVE_LOOP_CONSENSUS.md` |

---

## 九、开放问题（待进一步讨论）

1. **Hermes 的具体能力是什么？** 专家7假设了"信息专家"角色，但需要忠礼确认 Hermes 能做什么。

2. **OpenClaw 平台升级路线图？** 专家6的三层演进依赖 OpenClaw 平台能力的提升，需要了解 OpenClaw 团队的发展计划。

3. **Codex CLI 的集成方式？** 当前通过 sessions_spawn 启动，但 Codex 有自己的 Agent Loop，如何优雅对接？

4. **A2A/MCP 协议是否要在 OpenClaw 中实现？** 如果要实现跨工具标准互操作，需要 OpenClaw 原生支持 A2A/MCP。

5. **第一个实验项目是什么？** 选定一个小项目来验证这套架构，边做边迭代。

---

*7 位专家、两轮研讨、三轮调研。方案讨论阶段，不执行。*
