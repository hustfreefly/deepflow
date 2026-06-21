# DeepFlow 架构重设计 V3 — AI Native 最终方案

> **日期**: 2026-06-18 | **最后更新**: 2026-06-18 22:13（V3.1）
> **参与专家**: 16 位（三轮：6 + 6 + 4）
> **总报告量**: ~340KB（16 份专家报告）
> **核心转变**: 从"LLM + 确定性兜底" → **纯 AI Native 多 Agent 协作**
> **V3.1 更新**: 基于 OpenClaw 技术验证，确认 `sessions_send` 可向已完成 sub-agent 发送反馈，Agent 保持完整上下文。反馈闭环从"重新 spawn"升级为"持续对话"模式。

---

## 一、V2 → V3 的关键转变

### V2 方案（被否定）
```
LLM 前端解析 → SolutionIR → 确定性后端组装 → JSON Schema 校验
```
**问题**：把 LLM 当"提取器"用，核心智能工作（拆 WP、补 AC、估工时）还是确定性代码。不是 AI Native。

### V3 方案（16 专家共识 + 技术验证）
```
Solution Pro → final_result.json（多种格式）
    ↓
Ship Pro 多 Agent 协作（全部 LLM，零确定性代码）
    ├── Architect Agent（架构理解 + blueprint.json 生成）
    ├── Decomposer Agent（WP 拆解 + 依赖排序）
    ├── Specifier Agent（AC 生成 + 技术约束 + 交付物）
    ├── Calibrator Agent（工时校准 + 风险补充，可选）
    └── Reviewer Agent（质量审核 + 结构化反馈）
    ↓
  ★ 反馈闭环（sessions_send 持续对话，全自动）
    ↓
ship_package.json
    ↓
Super Loop → 代码
```

---

## 二、关键技术发现：sessions_send 持续对话能力

> **验证日期**: 2026-06-18 22:05-22:09

### 验证过程

| # | 动作 | 结果 | 时间 |
|---|------|------|------|
| 1 | `sessions_spawn(task="回复'我已完成任务'")` | sub-agent 回复"我已完成任务"，session 保留 | +3s |
| 2 | `sessions_send(sessionKey, "请回复：你好")` | sub-agent 回复"你好，我收到了你的后续消息" | +7s |

**sub-agent 的 thinking 记录**：
> *"My task was to reply '我已完成任务' and wait for further instructions. Now I'm receiving an inter-session message... I should follow instructions from my requester session."*

**确认**：sub-agent 保持了完整上下文，知道自己是 sub-agent，知道主 Agent 是 requester，继续执行后续指令。

### 对架构的影响

| 维度 | 旧方案（重新 spawn） | 新方案（sessions_send） |
|------|---------------------|------------------------|
| **上下文** | ❌ 丢失，需要重新加载全部输入 | ✅ 保持完整上下文 |
| **Token 消耗** | 每次修改 ~33KB 输入 + 新 prompt | 只需传 review_report ~2KB |
| **响应速度** | 30-60 秒（重新 spawn + 加载） | 7 秒（直接唤醒） |
| **修改质量** | 新 Agent 需要重新理解全部上下文 | 原 Agent 记得之前做了什么，修改更精准 |
| **模式** | 一次性任务 + 重做 | 持续对话 |

---

## 三、16 位专家对核心问题的投票

### Q1: Ship Pro 用多 Agent 还是单 Agent？

| 建议 | 票数 |
|------|:---:|
| **5 Agent 拆分**（Architect→Decomposer→Specifier→Calibrator→Reviewer） | **忠礼决策** |
| 3 Agent 串行 | 3/4 专家初始建议 |
| 单 Agent 干到底 | 0/4 |
| LLM + 确定性兜底 | 0/4 |

**最终决定**：5 Agent。每个 Agent 做一件事，prompt 聚焦。Planner 拆成 Decomposer + Specifier，新增 Calibrator。

### Q2: Agent 间协作契约

**共识**：`blueprint.json` 作为 Agent 协作契约（Architect 输出，Decomposer/Specifier 输入）。不叫 SolutionIR，避免传统编译器思维。

