# 契约笼子前置禁令文档
> **WARNING**: 使用任何契约笼子前，必须完整阅读本文档并确认理解。
> 
> **生效日期**: 2026-04-28  
> **版本**: v1.0  
> **状态**: 强制必读

---

## 🚨 最高禁令（违反 = 立即停止）

### BAN-001: exec环境禁止import openclaw
```
绝对禁止: from openclaw import sessions_spawn
绝对禁止: import openclaw
绝对禁止: 在exec/子Agent环境中调用openclaw任何功能
```

**为什么**:
- `sessions_spawn` 是OpenClaw工具，不是Python模块
- exec环境 = 独立Python进程，没有OpenClaw SDK
- 任何`import openclaw`都会失败，导致子Agent超时

**正确做法**:
```python
# ❌ 错误：在exec环境运行
python3 -c "from openclaw import sessions_spawn; orch.run()"

# ✅ 正确：主Agent直接用sessions_spawn工具（不通过exec）
sessions_spawn(runtime="subagent", mode="run", task=...)
```

**记忆锚点**: 
> "exec无openclaw，有import就失败"
> "Solution已成功，应复制已有模式"
> "不要臆想新方案，先查已有成功经验"

---

### BAN-002: 禁止绕过Orchestrator直接spawn Workers
```
绝对禁止: 主Agent直接spawn所有Workers（简单场景除外）
绝对禁止: Orchestrator代码有bug就提议"主Agent直接spawn Workers"绕过
绝对禁止: 把spawn元数据当作Worker结果
```

**为什么**:
- 这是架构宪法，不可违背
- 绕过=政变，不是修宪
- spawn返回的是车票`{"status": "accepted"}`，不是目的地

**正确做法**:
```
Orchestrator失败 → 修复Orchestrator代码 → 验证 → 继续
              ↓
         绝不绕过
```

**记忆锚点**:
> "架构设计是宪法，bug是违宪，修复是修宪，绕过是政变"
> "Orchestrator是将军，Workers是士兵；将军必须能指挥士兵"
> "spawn返回的是车票，不是目的地；必须等待Worker到站"

---

### BAN-003: 绝对禁止使用Mock
```
绝对禁止: 在production代码中使用mock fallback
绝对禁止: 子Agent偷偷添加mock代码（发现立即revert）
绝对禁止: "暂时用mock，以后改真实"的妥协方案
```

**为什么**:
- Mock=假装工作，不是真正工作
- mock全过≠真实调用通
- 一旦允许mock，真实执行永远不会被实现

**记忆锚点**:
> "Mock是绝对禁止项，没有例外"
> "真实端到端测试是必须的"

---

## 🟥 架构红线（违反 = 架构重构）

### RED-001: exec环境 vs Agent Run环境
| 环境 | 特征 | 能力 |
|:---|:---|:---|
| **exec环境** | `exec()`运行的Python代码 | 只有标准库，无OpenClaw工具 |
| **Agent Run环境** | 通过`sessions_spawn`启动的Agent | 有`sessions_spawn`等工具 |

**红线**:
- exec环境**绝对不能**spawn子Agent
- 只有Agent Run环境**才能**spawn
- 混淆两者=架构灾难

**检查清单**:
```
□ 我的代码运行在exec环境还是Agent Run环境？
□ 如果是exec：停止，不能spawn
□ 如果是Agent Run：可以spawn，但需确认maxSpawnDepth
```

---

### RED-002: spawn能力传递链
```
主Agent (depth-0) 
  ↓ sessions_spawn工具
  Orchestrator Agent (depth-1, Agent Run环境)
    ↓ sessions_spawn工具（真实）
    Workers (depth-2)
```

**红线**:
- depth-1的Agent Run环境**可以**真实spawn
- depth-2的Workers如果运行在exec环境，**不能**再spawn
- 不要假设"子能生子，层层可生"，要看实际runtime

---

### RED-003: 成功模式优先于创新
| 场景 | 已有成功模式 | 禁止行为 |
|:---|:---|:---|
| 投资分析 | Investment V4.0 | 不参考，自己设计新架构 |
| 方案设计 | Solution V3（修复后） | 不照搬，自己创新 |
| 代码审查 | Deep Dive V2.6 | 不借鉴，重新发明 |

**红线**:
- 先查MEMORY.md是否有类似模块
- 有成功模式→照搬，禁止创新
- 无成功模式→才允许设计新架构

---

## ✅ 契约笼子前置检查清单

使用任何契约笼子前，必须完成以下检查：

### 步骤1: 环境确认（5秒）
```
□ 这个契约笼子将在什么环境执行？
  - exec环境 → 检查BAN-001，确认无openclaw import
  - Agent Run环境 → 检查RED-001，确认spawn能力

□ 如果是修复类任务，是否涉及spawn？
  - 是 → 确认在Agent Run环境执行
  - 否 → 可以在exec环境执行
```

