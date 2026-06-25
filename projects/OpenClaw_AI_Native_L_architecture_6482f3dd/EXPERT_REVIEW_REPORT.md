# AI Native Loop Framework 专家评审综合报告

> **日期**: 2026-06-25  
> **评审对象**: Hermes + Codex 交付的 OpenClaw AI Native Loop Engineering Framework  
> **评审专家**: 5 位（架构师、OpenClaw 集成、可靠性、异步框架、项目经理）  
> **评审模型**: Qwen 3.7 Max × 5 并行  

---

## 综合评分

| 专家 | 维度 | 评分 | 一句话 |
|------|------|------|--------|
| 🏗️ 架构师 | 架构对齐度 | **3.5/10** | 9个零件没有引擎和方向盘，"全LLM控制"被完全违背 |
| 🔌 OpenClaw集成 | 平台适配度 | **6/10** | 70%组件可被OpenClaw原生替代，不是代码问题而是路径问题 |
| 🛡️ 可靠性 | 8h运行就绪度 | **4/10** | 信号→执行断裂，像火警响了没人接警 |
| ⚡ 异步框架 | 工程质量 | **5.5/10** | 精密零件没有发动机，缺执行引擎和并发控制 |
| 📋 项目经理 | 交接完整性 | **5.5/10** | 有条件通过，7/16 WP有问题，最关键是缺编排层 |

**综合评分：4.9/10**

---

## 核心发现（5位专家共识）

### 共识 1：交付件是"组件工具箱"，不是"可运行系统"

9 个模块代码质量不错（类型安全、零依赖、测试覆盖），但**缺少编排层**把它们串成 Loop。这恰恰是最核心、最复杂的部分。

### 共识 2："全 LLM 控制"决策被完全违背

8 位专家研讨的核心裁决是"全 LLM 控制，Python 不做控制流"。但代码中：
- `ModelRouter` → 硬编码 dict 映射（不是 LLM 决策）
- `DAGDecomposer` → 关键词匹配 + fallback 固定 plan（不是 LLM 规划）
- `Zone2Tuner` → if/else 规则引擎（不是 LLM 调优）

**架构师原话**："这不是 AI Native，这是传统规则引擎套了 AI Native 的文档壳。"

### 共识 3：70% 组件可被 OpenClaw 原生能力替代

| 建议 | 组件 | 理由 |
|------|------|------|
| 🗑️ 废弃 | ModelRouter, TokenBucket, PriorityQueue, ContextCompressor | OpenClaw model alias + Gateway 并发控制 + session context 管理更好 |
| 🔄 替代 | DAGDecomposer, Blackboard, SignalDetector | 用 LLM prompt + workspace 文件 + cron watcher 替代 |
| ✅ 复用思路 | DreamLoop, MetaLoop, QualityHarness | 验证逻辑有价值，但应重写为 Skill/cron prompt |

### 共识 4：三层循环数据流完全断路

```
Task Loop → Dream Loop？  ❌ 无通道（history 不自动流入反思）
Dream Loop → Meta Loop？  ❌ 无通道（教训不写入调优指标）
Meta Loop → Task Loop？   ❌ 无通道（TuningAction 输出了但无人消费）
```

### 共识 5：信号检测→执行响应断裂

SignalDetector 能检测 4 类信号（重复/token异常/心跳超时/无进展），但检测完了就结束了——没有 CircuitBreakerExecutor 来执行 warn→pause→terminate 动作。可靠性专家原话："像一个火警报警器响了但没人接警。"

---

## 紧急风险

### 🔴 R1：/tmp/ 代码即将丢失

