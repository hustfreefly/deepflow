# DeepFlow 全链路系统性偏差分析报告

> **案例**: OpenClaw AI Native Loop Engineering Framework  
> **日期**: 2026-06-25  
> **分析方法**: 逐阶段追踪 10 条约束从 Spec Pro → Ship Pro → 实现的传递与丢失  
> **分析者**: 小满（主 Agent）+ 5 位外部专家  

---

## 一、偏差全景：10 条约束的最终命运

Spec Pro planning 阶段正确提取了 10 条约束（C-001~C-010）。追踪每条约束到最终交付件的状态：

| 约束 | 描述 | 优先级 | 最终状态 | 偏差说明 |
|------|------|--------|---------|---------|
| **C-001** | 一步到位，不分阶段 | P0 | ✅ 保持 | 元约束（描述交付方式），不需要代码表达 |
| **C-002** | 全LLM控制，Python不做控制流 | P0 | ❌ **违反** | ModelRouter硬编码dict, DAGDecomposer关键词匹配, Zone2Tuner规则引擎 |
| **C-003** | 基于OpenClaw平台，不引入外部框架 | P0 | ❌ **违反** | 零OpenClaw集成，9个自建Python类重新造了6个已有轮子 |
| **C-004** | Zone 0安全规则不可修改 | P0 | ✅ 保持 | 框架未实现修改自身的能力（默认满足） |
| **C-005** | Hermes是对等协作伙伴，不是子Agent | P0 | ⚠️ **降级** | 无双向通信协议，架构文档中Hermes只在Worker Allocator中提及 |
| **C-006** | 默认不限制token消耗 | P1 | ⚠️ **忽略** | 未体现在代码中 |
| **C-007** | 最大并发6个子Agent | P1 | ⚠️ **忽略** | DAGScheduler有max 6参数但无执行引擎 |
| **C-008** | 必须有死循环熔断机制 | P0 | ⚠️ **不完整** | SignalDetector检测4类信号，但无执行器响应（检测到→然后呢？） |
| **C-009** | Dream Loop只增不删memory | P0 | ⚠️ **不完整** | L1/L1.5/L2验证有了，但权重衰减（WP-012）代码在/tmp/未合并 |
| **C-010** | HITL超时24小时后升级 | P1 | ❌ **丢失** | 无任何24h超时升级逻辑 |

**统计**：
- ✅ 保持：2/10（C-001, C-004 — 都是不需要代码表达的元约束）
- ⚠️ 降级/不完整：5/10
- ❌ 违反/丢失：3/10

**核心发现**：所有需要代码表达的约束（C-002, C-003, C-005, C-008, C-010）全部被违反或丢失。

---

## 二、逐阶段追踪：偏差在哪个阶段产生

### 2.1 Spec Pro 全链路追踪

Spec Pro 有 13 个阶段。逐阶段检查约束的传递情况：

| 阶段 | 约束处理 | 评价 |
|------|---------|------|
| **data/collection** | 44 个 REQ 采集 | ✅ 正确 |
| **planning** | 10 条约束结构化提取（C-001~C-010），7 维度分析 | ✅ **完美** |
| **reviewer_technical** | 技术评审 | ✅ 正常 |
| **reviewer_risk** | 风险评审 | ✅ 正常 |
| **reviewer_business** | 业务评审 | ✅ 正常 |
| **research_expert_1** | 高并发架构专家 | ✅ 正确引用约束 |
| **research_expert_2** | 行业最佳实践专家 | ✅ 正确引用约束 |
| **research_expert_3** | 成本控制专家 | ✅ 正确引用约束 |
| **consolidator** | 整合三位专家研究 | ✅ 约束可见（提到C-002, C-009） |
| **audit** | 质量审计 | ⚠️ 关注实现细节，未验证约束 |
| **fix** | 修复审计发现的问题 | ⚠️ 修复实现细节，不涉及约束 |
| **fixer_expert** | 深度修复 | ⚠️ 修复实现细节，不涉及约束 |
| **harness_final** | 最终质量检查 | ⚠️ 散文级验证（"全LLM控制符合C-002"），非结构化 |
| **final_result** | **最终输出** | 🔴 **约束消失** |