### Q3: 质量校验用什么？

**共识**：Reviewer Agent（LLM 审核）为主，JSON Schema 仅作为格式兜底。

### Q4: 反馈闭环怎么处理？

**旧方案**：最多 2 轮 → 人工介入
**新方案（忠礼决策）**：**全自动，无人工介入，token 预算兜底**

### Q5: 实施信心评分

| 专家 | 信心 | 主要顾虑 |
|------|:---:|---------|
| AI Native 架构师 | **8/10** | Agent 分工需要迭代调优 |
| Prompt 工程师 | **7/10** | 输入格式多样性对 prompt 稳定性有挑战 |
| 编排专家 | **8/10** | OpenClaw 完全支持这个模式 |
| 质量工程师 | **7/10** | Reviewer Agent 和生产 Agent 可能有"共谋"风险 |
| **平均** | **7.5/10** | sessions_send 验证后信心提升 |

---

## 四、V3.1 最终架构设计

### 4.1 多 Agent 架构图

```
Solution Pro 完成
  ↓
  触发 Ship Pro Orchestrator
  ↓
  ┌──────────────────────────────────────────────────────────────────┐
  │                  Ship Pro 五 Agent 协作管线                       │
  │                                                                  │
  │  Stage 1: Architect Agent ──── sessions_spawn                    │
  │    输入: final_result.json + RTM + execution_plan.json           │
  │    工作: 理解架构语义，统一为标准格式                               │
  │    输出: blueprint.json                                          │
  │    ↓（session 保留，等待反馈）                                     │
  │                                                                  │
  │  Stage 2: Decomposer Agent ──── sessions_spawn                   │
  │    输入: blueprint.json                                          │
  │    工作: 模块 → WP 拆分 + 依赖关系 + phase 排序                   │
  │    输出: wp_structure.json                                       │
  │    ↓（session 保留，等待反馈）                                     │
  │                                                                  │
  │  Stage 3: Specifier Agent ──── sessions_spawn                    │
  │    输入: blueprint.json + wp_structure.json                      │
  │    工作: 为每个 WP 生成 AC + 技术约束 + 交付物                     │
  │    输出: wp_specs.json                                           │
  │    ↓（session 保留，等待反馈）                                     │
  │                                                                  │
  │  Stage 4: Calibrator Agent ──── sessions_spawn（可选）            │
  │    输入: wp_specs.json + 历史项目数据                             │
  │    工作: 校准工时估算 + 补充风险识别                               │
  │    输出: wp_specs_calibrated.json                                │
  │    ↓（session 保留，等待反馈）                                     │
  │                                                                  │
  │  Stage 5: Reviewer Agent ──── sessions_spawn                     │
  │    输入: wp_specs.json（或 calibrated）+ blueprint.json          │
  │    工作: 审核质量、一致性、可执行性                                 │
  │    输出: review_report.json（结构化反馈，标注修改目标 Agent）       │
  │    ↓（session 保留，等待反馈）                                     │
  │                                                                  │
  │  ★ 反馈闭环（全自动，sessions_send 持续对话）                      │
  │    ├── PASS → 组装 ship_package.json → 完成                      │
  │    ├── WP 拆分问题 → sessions_send → Decomposer 修改             │
  │    ├── AC 质量问题 → sessions_send → Specifier 修改              │
  │    ├── 工时问题 → sessions_send → Calibrator 修改                │
  │    ├── 架构理解错误 → sessions_send → Architect 修改 blueprint   │
  │    └── 多问题 → 并行 sessions_send 给多个 Agent                   │
  │    ↓（循环，直到 Reviewer 判定 PASS 或 token 预算用完）            │
  │                                                                  │
  └──────────────────────────────────────────────────────────────────┘
  ↓
Super Loop 消费 ship_package.json
```

### 4.2 各 Agent 职责定义

#### Architect Agent（架构理解器）

