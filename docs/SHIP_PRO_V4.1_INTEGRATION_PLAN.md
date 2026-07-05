# Ship Pro 2.0.0 整合方案

> **日期**: 2026-06-26  
> **版本**: 2.0.0（2.0.0 提案 + 实际修复 + AI Native 差距分析）  
> **前置**: `SHIP_PRO_AI_NATIVE_PROPOSAL_V4.md`（2026-06-25）  
> **状态**: 待忠礼决策

---

## 一、现状盘点：2.0.0 提案 vs 实际代码

### 1.1 2.0.0 提出的 9 个变更，哪些已落地？

| 2.0.0 变更项 | 落地状态 | 说明 |
|:---|:---:|:---|
| ① capability-registry.json（替代 stage-dependencies.json） | ❌ 未落地 | 当前仍用硬编码 `AGENT_ORDER` + `GATE_CONFIG` |
| ② Goal 声明式 Orchestrator Prompt | ❌ 未落地 | 当前 prompt 仍是过程式 ~200 行 |
| ③ LLM 自主选择执行路径 | ❌ 未落地 | 当前固定 5 阶段顺序执行 |
| ④ io_helper.py 新命令（4 个） | ⚠️ 部分落地 | `semantic-task` + `merge-semantic` 已有，但 `increment-retry` / `validate-coverage` / `list-capabilities` / `list-plans` 没有 |
| ⑤ Judge Worker 差异化视角 | ⚠️ 部分落地 | `ship_harness.md` 存在但是 Fixer 验证，不是独立 Judge |
| ⑥ Worker Prompt 增加 `{failure_feedback}` | ✅ 已落地 | `feedback` CLI 命令已实现 |
| ⑦ compact-history 保留决策原因 | ❌ 未落地 | 无 compact-history 命令 |
| ⑧ log-decision 枚举化 | ❌ 未落地 | 无 log-decision 命令 |
| ⑨ 超时控制 config 层 | ⚠️ 部分落地 | `start_ship_pro.py` 传了 `runTimeoutSeconds: 1800`，但该参数可能不被支持 |

### 1.2 实际修复了哪些（本次断点续接修复）

| 修复项 | 与 2.0.0 的关系 |
|:---|:---|
| ✅ CONDITIONAL 处理规则 | 2.0.0 未提及，属于 bug 修复 |
| ✅ 断点续接规则 | 2.0.0 的 `resume-context` 命令未实现，但 prompt 层面已 workaround |
| ✅ 上下文节约规则 | 2.0.0 的 `compact-history` 未实现，但 prompt 层面已 workaround |
| ✅ `get_pipeline_status` bug（gate_conditional 误判） | 2.0.0 未提及，属于 bug 修复 |
| ✅ `finalize` 未写 `.completed` | 2.0.0 未提及，属于 bug 修复（刚修） |

### 1.3 新版本已验证的 AI Native 能力

| 能力 | 当前实现 | 2.0.0 是否覆盖 |
|:---|:---|:---|
| **架构原则提取** | ✅ Phase -1 已实现 | 2.0.0 未提及 |
| **语义检查** | ✅ `semantic-task` + `merge-semantic` | 2.0.0 未提及 |
| **原则审计** | ✅ Reviewer `principle_audit` + `platform_audit` | 2.0.0 未提及 |
| **三层质量报告** | ✅ Packager `layer1_structural` + `layer2_semantic` + `layer3_actionable` | 2.0.0 未提及 |
| **AC 分级标签** | ✅ Specifier 输出 `[L4]` / `[L3]` | 2.0.0 未提及 |

---

## 二、AI Native 差距分析（忠礼最关心的）

### 2.1 2.0.0 核心理念回顾

> **"LLM 声明式规划，代码验证护栏。不给 LLM 无限权力，也不把 LLM 当执行器。"**

这完全符合 AI Native 原则。问题是：**2.0.0 的设计很好，但没落地。**

### 2.2 当前代码 vs AI Native 原则的差距