#### 🔴 关键断点：final_result 的 Schema

`final_result.json` 的顶层字段：

```json
{
  "status": "completed",
  "stage": "summarizer",
  "session_id": "...",
  "covered_req_ids": [...],        // ← 只有 REQ
  "requirement_evidence": [...],   // ← 只有需求证据
  "final_solution": {              // ← 只有方案
    "solution_executive_summary": {...},
    "detailed_solution": {
      "architecture": {...},       // ← 组件列表
      "implementation": {...},     // ← 实施计划
      "risk_management": {...}     // ← 风险
    }
  }
}
```

**缺失字段**：
- ❌ `constraints` — 10条约束去哪了？
- ❌ `architecture_principles` — 架构原则？
- ❌ `platform_dependencies` — 平台依赖？

**约束在 final_result 中的存在感**：
- C-002 "全LLM控制" → 仅出现 **1次**（在 key_benefits 散文中）
- C-003 "基于OpenClaw" → 仅出现 **1次**（在散文中）
- C-005 "Hermes对等" → 仅出现 **1次**（在散文中）

**结论**：`final_result` 的 schema 是一个**信息过滤器**。它保留了 WHAT（功能需求 + 组件设计），丢弃了 HOW（架构约束 + 平台约束）。这直接导致 Ship Pro 看不到约束。

---

### 2.2 Ship Pro 全链路追踪

Ship Pro 的唯一输入是 Spec Pro 的 `final_result.json`。

| 阶段 | 约束处理 | 评价 |
|------|---------|------|
| **Architect** | 9 COMP + 7 dependencies + 8 risks | 🔴 无编排层组件，无约束验证 |
| **Decomposer** | 9 COMP → 16 WP | 🔴 无编排层WP，WP无serving_principles |
| **Specifier** | 16 WP 的 Given-When-Then AC | 🔴 AC只验功能，不验约束 |
| **Reviewer** | 4 medium + 4 low issues | 🔴 未检查架构原则违反 |
| **Packager** | 打包执行计划 | ⚠️ 正常（打包忠实于WP） |

#### 🔴 断点 2：Architect 的架构→组件映射缺陷

8位专家共识中设计了 4 个核心 LLM 决策模块：

| 设计模块 | 在 Architect 9 COMP 中的承接 |
|---------|---------------------------|
| Goal Parser（目标解析器） | ❌ **不存在** |
| Phase Selector（阶段选择器） | ❌ **不存在** |
| Worker Allocator（Worker分配器） | ❌ **不存在** |
| Error Analyzer（错误分析器） | ⚠️ CircuitBreaker 只做检测 |
| **MainLoop Orchestrator** | ❌ **不存在** |

**Architect 输出了 9 个"做什么"的组件，但没输出"谁来串联它们"的组件。**

#### 🔴 断点 3：Reviewer 的审计盲区

Ship Pro Reviewer 发现的 8 个 issue 全是细节层面的：
- WP-005 超时阈值与 SLA 不一致
- Hermes 协议缺少 WP
- LLM API 中断风险
- AC 精度不够
- complexity 枚举不一致
- 交叉验证模型未指定

**Reviewer 从未检查**：
- ❌ "全LLM控制"在哪些 WP 中有可验证的对应？
- ❌ 哪些组件应该用 OpenClaw 原生能力而非自建？
- ❌ 4 个核心 LLM 决策模块（Goal Parser / Phase Selector / Worker Allocator / Error Analyzer）去哪了？
- ❌ 三层循环之间的数据流通道在哪些 WP 中实现？

---

### 2.3 Hermes + Codex 实现层追踪