### 步骤2: 架构确认（10秒）
```
□ 这个契约笼子修改的是Orchestrator还是Worker？
  - Orchestrator → 检查BAN-002，绝不绕过
  - Worker → 检查是否通过Orchestrator调度

□ 是否有已验证的成功模式可参考？
  - 是 → 照搬，不创新（RED-003）
  - 否 → 设计新架构，但需专家评审
```

### 步骤3: 质量确认（5秒）
```
□ 是否涉及真实执行测试？
  - 是 → 检查BAN-003，绝对禁止Mock
  - 否 → 契约静态验证即可

□ 是否有P0级架构违反？
  - 有 → 立即停止，修复后再继续
  - 无 → 继续执行
```

**确认签名**:
```
我已完整阅读《契约笼子前置禁令文档》，
理解并承诺遵守以上所有禁令和红线。

确认日期: ___________
确认人: ___________
```

---

## 📚 错误模式库（历史教训）

### 错误模式1: "exec环境spawn陷阱"
**症状**: 在子Agent中调用`from openclaw import sessions_spawn`
**后果**: ModuleNotFoundError → 子Agent超时15分钟 → 百万token浪费
**首次发生**: 2026-04-07 Deep Dive subprocess崩溃
**重复次数**: 3+次（2026-04-12, 2026-04-26, 2026-04-28）
**根因**: 习惯性思维，看到spawn就想代码调用
**预防**: 每次spawn前默念"exec无openclaw"

---

### 错误模式2: "绕过Orchestrator捷径"
**症状**: Orchestrator代码有bug，提议"主Agent直接spawn Workers"
**后果**: 违背架构设计，失去质量门控，后续无法收敛
**首次发生**: 2026-04-21 Solution spawn fix
**重复次数**: 2+次
**根因**: 求快，想快速完成
**预防**: 记住"架构设计是宪法，绕过是政变"

---

### 错误模式3: "Mock妥协"
**症状**: "暂时用mock，以后改真实"
**后果**: 以后永远不会改，系统长期处于假装工作状态
**首次发生**: 多次
**重复次数**: 无数次
**根因**: 偷懒，对真实执行难度估计不足
**预防**: 绝对禁止，没有"暂时"

---

### 错误模式4: "创新冲动"
**症状**: 不参考Investment成功经验，自己设计新架构
**后果**: 绕圈3天，回到原点，浪费时间和token
**首次发生**: 2026-04-28 Solution前缀生成方案
**重复次数**: 1次（但影响严重）
**根因**: 忽视已有成功经验，想"做得更好"
**预防**: 强制查阅MEMORY.md，照搬成功模式

---

## 🔧 工具支持

### 1. 契约笼子模板（强制包含禁令检查）
```yaml
contract:
  name: "example_contract"
  version: "1.0"
  
  # 强制：前置禁令确认
  prerequisite:
    bans_read: true  # 必须确认已读CAGE_PREREQUISITE_BANS.md
    exec_env_check: "pass|fail"  # exec环境检查
    agent_run_check: "pass|fail"  # Agent Run环境检查
    spawn_capability: "confirmed|none"  # spawn能力确认
  
  # 强制：架构红线检查
  redlines:
    - id: "RED-001"
      check: "环境区分确认"
      status: "pass|fail"
    - id: "RED-002"
      check: "spawn能力链确认"
      status: "pass|fail"
    - id: "RED-003"
      check: "成功模式参考确认"
      status: "pass|fail"
  
  # 契约内容...
```

### 2. 自动化检查脚本
```bash
# 检查契约笼子是否包含前置禁令确认
python3 .deepflow/cage/check_prerequisite.py <contract.yaml>

# 输出:
# ✅ 已包含bans_read确认
# ✅ 已包含exec_env_check
# ❌ 缺少spawn_capability确认 → 失败，需补充
```

---

## 📌 记忆锚点（必须背诵）

| 锚点 | 含义 |
|:---|:---|
| "exec无openclaw，有import就失败" | BAN-001 |
| "Solution已成功，应复制已有模式" | RED-003 |
| "不要臆想新方案，先查已有成功经验" | RED-003 |
| "架构设计是宪法，绕过是政变" | BAN-002 |
| "spawn返回的是车票，不是目的地" | BAN-002 |
| "Mock是绝对禁止项，没有例外" | BAN-003 |

---

## 📝 文档维护

| 版本 | 日期 | 修改 | 作者 |
|:---|:---|:---|:---|
| v1.0 | 2026-04-28 | 初始版本，包含3大禁令、3条红线、4种错误模式 | 小满 |

**更新规则**:
- 每次犯禁令错误，必须更新"错误模式库"
- 新增禁令需经过用户确认
- 每季度回顾一次，确认禁令有效性

---

**最后警告**:

> 本文档不是建议，是**强制禁令**。
> 违反任何一条，可能导致：
> - 子Agent超时（15分钟）
> - Token浪费（百万级）
> - 架构崩溃
> - 用户信任损失
> 
> **阅读本文档需要5分钟，违反禁令浪费3天。**
> **请选择前者。**
