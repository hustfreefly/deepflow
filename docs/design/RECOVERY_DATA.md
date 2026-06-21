# DeepFlow 数据恢复文件

> **恢复日期**: 2026-06-21
> **数据来源**: Session 日志文件（7b9c5e09, 86924325, 86c101b7, 3759218e, a0ed2c1b, 8687bdaa, 1913e37e, 2762da70）
> **恢复范围**: 2026-06-11 至 2026-06-21 的所有改动

---

## 目录

1. [今天创建的文档](#1-今天创建的文档)
2. [代码改动](#2-代码改动)
3. [分析数据](#3-分析数据)
4. [专家评审结论](#4-专家评审结论)
5. [关键决策](#5-关键决策)

---

## 1. 今天创建的文档


### 1.1 V1_V3_COMPARISON.md — Ship Pro V1 vs V3 宏观对比报告

# Ship Pro V1 vs V3 宏观对比报告

> **项目**: DeepFlow 开发者可观测性系统 (dfobs)
> **Living Spec**: 同一份 `observability_requirement.md`（164行）
> **V1**: Solution Pro 122 REQ（全量）→ Ship Pro（2026-06-20 22:39~23:05）
> **V3**: Solution Pro 108 REQ（部分去重）→ Ship Pro（2026-06-21 10:44~11:11）
> **对比方法**: Ship Pro Quality Guide 三层架构

---

## 一、宏观指标一览

| 指标 | V1 | V3 | 差异 | 评价 |
|:---|:---|:---|:---|:---|
| **Architect REQ 数** | 122 | 12 | **-90%** | 🔴 V3 灾难性信息丢失 |
| **模块数** | 8 | 8 | 相同 | — |
| **依赖边** | 9 | 7 | -2 | 🟡 V3 略简 |
| **技术栈** | Python (.py/pytest) | TypeScript (.ts/npx jest) | 完全不同 | 🔴 同一需求两套技术栈 |
| **Specifier AC 数** | 31 | 37 | +6 | 🟢 V3 略多 |
| **Specifier 输出文件数** | 32 | 25 | -7 | 🟡 V1 更完整 |
| **Specifier 约束数** | 57 | 37 | -20 | 🟡 V3 约束丢失 35% |
| **Packager AC 数** | 31 | **0** | **-100%** | 🔴 V3 Packager 零 AC |
| **Packager 输出文件数** | 32 | 25 | -7 | 🟡 |
| **Packager REQ 映射** | 105 | 20 | -81% | 🔴 V3 追溯断裂 |
| **Packager 约束数** | 57 | **0** | **-100%** | 🔴 V3 约束全丢 |
| **Packager 风险数** | 7 | **0** | **-100%** | 🔴 V3 零风险识别 |
| **Reviewer 判定** | ✅ PASS | ❌ FAIL | — | 🔴 |
| **AC 可验证性分** | 81 | 68 | -13 | 🟡 |
| **Issue 分布** | 0C/0H/1M/4L | 0C/4H/3M/1L | — | 🔴 V3 有 4 个 high |
| **预估总工时** | 280min | 205min | -27% | 🟡 |
| **关键路径** | 190min | 150min | -21% | 🟡 |
| **Token 预算** | 500K | 365K | -27% | 🟡 |
| **项目类型判定** | greenfield | brownfield | 不同 | 🟡 |

---

## 二、🔴 致命差异 1：REQ 信息坍塌（122 → 12）

### 现象

| 阶段 | V1 | V3 |
|:---|:---|:---|
| Solution Pro Planning | 122 REQ-IDs (covered) | 108 REQ-IDs (covered) |
| Ship Pro Architect | **122 REQ-IDs** | **12 REQ-IDs** |
| 信息保留率 | 100% | **9.8%** |

### 根因推测

V3 Architect 将 108 条 REQ **压缩为 12 条高层需求**，而非逐条传递。这意味着 90% 的需求细节在 Architect 阶段就丢失了，后续 4 个阶段（Decomposer→Specifier→Reviewer→Packager）无法恢复。

### 影响链

```
Architect 12 REQ
  → Decomposer 8 WP，每个 WP 只映射 1-3 个 REQ
    → Specifier 约束数从 57 降到 37（-35%）
      → Packager REQ 映射只有 20 条（vs V1 的 105 条）
        → Reviewer FAIL（信息不足以做完整审查）
```

### 结论

**这是 V1 和 V3 所有差异的根因。** V1 Architect 忠实传递了 122 条 REQ，下游每个阶段都有充分的需求信息可以工作。V3 Architect 把需求压缩为 12 条高层摘要，导致下游信息饥渴。

---

## 三、🔴 致命差异 2：技术栈漂移（Python → TypeScript）

### 现象

| 维度 | V1 | V3 |
|:---|:---|:---|
| 语言 | Python | TypeScript |
| 测试框架 | pytest | npx jest |
| 包管理 | pyproject.toml + Typer | npm/package.json |
| CLI 框架 | Typer (Python) | 未明确（Node CLI） |
| 文件扩展名 | .py | .ts |
| 项目结构 | `src/dfobs/...` | 扁平结构 `analysis/...` |

### Living Spec 约束

Living Spec 明确说明：
- "运行平台：OpenClaw（AI Agent 平台）"
- "OpenClaw 已有能力：diagnostics 功能"
- "SQLite + WAL 模式"

但没有指定 Python 还是 TypeScript。Living Spec 的"我的一些思考"部分没有提及语言选择。

### 分析

两个版本都没有明确的 Living Spec 依据来选择技术栈。但 OpenClaw 平台本身是 Node.js 环境（从 `sessions_spawn` API 和 diagnostics API 可以看出），V3 选择 TypeScript 可能是合理的推断。然而 V1 选择 Python 也合理（AI/ML 生态更丰富）。

**核心问题不是哪个对，而是不一致。** 同一份 Living Spec 应该产出相同的技术栈选择。这说明 Architect 在技术栈决策上**缺乏约束锚定**，是随机行为。

---

## 四、🔴 致命差异 3：Packager 信息断崖

### V1 Packager（健康）

```
8 WP × {outputs, ACs, constraints, requirements, retry_policy, tags}
31 AC | 32 outputs | 105 REQ | 57 constraints | 7 risks
Reviewer: PASS | AC quality: 81
```

### V3 Packager（病态）

```
8 WP × {outputs, requirements} ← 缺少 acceptance_tests, constraints
0 AC | 25 outputs | 20 REQ | 0 constraints | 0 risks
Reviewer: FAIL | AC quality: 68
```

### 断崖分析

| 字段 | V1 | V3 | 说明 |
|:---|:---|:---|:---|
| acceptance_tests | 31 条 | **0 条** | Specifier 写了 37 条 AC，Packager 全部丢弃 |
| constraints | 57 条 | **0 条** | 约束信息在 Packager 阶段完全蒸发 |
| risk_register | 7 条 | **0 条** | V3 识别零风险 |
| requires_human_approval | 有 | 无 | V3 缺少人工审批标记 |
| retry_policy | 有 | 无 | V3 缺少重试策略 |
| tags | 有 | 无 | V3 缺少标签分类 |

### 推测根因

V3 的 Packager 输出文件只有 13KB（V1 是 41KB），说明 Packager 可能因为输入信息不足（Architect 只有 12 REQ → Decomposer 和 Specifier 信息也不足）而无法生成完整的交付包。

---

## 五、🟡 模块设计差异

### 模块命名对比

| V1 模块 | V3 模块 | 功能对齐 |
|:---|:---|:---|
| COMP-001: PipelineCollector | COMP-02: EventProtocol | 部分对齐（V1 采集器 vs V3 协议定义） |
| COMP-002: DiagnosticsCollector | COMP-01: EventCollector | 对齐（都是采集） |
| COMP-003: PromptTracker | COMP-08: PromptTracker | ✅ 完全对齐 |
| COMP-004: safe_emit | — | V3 无独立 safe_emit 模块 |
| COMP-005: AnalysisEngine | COMP-04: AnalysisEngine | ✅ 完全对齐 |
| COMP-006: DiagnosticReporter | COMP-07: ReportGenerator | ✅ 对齐 |
| COMP-007: CLI Tool | COMP-07: ReportGenerator | 合并（V3 把 CLI 和报告合并） |
| COMP-008: FeishuPusher | COMP-07: ReportGenerator | 合并（V3 把飞书推送并入报告） |
| — | COMP-03: SQLiteStore | V3 独立存储模块 |
| — | COMP-05: ConvergenceDetector | V3 独立收敛检测 |
| — | COMP-06: ThresholdEngine | V3 独立阈值引擎 |

### 架构差异总结

| 维度 | V1 | V3 |
|:---|:---|:---|
| 架构风格 | **功能聚合型**（8 个功能组件） | **职责分离型**（8 个职责单元） |
| 数据采集 | 3 个 Collector（Pipeline + Diagnostics + Prompt） | 2 阶段采集（fire-and-forget + artifact） |
| 分析能力 | 1 个大 AnalysisEngine（含插件） | 3 个独立引擎（Analysis + Convergence + Threshold） |
| 输出层 | 3 个独立（Reporter + CLI + FeishuPusher） | 1 个合并 ReportGenerator |
| 存储层 | 内嵌在 safe_emit 基础设施中 | 独立 SQLiteStore 模块 |
| safe_emit | 独立模块（COMP-004） | 无独立模块（可能内嵌在 Collector 中） |

### 评价

V3 的模块拆分在**职责分离**上更清晰（ConvergenceDetector、ThresholdEngine 独立），但 V1 的**功能聚合**更贴近 Living Spec 描述的痛点（管线诊断、Prompt 追踪、报告输出）。

V3 把 CLI + 报告 + 飞书合并为一个 ReportGenerator，丢失了 V1 中三者独立演进的灵活性。

---

## 六、🟡 执行计划差异

### 依赖图

| 维度 | V1 | V3 |
|:---|:---|:---|
| Phase 数 | 5 | 5 |
| Phase 1 内容 | 存储层基础设施 | 事件协议 + 3 个独立引擎并行 |
| Phase 2 | 3 个 Collector 并行 | 事件采集器 |
| Phase 3 | 分析引擎 | 存储层 |
| Phase 4 | 报告 | 分析引擎（依赖前 4 个 WP） |
| Phase 5 | CLI + 飞书并行 | 报告生成器 |
| 关键路径 | 190min | 150min |
| 最大并行度 | Phase 2（3 WP 并行） | Phase 1（4 WP 并行） |

### V3 Phase 1 的激进并行

V3 在 Phase 1 就并行 4 个 WP（事件协议 + 收敛检测 + 阈值引擎 + Prompt 追踪），但 Reviewer 已指出问题：WP-005/006/007 依赖 WP-001 的事件类型定义，依赖边缺失。

V1 的串行起步（先做存储层基础设施）更稳健。

---

## 七、Reviewer 质量对比

| 维度 | V1 Reviewer | V3 Reviewer |
|:---|:---|:---|
| 判定 | PASS | FAIL |
| 问题数 | 5 | 8 |
| High severity | 0 | **4** |
| 核心关注 | AC 分阶段标注、信息黑洞 | AC 不可验证、依赖缺失、信息不足 |
| 建议质量 | 具体可操作 | 具体但需要大量返工 |

### V3 Reviewer 4 个 High Issue 根因追溯

| # | High Issue | 根因 |
|:---|:---|:---|
| 1 | WP-006 AC 全 L2 级空泛 | Specifier 信息不足（Architect 只有 12 REQ） |
| 2 | WP-004 L4/L5 验证缺失 | Architect 需求压缩导致 Specifier 无法展开 |
| 3 | WP-004 子组件调用 AC 无验证方法 | 同上 |
| 4 | WP-005/006/007 依赖声明缺失 | Decomposer 收到的架构信息不完整 |

**4 个 High Issue 全部可追溯到 Architect 的 REQ 坍塌。**

---

## 八、Living Spec 约束遵守对比

| 硬约束 | V1 | V3 |
|:---|:---|:---|
| Worker 零改动 | ✅ 外部观测 | ✅ 外部观测 |
| 不引入外部基础设施 | ✅ SQLite 嵌入式 | ✅ SQLite 嵌入式 |
| 确定性优先 | ✅ 三层漏斗（Phase 1-2 零 LLM） | ✅ 三层漏斗 |
| 渐进交付 | ✅ 五层分阶段 | ✅ 五层分阶段 |
| 事件采集不阻断管线 | ✅ safe_emit 独立模块 | ✅ fire-and-forget |
| < 30s 诊断 | ✅ CLI diagnose < 30s | ✅ 端到端 < 30s |
| 月成本 < $15 | ✅ Phase 4 ~$4.06/月 | ✅ 有成本估算 AC |

**两个版本都遵守了全部 7 个硬约束。** 差异不在约束遵守，而在信息传递的完整性。

---

## 九、Living Spec 痛点覆盖对比

| 痛点 | V1 覆盖 | V3 覆盖 |
|:---|:---|:---|
| 1. 管线挂了不知道哪里挂的 | ✅ PipelineCollector + CLI diagnose | ✅ EventCollector + AnalysisEngine |
| 2. Worker 反复试错不知道原因 | ✅ AnalysisEngine 重试分析 | ✅ ConvergenceDetector（独立模块） |
| 3. LLM 行为黑盒 | ✅ DiagnosticsCollector（tokens/cost） | ✅ EventCollector + SQLiteStore |
| 4. Prompt 效果无法追踪 | ✅ PromptTracker（双 hash） | ✅ PromptTracker（双 hash + 6 步规范化） |
| 5. 跨域语义丢失 | ✅ L4/L5 语义分析 | 🟡 L4/L5 提及但 AC 不完整 |
| 6. 修好的问题容易复发 | ✅ AnalysisEngine 回归检测 | 🟡 隐含在 ThresholdEngine 中 |
| 7. 上下文膨胀不可见 | ✅ DiagnosticsCollector context 追踪 | 🟡 无专门模块 |

V3 在痛点 2（重试模式检测）上做得更专（独立 ConvergenceDetector），但在痛点 5-7 上覆盖弱于 V1。

---

## 十、总结

### 一句话结论

> **V1 是"信息丰富的正确方向"，V3 是"信息贫乏的精致碎片"。**

### 三个核心发现

1. **REQ 坍塌是所有差异的根因**：122→12 的需求压缩导致下游每个阶段都在信息饥渴中工作。V3 的 4 个 High Issue 全部可追溯到此。

2. **技术栈随机性**：同一份 Living Spec 产出 Python 和 TypeScript 两个完全不同的技术栈，说明 Architect 在技术选型上缺乏锚定。这不是 V1 或 V3 谁对的问题，而是**两者都不可靠**的信号。

3. **Packager 信息断崖**：V3 Packager 丢失了 Specifier 阶段写的 37 条 AC、57 条约束、7 条风险，这不是 Packager 的 bug，是上游信息不足导致的级联失败。

### 对 Solution Pro 去重效果的判断

V1（122 REQ 全量）→ V3（108 REQ 部分去重）的 Solution Pro 改进本身是合理的。但 **Ship Pro Architect 的需求压缩行为**是意外变量——108 REQ 被压缩为 12 条，这才是 V3 质量下降的直接原因。

如果 Ship Pro Architect 能忠实传递 108 条 REQ（像 V1 传递 122 条那样），V3 的质量可能接近甚至超过 V1（因为去重后的 108 条 REQ 质量更高）。

### 行动建议

1. **Ship Pro Architect Prompt 加固**：增加"REQ 忠实传递"约束，禁止将需求压缩为高层摘要
2. **Packager Schema 校验**：增加 `acceptance_tests` 和 `constraints` 字段的非空检查
3. **技术栈锚定**：在 Living Spec 或 Ship Pro 控制文件中明确技术栈（Python 或 TypeScript），不让 Architect 自行决定
4. **V3 不应作为基线**：V3 的 Architect 输出需要重跑（加固 REQ 传递后），当前 V3 Ship Pro 不应进入生产

---

*报告生成时间：2026-06-21 14:15*
*对比方法：Ship Pro Quality Guide 三层质量架构*
*数据来源：V1 `blackboard/blackboard/` + V3 `ship/blackboard/`*


---

### 1.2 REQ_FLOW_ANALYSIS.md — REQ 全链路流转分析

# V3 Solution Pro → Ship Pro REQ 流转链路分析

> **项目**: DeepFlow 开发者可观测性系统
> **追踪对象**: 108 条 REQ-ID 在 V3 全链路中的流转
> **核心问题**: Solution Pro 内部 108 REQ 全程保持，到 Ship Pro 只剩 12 条，信息在哪里丢的？

---

## 一、REQ 全链路流转图

```
Living Spec (observability_requirement.md, 164行)
    │
    ▼
┌─ Solution Pro 10阶段管线 ──────────────────────────────────────┐
│                                                                  │
│  Stage 1: Planning                                               │
│  ┌──────────────────────────────────┐                            │
│  │ planning.json (16KB)             │                            │
│  │ REQ-IDs: 108 (REQ-001~108)       │ ← 从 Living Spec 提取     │
│  │ covered_req_ids: 108             │                            │
│  └──────────────────────────────────┘                            │
│    │                                                             │
│  Stage 2: 三路 Reviewer（并行）                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ reviewer_technical (19KB) │ REQ-IDs: 57  │ 技术维度深度  │    │
│  │ reviewer_business  (30KB) │ REQ-IDs: 108 │ 业务全覆盖    │    │
│  │ reviewer_risk      (22KB) │ REQ-IDs: 29  │ 风险子集      │    │
│  └──────────────────────────────────────────────────────────┘    │
│    │                                                             │
│  Stage 3: 三路 Research Expert（并行）                            │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ research_expert_1 (23KB) │ REQ-IDs: 23  │ 存储/协议方向  │    │
│  │ research_expert_2 (20KB) │ REQ-IDs: 16  │ 分析/检测方向  │    │
│  │ research_expert_3 (27KB) │ REQ-IDs: 15  │ 报告/推送方向  │    │
│  └──────────────────────────────────────────────────────────┘    │
│    │                                                             │
│  Stage 4: Consolidator                                           │
│  ┌──────────────────────────────────┐                            │
│  │ consolidator.json (37KB)         │                            │
│  │ REQ-IDs: 107 (REQ-001~108)       │ ← 统一方案，几乎全覆盖  │
│  └──────────────────────────────────┘                            │
│    │                                                             │
│  Stage 5: Audit                                                  │
│  ┌──────────────────────────────────┐                            │
│  │ audit.json (21KB)                │                            │
│  │ REQ-IDs: 108                     │ ← 全覆盖检查            │
│  └──────────────────────────────────┘                            │
│    │                                                             │
│  Stage 6: Fix                                                    │
│  ┌──────────────────────────────────┐                            │
│  │ fix.json (40KB)                  │                            │
│  │ REQ-IDs: 107                     │                           │
│  └──────────────────────────────────┘                            │
│    │                                                             │
│  Stage 7: Fixer Expert                                           │
│  ┌──────────────────────────────────┐                            │
│  │ fixer_expert.json (30KB)         │                            │
│  │ REQ-IDs: 107                     │                           │
│  └──────────────────────────────────┘                            │
│    │                                                             │
│  Stage 8: Harness Final                                          │
│  ┌──────────────────────────────────┐                            │
│  │ harness_final.json (15KB)        │                            │
│  │ REQ-IDs: 108                     │ ← 质量门禁，全覆盖      │
│  └──────────────────────────────────┘                            │
│    │                                                             │
│  Stage 9: Summarizer ← ⚠️ 断裂点                                 │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ summarizer.json (28KB)                                   │    │
│  │ REQ-IDs: 108 (in covered_req_ids + requirement_evidence) │    │
│  │ requirement_evidence: 41 entries                         │    │
│  │                                                          │    │
│  │ ❌ 但 final_solution 部分: 0 REQ-IDs                    │    │
│  │ ❌ 但 detailed_solution 部分: 0 REQ-IDs                 │    │
│  └──────────────────────────────────────────────────────────┘    │
│    │                                                             │
│  Stage 10: 写 final_result.json ← 🔴 断裂确认                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ final_result.json (5KB) ← Summarizer 写的交接文件        │    │
│  │                                                          │    │
│  │ ❌ REQ-IDs: 0 (零！)                                    │    │
│  │ ❌ covered_req_ids: 不存在                               │    │
│  │ ❌ requirement_evidence: 空                              │    │
│  │                                                          │    │
│  │ 只包含:                                                   │    │
│  │  - pipeline_summary（声明 108/108，但不传递数据）        │    │
│  │  - final_solution.executive_summary（高层摘要）          │    │
│  │  - final_solution.architecture_components（8 组件一句话）│    │
│  │  - final_solution.implementation_phases（4 阶段）        │    │
│  │  - final_solution.success_criteria（5 个指标）           │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Ship Pro 5阶段管线 ────────────────────────────────────────────┐
│                                                                  │
│  Stage 1: Architect                                              │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ architect_output.json (17KB)                              │    │
│  │                                                           │    │
│  │ 输入: final_result.json (5KB, 0 REQ)                     │    │
│  │ 输出: 自行归纳为 12 条高层需求                            │    │
│  │                                                           │    │
│  │ 🔴 Architect 在信息荒漠中工作:                            │    │
│  │    - 没有 108 条 REQ 的完整列表                           │    │
│  │    - 没有 requirement_evidence                            │    │
│  │    - 只能从 executive_summary 和 components 推断          │    │
│  │    - 结果: 122 REQ → 12 REQ (-90%)                       │    │
│  └──────────────────────────────────────────────────────────┘    │
│    │                                                             │
│    ↓ (后续 4 阶段在 12 REQ 基础上工作，信息已不可恢复)          │
│                                                                  │
│  Decomposer: 8 WP, 每 WP 1-3 REQ → 总 20 REQ 映射             │
│  Specifier:  37 AC, 但约束只有 37 (V1 有 57)                   │
│  Reviewer:   FAIL (4 个 high issue)                             │
│  Packager:   0 AC, 0 约束, 0 风险                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、断裂点精确定位

### 断裂不在 Solution Pro 内部

Solution Pro 的 10 个阶段全程保持 107-108 条 REQ-ID。每个阶段的 `covered_req_ids` 和文件内容中的 REQ-引用都完整。**Solution Pro 管线本身没有 REQ 丢失问题。**

### 断裂在两个位置

| # | 断裂位置 | 断裂类型 | 影响 |
|:---|:---|:---|:---|
| **1** | Summarizer → final_result.json | **信息压缩丢失** | 108 REQ → 0 REQ |
| **2** | final_result.json → Ship Pro Architect | **信息荒漠** | 0 REQ → 自造 12 REQ |

### 断裂 1 详细分析：Summarizer 写 final_result.json

**Summarizer 输出 vs final_result.json 对比**:

| 字段 | summarizer.json (28KB) | final_result.json (5KB) |
|:---|:---|:---|
| covered_req_ids | ✅ 108 条 | ❌ 不存在 |
| requirement_evidence | ✅ 41 条 | ❌ 空 `{}` |
| final_solution.executive_summary | ✅ 完整 | ✅ 保留（略有不同） |
| final_solution.detailed_solution | ✅ 14KB 完整方案 | ❌ 替换为 4 个小组件 |
| architecture_components | ✅ 8 组件详细描述 | ✅ 8 组件（一句话 summary） |
| implementation_phases | ✅ 含 deliverables | ✅ 简化（只有 scope+cost） |
| risk_management | ✅ 完整 | ❌ 不存在 |
| recommendations | ✅ 完整 | ❌ 不存在 |

**根因**: Summarizer prompt 的 **输出结构契约** 聚焦于 4 件事：
1. `final_solution` 顶层 wrapper
2. `executive_summary` 字段名规范
3. `components` 字段名规范
4. component 的 `id/name/summary` 三字段

**Prompt 没有说的**:
- ❌ "必须将 `covered_req_ids` 传播到 `final_result.json`"
- ❌ "必须将 `requirement_evidence` 传播到 `final_result.json`"
- ❌ "`final_result.json` 必须包含 ≥N 条 REQ-ID 引用"
- ❌ "不能将 `detailed_solution` 替换为精简摘要"

Summarizer 作为一个 LLM sub-agent，忠实执行了 prompt 的结构要求，但**没有传播 prompt 没要求的字段**。

### 断裂 2 详细分析：Architect 的信息荒漠

V3 Ship Pro Architect 收到的输入（`final_result.json`）只有 5KB：
- 一段 executive_summary（问题描述 + 方案概述 + 8 组件一句话 + 4 阶段 + 5 指标）
- 声明 "108/108 REQ-IDs 覆盖" 但**不传递具体 REQ 数据**

Architect 面对的选择：
1. 从 executive_summary 的 8 个组件 + 7 个痛点 → 自行归纳为 12 条高层需求 ← **V3 做了这个**
2. 拒绝工作，要求更多输入 ← 没有这个机制
3. 从 `stages/summarizer.json` (28KB) 读取完整数据 ← Ship Pro 不知道这个文件存在

Architect 选了 #1，这是合理但灾难性的选择。

---

## 三、V1 为什么没断？

V1 的 Ship Pro `final_result.json` 是 **61KB**，包含 122 REQ-IDs 和 28 条 requirement_evidence。

**关键区别**: V1 运行于 2026-06-20 22:39，可能使用了**旧版 Summarizer prompt**或旧版 Solution Pro 管线。V1 的 `blackboard/blackboard/final_result.json` 实际上就是 Ship Pro 的 Packager 输出（包含完整的 architecture_decisions, event_protocol, components, data_model, interfaces 等），不是 Solution Pro 的 final_result.json。

**推论**: V1 可能是走了旧链路（Solution Pro → Frozen Blueprint → Ship Pro），或者 V1 的 Summarizer 在写 final_result.json 时传播了完整数据。**V1 的数据保留可能是偶然的，不是设计保证。**

---

## 四、requirements_traceability_matrix.json — 被遗忘的宝藏

V3 的 `requirements_traceability_matrix.json`（25KB）包含完整的 108 条 REQ，每条都有：
- req_id
- description
- source（来自 Living Spec 哪个部分）
- coverage_status
- evidence（哪些阶段覆盖了这条 REQ）

**但这个文件不在 Ship Pro 的消费路径上。** Ship Pro 只读 `final_result.json`。

---

## 五、根因总结

```
┌───────────────────────────────────────────────────────────────┐
│                     根因链（3 级）                              │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  L1 (直接原因):                                                │
│  Summarizer 写 final_result.json 时没有传播 covered_req_ids   │
│  和 requirement_evidence                                       │
│                                                               │
│  L2 (设计原因):                                                │
│  Summarizer prompt v5.4.0 的输出契约只规定了结构字段名         │
│  （final_solution wrapper, executive_summary, components）    │
│  没有规定"必须传播哪些数据字段到 final_result.json"            │
│                                                               │
│  L3 (系统原因):                                                │
│  2026-06-19 退役 Frozen Blueprint 后，final_result.json       │
│  成为 Solution Pro → Ship Pro 的唯一交接文件。               │
│  但交接文件的 Schema（final_result_v3.schema.json）           │
│  用 oneOf 支持 4 种格式变体，covered_req_ids 是 optional     │
│  → 没有强制校验，LLM 可以合法地省略                          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## 六、修复建议（按 ROI 排序）

### 修复 1: Summarizer Prompt 加固（ROI 最高，改动最小）

在 `prompts/summarizer.md` 的输出结构契约中增加：

```markdown
## ⚠️ 数据传播铁律（新增）

final_result.json 必须包含以下字段（不可省略）：
1. `covered_req_ids`: 完整的 REQ-ID 列表（从 summarizer.json 传播）
2. `requirement_evidence`: 完整的需求证据映射（从 summarizer.json 传播）
3. `final_solution.detailed_solution`: 完整方案详情（不是精简摘要）

禁止将 final_result.json 写成精简版。下游 Ship Pro 需要完整的
需求列表来生成准确的架构设计。
```

### 修复 2: final_result_v3.schema.json 加固

将 `covered_req_ids` 从 optional 改为 required（至少 Format A/B/C 必须有）：
```json
{
  "required": ["status", "final_solution", "covered_req_ids"],
  "properties": {
    "covered_req_ids": {
      "type": "array",
      "minItems": 1,
      "description": "必须非空，包含所有 REQ-ID"
    }
  }
}
```

### 修复 3: Ship Pro Architect 降级策略

当 Architect 收到的 final_result.json 中 `covered_req_ids` 为空或缺失时：
- 尝试读取同目录下的 `stages/summarizer.json`（28KB，有完整 REQ）
- 或者读取 `requirements_traceability_matrix.json`（25KB，有完整 REQ）
- 在 `_meta.data_sufficiency` 中标记 `"requirements": "degraded"`

### 修复 4: 交接文件统一化（长期）

将 `final_result.json` 和 `stages/summarizer.json` 合并为一个文件，消除信息冗余和信息丢失的风险。

---

## 七、与 V1 对比的结论

| 维度 | V1 | V3 | 评价 |
|:---|:---|:---|:---|
| Solution Pro 内部 REQ | 122（全程保持） | 108（全程保持） | ✅ 两者都健康 |
| 交接文件 REQ | 122（61KB） | **0**（5KB） | 🔴 V3 断裂 |
| Ship Pro Architect REQ | 122（忠实传递） | 12（自造摘要） | 🔴 V3 级联失败 |
| 下游影响 | 31 AC, 57 约束, 7 风险 | 0 AC, 0 约束, 0 风险 | 🔴 V3 Packager 空壳 |

**V3 的 Solution Pro 去重（122→108）本身是正确的。** 问题不在去重，而在交接文件的生成逻辑。

---

*分析时间: 2026-06-21 14:25*
*数据来源: V3 stages/ 目录 13 个 JSON 文件 + final_result.json + ship/blackboard/ 目录*


---

### 1.3 blackboard_system_redesign.md — Blackboard 重构方案

# DeepFlow Blackboard 系统重构方案

> **版本**: v1.0.0-draft
> **日期**: 2026-06-21
> **状态**: 待专家评审
> **作者**: 小满 🦞

---

## 一、现状诊断

### 1.1 当前目录结构（以 DeepFlow 可观测性项目为例）

```
.deepflow/blackboard/
├── DeepFlow_开发者可观测性系统架构_architecture_1a43ee1f/    ← Solution Pro 项目目录
│   ├── .completed                                           ← 状态文件（混在根目录）
│   ├── .cron_run_count                                      ← 状态文件
│   ├── .delivery_config.json                                ← 状态文件
│   ├── .notified_stages.json                                ← 状态文件
│   ├── .stage_progress.json                                 ← 状态文件
│   ├── control_contract.json                                ← 控制文件
│   ├── execution_plan.json                                  ← 控制文件
│   ├── final_result.json                                    ← ⚠️ 交付文件（5KB，0 REQ）
│   ├── final_solution.md                                    ← 交付文件（即将废弃）
│   ├── requirements_traceability_matrix.json                ← 交付文件
│   ├── tasks.json                                           ← 控制文件
│   ├── COMPARISON_REPORT.md                                 ← 分析文件（非管线产物）
│   ├── data/                                                ← 输入数据
│   │   ├── collection.json
│   │   ├── frozen_spec.json
│   │   └── structured_requirements.json
│   ├── stages/                                              ← 10 个阶段输出
│   │   ├── planning.json
│   │   ├── reviewer_technical.json
│   │   ├── ...
│   │   └── summarizer.json                                  ← ⚠️ 即将废弃
│   ├── .prompts/                                            ← orchestrator prompt 快照
│   └── ship/                                                ← Ship Pro 输出（嵌套！）
│       ├── pipeline_config.json
│       ├── pipeline_status.json
│       ├── .cron_job_id                                     ← 状态文件（又一层）
│       ├── .cron_run_count
│       ├── ...
│       ├── review_*.md                                      ← 评审文件
│       └── blackboard/                                      ← ⚠️⚠️ 套娃！
│           ├── .completed
│           ├── .cron_job_id
│           ├── architect_output.json
│           ├── decomposer_output.json
│           ├── specifier_output.json
│           ├── reviewer_output.json
│           ├── packager_output.json
│           ├── final_result.json
│           └── summary.md
│
├── blackboard/                                              ← ⚠️ V1 Ship Pro 独立运行的遗留
│   ├── architect_output.json
│   ├── final_result.json
│   └── ...
│
└── archive/                                                 ← 归档（刚清理完）
```

### 1.2 五个核心问题

| # | 问题 | 严重度 | 影响 |
|:---|:---|:---:|:---|
| **P1** | **同 topic 重跑互相覆盖** | 🔴 | Solution Pro 目录名 = `{topic}_{domain}_{hash6}`，hash 由输入决定。同输入 → 同目录 → stages/ 被覆盖。今天 V1 的 Solution Pro stages 就是这样丢的 |
| **P2** | **Ship Pro 嵌套 blackboard/ 子目录** | 🔴 | `run_pipeline.py` 硬编码 `bb_dir = output_p / "blackboard"`。当 output_dir 是 Solution Pro 的 `ship/` 时，产生 `ship/blackboard/` 套娃 |
| **P3** | **状态文件散落根目录** | 🟡 | `.completed`、`.cron_*`、`.stage_progress.json` 等 8+ 个状态文件混在项目根目录，跟交付文件 `final_result.json` 不分彼此 |
| **P4** | **三域命名规则不统一** | 🟡 | Spec Pro: `{prefix}_spec_{uuid16}`；Solution Pro: `{topic}_{architecture}_{hash6}`；Research Pro: `research_pro_{hash8}_{timestamp}`；Ship Pro: 无独立目录 |
| **P5** | **无版本/运行隔离** | 🔴 | 没有"第 N 次运行"的概念。同一个项目跑 3 次 Solution Pro，只有最后一次的数据。无法做 A/B 对比 |

### 1.3 三个域的 session_id 生成逻辑

| 域 | 生成方式 | 唯一性保证 | 可重跑？ |
|:---|:---|:---|:---|
| **Spec Pro** | `{prefix}_spec_{uuid16}` | UUID 保证 | ✅ 每次运行新目录 |
| **Solution Pro** | `{topic截断}_{domain}_{hash6}` | hash 由输入决定 | ❌ 同输入同目录 |
| **Research Pro** | `research_pro_{hash8}_{timestamp}` | timestamp 保证 | ✅ 每次运行新目录 |
| **Ship Pro** | 无独立目录，嵌套在 Solution Pro 的 `ship/` 下 | 依赖父目录 | ❌ 同项目覆盖 |

**核心矛盾**：Solution Pro 和 Ship Pro 用**确定性 hash**做目录名（同输入 → 同目录），Spec Pro 和 Research Pro 用 **UUID/timestamp**（每次新目录）。前者保证幂等但无法多版本，后者保证隔离但可能产生垃圾。

---

## 二、设计目标

基于 DeepFlow 未来作为 **Loop Engine** 的定位，Blackboard 系统需要满足：

### 2.1 核心需求

| # | 需求 | 理由 |
|:---|:---|:---|
| **R1** | **运行隔离** | 同一项目可以跑 N 次，每次互不影响。支持 A/B 对比（今天的 V1 vs V3 需求） |
| **R2** | **跨域数据流清晰** | Spec Pro → Solution Pro → Ship Pro 的数据传递路径明确，不依赖隐式约定 |
| **R3** | **状态与产出分离** | 控制文件（`.completed`、`.cron_*`）和交付文件（`final_result.json`、stages/）分开放 |
| **R4** | **统一命名规范** | 三个域 + 未来的 Loop Engine 共用一套目录命名规则 |
| **R5** | **向后兼容** | 现有代码（run_pipeline.py、completion_handler.py 等）改动最小化 |

### 2.2 面向未来的扩展

- **Loop Engine**: 同一项目多轮迭代（Spec → Solution → Ship → 运行 → 反馈 → 修改 Spec → 重新跑），每轮是一个独立的 "run"
- **Dashboard**: 前端需要按项目分组、按运行对比
- **清理机制**: 过期运行自动归档，不手动清理

---

## 三、方案设计

### 3.1 新目录结构

```
.deepflow/blackboard/
├── projects/                                    ← 🆕 项目层（按 topic 分组）
│   └── deepflow-observability/                  ← 项目 slug（人类可读）
│       ├── project.json                         ← 项目元数据
│       ├── runs/                                ← 🆕 运行层（每次运行一个目录）
│       │   ├── 20260620_223900/                 ← Run 1（V1，时间戳命名）
│       │   │   ├── run.json                     ← 运行元数据（domain, status, input_hash）
│       │   │   ├── input/                       ← 输入数据
│       │   │   │   ├── living_spec.json         ← Spec Pro 输出 / Solution Pro 输入
│       │   │   │   └── frozen_spec.json
│       │   │   ├── stages/                      ← 阶段输出
│       │   │   │   ├── planning.json
│       │   │   │   ├── consolidator.json
│       │   │   │   └── ...
│       │   │   ├── output/                      ← 🆕 交付文件（状态与产出分离）
│       │   │   │   ├── final_result.json
│       │   │   │   └── requirements_traceability_matrix.json
│       │   │   ├── state/                       ← 🆕 状态文件（集中管理）
│       │   │   │   ├── .completed
│       │   │   │   ├── .cron_job_id
│       │   │   │   ├── .stage_progress.json
│       │   │   │   └── ...
│       │   │   └── ship/                        ← Ship Pro 输出（同级，不嵌套 blackboard/）
│       │   │       ├── run.json
│       │   │       ├── stages/                  ← Ship Pro 阶段输出
│       │   │       │   ├── architect_output.json
│       │   │       │   └── ...
│       │   │       ├── output/
│       │   │       │   └── ship_package.json
│       │   │       └── state/
│       │   │           └── .completed
│       │   │
│       │   ├── 20260621_093600/                 ← Run 2（V2，去重实验）
│       │   │   └── ...
│       │   │
│       │   └── 20260621_104400/                 ← Run 3（V3，部分去重 + Living Spec）
│       │       └── ...
│       │
│       └── runs.json                            ← 运行索引（所有 run 的摘要列表）
│
├── archive/                                     ← 归档（已有）
└── _legacy/                                     ← 🆕 旧数据迁移目录
    └── DeepFlow_开发者可观测性系统架构_architecture_1a43ee1f/
        └── ... (原样保留)
```

### 3.2 关键设计决策

#### D1: 项目 slug 怎么来？

**方案 A**: 从 topic 自动生成 slug（`DeepFlow 开发者可观测性系统架构` → `deepflow-observability`）
- ✅ 人类可读
- ❌ 需要 slug 生成逻辑，可能冲突

**方案 B**: 用 topic 的 hash 前 8 位（`DeepFlow...` → `1a43ee1f`）
- ✅ 确定性，无冲突
- ❌ 不直观

**方案 C**: 用户首次运行时指定，后续自动继承
- ✅ 人类可读 + 无冲突
- ❌ 需要交互

**推荐**: **方案 A + 冲突时加 hash 后缀**。大多数情况人类可读，极端情况自动去重。

#### D2: Run 目录用什么命名？

**方案**: `{YYYYMMDD_HHMMSS}`（时间戳）
- ✅ 天然有序，每次运行唯一
- ✅ 不需要额外 ID 生成逻辑
- ✅ 跟 cron watcher 的 `run_start_at` 天然对齐
- ❌ 长，但作为目录名可以接受

#### D3: 状态文件怎么集中？

**方案**: 所有 `.xxx` 状态文件写入 `state/` 子目录。
- `completion_handler.py` 检查 `.completed` → 改为 `state/.completed`
- `pipeline_watcher.py` 读写 `.stage_progress.json` → 改为 `state/.stage_progress.json`
- 所有 `.cron_*`、`.watcher_*`、`.pipeline_watcher.lock` → `state/`

**改动量**: ~10 个文件的路径字符串替换。

#### D4: Ship Pro 怎么不再套娃？

**当前**: `run_pipeline.py prepare()` 中 `bb_dir = output_p / "blackboard"`
**修改**: `bb_dir = output_p`（直接用 output_dir 作为 blackboard）

Ship Pro 的 output_dir 改为：
```
projects/{slug}/runs/{timestamp}/ship/
```

不再创建 `ship/blackboard/`，Ship Pro 阶段文件直接写入 `ship/stages/`。

#### D5: 跨域数据流怎么传递？

```
Spec Pro
  output → projects/{slug}/runs/{ts}/input/living_spec.json

Solution Pro
  input  ← projects/{slug}/runs/{ts}/input/living_spec.json
  output → projects/{slug}/runs/{ts}/output/final_result.json

Ship Pro
  input  ← projects/{slug}/runs/{ts}/output/final_result.json  (Solution Pro 的交付)
  output → projects/{slug}/runs/{ts}/ship/output/ship_package.json
```

每个域的输入从**上游的 output/** 读取，输出写入**自己的 output/**。数据流方向清晰，不需要隐式约定。

#### D6: 向后兼容策略

| 组件 | 改动 | 兼容层 |
|:---|:---|:---|
| `blackboard.py` STAGE_PATH_REGISTRY | 路径前缀加 `output/` 或 `stages/` | 提供 `get_stage_path()` 函数，内部判断新旧格式 |
| `completion_handler.py` | `.completed` 路径改为 `state/.completed` | 先查新路径，降级查旧路径 |
| `pipeline_watcher.py` | 状态文件路径改为 `state/` | 同上 |
| `run_pipeline.py` | 删除 `bb_dir = output_p / "blackboard"` | 直接用 `output_p` |
| `status_v2.py` | 查找路径改为 `output/final_result.json` | 先查新路径，降级查旧路径 |

**原则**: 新代码走新路径，旧数据走降级路径。不迁移历史数据。

### 3.3 project.json 和 run.json 设计

```json
// project.json
{
  "slug": "deepflow-observability",
  "topic": "DeepFlow 开发者可观测性系统架构设计",
  "created_at": "2026-06-20T21:00:00+08:00",
  "domains": ["spec_pro", "solution_pro", "ship_pro"],
  "runs_count": 3
}

// run.json (每次运行)
{
  "run_id": "20260621_104400",
  "domain": "solution_pro",
  "topic": "DeepFlow 开发者可观测性系统架构设计",
  "input_hash": "a1b2c3d4",
  "status": "completed",
  "started_at": "2026-06-21T10:44:00+08:00",
  "completed_at": "2026-06-21T11:11:00+08:00",
  "input_source": "projects/deepflow-observability/runs/20260621_104400/input/living_spec.json",
  "req_count": 108,
  "covered_req_count": 108,
  "quality_score": 0.89
}

// runs.json (运行索引，项目级)
{
  "runs": [
    {
      "run_id": "20260620_223900",
      "domain": "solution_pro",
      "status": "completed",
      "req_count": 122,
      "quality_score": null,
      "note": "V1: 全量 Living Spec"
    },
    {
      "run_id": "20260621_093600",
      "domain": "solution_pro",
      "status": "completed",
      "req_count": 8,
      "quality_score": null,
      "note": "V2: 过度去重"
    },
    {
      "run_id": "20260621_104400",
      "domain": "solution_pro",
      "status": "completed",
      "req_count": 108,
      "quality_score": 0.89,
      "note": "V3: 部分去重 + Living Spec"
    }
  ]
}
```

### 3.4 与 Loop Engine 的对齐

未来 DeepFlow Loop 的一次完整迭代：

```
Loop Iteration #1:
  projects/{slug}/runs/{ts1}/
    ├── spec/          ← Spec Pro Run
    ├── solution/      ← Solution Pro Run（读 spec/ 的输出）
    ├── ship/          ← Ship Pro Run（读 solution/ 的输出）
    └── feedback/      ← 🆕 运行反馈（用户评审、测试结果）

Loop Iteration #2:
  projects/{slug}/runs/{ts2}/
    ├── spec/          ← 基于 feedback 修改的 Spec
    ├── solution/      ← 重新跑 Solution Pro
    ├── ship/          ← 重新跑 Ship Pro
    └── feedback/
```

每次 Loop 迭代是一个 run，包含完整的 Spec→Solution→Ship→Feedback 链路。runs.json 记录所有迭代的历史，支持跨迭代的 A/B 对比。

---

## 四、实施计划

### Phase 1: 基础设施（不影响现有功能）

| # | 任务 | 改动文件 | 风险 |
|:---|:---|:---|:---|
| 1.1 | 创建 `projects/` 目录结构 | 无代码改动 | 零 |
| 1.2 | 新增 `blackboard_manager.py`（项目/运行管理 API） | 新文件 | 零 |
| 1.3 | 新增 `path_resolver.py`（新旧路径兼容层） | 新文件 | 零 |

### Phase 2: 核心迁移（改动 5 个文件）

| # | 任务 | 改动文件 |
|:---|:---|:---|
| 2.1 | Solution Pro session_id 改为 `{slug}/runs/{timestamp}` | `start_solution_pro.py` |
| 2.2 | Ship Pro 删除 `bb_dir = output_p / "blackboard"` | `run_pipeline.py` |
| 2.3 | 状态文件路径改为 `state/` 子目录 | `completion_handler.py`、`pipeline_watcher.py` |
| 2.4 | STAGE_PATH_REGISTRY 适配新结构 | `blackboard.py` |
| 2.5 | 前端 API 适配新路径 | `status_v2.py` |

### Phase 3: 增强功能

| # | 任务 |
|:---|:---|
| 3.1 | `runs.json` 自动更新（每次运行完成写入摘要） |
| 3.2 | Dashboard 按项目分组 + 按运行对比 |
| 3.3 | 过期运行自动归档（>30 天的 run → archive/） |
| 3.4 | 旧数据迁移脚本（`_legacy/` → `projects/`） |

---

## 五、风险与缓解

| 风险 | 缓解 |
|:---|:---|
| 改动 `run_pipeline.py` 影响 Ship Pro 所有运行 | 兼容层：新路径不存在时降级到旧路径 |
| 旧项目的 cron watcher 找不到状态文件 | completion_handler 先查新路径再查旧路径 |
| slug 生成冲突 | 冲突时自动加 hash 后缀 |
| 前端 status_v2 找不到历史数据 | 前端同时搜索 `projects/` 和 `_legacy/` |

---

## 六、开放问题（待专家评审）

1. **slug 生成策略**：自动 slug vs 用户指定 vs hash？推荐自动 + 冲突加后缀，是否有更好的方案？
2. **run 目录是否要分 domain 子目录**：当前方案是 `runs/{ts}/solution/` + `runs/{ts}/ship/`，还是 `runs/{ts}/`（Solution Pro）+ `runs/{ts}/ship/`（Ship Pro 嵌套）？
3. **runs.json 由谁维护**：orchestrator 写？completion_handler 写？还是独立的 registry 服务？
4. **旧数据迁移**：是否值得写迁移脚本把 `_legacy/` 数据搬到 `projects/`？还是直接保留原样？
5. **`input/` vs `data/`**：当前 Solution Pro 用 `data/` 放输入，新方案改为 `input/` 更语义化，但需要改 `data/collection.json` 等引用。

---

*本文档待专家评审后进入实施阶段。*


---

### 1.4 blackboard_review_context.md — 评审上下文

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


---

### 1.5 review_architect.md — 架构师评审

# Blackboard 重构方案评审 — 系统架构师视角

> **评审人**: 系统架构师（架构合理性、扩展性、实施风险）
> **评审日期**: 2026-06-21

---

## 总体判断

**方案核心设计合理，建议按此实施。** 理由：

1. `projects/{slug}/runs/{ts}/` 三层结构精准解决了覆盖问题（P1、P5）和套娃问题（P2）
2. 域分离（spec/solution/ship）让数据流从"隐式约定"变成"显式结构"
3. Research Pro 独立是正确的——没有数据流的域不应该强行关联
4. 不拆 input/output/state 是对的，符合忠礼"够用就行"的价值观

但有几个需要澄清的点，否则实施时会踩坑。

---

## 详细评审

### 1. slug 生成策略需要更明确

**当前方案**：从 topic 自动生成，冲突时加 hash 后缀。

**问题**：
- 如果两个项目 topic 相似（"AI 客服系统" vs "AI 智能客服系统"），slug 可能都是 `ai-kefu`，需要加后缀区分
- slug 一旦生成，后续能否修改？如果能改，路径怎么办？
- slug 的字符集限制是什么？中文 slug 会导致路径编码问题吗？

**建议**：
```
slug = slugify(topic[:30]) + "-" + hash8

示例：
- "DeepFlow 开发者可观测性系统" → "deepflow-observability-a1b2c3d4"
- "跨境 AI 算力中转站" → "cross-border-ai-compute-e5f6g7h8"
```

这样既保持可读性，又天然避免冲突，不需要"冲突检测+加后缀"的额外逻辑。

### 2. 跨域路径引用需要统一规范

**当前问题**：Solution Pro 需要读 `spec/living_spec.json`，Ship Pro 需要读 `solution/final_result.json`。这些路径是相对的还是绝对的？

**建议**：统一用**相对于 run 根目录的路径**。

```
run 根目录 = /blackboard/projects/{slug}/runs/{ts}/

Solution Pro 读 Spec：
  relative: ../spec/living_spec.json
  absolute: /blackboard/projects/{slug}/runs/{ts}/spec/living_spec.json

Ship Pro 读 Solution：
  relative: ../solution/final_result.json
  absolute: /blackboard/projects/{slug}/runs/{ts}/solution/final_result.json
```

**为什么用相对路径**：
- LLM sub-agent 的 working directory 通常是 run 根目录
- 相对路径更短，拼接出错概率更低
- 便于未来迁移（整个 projects/ 目录移动，相对路径不变）

### 3. 路径深度增加的影响需要验证

**当前**：`stages/planning.json`（2 层）
**新方案**：`solution/stages/planning.json`（3 层）

**风险**：LLM sub-agent 拼接路径时，多一层意味着多一次出错机会。

**建议**：
1. 在 `blackboard.py` 中提供 helper 函数：
   ```python
   def get_stage_path(run_dir: str, domain: str, stage: str) -> str:
       return os.path.join(run_dir, domain, "stages", f"{stage}.json")
   ```
2. 先在一个新项目上试点，观察 LLM sub-agent 是否能正确处理新路径
3. 如果 LLM 频繁出错，可以考虑在 run 根目录放一个 `paths.json`，列出所有关键路径

### 4. 旧数据处理策略

**当前方案**：不迁移，保留 `_legacy/` 原样。

**问题**：
- 旧项目还能被读取吗？如果能，路径解析逻辑需要兼容
- 如果用户想对比新旧项目的数据，怎么办？

**建议**：
- 写一个简单的迁移脚本（50 行代码），把现有项目移到 `_legacy/`
- 新代码只认 `projects/{slug}/runs/{ts}/` 结构
- 旧数据保留但不再更新，作为历史参考

### 5. runs.json 的维护策略

**当前方案**：未明确由谁维护 `runs.json`。

**建议**：由 `completion_handler.py` 在 run 完成时写入。

```python
def update_runs_index(project_dir: str, run_id: str, status: str):
    index_path = os.path.join(project_dir, "index.json")
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {"runs": []}
    
    index["runs"].append({
        "run_id": run_id,
        "status": status,
        "completed_at": datetime.now().isoformat(),
        "domains": ["spec", "solution", "ship"]
    })
    
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
```

这样 `index.json` 是自动维护的，不需要用户手动更新。

---

## 盲点检查

### 我发现了什么方案没提到的问题？

**1. 并发写入风险**

如果用户同时跑两个 Solution Pro（比如开了两个终端），两个 run 的 `spec/living_spec.json` 会不会冲突？

**答案**：不会，因为每个 run 有自己的 `spec/` 目录。但需要确保 `project.json` 和 `index.json` 的写入是原子操作（用 `tempfile` + `rename`）。

**2. 磁盘空间管理**

每次 run 都会生成完整的 stages/ 数据。如果用户频繁重跑（比如调试阶段一天跑 10 次），磁盘空间会快速增长。

**建议**：加一个简单的清理策略：
```bash
# 保留最近 10 个 run，删除更早的
find /blackboard/projects/*/runs/ -maxdepth 1 -type d -mtime +7 | xargs rm -rf
```

**3. 调试友好性**

当 LLM sub-agent 出错时，用户需要快速定位是哪个 run、哪个域、哪个 stage。新结构下，用户需要：
```bash
cd /blackboard/projects/{slug}/runs/{ts}/solution/stages/
ls -lh
```

这比旧结构的 `cd /blackboard/{session_id}/stages/` 多了一层。

**建议**：在 run 根目录放一个 `README.md`，列出所有关键路径和状态。

---

## 最终建议

1. **方案可行，建议实施**
2. **补充 slug 生成规则**：`slugify(topic[:30]) + "-" + hash8`
3. **统一跨域路径引用**：相对路径，相对于 run 根目录
4. **先试点再推广**：在一个新项目上验证 LLM sub-agent 的路径拼接
5. **加清理策略**：避免磁盘空间快速增长

---

**评审完成**。如有需要，可以进一步讨论实施细节。


---

### 1.6 cage_step1_path_config.md — Step 1 契约笼子

# 契约笼子 Step 1: path_config.py

## 声明

**目标**: 在 `path_config.py` 中新增 Blackboard V2 路径管理能力，不改现有方法。

**新增方法**:
1. `generate_slug(topic: str) -> str` — 从 topic 生成人类可读 slug
2. `get_project_path(slug: str) -> Path` — 获取项目目录路径
3. `get_run_path(slug: str, run_id: str) -> Path` — 获取运行目录路径
4. `is_v2_session_id(session_id: str) -> bool` — 判断 session_id 是否为新格式

**不改动**:
- `get_blackboard_path()` 保持原样
- `_sanitize_session_id()` 保持原样
- `resolve()` 保持原样

## 验证标准

| # | 验证项 | 方法 | 通过条件 |
|:---|:---|:---|:---|
| V1 | generate_slug 生成正确 | 运行测试 | slug 是 ASCII + hyphen，≤50 字符 |
| V2 | generate_slug 冲突处理 | 运行测试 | 同 topic 两次生成不同 slug（加 hash 后缀） |
| V3 | get_project_path 路径正确 | 运行测试 | 返回 `blackboard/projects/{slug}` |
| V4 | get_run_path 路径正确 | 运行测试 | 返回 `blackboard/projects/{slug}/runs/{run_id}` |
| V5 | is_v2_session_id 判断正确 | 运行测试 | 含 `/runs/` 返回 True，否则 False |
| V6 | 现有方法不受影响 | 运行现有测试 | test_path_config.py 全部通过 |
| V7 | 语法正确 | python3 -c import | 无语法错误 |


---

### 1.7 cage_step2_blackboard.md — Step 2 契约笼子

# 契约笼子 Step 2: blackboard.py

## 声明

**目标**: 修改 STAGE_PATH_REGISTRY，stage 路径加域前缀 `solution/`。

**改动**:
1. STAGE_PATH_REGISTRY 中所有 stage 路径从 `stages/xxx` 改为 `solution/stages/xxx`
2. `__init__` 中 base_path 构造适配 V2 session_id（`{slug}/runs/{run_id}` 格式）

**不改**:
- 类名、其他方法、blackboard_manager 等

## 验证标准

| # | 验证项 | 方法 | 通过条件 |
|:---|:---|:---|:---|
| V1 | STAGE_PATH_REGISTRY 有 solution/ 前缀 | 代码检查 | 所有值以 `solution/` 开头 |
| V2 | V2 session_id 初始化 BlackboardManager | 运行测试 | base_path 正确 |
| V3 | V1 session_id 仍可初始化（兼容） | 运行测试 | 不报错 |
| V4 | 语法检查 | python3 import | 无语法错误 |


---

## 2. 代码改动

### 2.1 core/config/path_config.py — 新增 V2 Blackboard 方法

**改动原因**: 支持 V2 Blackboard 结构 `projects/{slug}/runs/{run_id}/{domain}/`

**新增方法**:
- `get_projects_dir()` — 获取 projects 根目录
- `get_research_dir()` — 获取 research 根目录
- `get_project_path(slug)` — 获取项目目录路径
- `get_run_path(slug, run_id)` — 获取运行目录路径
- `get_domain_path(slug, run_id, domain)` — 获取域目录路径
- `generate_slug(topic, existing_slugs)` — 从 topic 生成人类可读的 slug
- `generate_run_id(ts)` — 生成运行 ID（时间戳格式）
- `is_v2_session_id(session_id)` — 判断是否为 V2 格式
- `parse_v2_session_id(session_id)` — 解析 V2 session_id
- `_sanitize_slug(slug)` — 清理 slug
- `_sanitize_run_id(run_id)` — 清理 run_id
- `get_blackboard_path_v2(slug, run_id, domain)` — V2 版本入口

**新增 imports**: `hashlib`, `unicodedata`, `datetime`, `Set`

---

### 2.2 domains/solution/blackboard.py — STAGE_PATH_REGISTRY v3.0.0

**改动原因**: 支持 V2 Blackboard 结构，路径加 `solution/` 域前缀

**改动内容**:
```python
# 旧版 (v2.1.0):
STAGE_PATH_REGISTRY = {
    "data_collection": "data/collection.json",
    "planning": "stages/planning.json",
    ...
    "summarizer": "stages/summarizer.json",
}

# 新版 (v3.0.0):
STAGE_PATH_REGISTRY = {
    # Solution Pro 输入数据
    "data_collection": "solution/data/collection.json",
    "structured_requirements": "solution/data/structured_requirements.json",
    "frozen_spec": "solution/data/frozen_spec.json",
    # 跨域交付文件（保持在 run 根目录）
    "requirements_traceability_matrix": "requirements_traceability_matrix.json",
    # Solution Pro 阶段输出
    "planning": "solution/stages/planning.json",
    ...
    "summarizer": "final_result.json",  # 关键改动：不再写 stages/summarizer.json
    # Iteration reflection outputs
    "research_reflection": "solution/stages/research_reflection.json",
    ...
}
```

**目录创建改动**:
```python
# 旧版:
(self.base_path / "stages").mkdir(exist_ok=True)

# 新版:
(self.base_path / "solution" / "stages").mkdir(parents=True, exist_ok=True)
(self.base_path / "solution" / "data").mkdir(parents=True, exist_ok=True)
```

---

### 2.3 domains/solution/prompts/summarizer.md — v5.5.0 单文件输出改动

**改动原因**: 修复 REQ 信息在 final_result.json 中丢失的问题（断裂点）

**关键改动**:
1. 版本号: 5.4.0 → 5.5.0
2. 输出文件: 从 3 个文件改为 1 个文件
   - 旧: `stages/summarizer.json` + `final_result.json` + `final_solution.md`
   - 新: 只写 `final_result.json`
3. 新增铁律 6/7: `covered_req_ids` 和 `requirement_evidence` 必须传播
4. 删除 Markdown 文档结构要求（不再写 final_solution.md）
5. 新增"单文件规则"明确说明

---

### 2.4 domains/solution/completion_handler.py — REQUIRED_SOLUTION_FINAL_ARTIFACTS 改动

**改动原因**: 配合 summarizer 单文件输出

```python
# 旧版:
REQUIRED_SOLUTION_FINAL_ARTIFACTS = [
    STAGE_PATH_REGISTRY['requirements_traceability_matrix'],
    'final_result.json',
    'final_solution.md',
]

# 新版:
REQUIRED_SOLUTION_FINAL_ARTIFACTS = [
    STAGE_PATH_REGISTRY['requirements_traceability_matrix'],
    'final_result.json',
]
```

---

### 2.5 core/orchestrator/pipeline_orchestrator.py — STAGE_PATHS 改动

```python
# 旧版:
"summarizer": "stages/summarizer.json",

# 新版:
"summarizer": "final_result.json",
```

---

### 2.6 domains/solution/eval/propagation_checker.py — summarizer.json 降级逻辑删除

**改动原因**: 不再需要降级到 summarizer.json，因为 final_result.json 是唯一输出

```python
# 旧版:
final_path = bb_path / "final_result.json"
if not final_path.exists():
    final_path = bb_path / "stages" / "summarizer.json"
if not final_path.exists():
    print(f"❌ final_result.json 和 summarizer.json 都不存在")

# 新版:
final_path = bb_path / "final_result.json"
if not final_path.exists():
    print(f"❌ final_result.json 不存在")
```

---

### 2.7 frontend/backend/routers/status_v2.py — 从 JSON 渲染改动

**改动原因**: 前端需要从 final_result.json 渲染报告（不再依赖 final_solution.md）

**关键改动**: 新增从 final_result.json 渲染 markdown 的逻辑：
- 读取 final_result.json
- 提取 executive_summary（name, problem_statement, solution_overview）
- 提取 detailed_solution.architecture.components
- 渲染为可读的 markdown 格式
- 降级到 report.md / final_report.md

---

### 2.8 domains/solution/task_builder.py — 输出文件要求改动

```markdown
# 旧版:
## 输出文件要求
1. stages/summarizer.json - Stage完成信号与结构化摘要
2. final_result.json - 结构化最终结果
3. final_solution.md - Markdown汇报文档

# 新版:
## 输出文件要求
1. final_result.json - 结构化最终结果（仅此一个文件，不写其他文件）
```

---

### 2.9 scripts/golden_solution_pro_dry_run.py — mock 改动

**改动原因**: 配合单文件输出，删除 final_solution.md 的 mock

---

### 2.10 tests/golden/verify_golden_case.py — final_result.json 检查改动

```python
# 旧版: 检查 final_solution.md
final_path = summarizer_exp.get("final_solution_path", "final_solution.md")
self._check("final_solution.md存在", exists, critical=True)

# 新版: 检查 final_result.json
final_path = summarizer_exp.get("final_result_path", "final_result.json")
self._check("final_result.json存在", exists, critical=True)
```

---

### 2.11 prompts/orchestrator_completion.md — final_result.json 引用改动

```markdown
# 旧版:
- Stage 10 Summarizer 必须读取覆盖矩阵，并在 `final_solution.md` 中输出"需求覆盖度"章节。

# 新版:
- Stage 10 Summarizer 必须读取覆盖矩阵，并在 `final_result.json` 中传播完整的 `covered_req_ids` 和 `requirement_evidence`。
```

---

### 2.12 skills/solution-pro/orchestrator_prompt_v2.md — final_result.json 引用改动

```markdown
# 旧版:
写入：`final_solution.md`
"final_output": "{base_path}/final_solution.md"

# 新版:
写入：`final_result.json`
"final_output": "{base_path}/final_result.json"
```


---

## 3. 分析数据

### 3.1 V1 vs V3 Ship Pro 对比核心数据

| 维度 | V1 (122 REQ) | V3 (108 REQ) | 差异 |
|:---|:---|:---|:---|
| Architect 输出 REQ 数 | 122 | 12 | -90% 🔴 |
| Specifier AC 数 | 31 | 0 | 全部丢失 🔴 |
| Packager 约束数 | 57 | 0 | 全部丢失 🔴 |
| Packager 风险数 | 7 | 0 | 全部丢失 🔴 |
| 技术栈 | Python | TypeScript | 随机漂移 🔴 |
| 硬约束遵守 | 7/7 ✅ | 7/7 ✅ | 一致 |
| 模块数 | 8 | 8 | 一致 |
| 执行阶段 | 5 | 5 | 一致 |

**一句话结论**: V1 是"信息丰富的正确方向"，V3 是"信息贫乏的精致碎片"。

**根因**: 不在 Solution Pro 去重，在 Ship Pro Architect 把 108 条 REQ 压缩为 12 条 + Summarizer 写 final_result.json 时 0 REQ 传播。

### 3.2 REQ 全链路流转图

```
Solution Pro 内部（10 阶段）:  108 REQ ───────────────────── 108 REQ  ✅ 全程保持
                                    │
Summarizer 写 summarizer.json: 108 REQ（covered_req_ids + 41 evidence）✅
                                    │
Summarizer 写 final_result.json:  0 REQ  🔴 ← 断裂点！
                                    │
Ship Pro Architect 收到:          0 REQ → 自造 12 条高层需求  🔴 级联失败
```

**断裂点**: Summarizer prompt v5.4.0 的输出契约只规定了结构字段名，没有规定必须传播 `covered_req_ids` 和 `requirement_evidence` 到 final_result.json。

### 3.3 三专家评审核心结论（Pipeline Watcher 改动）

| 专家 | 角色 | 核心观点 |
|:---|:---|:---|
| A | 系统稳定性工程师 | 改 prompt 可能导致管线卡住，先改 watcher 兼容层 |
| B | LLM 编排专家 | 工具切换（write→exec）混淆风险高，需要硬约束+回滚开关 |
| C | 运维可靠性工程师 | 兼容层简单有效，不会掩盖真实 bug，建议加 schema 版本字段 |

**三方共识**: 先只改 watcher 兼容层，不动 orchestrator prompt。

### 3.4 三份 Ship Pro 评审综合结论（V1 vs V2 去重影响）

| 评审维度 | Run A (81 REQ) | Run B (8 REQ) | 胜者 |
|:---|:---|:---|:---|
| 规格质量（AC L4级占比） | 67% | 100% | B |
| 信息保真度（10项关键设计要点） | 10-40% | 100% | B |
| 架构完整性（问题域理解） | ✅ AI Agent管线 | ❌ 通用进程运行时 | **A** |
| REQ 展开比 | 1.8:1 | 5.9:1 | B |

**统一结论**: Run B 形式质量更高，但建立在错误前提上。架构正确性 > 架构复杂度。

### 3.5 Pipeline Watcher 全面 Review 发现的 12 个问题

**🔴 当前 Bug（4 个）**:
1. Solution Pro `__init__.py` 清理清单不完整（只清理 3 个文件，缺 6 个）
2. OrchestratorHeartbeat 字段名不匹配（Ship Pro 写 `current_stage`，Solution Pro 写 `current_phase`）
3. CompletionChecker 时区不一致（本地时区 vs UTC）
4. Solution Pro 的 stages/ 和 data/ 子目录不清理

**🟡 隐患（5 个）**:
5. `emit()` 调 `sys.exit(0)` 但调用者不知道
6. lock file 在 emit 时未关闭
7. StageDetector 对 Solution Pro 的 merge_group 进度计算不对（13/10 溢出）
8. `RunCounter.increment()` 读-改-写非原子
9. WRAPPER_PROMPT 里 `{cron_job_id}` 没被替换

**🔵 设计弱点（3 个）**:
10. orchestrator 写 `.stage_progress.json` 靠 LLM 遵守 prompt（随机性）
11. 没有 watcher 自检机制
12. 主 Agent 兜底清理没有代码保证

### 3.6 已修复的 7 项（低风险）

| # | 严重度 | 修复 | 文件 |
|:---|:---|:---|:---|
| 1 | 🔴 Bug | Solution Pro 清理清单 3→9 个文件 + stages/data 目录 | `solution/__init__.py` |
| 2 | 🔴 Bug | watcher 字段名兼容（同时支持 current_stage 和 current_phase） | `pipeline_watcher.py` |
| 3 | 🔴 Bug | 时区解析容错（无时区默认本地时区） | `pipeline_watcher.py` |
| 4 | 🔴 Bug | Solution Pro 清理旧 stages/data 目录 | `solution/__init__.py` |
| 5 | 🟡 隐患 | lock file 在 emit() 时正确关闭 | `pipeline_watcher.py` |
| 6 | 🟡 隐患 | RunCounter.is_timeout() 时区感知比较 | `pipeline_watcher.py` |
| 7 | 🟡 隐患 | StageDetector merge_group 进度溢出防护 | `pipeline_watcher.py` |


---

## 4. 专家评审结论（原文）

### 4.1 专家 A — 系统稳定性工程师

**问题**: 这个改动会不会导致已稳定管线中断？

**结论**:
- 改 prompt 会导致管线卡住的风险**高**（LLM 可能不遵守 exec 指令）
- 建议：先只改 watcher 兼容层，不动 orchestrator
- 如果以后要改 orchestrator，需要灰度发布 + 回滚开关

### 4.2 专家 B — LLM 编排专家

**问题**: prompt 从 `write` 改 `exec` 的风险是什么？

**结论**:
- 工具切换（write→exec）混淆风险**高**
- LLM 常见问题：仍用 write、参数拼错、顺序错乱
- 如果做，需要硬约束（"禁止用 write"），且保留回滚开关
- 灰度策略：先改 Ship Pro（更成熟），验证 3 天 exec 成功率 > 95%

### 4.3 专家 C — 运维可靠性工程师

**问题**: watcher 兼容层怎么做最安全？

**结论**:
- 字段名兼容 `data.get("current_stage") or data.get("current_phase")` 是标准做法
- 建议加 schema 版本字段（`schema_version: 2`），避免无限堆叠 fallback
- 验证：4 个 fixture 覆盖所有组合（有/无时区 × current_stage/current_phase）
- 防御措施：JSON 解析失败兜底 + 文件原子写入 + 必填字段校验

### 4.4 架构师评审（Blackboard v2.0.0-draft）

**核心判断**: 三层结构 `projects/{slug}/runs/{ts}/` 方向正确，能解决 P1-P5；但方案内部存在结构性矛盾（D5 数据流描述与目录树不一致），跨域数据消费寻址机制没定义清楚。

**必须修正（阻塞实施）**:
1. 统一 3.1 目录树和 D5 数据流描述
2. 明确 run.json vs runs.json vs project.json 的职责和数量

**强烈建议**:
3. run.json 增加 `parent_run_id` 和 `iteration` 字段（为 Loop Engine 铺路）
4. run.json 预留 `external_refs` 字段（为 Research Pro 接入留口子）
5. runs.json 改为 JSONL 格式（append-only，避免并发写入问题）

---

## 5. 关键决策

### 5.1 Summarizer 单文件输出决策

**问题**: final_result.json 中 REQ 信息丢失（0 条），导致 Ship Pro Architect 在信息荒漠中自造 12 条高层需求。

**根因**: Summarizer prompt 要求写 2 个 JSON 文件（summarizer.json + final_result.json），但没有区分各自应包含什么字段。LLM 把详细数据写入 summarizer.json，final_result.json 自由发挥为精简版。

**决策**: 
- 改为只写 final_result.json 一个文件
- prompt 铁律新增：covered_req_ids 和 requirement_evidence 必须传播
- 删除 final_solution.md 的生成要求

### 5.2 Pipeline Watcher 改造方向决策

**问题**: Watcher 假设 orchestrator 行为确定，但 orchestrator 是 LLM，行为有随机性。

**两个方向**:
- A: watcher 加智能（适应随机性）
- B: orchestrator 输出标准化（消除随机性）

**决策**: 方向 B 是根治，方向 A 是防御。两者都需要，但 B 优先。
**当前实施**: 只改 watcher 兼容层（低风险），不动 orchestrator prompt。
**远期方向**: 等 orchestrator 足够稳定后，灰度引入 progress_writer.py（确定性脚本）。

### 5.3 V2 Blackboard 结构设计决策

**核心原则**: 
- 三层结构: `projects/{slug}/runs/{run_id}/{domain}/`
- slug 人类可读 + hash 后缀（确定性，避免冲突）
- run_id 时间戳格式（YYYYMMDD_HHMMSS）
- 域分离: spec/、solution/、ship/ 平级兄弟
- 跨域寻址: 通过 `../{sibling}/final_result.json`

**预留字段**:
- `parent_run_id` — Loop Engine 迭代因果链
- `external_refs` — Research Pro 未来接入
- `iteration` — 迭代编号

### 5.4 7 步改动顺序（Cage Step）

**Step 1 — Path Config 笼子**:
- 新增 V2 方法到 path_config.py
- 所有路径计算通过 PathConfig，不硬编码

**Step 2 — Blackboard 笼子**:
- STAGE_PATH_REGISTRY 加 solution/ 前缀
- 目录创建适配新结构

**后续步骤**: 其他模块逐步适配 V2 结构

### 5.5 Emoji 语义统一

| 语义 | 改前 | 改后 |
|:---|:---|:---|
| 运行中 | ✅ | 🟢 |
| 完成 | 🟢 | ✅ |
| 失败 | 🔴 | 🔴 |
| 阶段 | 💎 | 💎 |
| 时间 | ⏱️ | ⏱️ |

### 5.6 Pipeline Watcher 版本命名规范化

| 版本 | 日期 | 变更 |
|:---|:---|:---|
| 2.0.0 | 2026-06-20 | 初始版本：Python 脚本替代 cron_watcher.md |
| 2.1.0 | 2026-06-20 | Bug 修复：partial 状态 + 多信号心跳 |
| 2.2.0 | 2026-06-21 | 路径校验 + 单例原则 |
| 2.3.0 | 2026-06-21 | 三方评审 + 7 项修复 + 兼容层 |

**命名规范**: 文件名不带版本号（`pipeline_watcher_contract.md`），版本号写在文件头元数据。

---

## 6. 其他恢复的文件

### 6.1 CONTRACT_SUMMARIZER_SINGLE_FILE.md

位置: `domains/solution/eval/CONTRACT_SUMMARIZER_SINGLE_FILE.md`

内容: 单文件输出契约规范（summarizer v5.5.0 的评估合同）

### 6.2 Pipeline Watcher 修复文件列表

| 文件 | 改动类型 |
|:---|:---|
| `domains/ship_pro/scripts/run_pipeline.py` | 清理清单 + watcher_base_path |
| `scripts/pipeline_watcher.py` | _validate_base_path() + 字段兼容 + 时区容错 + lock file |
| `domains/ship_pro/SKILL.md` | 强制用 watcher_base_path |
| `scripts/start_solution_pro.py` | 同步加 watcher_base_path |
| `domains/solution/SKILL.md` | 同步强制用 watcher_base_path |
| `contracts/shared/pipeline_watcher_contract.md` | v2.3.0 更新 |
| `tests/integration/test_watcher_contract.py` | 6/6 PASS |
| `scripts/pipeline_progress_notify.py` | 通知脚本 |

---

*恢复完成。所有数据从 session 日志中提取，时间范围 2026-06-11 至 2026-06-21。*