| 环节 | 偏差 | 评价 |
|------|------|------|
| WP-001 实现 ModelRouter | `DEFAULT_ROUTES = {SIMPLE: "flash", COMPLEX: "opus"}` | ❌ 违反 C-002 |
| WP-001 实现 TokenBucket | 自建 async 令牌桶 | ❌ 违反 C-003（OpenClaw Gateway 已有） |
| WP-001 实现 PriorityQueue | 自建 heapq 优先级队列 | ❌ 违反 C-003（sessions_spawn 天然优先级） |
| WP-008 实现 DAGDecomposer | `if "rest api" in goal.lower()` 关键词匹配 | ❌ 违反 C-002 |
| WP-008 实现 _fallback_plan | 固定 auth→api→tests 三节点 | ❌ 违反 C-002 |
| WP-015 实现 Zone2Tuner | if/else 规则引擎 | ❌ 违反 C-002 |
| WP-007 偏离检测 | **完全未实现** | ❌ WP 代码不存在 |
| WP-003/005/009/012/014/016 | 代码在 /tmp/ 未合并 | ⚠️ 交付不完整 |
| 反馈循环 | SHIP_PRO_FEEDBACK.md 提了 5 项改进 | ❌ 无人处理 |

**Codex 没做错任何事** — 它忠实执行了规格。规格说"实现一个 Python 类"，它就写 Python 类。规格没提到约束，它就不考虑约束。

---

## 三、超越约束的额外偏差

除了 10 条约束的违反，还发现以下系统性偏差：

### 偏差 D1：Hermes 对等协作降级为 Supervisor-Worker

| 设计 | 实现 |
|------|------|
| "Hermes 是协作伙伴，不是子 Agent" | 架构文档中 Hermes 只在 Worker Allocator 的上下文中提及 |
| 双向通信（sessions_send / 共享 memory） | 无任何双向通信协议 |
| Hermes 有自己的 Loop、记忆、Skill | 完全未体现 |

**偏差类型**：关系降级 — 对等伙伴被隐式降级为单向 Worker。

### 偏差 D2：Goal 嵌套与演化能力缺失

| 设计 | 实现 |
|------|------|
| 分形 Goal 嵌套（主→子→孙） | DAGDecomposer 只做一层分解 |
| 子 Goal 反向修改父 Goal 约束 | 无冒泡机制 |
| Goal 演化（只能增约束、不能删约束） | 无演化机制 |
| Goal 优先级竞争 | 无竞争策略 |

**偏差类型**：能力降级 — 动态系统被实现为静态系统。

### 偏差 D3：间歇式心跳四级调度缺失

| 设计 | 实现 |
|------|------|
| 快脉冲（3min）→ Worker 状态 | ❌ 无 |
| 慢脉搏（1h）→ 项目进度 | ❌ 无 |
| 深呼吸（日）→ Dream Loop | ❌ 无（DreamLoopValidator 有但无触发） |
| 长冥想（周）→ Meta-Loop | ❌ 无（Zone2Tuner 有但无触发） |

**偏差类型**：运行时机制缺失 — 调度逻辑不存在。

### 偏差 D4：端到端验证缺失

| 应有的 | 实际的 |
|--------|--------|
| Goal 输入 → Plan → Execute → Result 的端到端测试 | 无（test_task_loop_flow 只验了 4 个组件的串联） |
| 8 小时无人运行测试 | 无 |
| Dream Loop 触发→反思→教训写入的完整测试 | 无 |
| 跨 Session 恢复测试 | 无 |

**偏差类型**：验证缺失 — 只测了"零件能不能转"，没测"车能不能开"。

### 偏差 D5：Ship Pro 反馈未闭环

Hermes 在 `SHIP_PRO_FEEDBACK.md` 中提出了 5 项改进建议：
1. 增加 `api_conventions` 字段
2. 增加 `integration_tests` 字段
3. 增加 `environment` 字段
4. 增加 `performance_targets` 字段
5. 增加 `error_handling` 字段

**当前状态**：全部 5 项无人处理，未反馈到 Ship Pro 管线改进中。

**偏差类型**：反馈断裂 — 下游的经验无法回流到上游改进。

---

## 四、根因归因：6 个系统级缺陷

将上述所有偏差归纳为系统级缺陷：

### 缺陷 S1：约束信息管道断裂（影响 C-002, C-003, C-005, C-008, C-010）

**问题链**：
```
planning.json ✅ 有 constraints[] 
    → 中间阶段 ✅ 可见
    → final_result.json 🔴 无 constraints 字段
    → Ship Pro 🔴 看不到约束
    → 实现 🔴 违反约束
```

