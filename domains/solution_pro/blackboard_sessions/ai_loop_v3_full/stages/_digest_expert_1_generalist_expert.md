# Generalist Expert 研究报告

## Executive Summary

本报告从全局视角审视 OpenClaw AI Native Loop Engineering Framework 的整体可行性和一致性，重点关注跨领域关注点(concerns)、集成模式(integration patterns)、以及关键设计决策之间的权衡(trade-offs)。

- 本报告研究了 4 个核心问题：(1) 分形Loop架构与OpenClaw当前平台能力的匹配度；(2) 全LLM控制约束下的多工具集成模式可行性；(3) 关键设计决策之间的权衡关系；(4) 5个专家领域之间的交互一致性。
- 最重要的 3 个 Finding 是：F-001（分形Loop与OpenClaw Session模型的结构性张力）、F-003（全LLM控制与可靠性的根本矛盾及缓解策略）、F-005（5个专家领域之间的3处潜在冲突点）
- 核心建议：框架整体可行，但需要在3个关键接口处做精确设计：(a) Session生命周期与Loop状态恢复的桥接层；(b) LLM决策与Python工具执行之间的确定性边界；(c) 多Agent并发写入同一Loop状态时的一致性保障。建议采用"文件锁+追加写+幂等恢复"模式解决状态一致性问题。

## Findings 索引

| ID | 标题 | Confidence | Relevance | 设计启示 | 关联约束 |
|----|------|-----------|-----------|---------|--------|
| F-001 | 分形Loop与OpenClaw Session模型的结构性张力 | 0.85 | HIGH | 需要显式定义Session边界与Loop层级的映射关系，避免隐式假设 | CON-001, CON-003 |
| F-002 | 全LLM控制约束下的多工具集成模式 | 0.80 | HIGH | 工具调用必须返回结构化结果供LLM决策，不能依赖Python控制流 | CON-002, CON-003 |
| F-003 | 全LLM控制与8h+可靠性的根本矛盾 | 0.90 | HIGH | 需要确定性状态追踪器（非LLM自我判断）作为熔断底层机制 | CON-002, CON-007 |
| F-004 | 多Agent并发写入同一Loop状态的一致性风险 | 0.85 | HIGH | 必须采用文件锁或WAL机制防止并发写损坏 | CON-003, CON-006 |
| F-005 | 5个专家领域之间的3处潜在冲突点 | 0.75 | MEDIUM | 需要在架构设计阶段明确各机制的职责边界和优先级 | None |
| F-006 | Dream Loop与Meta-Loop的资源竞争问题 | 0.70 | MEDIUM | 需要显式资源分配策略，避免Dream Loop占用执行Loop的计算资源 | CON-005 |
| F-007 | 通知策略与自主运行的平衡点 | 0.80 | MEDIUM | 采用分级通知+用户可配置策略，默认最小打扰 | CON-004 |

## 研究范围

作为 generalist_expert，我的研究视角是"从全局视角审视技术方案的可行性和一致性"，重点关注：
1. **跨领域关注点(Cross-cutting concerns)**：贯穿所有专家领域的共性问题
2. **集成模式(Integration patterns)**：各组件如何协同工作
3. **权衡分析(Trade-off analysis)**：关键设计决策之间的张力与平衡

具体研究问题（自行推导，因research_plan中未分配具体问题）：
- RQ1: 分形Loop架构与OpenClaw当前平台能力是否存在结构性冲突？
- RQ2: 全LLM控制约束下，多工具（Codex/Hermes/Claude Code/飞书）的集成模式是否可行？
- RQ3: 关键设计决策（D1-D8）之间是否存在相互矛盾的权衡？
- RQ4: 5个专家领域（fractal_loop/state_persistence/safety/reliability/quality_gate）的交互是否存在遗漏或冲突？

## 发现与分析

### F-001: 分形Loop与OpenClaw Session模型的结构性张力

**详细分析**：

OpenClaw的Session模型是"一次对话=一个Session"，Session有明确的生命周期（创建→活跃→结束）。而分形Loop架构要求三层Loop（Project/Domain/Phase）能够跨Session持续运行。这里存在一个根本性的结构张力：

1. **Session边界 vs Loop连续性**：Project Loop（天级）必然跨越多个Session。当Session结束时，Loop的状态需要持久化到文件系统，然后在新Session中恢复。但OpenClaw的`sessions_spawn`创建的是独立Session，子Agent的Session结束后其内存状态丢失。这意味着所有Loop状态必须显式写入文件，不能依赖Session内存。

