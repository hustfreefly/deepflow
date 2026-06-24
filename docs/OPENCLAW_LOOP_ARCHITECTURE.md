# OpenClaw AI Native Loop 架构设计

> 版本: v1.0 | 2026-06-25
> 定位: 基于 OpenClaw 平台原语的 AI Native Loop 系统架构

---

## 一、设计哲学：Loop 即 Agent 的生活方式

传统自动化是**线性的**：触发 → 执行 → 结束。AI Native Loop 是**分形的**：Agent 永远活在一个嵌套的 Loop 结构中，每一层都在观察、决策、行动、反思。

**核心原则**：
- **语义反馈 > 状态机**：Loop 的推进靠 LLM 判断"目标是否满足"，不是靠检查状态字段
- **间歇 > 连续**：Loop 不需要一直运行，cron 让它像心跳一样间歇式存活
- **分形 > 线性**：每一层 Loop 都是完整的 观察→决策→行动→反思 循环
- **记忆 > 上下文**：跨 Loop 的知识通过 memory 持久化，不依赖单个 session 的上下文窗口

---

## 二、Loop 原语设计

### 2.1 三大原语

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenClaw Loop 原语                        │
├──────────────┬──────────────────────────────────────────────┤
│  /loop       │ 创建 Loop 实例                                │
│              │ 参数: name, goal, tools, routines             │
│              │ 存储: .deepflow/loops/<name>/config.json      │
│              │ 行为: 初始化 pipeline_state + 注册 cron        │
├──────────────┼──────────────────────────────────────────────┤
│  /routine    │ 注册 Routine（Loop 的触发器）                  │
│              │ 参数: name, trigger, action, loop_ref         │
│              │ 类型: cron | event | state_watch              │
│              │ 实现: OpenClaw cron job / file watcher        │
├──────────────┼──────────────────────────────────────────────┤
│  /goal       │ 定义/更新 Loop 目标                           │
│              │ 参数: description, verify, parent_goal        │
│              │ 验证: llm_judge | file_check | test_run       │
│              │ 分解: 自动拆解为子 goal 树                     │
└──────────────┴──────────────────────────────────────────────┘
```

### 2.2 `/loop` 的实现架构

```
用户: /loop ship-feature --goal "完成用户认证模块的部署" 
      --tools [exec, sessions_spawn, web_search] 
      --routines [hourly-check, feishu-alert]

→ 创建 .deepflow/loops/ship-feature/
  ├── config.json        # Loop 配置（goal, tools, routines）
  ├── state.json         # Loop 状态（running/paused/blocked/done）
  ├── history.jsonl      # Loop 迭代历史（每轮一次 append）
  ├── goals/
  │   ├── root.json      # 根目标 + 验证方法
  │   └── sub_*.json     # 子目标树
  └── artifacts/         # Loop 产出物
```

**关键设计**：Loop 不是代码，是**目录结构 + 状态机 + LLM 决策**的结合体。Python 只管骨架（状态转换、文件读写），LLM 负责肉（判断、规划、反思）。

### 2.3 `/routine` 的三种触发模式

| 类型 | 触发方式 | OpenClaw 实现 | 示例 |
|------|---------|--------------|------|
| **cron** | 定时 | OpenClaw cron job | 每小时检查进度 |
| **event** | 文件/消息 | file watcher + webhook | 飞书消息到达时处理 |
| **state_watch** | 状态变化 | pipeline_state 轮询 | Worker 完成时触发下一步 |

```
/routine hourly-check --trigger "cron:0 * * * *" 
  --action "exec loop_runner.py check ship-feature" 
  --loop-ref ship-feature