**根因**：`final_result` 的 Pydantic schema 没有 `constraints` / `architecture_principles` / `platform_dependencies` 字段。约束只能以散文形式存在于 `key_benefits` 中，不被下游结构化消费。

**泛化影响**：任何项目的任何约束，只要需要在代码中表达，都会在 final_result 处丢失。

---

### 缺陷 S2：架构→组件映射无完整性校验（影响 Goal Parser, Phase Selector, Worker Allocator, Orchestrator）

**问题链**：
```
8位专家设计了 5 个核心模块（Goal Parser, Phase Selector, Worker Allocator, Error Analyzer, Orchestrator）
    → Spec Pro consolidator ✅ 提到这些模块
    → Spec Pro final_result 🔴 9个组件中不含这5个
    → Ship Pro Architect 🔴 继承 final_result 的 9 组件
    → 实现 🔴 这 5 个核心模块完全不存在
```

**根因**：没有机制检查"设计中的所有模块是否在组件列表中有对应"。从架构概念到代码组件的映射是隐式的、无人验证的。

**泛化影响**：任何"概念层存在但实现层缺失"的模块都会被忽略。

---

### 缺陷 S3：平台能力复用无检查机制（影响 C-003）

**问题链**：
```
C-003 "基于当前OpenClaw平台能力"
    → planning.json ✅ 正确识别
    → final_result 🔴 降级为散文 "充分利用现有OpenClaw能力"
    → Ship Pro Architect 🔴 列出 "OpenClaw sessions_spawn" 作为 tech stack 参考
    → Decomposer 🔴 WP 中没有 "must_use_openclaw" 标记
    → Codex 🔴 不知道 OpenClaw 有什么，自己造了 6 个轮子
```

**根因**：
1. 没有 "平台能力清单" 结构化字段
2. 没有 "不要造轮子" 的反模式检查
3. Codex 的 prompt 中不包含 "OpenClaw 已有哪些能力可以复用"

**泛化影响**：任何基于现有平台的项目都会重复造轮子。

---

### 缺陷 S4：评审维度单一（只查细节不查灵魂）

**当前 Reviewer 检查**：
- ✅ WP 之间 AC 一致性
- ✅ 依赖关系无环
- ✅ 风险覆盖
- ✅ AC 可测试性评分

**当前 Reviewer 不检查**：
- ❌ 架构原则是否在每个 WP 中有可验证的对应
- ❌ 平台能力是否被复用
- ❌ 设计中的所有模块是否在 WP 中有承接
- ❌ 三层循环数据流是否完整
- ❌ 端到端路径是否可运行

**根因**：Reviewer 的 prompt 和评分标准只关注 WP 级别的细节质量，没有"架构原则审计"维度。

**泛化影响**：所有项目的设计意图在执行层面都会被稀释。

---

### 缺陷 S5：反模式检测缺失

**当前系统有**：
- ✅ 正面模式验证（功能 AC、单元测试）
- ❌ 反模式检测（"不要这样做"的自动检查）

**应该检测但没检测的反模式**：
- "硬编码路由表" 违反 "全LLM控制"
- "自建并发控制" 违反 "基于OpenClaw"
- "Python if/else 决策" 违反 "LLM做决策"
- "同步阻塞I/O" 违反 "8小时运行"

**根因**：管线中没有任何阶段检查"实现中是否出现了禁止的代码模式"。

**泛化影响**：任何"禁止做X"类约束都不会被自动检测。

---

### 缺陷 S6：反馈循环不闭合

**当前状态**：
```
Spec Pro → Ship Pro → 实现 → [完成]
                                  ↓
                           SHIP_PRO_FEEDBACK.md (无人读)
```

**应该变成**：
```
Spec Pro → Ship Pro → 实现 → 反馈 → Ship Pro 改进 → 下次更好
```

**具体断裂**：
- Hermes 反馈 5 项 Ship Pro 改进建议 → 无人处理
- 实现中发现 Spec Pro 遗漏（如缺少编排层）→ 无回流机制
- 专家评审发现架构偏差 → 无法回溯修改 Spec Pro 输出

**泛化影响**：每次项目都从零开始，无法从历史项目中学习改进。

---

## 五、缺陷影响矩阵