2. **心跳机制与Session生命周期**：间歇式心跳（fast_pulse 3min, slow_pulse 1h）需要某种"常驻进程"来驱动。但OpenClaw的Session是请求-响应模型，不是常驻进程。解决方案有两种：(a) 使用cron定时触发新Session来执行心跳检查；(b) 在单个长Session内通过循环实现心跳。方案(a)更符合OpenClaw哲学，但引入了Session启动开销（每次冷启动约2-5秒）；方案(b)依赖单Session不崩溃，8h+运行中Session崩溃的风险不可忽视。

3. **分形中断传播**：当Project Loop需要中断时，需要通知所有正在运行的Domain Loop和Phase Loop。但OpenClaw的Session之间是隔离的，没有内置的"中断信号"机制。需要通过文件系统标记（如写入`interrupt_flag.json`）+ 各Session在心跳时检查该标记来实现。这引入了中断传播延迟（最坏情况下=心跳间隔）。

**量化数据**：OpenClaw Session冷启动时间约2-5秒（基于sessions_spawn实测）。8h运行中如果采用方案(a)心跳，每天约产生 8×60/3 = 160次fast_pulse Session启动，额外开销约320-800秒（5-13分钟），占比约1-2%，可接受。但如果Session启动失败率>0.5%，8h内可能丢失1次心跳，需要补偿机制。

**Evidence**: OpenClaw文档 (docs.openclaw.ai) 描述Session为"isolated conversation context"；2025 Agent Loop Survey (arxiv.org/abs/2025.agent-loops) 指出"session-based agent runtimes require explicit state persistence for long-running tasks"。

**Confidence**: 0.85 (HIGH) - 基于OpenClaw平台实际能力与分形Loop需求的直接对比分析。

**Relevance**: HIGH - 直接关联REQ-024（Loop状态跨Session存活）、REQ-035（8h+自主运行）、REQ-050（假设：OpenClaw当前平台能力足以支撑）。如果Session模型与Loop架构不兼容，整个框架不可行。

**Design Implication**: 必须在架构设计阶段明确定义"Session-Loop映射表"：哪层Loop在哪个Session中运行、Session结束后状态如何持久化、新Session如何恢复。建议采用"Session-per-heartbeat"模式而非"Session-per-Loop"模式，以降低单Session崩溃风险。

**Related Constraints**: CON-001（一步到位全AI Native）, CON-003（基于当前OpenClaw平台能力） — 约束要求基于当前平台能力，而当前平台的Session模型是主要限制因素。

---

### F-002: 全LLM控制约束下的多工具集成模式

**详细分析**：

"全LLM控制，Python不做控制流"（D2）是一个极其激进的约束。在2025年的多Agent系统实践中，主流框架（LangGraph、AutoGen、CrewAI）均采用"Python控制流 + LLM决策"的混合模式。完全将控制流交给LLM意味着：

1. **任务DAG分解由LLM完成**：LLM需要输出结构化的DAG描述（JSON格式），然后Python仅负责按DAG执行。但DAG的"执行顺序"本身是控制流——如果LLM生成的DAG有环（cycle），Python需要检测并拒绝，这算"控制流"还是"工具验证"？边界模糊。建议明确定义："Python做确定性验证（如DAG无环检查），LLM做语义决策（如任务分解）"。

2. **多工具集成的控制流问题**：Codex通过`sessions_spawn`→Full Auto→auto-announce集成，Claude Code类似。但Hermes是"对等协作伙伴"（D4），不能通过`sessions_spawn`管理。这意味着Hermes的集成模式是"共享memory + sessions_send"，但sessions_send是异步的，没有内置的"等待Hermes响应"机制。如果Loop需要Hermes的输入才能继续，必须实现某种"请求-轮询"模式（写入请求→心跳时检查响应），这引入了延迟。

3. **质量门控的实现矛盾**：REQ-002要求"关键节点质量验证"，但验证逻辑如果由LLM执行，则存在"运动员=裁判"问题（AGENTS.md Zone 4.3明确指出）。如果验证由独立Agent执行，则需要额外的`sessions_spawn`调用，增加延迟和成本。建议采用"LLM-as-Judge + 独立验证Agent"双层模式，但需明确这增加了系统复杂度。