| 维度 | 设计 |
|------|------|
| **一句话定义** | 从任意格式的方案中提取统一架构描述 |
| **输入** | final_result.json + requirements_traceability_matrix.json + execution_plan.json |
| **输出** | blueprint.json |
| **核心工作** | 1. 识别所有模块（无论在哪种格式中）<br>2. 提取每个模块的职责、技术栈、部署方式<br>3. 推导模块间依赖关系<br>4. 提取需求覆盖信息 |
| **prompt 设计** | 提供 5 种格式的 few-shot 示例，让 LLM 学会"不管格式怎么变，找到模块信息" |
| **feedback** | ✅ Reviewer 反馈后可通过 sessions_send 修改 blueprint |

#### Decomposer Agent（任务分解器）

| 维度 | 设计 |
|------|------|
| **一句话定义** | 把架构模块拆成可执行的工作包并排依赖 |
| **输入** | blueprint.json |
| **输出** | wp_structure.json |
| **核心工作** | 1. 模块 → WP（大模块拆成多个 WP）<br>2. 推导 WP 间依赖关系<br>3. Phase 排序（拓扑排序）<br>4. 识别集成检查点 |
| **prompt 设计** | 明确的拆分原则 + 依赖推导规则 |
| **feedback** | ✅ Reviewer 反馈后可通过 sessions_send 修改 WP 拆分 |

#### Specifier Agent（规格细化器）

| 维度 | 设计 |
|------|------|
| **一句话定义** | 为每个工作包写具体的验收标准和技术约束 |
| **输入** | blueprint.json + wp_structure.json |
| **输出** | wp_specs.json |
| **核心工作** | 1. 从模块职责生成具体的、可验证的 AC<br>2. 提取技术约束（从 blueprint 传递）<br>3. 定义交付物清单 |
| **prompt 设计** | "好 AC"和"坏 AC"的对比示例 + 禁止废话规则 |
| **feedback** | ✅ Reviewer 反馈后可通过 sessions_send 修改 AC |

#### Calibrator Agent（校准器，可选）

| 维度 | 设计 |
|------|------|
| **一句话定义** | 校准工时估算，补充风险识别 |
| **输入** | wp_specs.json + 历史项目数据（可选） |
| **输出** | wp_specs_calibrated.json |
| **核心工作** | 1. 基于复杂度校准工时<br>2. 补充遗漏的风险<br>3. 交叉验证依赖合理性 |
| **何时启用** | 项目复杂度高（>5 模块）或用户明确要求 |
| **feedback** | ✅ Reviewer 反馈后可通过 sessions_send 修改工时 |

#### Reviewer Agent（质量审核器）

| 维度 | 设计 |
|------|------|
| **一句话定义** | 审核工作包质量，发现不合格就反馈修改 |
| **输入** | wp_specs.json + blueprint.json |
| **输出** | review_report.json（结构化反馈，标注修改目标 Agent） |
| **核心工作** | 1. AC 是否具体可验证？<br>2. 依赖关系是否合理？<br>3. 工时估算是否靠谱？<br>4. 技术约束是否正确传递？<br>5. 是否有遗漏的模块或需求？ |
| **反馈格式** | 结构化 JSON，每个 issue 标注 `target_agent`（Decomposer/Specifier/Calibrator/Architect） |
| **feedback** | ✅ 自身也可通过 sessions_send 被要求"重新审核" |

### 4.3 Agent 间数据传递

```
blackboard/{session_id}/
├── final_result.json                    ← Solution Pro 输出
├── requirements_traceability_matrix.json ← Solution Pro 输出
├── execution_plan.json                   ← Solution Pro 输出
├── blueprint.json                        ← Architect Agent 输出
├── wp_structure.json                     ← Decomposer Agent 输出
├── wp_specs.json                         ← Specifier Agent 输出
├── wp_specs_calibrated.json              ← Calibrator Agent 输出（可选）
├── review_report.json                    ← Reviewer Agent 输出
├── review_report_v2.json                 ← Reviewer Agent 输出（第二轮）
└── ship_package.json                     ← 最终组装输出
```

---

## 五、在 OpenClaw 上的实现方案

### 5.1 编排模式（V3.1 持续对话版）