| 缺陷 | 影响的约束 | 影响的设计 | 影响的阶段 | 严重度 |
|------|----------|----------|----------|--------|
| **S1 约束管道断裂** | C-002, C-003, C-005, C-008, C-010 | — | Spec Pro → Ship Pro | 🔴 Critical |
| **S2 映射无校验** | — | Goal Parser, Phase Selector, Worker Allocator, Orchestrator, Error Analyzer | Spec Pro → Ship Pro | 🔴 Critical |
| **S3 平台复用无检查** | C-003 | ModelRouter, TokenBucket, PriorityQueue, Blackboard, ContextCompressor, SignalDetector | Ship Pro → 实现 | 🔴 Critical |
| **S4 评审维度单一** | 所有约束 | 编排层, 数据流通道 | Ship Pro Reviewer | 🟡 High |
| **S5 反模式无检测** | C-002, C-003 | 硬编码路由, 自建轮子, 规则引擎 | 实现 | 🟡 High |
| **S6 反馈不闭合** | — | Ship Pro 改进 | 全管线 | 🟠 Medium |

---

## 六、系统性修复方案：五维修复

### 修复 F1：约束传递管道（修 S1）

**改动范围**：Spec Pro schemas + final_result + Ship Pro Architect

1. Spec Pro `final_result` schema 增加一等公民字段：
   - `architecture_principles[]`（风格约束：必须做/禁止做）
   - `platform_dependencies[]`（平台约束：必须复用/禁止重建）
   - `invariants[]`（不变量：始终为真的条件）

2. 每个约束字段包含：
   - `id`, `name`, `type`（must_do / must_not_do / must_have / invariant）
   - `description`
   - `anti_patterns[]`（具体的反面模式描述）
   - `verification_method`（如何验证）
   - `severity`（BLOCKER / WARNING）

3. Ship Pro Architect prompt 注入这些约束，输出 `principle_coverage[]` 映射

**效果**：约束从 planning → final_result → Ship Pro 全程可见。

---

### 修复 F2：架构→组件完整性校验（修 S2）

**改动范围**：Spec Pro final_result + Ship Pro Architect + 新 gate

1. Spec Pro `final_result` 增加 `core_modules[]` 字段：
   - 列出所有设计中提到的核心模块（不仅是组件，还包括编排器、解析器等）
   - 每个模块标注 `role`（executor / orchestrator / parser / validator / connector）

2. Ship Pro Architect 必须为每个 `core_modules` 条目创建对应 COMP

3. 新增 gate `gate_architecture_completeness`：
   - 检查 final_result.core_modules 的每一项是否在 Architect.modules 中有对应
   - 缺失 → gate 拒绝

**效果**：设计中的每个模块都不会在组件化过程中丢失。

---

### 修复 F3：平台能力复用检查（修 S3）

**改动范围**：Spec Pro + Ship Pro Architect/Decomposer/Specifier + 新 gate

1. Spec Pro `final_result` 增加 `platform_dependencies[]`：
   ```json
   {
     "platform": "OpenClaw",
     "capabilities_to_reuse": [
       {"capability": "子Agent调度", "api": "sessions_spawn", "replaces": ["Worker Pool", "PriorityQueue"]},
       {"capability": "模型路由", "api": "model aliases", "replaces": ["ModelRouter"]},
       ...
     ],
     "build_only_when": "OpenClaw 没有对应能力时才自建"
   }
   ```

2. Ship Pro Architect 每个 COMP 标注 `implementation_source`：
   - `openclaw_native`（直接用 OpenClaw）
   - `hybrid`（部分 OpenClaw + 部分自建）
   - `custom_logic`（OpenClaw 没有，必须自建）

3. Ship Pro Specifier 每个 WP 增加 `platform_integration` 字段 + 平台验证 AC

4. 新增 gate `gate_platform_coverage`：
   - 检查每个 `must_use: true` 的平台能力是否在某个 WP 中被使用
   - 检查 `implementation_source: openclaw_native` 的 COMP 是否真的没有自建代码

**效果**：不会重复造轮子。

---

### 修复 F4：评审维度升级（修 S4）