→ 注册 OpenClaw cron job
→ cron 触发时 spawn 一个 sub-agent 执行 check 动作
→ check 结果决定 Loop 下一步
```

---

## 三、Nested Loop 架构（分形 Loop）

### 3.1 三层分形结构

```
┌─────────────────────────────────────────────────────────┐
│  外 Loop: Project Loop（项目级）                          │
│  周期: 天级 | 目标: 从需求到交付                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  中 Loop: Domain Loop（域级）                     │    │
│  │  周期: 小时级 | 目标: 单域完整执行                 │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │  内 Loop: Phase Loop（阶段级）            │    │    │
│  │  │  周期: 分钟级 | 目标: 单 Phase 执行       │    │    │
│  │  │                                          │    │    │
│  │  │  spawn Worker → yield → 检查 → 下一Phase │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  │                                                  │    │
│  │  Spec Pro ← Solution Pro ← Ship Pro ← Research  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  观察 → 分解目标 → 分派域 → 收集结果 → 调整策略           │
└─────────────────────────────────────────────────────────┘
```

### 3.2 层间协作协议

**外 Loop → 中 Loop（目标分解）**：
```
外 Loop 的 LLM 决策:
  输入: root goal + 当前 state
  输出: [
    { domain: "spec_pro", goal: "产出完整 spec 文档", verify: "file_check:spec.json" },
    { domain: "solution_pro", goal: "产出技术方案", verify: "file_check:solution.json", depends: ["spec_pro"] },
    { domain: "ship_pro", goal: "完成部署", verify: "test_run:smoke_test", depends: ["solution_pro"] }
  ]
```

**中 Loop → 内 Loop（任务分派）**：
```
中 Loop（已由 loop_runner.py 实现）:
  exec("loop_runner.py next solution_pro <base_path>")
  → 返回 { action: "spawn_serial|spawn_parallel", tasks: [...] }
  → sessions_spawn(task=...) → sessions_yield()
  → 恢复后再次 next → 直到 done
```

**内 Loop → 外 Loop（失败上报）**：
```
内 Loop 失败 → 写入 state.json { status: "blocked", reason: "..." }
中 Loop 检测到 → 尝试自愈（retry / 换策略）
自愈失败 → 上报外 Loop
外 Loop LLM 决策 → 重新规划 / 通知人类 / 降级目标
```

### 3.3 与现有 loop_runner.py 的映射

| 架构层 | 现有实现 | 演进方向 |
|--------|---------|---------|
| 内 Loop | `loop_runner.py next` + `sessions_spawn` + `sessions_yield` | 保持不变，已验证 |
| 中 Loop | `loop_runner.py check/resume` + Cron Watcher | 增加 LLM 决策层（goal judge） |
| 外 Loop | 尚未实现 | 新增 Project Loop 控制器 |

---

## 四、Intermittent Loop（间歇式 Loop）

### 4.1 "永远醒着的守望者"架构

```
时间轴 →
──────────────────────────────────────────────────────
  │         │         │         │         │
  ▼         ▼         ▼         ▼         ▼
[Cron 1h] [Cron 1h] [Cron 1h] [Cron 1h] [Cron 1h]
  │         │         │         │         │
  ▼         ▼         ▼         ▼         ▼
 check()   check()   check()   check()   check()
  │         │         │         │         │
  ├─ 无事   ├─ 有新    ├─ 阻塞   ├─ 无事   ├─ 完成
  │  → 等待  │  消息    │  → 通知  │  → 等待  │  → 报告
  │         │  → 处理  │  → 人类  │         │  → 清理
  │         │         │  → 等待  │         │
```

### 4.2 三级间歇频率

| 级别 | 频率 | 动作 | OpenClaw 实现 |
|------|------|------|--------------|
| **快脉冲** | 每 3 分钟 | 检查 Worker 完成状态 | Cron Watcher（已有） |
| **慢脉搏** | 每小时 | 检查项目进度、调整策略 | `/routine hourly-check` |
| **深呼吸** | 每天 | Dream Loop：反思+优化+记忆整理 | `/routine daily-dream` |
| **长冥想** | 每周 | Meta-Loop：调整目标、进化 Skill | `/routine weekly-evolve` |

### 4.3 Dream Loop（每日反思）

```
/routine daily-dream --trigger "cron:0 3 * * *"  # 每天凌晨 3 点
  --action "dream-loop"