```python
# 伪代码 — Ship Pro Orchestrator 核心逻辑

# Phase 1: 首次执行（全部 spawn）
architect_key = sessions_spawn(task=architect_prompt, taskName="architect")
sessions_yield()  # 等 Architect 完成

decomposer_key = sessions_spawn(task=decomposer_prompt, taskName="decomposer")
sessions_yield()

specifier_key = sessions_spawn(task=specifier_prompt, taskName="specifier")
sessions_yield()

# Calibrator 可选
calibrator_key = sessions_spawn(task=calibrator_prompt, taskName="calibrator")
sessions_yield()

reviewer_key = sessions_spawn(task=reviewer_prompt, taskName="reviewer")
sessions_yield()

# Phase 2: 反馈闭环（全部 sessions_send）
max_rounds = token_budget / per_round_cost  # 动态计算

for round in range(max_rounds):
    report = read("review_report.json")
    
    if report.verdict == "PASS":
        assemble_ship_package()
        break
    
    # 解析反馈，确定修改目标
    for issue in report.issues:
        target = issue.target_agent  # "decomposer" / "specifier" / etc
        target_key = {"architect": architect_key, "decomposer": decomposer_key, ...}[target]
        
        # 直接 sessions_send 给目标 Agent（保持上下文！）
        sessions_send(target_key, f"请根据以下反馈修改你的输出：\n{issue.feedback}")
    
    sessions_yield()  # 等所有修改完成
    
    # 要求 Reviewer 重新审核
    sessions_send(reviewer_key, "以下 Agent 已根据反馈修改，请重新审核。")
    sessions_yield()
```

### 5.2 每个 Agent 的实现

| Agent | 首次执行 | 反馈修改 | 模型选择 | 超时 |
|-------|---------|---------|---------|------|
| Architect Agent | sessions_spawn | sessions_send | 强模型（opus/kimi-k2） | 300s |
| Decomposer Agent | sessions_spawn | sessions_send | 强模型（opus/kimi-k2） | 300s |
| Specifier Agent | sessions_spawn | sessions_send | 强模型（opus/kimi-k2） | 300s |
| Calibrator Agent | sessions_spawn | sessions_send | 中模型（qwen/kimi-k2.5） | 180s |
| Reviewer Agent | sessions_spawn | sessions_send | 不同模型（避免共谋） | 300s |

### 5.3 质量闭环（全自动）

```
首次执行完毕 → Reviewer 输出 review_report.json
    ↓
Orchestrator 读 review_report → 判断 PASS/FAIL
    ├── PASS → 组装 ship_package.json → 完成 ✅
    │
    └── FAIL → 解析反馈，确定修改目标 Agent
         ↓
    sessions_send(目标 Agent sessionKey, 反馈内容)
         ↓（Agent 保持上下文，直接修改，无需重新加载）
    Agent 输出修改后的文件
         ↓
    sessions_send(Reviewer sessionKey, "请重新审核以下变更：...")
         ↓（Reviewer 也保持上下文，对比审核）
    Reviewer 输出新 review_report.json
         ↓
    循环，直到 PASS 或 token 预算用完
```

**关键特性**：
- **全自动**：无人工介入断点，Reviewer 不满意就一直修改
- **保持上下文**：每个 Agent 记得之前做了什么，修改更精准
- **Token 高效**：反馈只需传 review_report（~2KB），不需要重传全部输入（~33KB）
- **安全阀**：总 token 预算上限（如 100K tokens），超出则输出当前最佳结果

---

## 六、与 V2 方案的关键差异

| 维度 | V2（被否定） | V3.1（最终） |
|------|-------------|-----------|
| **Ship Pro 实现** | LLM 提取 + 确定性组装 | 5 Agent 纯 LLM 协作 |
| **质量校验** | JSON Schema（确定性） | Reviewer Agent（LLM 审核） |
| **反馈机制** | L1→L2→L3（LLM→规则→骨架） | **sessions_send 持续对话**（Agent 保持上下文修改） |
| **闭环策略** | 最多 2 轮 + 人工介入 | **全自动**，直到 PASS 或 token 预算用完 |
| **可调试性** | SolutionIR dump | blueprint.json + review_report.json |
| **代码量** | ~500 行 Python + Prompt | ~200 行编排代码 + 5 个 Prompt |
| **维护重点** | 代码逻辑 | Prompt 质量 + Agent 间协作 |