| AI Native 原则 | 当前代码 | 2.0.0 方案 | 差距 |
|:---|:---|:---|:---|
| **LLM 做决策，代码做护栏** | ⚠️ 固定 5 阶段顺序 + 硬编码依赖 | ✅ LLM 自主规划 + capability-registry | 中 |
| **结构化输出源头对齐** | ❌ AC 是纯字符串 | ❌ 2.0.0 也没解决 | 大 |
| **Schema 从契约生成** | ❌ prompt schema 手写 vs Pydantic 不同步 | ❌ 2.0.0 也没解决 | 大 |
| **断点续接** | ⚠️ prompt workaround | ⚠️ `resume-context` 未实现 | 中 |
| **上下文管理** | ⚠️ prompt workaround | ⚠️ `compact-history` 未实现 | 中 |
| **独立 Judge** | ⚠️ ship_harness 是 Fixer 验证 | ✅ 差异化 Judge Worker | 中 |
| **Goal 声明式 Prompt** | ❌ 过程式 ~200 行 | ✅ Goal <50 行 + Reference Docs | 大 |
| **能力注册表** | ❌ 硬编码 | ✅ capability-registry.json | 大 |

### 2.3 两个被遗漏的 AI Native 问题

2.0.0 没覆盖、但本次对比暴露的：

1. **AC 结构化**：Specifier 输出 `[L4]` 标签是进步，但仍是纯字符串。应该从源头就输出 `{id, level, description, test_command}`。这是 AI Native 的"结构化输出"原则。

2. **Schema 自动生成**：Packager 重试 2 次是因为 prompt schema 和 Pydantic gate 不同步。应该从 Pydantic model 自动生成 prompt 中的 schema 描述。

---

## 三、2.0.0 整合方案

### 3.1 设计原则

1. **一步到位**（忠礼决策）：不搞渐进迁移，2.0.0 直接落地全部 AI Native 改进
2. **保留已验证能力**：Phase -1 原则提取、语义检查、原则审计、三层质量报告 — 这些已跑通，不丢
3. **补齐 2.0.0 核心架构**：capability-registry + Goal 声明式 Prompt + Judge Worker
4. **补齐 2 个遗漏**：AC 结构化 + Schema 自动生成

### 3.2 2.0.0 变更清单

| 优先级 | 变更项 | 来源 | 影响范围 |
|:---:|:---|:---|:---|
| **P0** | 创建 `capability-registry.json` | 2.0.0 §2 | 替代硬编码 AGENT_ORDER + GATE_CONFIG |
| **P0** | Goal 声明式 Orchestrator Prompt | 2.0.0 §3 | 重写 `start_ship_pro.py` 中的 task |
| **P0** | AC 结构化（Specifier prompt + gate） | 本次发现 | specifier prompt + gate_specifier |
| **P0** | Schema 从 Pydantic 自动生成 | 本次发现 | `run_pipeline.py task` 命令 |
| **P1** | `increment-retry` 原子命令 | 2.0.0 §4.3 | `run_pipeline.py` 新增命令 |
| **P1** | `validate-coverage` 命令 | 2.0.0 §4.4 | `run_pipeline.py` 新增命令 |
| **P1** | `list-capabilities` / `list-plans` 命令 | 2.0.0 §4.1 | `run_pipeline.py` 新增命令 |
| **P1** | Judge Worker 独立 Prompt | 2.0.0 §5 | `prompts/ship_judge.md` 新增 |
| **P1** | `compact-history` 命令 | 2.0.0 §4 | `run_pipeline.py` 新增命令 |
| **P1** | `log-decision` 枚举化 | 2.0.0 §4 | `run_pipeline.py` 修改命令 |
| **P1** | Worker Prompt 增加 `{failure_feedback}` | 2.0.0 §6 | ✅ 已有，无需改动 |
| **P2** | `resume-context` 断点恢复 | 2.0.0 §7 | `run_pipeline.py` 新增命令 |
| **P2** | 超时控制 config 层 | 2.0.0 §7.1 | 配置调整 |
| **P2** | Announce 丢失降级策略 | 2.0.0 §7.3 | Orchestrator prompt 增加 |

### 3.3 架构对比