Dream Loop 执行流程:
1. 读取今日所有 Loop 的 history.jsonl
2. 分析: 哪些迭代成功了？哪些失败了？失败模式是什么？
3. 提炼: 可复用的经验 → 写入 memory
4. 优化: 更新 Loop 的 prompts / 工具配置
5. 清理: 归档已完成的 Loop 目录
6. 报告: 生成 Dream Report → 飞书通知
```

### 4.4 事件驱动的间歇 Loop

```
飞书消息到达 → OpenClaw webhook → 触发 event routine
  → Loop 被"唤醒"
  → LLM 判断消息意图
  → 如果是 Loop 相关的 → 更新 state / 调整策略
  → 如果需要人类输入 → 回复飞书 → 等待 → 继续
  → 处理完毕 → Loop 回到"休眠"
```

---

## 五、Cross-Tool Orchestration（跨工具编排）

### 5.1 编排模式

```
┌──────────────────────────────────────────────────────┐
│               OpenClaw = 决策中枢                      │
│                                                       │
│   观察 → LLM 判断 → 选择工具 → 执行 → 观察结果        │
│                                                       │
│   工具选择矩阵:                                       │
│   ┌──────────┬────────────────────────────────────┐  │
│   │ 需要编码  │ → sessions_spawn(Codex Agent)      │  │
│   │ 需要搜索  │ → web_search / web_fetch           │  │
│   │ 需要通知  │ → message(feishu) / imsg           │  │
│   │ 需要计算  │ → exec(python)                     │  │
│   │ 需要记忆  │ → memory_get / memory_search       │  │
│   │ 需要设计  │ → image_generate / diagram-maker   │  │
│   │ 需要审批  │ → message → 等待人类回复            │  │
│   └──────────┴────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 5.2 跨工具编排的三种模式

**模式 A: 串行管道**
```
web_search("API 文档") → LLM 整理 → sessions_spawn(Codex 实现) → exec(测试) → message(报告)
```
适用: 步骤间有强依赖

**模式 B: 并行扇出**
```
sessions_spawn(研究专家 1) ─┐
sessions_spawn(研究专家 2) ─┼→ sessions_yield → LLM 综合 → 决策
sessions_spawn(研究专家 3) ─┘
```
适用: 多角度分析、并行探索

**模式 C: 人类在环**
```
Loop 遇到阻塞 → message(feishu, "需要确认: X 还是 Y?")
→ 等待人类回复 → 解析回复 → 继续执行
```
适用: 需要人类判断的关键决策点

### 5.3 Codex 编排协议

```
OpenClaw 决定需要编码:
1. 生成编码任务描述（包含上下文、约束、验收标准）
2. sessions_spawn(task="<编码任务>", label="codex-worker")
3. sessions_yield()
4. Codex 在隔离环境中实现代码
5. 完成后 auto-announce 回 OpenClaw
6. OpenClaw 验证: exec("pytest tests/") → 通过 → 继续
7. 失败 → 分析错误 → 重新 spawn 或人工介入
```

---

## 六、Loop 完整生命周期

```
  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │  ① 创建        ② 规划        ③ 执行        ④ 暂停          │
  │  /goal → init  LLM 分解     spawn/yield   阻塞→通知        │
  │     │            │              │             │             │
  │     ▼            ▼              ▼             ▼             │
  │  ┌──────┐   ┌──────┐      ┌────────┐   ┌────────┐        │
  │  │config│   │sub   │      │worker  │   │blocked │        │
  │  │.json │   │goals │      │results │   │waiting │        │
  │  └──────┘   └──────┘      └────────┘   └────────┘        │
  │                                     │            │         │
  │     ┌───────────────────────────────┘            │         │
  │     ▼                                            │         │
  │  ⑤ 反思 ←──── heartbeat/cron ────→ ⑤            │         │
  │  LLM 分析 history → 优化策略                     │         │
  │     │                                            │         │
  │     ▼                                            │         │
  │  ⑥ 完成 ←──── goal verified ────────────────────┘         │
  │  生成报告 → 清理资源                                        │
  │     │                                                      │
  │     ▼                                                      │
  │  ⑦ 进化                                                    │
  │  经验 → memory → Skill Workshop → 下次 Loop 复用            │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
```