---

## 七、实施路线

### Phase 1: Prompt 设计 + 单 Agent 验证（1 周）

1. 设计 Architect Agent 的 prompt（含 5 种格式的 few-shot 示例）
2. 用 3 个案例测试 Architect Agent → blueprint.json 质量
3. 设计 Decomposer Agent 的 prompt
4. 设计 Specifier Agent 的 prompt
5. 设计 Reviewer Agent 的 prompt + 结构化反馈格式

### Phase 2: 多 Agent 编排（1 周）

1. 实现 Ship Pro Orchestrator（~200 行编排代码）
2. 5 个 Agent 串行 spawn + sessionKey 管理
3. sessions_send 反馈闭环（验证持续对话能力）
4. token 预算管理

### Phase 3: 集成验证（1 周）

1. 端到端测试：Solution Pro → Ship Pro → ship_package
2. 用 5 个案例验证 ship_package 质量
3. 对比 V1 确定性编译器 vs V3.1 多 Agent 的输出质量
4. 用户验收（忠礼确认 ship_package 是否可用）

---

## 八、给忠礼的决策清单

| # | 决策 | 推荐 | 状态 |
|---|------|------|:---:|
| 1 | 5 Agent 拆分（Architect→Decomposer→Specifier→Calibrator→Reviewer） | ✅ | ☐ |
| 2 | blueprint.json 作为 Agent 协作契约 | ✅ | ☐ |
| 3 | Reviewer Agent 做质量审核（LLM，不是 JSON Schema） | ✅ | ☐ |
| 4 | 文件系统传递（blackboard 目录） | ✅ | ☐ |
| 5 | 质量闭环全自动（sessions_send 持续对话，无人工介入，token 预算兜底） | ✅ | ☐ |
| 6 | Calibrator Agent 可选（>5 模块时启用） | ✅ | ☐ |

---

## 九、所有报告索引

| 轮次 | 专家 | 视角 | 文件 |
|------|------|------|------|
| 第一轮 | 1. 系统架构师 | DDD + 分层架构 | `expert_1_system_architect.md` |
| | 2. AI Agent 编排 | Manus/Hermes/Claude Code 对比 | `expert_2_agent_orchestration.md` |
| | 3. SE 方法论 | IEEE 标准 + ADR | `expert_3_se_methodology.md` |
| | 4. 产品经理 | 用户工作流 + 决策点 | `expert_4_product.md` |
| | 5. 简约主义 | 反过度工程 | `expert_5_simplicity.md` |
| | 6. 信息架构师 | 数据流 + 信息保真度 | `expert_6_information_architect.md` |
| 第二轮 | 7. LLM 可靠性 | LLM-as-Compiler 可行性 | `expert_7_llm_reliability.md` |
| | 8. 数据工程师 | ETL + Schema 演化 | `expert_8_data_engineer.md` |
| | 9. DevOps | CI/CD + 质量门禁 | `expert_9_devops.md` |
| | 10. 技术写作 | Specification 精确度 | `expert_10_tech_writing.md` |
| | 11. AI 产品经理 | 用户旅程 + 决策点 | `expert_11_product_v2.md` |
| | 12. 编译器设计师 | IR + 前端/后端 | `expert_12_compiler.md` |
| 第三轮 | 13. AI Native 架构师 | 多 Agent 协作设计 | `expert_13_ai_native_architect.md` |
| | 14. Prompt 工程师 | Agent 任务设计 | `expert_14_prompt_engineer.md` |
| | 15. 编排专家 | OpenClaw 编排模式 | `expert_15_orchestration.md` |
| | 16. AI 质量工程师 | Agent 审核 Agent | `expert_16_quality.md` |

---

*V3.1 综合报告完毕。16 份专家原始报告存档于 `.deepflow/docs/research/2026-06-18_expert_reports/`。*