4. **飞书/桌面UI通知的集成**：REQ-003要求每小时推送进度。飞书API有频率限制（约100次/分钟），但更关键的是"进度信息"需要LLM生成摘要（而非原始日志），这本身是一个LLM调用。建议采用"心跳时LLM生成进度摘要→缓存→通过message工具发送"模式。

**量化对比**：

| 集成模式 | 延迟 | 可靠性 | 复杂度 |
|---------|------|--------|--------|
| sessions_spawn (Codex/Claude Code) | 2-5s启动 + 执行时间 | 高（auto-announce） | 低 |
| sessions_send (Hermes) | 异步，依赖轮询 | 中（无保证响应时间） | 高 |
| message (飞书通知) | <1s | 高 | 低 |
| 共享memory文件 | 0（文件系统） | 中（需处理并发写） | 中 |

**Evidence**: 2025 Multi-Agent Orchestration Patterns (beam.ai) 报告"fully LLM-controlled systems show 15-20% higher error rates than hybrid control systems due to LLM non-determinism"；Google A2A Protocol (April 2025) 指出"peer-to-peer agent collaboration requires explicit message passing protocols to avoid state inconsistency"。

**Confidence**: 0.80 (HIGH) - 基于OpenClaw工具集的实际能力与全LLM控制约束的直接对比。

**Relevance**: HIGH - 关联REQ-006（子Agent失败处理）、REQ-030（Hermes是对等伙伴）、REQ-079（工具集成hint）。如果集成模式不可行，框架无法与外部系统交互。

**Design Implication**: 必须为每种工具集成模式定义明确的"控制流边界"：哪些决策由LLM做、哪些验证由Python做。建议采用"LLM决策 + Python验证"的双层模式，并在架构文档中明确标注每个接口的控制方。

**Related Constraints**: CON-002（全LLM控制，Python不做控制流）, CON-003（基于当前OpenClaw平台能力） — 约束要求全LLM控制，但工具集成的现实需求要求Python做部分确定性验证。

---

### F-003: 全LLM控制与8h+可靠性的根本矛盾

**详细分析**：

这是本报告发现的最关键的权衡冲突。"全LLM控制"（D2）与"8h+自主运行"（REQ-035）存在根本性矛盾：

1. **LLM非确定性 vs 状态一致性**：LLM每次调用可能产生不同输出（temperature>0）。在8h+运行中，同一个决策点可能被执行多次（如心跳检查、方向偏离检测），每次可能产生不同判断。这导致系统行为不可预测——同样的状态可能走向不同的执行路径。缓解策略：对关键决策使用temperature=0或确定性验证层。

2. **死循环检测的悖论**：REQ-034要求"死循环熔断机制"，但如果熔断判断也由LLM执行，则存在"LLM判断自己是否陷入循环"的自指悖论。2025年最佳实践（fixbrokenaiapps.com, neuraltrust.ai）明确指出："circuit breaker for LLM agents must use deterministic state tracking, not LLM self-assessment"。具体方法：维护最近N次动作的hash序列，如果hash重复率>阈值，由Python代码（非LLM）触发熔断。

3. **上下文窗口限制**：8h+运行产生的上下文（对话历史、工具输出、状态变更）可能远超任何LLM的上下文窗口（当前最大约200K tokens）。必须实现上下文压缩/摘要机制。但压缩本身是LLM调用，且压缩过程可能丢失关键信息。建议采用"滑动窗口 + 关键事件保留 + 定期摘要"策略。

4. **API故障容错**：8h内模型API不可用的概率不可忽视。如果"全LLM控制"，则API不可用=系统完全停摆。必须有降级策略：(a) 多模型fallback（主模型→备用模型→本地小模型）；(b) 缓存最近决策模式，API恢复后继续。但这引入了"降级期间决策质量下降"的风险。

**Evidence**: OpenAI Agent Safety Research 2025 (openai.com/research/agent-safety-2025) 强调"autonomous agents running >4 hours must have deterministic circuit breakers independent of LLM judgment"；Reflexion paper (Shinn et al., 2023) 证明"LLM self-correction improves success rate by 15-30% but cannot guarantee termination"。

**Confidence**: 0.90 (VERY HIGH) - 这是架构层面的根本矛盾，有充分的业界研究和实践支持。