### 各阶段详细设计

| 阶段 | 触发条件 | 核心动作 | 产出 |
|------|---------|---------|------|
| **① 创建** | 用户 `/loop` 或 `/goal` | 初始化目录结构、注册 cron | config.json, state.json |
| **② 规划** | Loop 启动 | LLM 分解目标为子目标树、选择工具、制定计划 | goals/sub_*.json |
| **③ 执行** | 规划完成 / 恢复 | `loop_runner.py next` → spawn → yield → 检查 → 循环 | history.jsonl 追加 |
| **④ 暂停** | 阻塞/需人类输入 | 写入 blocked 状态 → message 通知 → cron 定期检查恢复条件 | state.json=blocked |
| **⑤ 反思** | cron 触发 / heartbeat | LLM 读取 history → 分析模式 → 调整策略/ prompts | 更新 config, memory 写入 |
| **⑥ 完成** | goal verify 通过 | 生成报告 → 飞书通知 → 归档目录 | report.md, state=done |
| **⑦ 进化** | 完成后自动 | 提取经验 → memory → 可选提交 Skill Workshop | memory/*.md, skill proposal |

---

## 七、创新设计：OpenClaw 独有的 Loop 机制

### 创新 1: **Dream-Driven Self-Evolution（梦境驱动自进化）**

**原理**: 利用 OpenClaw 的 memory + cron + Skill Workshop 组合，让 Loop 在"休眠"时自动进化。

```
传统 Loop:          执行 → 完成 → 结束
OpenClaw Loop:      执行 → 完成 → Dream(反思) → 进化(Skill) → 下次更强
```

**实现**:
```
Dream Loop (每日 cron):
1. 读取所有 Loop 的 history.jsonl
2. LLM 分析: "这 10 次迭代中，哪些 prompt 模式导致了成功？哪些导致了失败？"
3. 提炼出 pattern: "当任务包含 X 特征时，使用 Y 策略的成功率高 40%"
4. 自动创建 Skill Workshop proposal:
   skill_workshop(action="create", name="pattern-X-strategy-Y", 
                  proposal_content="当遇到 X 类任务时...")
5. 积累足够证据后 → skill_workshop(action="apply") → 成为正式 Skill
6. 下次 Loop 自动加载这个 Skill → 表现更好
```

**为什么 OpenClaw 独有**: 需要 memory（跨 session 持久化）+ cron（定时触发）+ Skill Workshop（自我修改能力）+ sessions_spawn（隔离分析环境）的组合。其他平台没有这种"Agent 修改自己的 Skill 库"的能力。

### 创新 2: **Fractal Interrupt（分形中断）**

**原理**: 任何层级的 Loop 都可以被中断、暂停、恢复，且中断可以**向上传播**或**向下隔离**。

```
外 Loop 正在运行
  ├─ 中 Loop: Spec Pro (running)
  │   └─ 内 Loop: Phase 3 Research (running)
  │       └─ Worker: 架构专家 (running)
  │
  │ ← 飞书消息: "需求变了，暂停所有工作"
  │
  │ 外 Loop 收到中断 → 
  │   ├─ 暂停中 Loop → 中 Loop 暂停内 Loop → 内 Loop 暂停 Worker
  │   ├─ 保存断点: 每个 Loop 的 state.json 记录当前 phase + 已完成结果
  │   └─ 通知所有 Worker 停止
  │
  │ ← 30 分钟后: "需求确认完毕，继续"
  │
  │ 外 Loop 恢复 →
  │   ├─ 从中 Loop 的断点恢复 → 内 Loop 从断点恢复
  │   ├─ Worker 重新 spawn（带上之前的上下文）
  │   └─ 继续执行
```

**实现**:
```
中断传播:
  /loop pause-all
  → 外 Loop state.json → status: "paused"
  → 遍历子 Loop → 各自 state.json → status: "paused"  
  → 取消所有活跃 cron routines
  → 记录 pause_snapshot.json（完整断点）

恢复:
  /loop resume-all
  → 读取 pause_snapshot.json
  → 重新注册 cron routines
  → 从断点恢复每个 Loop 的执行
```

**为什么 OpenClaw 独有**: 需要 sessions_spawn（隔离执行）+ cron（可取消/重建）+ memory（断点持久化）+ message（中断通知）的组合。分形中断的传播和恢复依赖于 Loop 的嵌套目录结构，这是 OpenClaw 文件即状态的设计哲学所独有的。

---

## 八、架构总图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OpenClaw AI Native Loop                      │
│                                                                     │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────────┐   │
│  │ /loop   │  │ /routine │  │ /goal     │  │ memory           │   │
│  │ 创建Loop│  │ 注册触发器│  │ 定义目标  │  │ 跨Session持久化  │   │
│  └────┬────┘  └────┬─────┘  └─────┬─────┘  └────────┬─────────┘   │
│       │            │              │                  │             │
│  ┌────▼────────────▼──────────────▼──────────────────▼──────────┐  │
│  │                    Loop Controller (LLM)                      │  │
│  │         观察 → 判断 → 决策 → 分派 → 验证 → 反思              │  │
│  └────┬────────────┬──────────────┬──────────────────┬──────────┘  │
│       │            │              │                  │             │
│  ┌────▼────┐  ┌────▼─────┐  ┌────▼─────┐  ┌────────▼──────────┐  │
│  │sessions │  │ exec     │  │ message  │  │ cron              │  │
│  │_spawn   │  │ Python   │  │ 飞书/邮件 │  │ 间歇式触发        │  │
│  │Worker   │  │ 骨架     │  │ 人类在环  │  │ Dream/Meta Loop   │  │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       │            │              │                  │             │
│  ┌────▼────────────▼──────────────▼──────────────────▼──────────┐  │
│  │              .deepflow/loops/<name>/                          │  │
│  │   config.json + state.json + history.jsonl + goals/          │  │
│  │              （文件即状态，目录即 Loop）                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Cross-Tool Ecosystem                             │  │
│  │  Codex(编码) | Hermes(协作) | Claude Code(审查) | Web(搜索)  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 九、与 DeepFlow 现有架构的对接

### 渐进迁移路径

| 阶段 | 改动 | 风险 |
|------|------|------|
| **Phase 0** (已完成) | `loop_runner.py next` + Phase Worker 模式 | ✅ 已验证 |
| **Phase 1** | 为 loop_runner 增加 `/goal` 语义层（goal judge） | 低：只是在 check 上加 LLM 判断 |
| **Phase 2** | 实现 Project Loop 控制器（外 Loop） | 中：需要新的目录结构和 cron |
| **Phase 3** | 实现 Dream Loop + Skill 自进化 | 低：复用现有 memory + cron |
| **Phase 4** | 实现分形中断 + 跨工具编排 | 高：需要标准化中断协议 |

### 不变的部分

- `loop_runner.py` 的内 Loop 逻辑保持不变
- 契约笼子（Watcher）保持不变
- pipeline_state.json 的文件即状态模式保持不变
- Phase Worker 的 spawn/yield 模式保持不变

**核心思想**: 不是替换，是**包裹**。新的 Loop 原语包裹住现有的 loop_runner，在外层增加语义判断、间歇调度和自进化能力。

---

*设计完成。这不是代码，是蓝图。每一步实现都可以从现有架构渐进迁移，不需要推翻重来。*
