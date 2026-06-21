# Blackboard 重构方案 — 专家评审上下文

> **评审日期**: 2026-06-21
> **评审发起人**: 姬忠礼（DeepFlow 项目 owner）

---

## 一、项目背景

### DeepFlow 是什么

DeepFlow 是一个多 Agent 管线框架，跑在 OpenClaw 平台上。三个域协作形成完整的"需求→方案→代码"链路：

```
Spec Pro（需求收集）→ Solution Pro（方案设计）→ Ship Pro（代码生成）
```

- **Spec Pro**：苏格拉底式对话，输出 Living Spec（结构化需求文档）
- **Solution Pro**：10 阶段 LLM 管线，从 Living Spec 生成完整解决方案（final_result.json）
- **Ship Pro**：5 阶段 LLM 管线，从 final_result.json 生成可执行的工作包（Ship Package）
- **Research Pro**：独立研究域，不跟主链路有数据流

每个域的 Orchestrator 是一个 LLM sub-agent（通过 `sessions_spawn` 启动），Worker 也是 LLM sub-agent。它们通过文件系统（Blackboard）交换数据。

### Blackboard 是什么

Blackboard 是 DeepFlow 的数据交换层——一个文件系统目录，每个运行产生一个目录，包含输入、阶段输出、状态文件、交付文件。**没有数据库，所有状态都在文件系统里。** 消费者是 LLM sub-agent（通过 write/read 工具访问文件）。

### 未来方向

DeepFlow 未来会做成 **Loop Engine**——一个持续迭代的引擎：
```
Loop Iteration #1: Spec → Solution → Ship → 运行 → 反馈
Loop Iteration #2: 基于反馈修改 Spec → 重新 Solution → 重新 Ship → ...
```
每次迭代是一个完整的 run。需要支持跨迭代的 A/B 对比。

---

## 二、当前现状与痛点

### 现状数据
- blackboard/ 下原有 180 个目录（已清理 156 个测试垃圾，剩 16 个真实项目）
- 磁盘占用 23MB
- 三个域的 session_id 命名规则不统一
- Ship Pro 输出嵌套在 Solution Pro 目录下的 `ship/blackboard/` 子目录（套娃）

### 今天暴露的核心问题

**案例**：同一个 DeepFlow 可观测性项目，跑了 3 次 Solution Pro（V1、V2、V3）：

- **V1**（122 REQ，全量 Living Spec）→ stages/ 被 V2 覆盖，数据丢失
- **V2**（8 REQ，去重过度）→ stages/ 被 V3 覆盖，数据丢失
- **V3**（108 REQ，部分去重）→ stages/ 保留，但做 V1 vs V3 对比时需要从 backup 目录恢复

**根因**：Solution Pro 目录名 = `{topic}_{domain}_{hash}`，hash 由输入决定。同输入 → 同目录 → 前一次的 stages/ 被覆盖。没有"运行"的概念，每次运行直接覆盖上一次的数据。

### 五个核心问题

| # | 问题 | 严重度 |
|:---|:---|:---|
| P1 | 同 topic 重跑互相覆盖（无版本隔离） | 🔴 高 |
| P2 | Ship Pro 嵌套 `blackboard/` 子目录（套娃） | 🔴 高 |
| P3 | 状态文件散落根目录（`.completed`、`.cron_*` 混在数据文件里） | 🟡 中 |
| P4 | 三域命名规则不统一 | 🟡 中 |
| P5 | 无 A/B 对比支持（无法比较不同运行的输出） | 🔴 高 |

---

## 三、我们的价值观

### AI Native 原则
- **语义任务用 LLM，确定性任务用代码**：目录管理是确定性任务，应该用代码
- **LLM 是消费者**：Blackboard 的主要消费者是 LLM sub-agent，路径要简单、可预测
- **不过度设计**：当前是单用户系统（忠礼一个人在用），不需要多用户平台的设计

### 工程原则
- **声明-执行对齐**：先声明目标，再执行，再用声明验证
- **最小改动原则**：能改 3 个文件解决的，不改 10 个文件
- **向后兼容**：旧数据不迁移，新代码走新路径，旧数据走降级路径

### 忠礼的沟通风格
- 高信号密度：直接给结论
- 质量驱动：验证失败 = 失败，不接受"基本完成"
- 不喜欢过度设计：够用就行，面向未来但不提前实现

---

## 四、待评审方案

详见 `docs/design/blackboard_system_redesign.md`（v2.0.0-draft）。

### 核心设计

```
blackboard/
├── projects/{slug}/runs/{timestamp}/
│   ├── spec/          ← Spec Pro 输出（run 内，不共享）
│   ├── solution/      ← Solution Pro 输出
│   └── ship/          ← Ship Pro 输出（跟 solution 平级，不嵌套 blackboard/）
├── research/          ← Research Pro（独立，不在项目里）
└── archive/
```

### 关键设计决策

1. **项目 slug**：从 topic 自动生成人类可读的 slug（如 `deepflow-observability`），冲突时加 hash 后缀
2. **Run 命名**：时间戳 `{YYYYMMDD_HHMMSS}`，天然有序且唯一
3. **Spec Pro 在 run 内**：每个 run 是完整迭代快照，不同 run 可能用不同的 Living Spec
4. **Research Pro 独立**：跟主链路无数据流，强行放项目里是假关联
5. **不拆 input/output/state 子目录**：保持扁平，LLM sub-agent 拼路径少一层
6. **Ship Pro 不套娃**：直接写 `ship/stages/`，不再创建 `ship/blackboard/`

### 改动量评估

| 文件 | 改动 |
|:---|:---|
| `start_solution_pro.py` | session_id 生成逻辑 |
| `run_pipeline.py` | 删除 `bb_dir = output_p / "blackboard"` |
| `blackboard.py` | STAGE_PATH_REGISTRY 适配 |
| `completion_handler.py` | 路径适配 |
| `coordinator.py` (Spec Pro) | 输出路径适配 |

---

## 五、开放问题

1. **slug 生成**：自动 slug vs 用户指定 vs hash？推荐自动 + 冲突加后缀
2. **run 内域分离的代价**：多了一层目录（`solution/stages/` vs 直接 `stages/`），LLM sub-agent 路径拼接出错概率增加，这个 trade-off 值吗？
3. **旧数据**：是否值得写迁移脚本？还是直接保留 `_legacy/` 原样？
4. **runs.json/index.json**：由谁维护？orchestrator 还是 completion_handler？
5. **Research Pro 未来是否可能喂给 Solution Pro**：如果未来 research 的输出可以作为 Solution Pro research_expert 的输入，当前独立设计是否需要调整？

---

## 六、评审要求

请从你的认知视角评审这个方案：
1. **方案的核心设计是否合理**？有没有明显的盲点？
2. **改动量是否恰当**？是过度设计还是改动不够？
3. **面向 Loop Engine 的扩展性**？当前设计能否支撑未来的迭代需求？
4. **AI Native 适配性**？路径结构是否适合 LLM sub-agent 消费？
5. **你发现了什么我们没有看到的问题**？

请给出你的判断和建议。我们不需要打分，需要的是你的认知视角和具体建议。