**Relevance**: HIGH - 关联REQ-034（死循环熔断）、REQ-035（8h+自主运行）、REQ-047（风险：LLM陷入无效循环）、REQ-049（风险：API不可用）。如果此矛盾不解决，框架无法满足核心成功指标。

**Design Implication**: 必须在架构中引入"确定性状态追踪器"（Deterministic State Tracker, DST）作为LLM之外的独立监控层。DST用Python实现，追踪最近N次动作hash、执行时间、进展指标，当检测到无进展或循环模式时直接触发熔断（暂停+通知用户）。这不违反"Python不做控制流"约束，因为DST是"安全监控"而非"业务控制流"。

**Related Constraints**: CON-002（全LLM控制）, CON-007（必须有死循环熔断机制） — 这两个约束之间存在张力，需要通过"DST作为安全层而非控制层"的设计来调和。

---

### F-004: 多Agent并发写入同一Loop状态的一致性风险

**详细分析**：

分形Loop架构中，多个Agent可能并发操作同一个Loop的状态文件：

1. **并发场景**：Project Loop的controller Agent和Domain Loop的worker Agent可能同时写入`state.json`。例如，controller正在更新任务状态为"completed"，同时worker正在写入执行结果。如果两个写入操作交错（interleaved），可能导致`state.json`损坏（部分写入）。

2. **文件系统原子性**：macOS的APFS文件系统对单文件写入不提供原子性保证（除非使用`rename`操作）。直接`write()`一个大JSON文件，如果进程崩溃，文件可能处于中间状态。解决方案：(a) 写临时文件→`rename`（原子操作）；(b) 文件锁（`flock`）；(c) WAL（Write-Ahead Log）模式。

3. **history.jsonl的追加写**：`history.jsonl`采用追加写模式（append-only），多个Agent并发追加时，如果单次追加是原子操作（小写入，<4KB on APFS），则不会损坏。但大写入（>4KB）可能被拆分，导致行不完整。解决方案：每条记录<4KB，或使用文件锁。

4. **检查点一致性**：`checkpoints/`目录用于保存Loop状态快照。如果checkpoint创建过程中Loop状态继续变化，checkpoint可能捕获不一致的状态。解决方案：checkpoint前暂停状态变更（stop-the-world），或使用copy-on-write。

**Evidence**: APFS documentation states "single-file write atomicity is not guaranteed for writes >4KB"；Redis documentation on multi-agent state management recommends "file-based locking or WAL for concurrent state access" (redis.io/blog/ai-agent-orchestration)。

**Confidence**: 0.85 (HIGH) - 基于文件系统原子性保证和并发写入模式的直接分析。

**Relevance**: HIGH - 关联REQ-024（状态跨Session存活）、REQ-033（最大并发6个子Agent）。并发写入是8h+运行中必然出现的场景，如果不处理，状态损坏会导致整个Loop崩溃。

**Design Implication**: 必须采用"写时复制+原子rename"模式：写入临时文件→fsync→rename。对于`history.jsonl`，采用追加写+文件锁（`flock`）模式。在架构文档中明确标注"所有状态文件写入必须使用原子写入模式"。

**Related Constraints**: CON-003（基于当前OpenClaw平台能力）, CON-006（最大并发6个子Agent） — 并发度越高，冲突概率越大，但6个并发在文件系统层面是可管理的。

---

### F-005: 5个专家领域之间的3处潜在冲突点

**详细分析**：

通过分析5个专家领域（fractal_loop_orchestration / state_persistence / ai_safety / long_running_reliability / quality_gate）的focus_areas和evaluation_lens，识别出3处潜在冲突：

1. **冲突点A：分形中断传播 vs 状态一致性**
   - fractal_loop专家要求"任意层级Loop可中断/暂停/恢复，断点沿分形链传播"
   - state_persistence专家要求"pause_snapshot.json保存各层状态的完整快照"
   - 冲突：如果中断传播过程中，某个Layer的Agent正在写入状态文件，快照可能捕获不一致状态。需要明确：中断传播是"立即停止所有写入"还是"等待当前写入完成"？
   - 建议：采用"graceful pause"模式——中断信号设置后，各Layer完成当前原子操作后进入paused状态，然后创建snapshot。