**改动范围**：Ship Pro Reviewer prompt + 评审输出 schema

Reviewer 输出增加 3 个审计维度：

1. **principle_audit**：逐条检查架构原则在 WP 中的覆盖
2. **platform_audit**：逐条检查平台能力是否被复用
3. **architecture_completeness_audit**：检查设计中的所有模块是否有 WP 承接

每个审计维度输出：
```json
{
  "item": "PRINCIPLE-001: 全LLM控制",
  "wp_coverage": {"WP-001": "❌ AC只验功能", "WP-008": "❌ 硬编码fallback"},
  "overall": "FAIL",
  "action_required": "为 WP-001 和 WP-008 增加原则验证 AC"
}
```

**效果**：Reviewer 不仅查细节，还查"灵魂"。

---

### 修复 F5：反模式自动检测（修 S5）

**改动范围**：Ship Pro Packager 或新增 post-implementation gate

1. 每个架构原则定义对应的反模式 regex/AST 规则：
   ```
   PRINCIPLE-001 "全LLM控制":
     anti_patterns:
       - regex: "DEFAULT_ROUTES\s*=" → 硬编码路由表
       - regex: "if.*in.*goal\.lower" → 关键词匹配
       - regex: "fallback_plan" → 固定回退计划
   
   PRINCIPLE-003 "基于OpenClaw":
     anti_patterns:
       - class_name: "ModelRouter" → 自建模型路由
       - class_name: "TokenBucket" → 自建限流
       - class_name: "PriorityQueue" → 自建队列
   ```

2. 实现完成后，自动扫描代码检测反模式
3. 检测到 → 标记为 BLOCKER，不允许交付

**效果**：违反约束的代码模式会被自动拦截。

---

### 修复 F6：反馈循环闭合（修 S6）

**改动范围**：Ship Pro 管线 + 新增 feedback_collector

1. Hermes/Codex 反馈文件（如 `SHIP_PRO_FEEDBACK.md`）被自动解析
2. 反馈项结构化存储到 `feedback_registry.json`
3. 下次 Ship Pro 运行时，自动加载历史反馈到 prompt 中
4. 新反馈与已有反馈对比，标记"已处理"或"新增"

**效果**：Ship Pro 从历史项目中学习改进。

---

## 七、修复优先级与工作量

| 修复 | 优先级 | 工作量 | 理由 |
|------|--------|--------|------|
| **F1 约束传递管道** | 🔴 P0 | ~150 行 | 不修这个，所有约束都会丢失 |
| **F2 架构完整性校验** | 🔴 P0 | ~80 行 | 不修这个，核心模块会继续丢失 |
| **F3 平台复用检查** | 🔴 P0 | ~120 行 | 不修这个，每次都重新造轮子 |
| **F4 评审维度升级** | 🟡 P1 | ~60 行 | Reviewer 是最后防线 |
| **F5 反模式检测** | 🟡 P1 | ~100 行 | 自动化约束验证 |
| **F6 反馈循环** | 🟠 P2 | ~80 行 | 长期改进机制 |
| **总计** | | **~590 行** | 涉及 schemas + prompts + gates |

---

## 八、验证方案

修复后用本次案例做回归测试：

1. 用修复后的 Spec Pro 重跑 → 检查 final_result 是否含 `architecture_principles` + `platform_dependencies`
2. 用修复后的 Ship Pro 重跑 → 检查 Architect 是否含 Orchestrator 组件 + 平台复用标注
3. 检查 Reviewer 是否发现 C-002/C-003 违反
4. 检查 gate 是否在约束未覆盖时拒绝通过
5. 检查 Codex 收到的 WP prompt 是否含 `serving_principles` + `anti_patterns`

**成功标准**：重跑后交付件包含 MainLoop Orchestrator，ModelRouter/DAGDecomposer 通过 LLM API 实现而非硬编码，至少 4 个 OpenClaw 原生能力被复用。

---

*全链路追踪：10 条约束 × 13 个 Spec Pro 阶段 × 5 个 Ship Pro 阶段 × 16 个 WP 实现。*
*6 个系统级缺陷，6 个泛化修复方案。*
*这不是一次性的案例修复，是管线结构升级。*