6 个 WP 的代码（WP-003 并发锁、WP-005 熔断执行器、WP-009 并行执行器、WP-012 权重衰减、WP-014 双轨校准、WP-016 回归防护）**只存在于 /tmp/shippro-wp*/** 目录。系统清理或重启后永久丢失。

**建议**：立即合并到交付目录（0.5 天）

### 🔴 R2：LLM API 不可用零覆盖

8 小时运行中 LLM API 必然遇到限流/超时/错误，但当前无任何重试、退避、备用模型切换机制。

### 🟡 R3：全同步架构无法支撑 8 小时

同步阻塞 + 单线程 = 一个 Worker 超时整个 Loop 卡死。但专家共识是不需要自建 async，用 OpenClaw sessions_spawn 调度即可。

---

## 落地路线图建议（综合 5 位专家）

### Phase 0：紧急保全（0.5 天）⚡ 立即

| 任务 | 验收标准 |
|------|---------|
| 将 /tmp/ 中 6 个 WP 代码合并到交付目录 | 所有文件到位，pytest 通过 |

### Phase 1：最小可运行 Loop（5 天）

**核心策略变化**：不是"在交付件上加编排层"，而是"用 OpenClaw 原生能力重写编排，复用交付件中的好思路"

| 任务 | 说明 | 工作量 |
|------|------|--------|
| 创建 AI Native Loop Skill | SKILL.md 定义主 Agent 行为：Goal 解析→DAG 分解→Worker spawn→结果验证 | 2 天 |
| Goal Parser（LLM prompt） | 主 Agent 直接理解自然语言目标，生成 task_dag.json | 含在 Skill 中 |
| Worker 调度（sessions_spawn） | 按 DAG 依赖顺序 spawn 子 Agent，每个 Worker 用合适的 model | 1 天 |
| 状态持久化（memory/loops/） | 用 workspace 文件替代 Blackboard | 0.5 天 |
| Watcher Cron | 3min 快脉冲监控 Worker 进度 | 0.5 天 |
| 飞书通知 | message 集成，关键节点通知 | 0.5 天 |
| 端到端验证 | 一个简单 Goal 从头跑到尾 | 0.5 天 |

**里程碑**：`/loop "实现用户认证模块"` 能端到端运行

### Phase 2：并行 + 真实 LLM（5 天）

| 任务 | 说明 | 工作量 |
|------|------|--------|
| DAG 并行执行 | 无依赖节点并行 spawn，Semaphore 控制最大 6 并发 | 2 天 |
| 真实 LLM 集成 | DAGDecomposer 用 LLM 分解（不是 fallback） | 1.5 天 |
| 错误恢复链 | Worker 失败→重试→换模型→拆任务→上报人类 | 1.5 天 |

**里程碑**：复杂 Goal 分解为 5+ 节点 DAG，3+ Worker 并行执行，失败自动恢复

### Phase 3：Dream + Meta Loop（5 天）

| 任务 | 说明 | 工作量 |
|------|------|--------|
| Dream Loop Cron（日） | 空闲时 LLM 读 history.jsonl → 提取模式 → 写 memory/dreams/ | 2 天 |
| Meta Loop Cron（周） | 收集指标 → LLM 分析 → Skill Workshop 调参 | 1.5 天 |
| 间歇式心跳完善 | 快脉冲3min + 慢脉搏1h + 深呼吸日 + 长冥想周 | 1.5 天 |

**里程碑**：系统能 8 小时无人运行，Dream Loop 至少触发 1 次并产出有用教训

### Phase 4：加固（5 天）

| 任务 | 说明 | 工作量 |
|------|------|--------|
| 可观测性 | 结构化日志 + 指标收集 + 健康检查 | 2 天 |
| 测试套件 | 端到端测试 + 故障注入测试 + 性能测试 | 2 天 |
| 文档 | API 文档 + 运维手册 + 故障排查 | 1 天 |

**里程碑**：通过 72 小时稳定性测试

### 总计：20.5 人天（约 4 周）

---

## 战略建议（给决策者）

### 1. 路径选择：修补 vs 重写

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A. 在交付件上加编排层** | 保留 9 个组件，写 LoopRunner 串起来 | 不浪费已有代码 | 违背"全LLM控制"决策，需大量适配 |
| **B. OpenClaw 原生重写** ⭐ | 用 Skill + sessions_spawn + cron + memory 实现，复用交付件中的好思路 | 符合架构决策，代码量更少 | 交付件大部分代码不直接用 |

**推荐 B**。原因：
- 5 位专家共识：70% 组件可被 OpenClaw 替代
- "全 LLM 控制"意味着编排层应该是 LLM prompt（Skill），不是 Python 代码
- 交付件的最大价值是**设计思路**（三维验证、信号检测、权重衰减），不是代码本身

### 2. 交付件的价值定位

| 价值 | 说明 |
|------|------|
| ✅ 设计模式参考 | CircuitBreaker 四维信号、DreamLoop 三层验证、Meta Loop Zone2 调优 |
| ✅ 验收标准参考 | 16 WP 的 acceptance criteria 可直接复用于新实现 |
| ✅ 反面教材 | "全 LLM 控制"被违背的案例，帮助理解什么是 AI Native |
| ❌ 不宜直接复用 | 代码本身是传统 Python 库设计，与 AI Native 理念冲突 |

### 3. 立即行动项

1. **⚡ 今天**：合并 /tmp/ 代码（防止丢失）
2. **本周**：创建 AI Native Loop Skill V1（最小可运行）
3. **下周**：用 Skill 跑通第一个端到端 Loop

---

*5 位专家 × 独立评审 × 交叉验证。评审用时 ~10 分钟。*