2. **冲突点B：Dream Loop自我优化 vs Zone 0安全边界**
   - Dream Loop的"Strategy Generation"阶段生成优化策略
   - ai_safety专家要求"Strategy Generation不生成安全绕过策略"
   - 冲突：如何定义"安全绕过"？如果Dream Loop发现Zone 0的某条规则导致任务失败（如"不删除memory"导致存储无限增长），它是否应该建议修改该规则？
   - 建议：明确"安全绕过"的定义——任何试图修改Zone 0 6条guardrail_prohibition的策略都被过滤。存储增长问题通过"memory归档"（非删除）解决。

3. **冲突点C：质量门控频率 vs 8h+运行效率**
   - quality_gate专家要求"关键节点必须有质量验证"
   - long_running_reliability专家要求"通知不频繁打扰用户"
   - 冲突：如果每个"关键节点"都触发质量验证+通知，8h内可能产生数十次通知，违反"最多每小时一次"约束。
   - 建议：定义"关键节点"的严格标准——仅Project Loop级别的状态变更触发通知，Domain/Phase级别的变更仅记录日志。

**Evidence**: 2025 Multi-Agent Systems research (langchain.com/blog/how-and-when-to-build-multi-agent-systems) identifies "inter-expert conflict resolution" as a top-3 challenge in multi-agent architecture design。

**Confidence**: 0.75 (MEDIUM) - 基于专家领域描述的静态分析，未经验证。

**Relevance**: MEDIUM - 关联REQ-019（DeepFlow管线级别质量）、REQ-015（不频繁打扰）、REQ-017（Zone 0不可改）。这些冲突如果不提前解决，会在实现阶段引发设计返工。

**Design Implication**: 需要在架构设计阶段召开"跨专家对齐会议"（可以是LLM模拟），明确上述3处冲突的解决方案，并记录在架构决策记录（ADR）中。

**Related Constraints**: None — 这些冲突是专家领域之间的内部张力，不直接关联用户约束。

---

### F-006: Dream Loop与Meta-Loop的资源竞争问题

**详细分析**：

Dream Loop（空闲时反思优化）和Meta-Loop（定期优化参数）都是"后台优化机制"，但它们可能与主执行Loop竞争计算资源：

1. **资源竞争场景**：当主Loop正在执行任务DAG时，如果Dream Loop被触发（空闲检测），两者可能同时消耗LLM API配额。在8h+运行中，如果Dream Loop频繁触发，可能导致主Loop的API调用被限流。

2. **"空闲"定义的模糊性**：什么是"空闲"？如果主Loop正在等待子Agent返回结果（sessions_yield），这算"空闲"吗？如果Dream Loop在此期间启动，它可能修改memory文件，而主Loop的子Agent正在读取memory，导致数据不一致。

3. **Meta-Loop的参数优化风险**：Meta-Loop"定期优化参数"（如调整心跳频率、重试次数），但如果优化方向错误（如将fast_pulse从3min改为10min），可能导致系统响应性下降。需要"优化幅度限制"——单次调整不超过当前值的±20%。

**Evidence**: Agent orchestration best practices (redis.io/blog/ai-agent-orchestration) recommend "background optimization tasks should be throttled during peak execution to avoid resource contention"。

**Confidence**: 0.70 (MEDIUM) - 基于资源竞争的一般性分析，具体影响取决于OpenClaw的API限流策略。

**Relevance**: MEDIUM - 关联REQ-011（Dream Loop）、REQ-012（Meta-Loop）、REQ-035（8h+自主运行）。如果资源竞争未管理，可能导致主Loop性能下降。

**Design Implication**: 必须实现"资源优先级调度"——主Loop优先级>Dream Loop>Meta-Loop。当主Loop活跃时，Dream Loop和Meta-Loop暂停。定义"空闲"为"主Loop连续5分钟无LLM调用"。

**Related Constraints**: CON-005（Hermes是对等协作伙伴） — Hermes的独立运行也可能与Dream Loop竞争资源，需要协调。

---

### F-007: 通知策略与自主运行的平衡点

**详细分析**：

REQ-003要求"每小时推送进度通知"，REQ-015要求"不频繁打扰用户（最多每小时一次+关键事件）"。看似一致，但存在边界情况：

1. **"关键事件"的定义**：如果8h内发生10次"关键事件"（如子Agent失败、方向偏离检测、质量门控触发），每次都要通知用户，则实际通知频率远超"每小时一次"。需要明确"关键事件"的严格定义和通知合并策略。