```
当前（2.0.0+hotfix）:
  start_ship_pro.py → 过程式 prompt → 固定 5 阶段 → run_pipeline.py CLI
  └─ 已有增强: Phase -1 原则提取, semantic-task, principle_audit, 三层质量报告

2.0.0 目标:
  start_ship_pro.py → Goal 声明式 prompt → LLM 自主选择路径 → run_pipeline.py CLI
  ├─ capability-registry.json（能力注册表）
  ├─ Judge Worker（独立评审）
  ├─ compact-history + log-decision（上下文管理）
  ├─ AC 结构化（Specifier 输出 JSON 而非字符串）
  ├─ Schema 自动生成（Pydantic → prompt）
  └─ 保留已有增强: Phase -1, semantic, principle_audit, 三层质量报告
```

### 3.4 实施计划

| 阶段 | 内容 | 预估时间 |
|:---|:---|:---|
| **S1** | capability-registry.json + run_pipeline.py 重构（从 GATE_CONFIG 迁移） | 30min |
| **S2** | Goal 声明式 Orchestrator Prompt 重写 | 20min |
| **S3** | AC 结构化（specifier prompt + gate_specifier Pydantic） | 20min |
| **S4** | Schema 自动生成（Pydantic model → prompt schema） | 20min |
| **S5** | Judge Worker prompt + 管线集成 | 15min |
| **S6** | increment-retry + validate-coverage + list-capabilities | 15min |
| **S7** | compact-history + log-decision 枚举化 | 15min |
| **S8** | 端到端测试（3 场景） | 30min |

总计: ~2.5 小时

---

## 四、关键设计决策（需要忠礼确认）

### 4.1 capability-registry.json vs 硬编码

2.0.0 提出用 JSON 文件声明能力。但当前 `run_pipeline.py` 的 `GATE_CONFIG` 是 Python dict。

**选项 A**: 迁移到 `capability-registry.json`（2.0.0 方案）
- 优点: 声明式、可热更新、LLM 可读取
- 缺点: 需要重写 GATE_CONFIG 逻辑

**选项 B**: 保留 Python dict，但增加 `list-capabilities` 命令输出
- 优点: 改动小
- 缺点: 不符合 AI Native（配置不是声明式）

**推荐**: A（一步到位）

### 4.2 Judge Worker 时机

2.0.0 说"所有阶段完成后 spawn Judge"。但当前管线是 Packager 之后就结束。

**选项 A**: Packager 之后、`.completed` 之前插入 Judge
- 优点: 最后一道关卡
- 缺点: 增加一次 LLM 调用

**选项 B**: 用现有 Reviewer 的 principle_audit 替代 Judge
- 优点: 不增加调用
- 缺点: Reviewer 和 Judge 同偏差问题

**推荐**: A（独立 Judge 是 2.0.0 核心价值）

### 4.3 AC 结构化深度

当前: `"AC-001-1 [L4]: 运行 pytest ..."`

**选项 A**: 结构化 JSON
```json
{"id": "AC-001-1", "level": "L4", "description": "...", "test_command": "pytest ..."}
```

**选项 B**: 保持字符串但强制格式
```
[L4] description | test: command | deps: [...]
```

**推荐**: A（LLM 输出结构化 JSON 毫无难度，下游消费更方便）

---

## 五、不做的事（YAGNI）

| 项目 | 原因 |
|:---|:---|
| io_helper.py 独立文件 | 当前 run_pipeline.py CLI 已覆盖，不需要再拆 |
| stage-dependencies.json 兼容层 | 一步到位，不保留过渡 |
| 多 Reference Plans（quick_review / full_with_iteration） | 先用 standard plan，后续按需扩展 |
| Worker Prompt 重写 | 当前 prompt 质量已验证，只加 `{failure_feedback}` |

---

## 六、验证场景

| 场景 | 输入 | 预期 |
|:---|:---|:---|
| **标准管线** | OpenClaw AI Native L final_result.json | 5 阶段 + Judge 全 PASS |
| **简单改动** | 小型修改的 final_result.json | LLM 自主跳过 architect/decomposer |
| **断点续接** | 中途杀掉，重新 spawn | 从断点继续，不重跑已完成阶段 |

---

*2.0.0 = 2.0.0 核心架构 + 本次修复经验 + 2 个遗漏补齐。一步到位，不渐进。*