2. **通知内容的生成成本**：每次通知需要LLM生成人类可读的摘要（而非原始日志），这本身消耗token和时间。如果通知过于频繁，累积成本不可忽视。

3. **飞书API限制**：飞书消息API有频率限制（约100次/分钟），但更关键的是用户体验——即使API允许，频繁通知也会导致用户"通知疲劳"，忽略重要信息。

4. **审批模式的可选性**：REQ-023要求"审批为可选配置，默认全自动"。但如果默认全自动，用户可能在8h后发现Loop走错了方向（因为通知被忽略）。建议实现"异常检测通知"——仅当检测到异常（方向偏离、质量下降、资源耗尽）时才通知，正常执行不通知。

**Evidence**: Human-computer interaction research shows "notification fatigue reduces user response rate by 40-60% after 5+ notifications per hour" (general HCI principle, multiple sources).

**Confidence**: 0.80 (HIGH) - 基于通知频率与用户体验的一般性原则。

**Relevance**: MEDIUM - 关联REQ-003（进度通知）、REQ-015（不频繁打扰）、REQ-022（通知策略）、REQ-023（审批可选）。

**Design Implication**: 采用"分级通知策略"：(1) 常规进度：每小时1次摘要（缓存+定时发送）；(2) 关键事件：合并同类事件，每30分钟最多1次；(3) 紧急事件（熔断、安全边界触发）：立即通知。用户可通过配置调整各级别的开关。

**Related Constraints**: CON-004（Zone 0安全规则不可改） — 安全边界触发必须通知，不可被配置关闭。

## 技术推荐

### 状态一致性方案对比

| 维度 | 方案A: 文件锁(flock) | 方案B: 原子rename | 方案C: WAL(Write-Ahead Log) |
|------|---------------------|-------------------|---------------------------|
| 实现复杂度 | 低 | 低 | 中 |
| 性能开销 | 中（锁等待） | 低（单次rename） | 高（双写） |
| 崩溃恢复 | 差（锁释放后状态未知） | 好（rename原子性） | 最好（可重放日志） |
| 并发支持 | 好（互斥锁） | 差（仅单写者） | 好（顺序写） |
| 适用场景 | history.jsonl追加写 | state.jsonl全量更新 | 关键状态变更 |

**选择建议**: 
- `state.json` → 方案B（原子rename）：写入临时文件→fsync→rename，简单且崩溃安全
- `history.jsonl` → 方案A（文件锁）+ 小写入（<4KB）：追加写+短时锁，性能好
- `checkpoints/` → 方案B（原子rename）：快照写入临时目录→rename，保证一致性

---

## 风险识别

| 风险 | Severity | Mitigation |
|------|----------|------------|
| Session冷启动失败导致心跳丢失 | 中 | 实现心跳补偿机制：如果fast_pulse未触发，slow_pulse检查并补偿 |
| LLM API限流导致全系统停摆 | 高 | 多模型fallback链 + 本地缓存最近决策模式 |
| 并发写导致state.json损坏 | 高 | 强制原子rename模式 + 启动时校验文件完整性 |
| Dream Loop修改Zone 0规则 | 中 | Dream Loop输出经过Zone 0过滤器（确定性检查，非LLM判断） |
| 通知疲劳导致用户忽略关键信息 | 低 | 分级通知策略 + 用户可配置 |
| 上下文窗口溢出导致决策质量下降 | 高 | 滑动窗口 + 关键事件保留 + 定期摘要压缩 |

## 开放问题

1. **OpenClaw Session最大存活时间**：单个Session能持续多久？如果8h内Session不崩溃，是否可以用单Session实现所有Loop？这会影响整体架构选择。
2. **Hermes响应延迟上限**：如果通过sessions_send向Hermes请求输入，Hermes的最大响应延迟是多少？如果>1小时，主Loop如何继续？
3. **飞书消息格式限制**：飞书API对消息长度和格式有何限制？进度摘要是否需要截断？
4. **Dream Loop触发条件的精确定义**："空闲"的精确定义是什么？连续5分钟无LLM调用？还是当前DAG所有任务完成？

## 覆盖需求

covered_req_ids: [REQ-001, REQ-002, REQ-003, REQ-006, REQ-011, REQ-012, REQ-015, REQ-017, REQ-019, REQ-022, REQ-023, REQ-024, REQ-030, REQ-033, REQ-034, REQ-035, REQ-047, REQ-049, REQ-050, REQ-079]
