# Phase 3 — 忠礼模拟验收报告

> 验收人视角：姬忠礼（忠礼）
> 验收日期：2026-06-19
> 验收对象：Ship Pro V3 Phase 2 输出（3 个 E2E Case 的 ship_package）

---

## 总体判定：CONDITIONAL

Case 1 有风险登记簿空字段需修复；Case 2、Case 3 通过。总体 CONDITIONAL——Case 1 修完风险登记簿即可全部 ACCEPTED。

---

## Case 1: 企业AI客服（12 组件 → 8 WP）

### "这个 WP 给 Codex 能干活吗？"

| WP | objective 清晰度 | context_files | outputs | AC 可判 | 忠礼判定 |
|----|:---:|:---:|:---:|:---:|:---:|
| WP-001 数据层 | ✅ 四大能力+跨AZ | ✅ blueprint+设计文档 | ✅ 5个具体文件 | ✅ 5条全L4 | 能干 |
| WP-002 API网关 | ✅ 流量治理+分层超时 | ✅ blueprint+wp_specs+网关文档 | ✅ 6个配置文件 | ✅ 5条全L4 | 能干 |
| WP-003 合规 | ✅ GDPR/PIPL/EU AI Act | ✅ blueprint+合规需求+GDPR清单 | ✅ 7个文件 | ✅ 5条L3+L4 | 能干 |
| WP-004 多渠道 | ✅ 5种渠道→CloudEvents | ✅ blueprint+wp_specs+渠道规格 | ✅ 7个文件 | ✅ 4条L3+L4 | 能干 |
| WP-005 对话引擎 | ✅ ≥20轮+<50ms+50+意图 | ✅ blueprint+wp_specs+2个设计文档 | ✅ 7个文件 | ✅ 5条L3+L4 | 能干 |
| WP-006 RAG+LLM | ✅ 混合检索+三级路由 | ✅ blueprint+wp_specs+2个设计文档 | ✅ 12个文件 | ✅ 6条L3+L4 | 能干 |
| WP-007 人工坐席 | ✅ Warm Transfer+AI建议 | ✅ blueprint+wp_specs+转接设计 | ✅ 7个文件+前端 | ✅ 5条L3 | 能干 |
| WP-008 CRM集成 | ✅ Event Sourcing+CQRS+3 CRM | ✅ blueprint+wp_specs+集成规格 | ✅ 10个文件 | ✅ 6条L3+L4 | 能干 |

**结论：8 个 WP 全部"能干"。** objective 清晰，context_files 指向明确，outputs 具体到文件路径，AC 全部带验证命令和量化阈值。Codex/Claude Code 拿到任何一个 WP 都能直接开工。

### "AC 是不是在说人话？"

| 最好的 AC | 最差的 AC | 忠礼评语 |
|-----------|-----------|---------|
| WP-001 AC-2："Milvus P99 < 50ms，命令 `python3 benchmarks/milvus_benchmark.py --collection=faq --queries=10000 --topk=10`" | WP-007 AC-2："Warm Transfer 完整上下文包传递"（验证命令输出描述是枚举而非量化） | WP-001 到 WP-006 的 AC 质量很高——每条都有命令、有阈值、有通过条件。WP-007 略弱，"完整上下文包传递"的验证应该检查 6 个字段是否都存在，而不是只说"包含"。但整体 88 分，没有废话。 |

**AC 质量分布**：L4（可执行命令）23 条，L3（具体阈值）18 条，L2 零条，L1 零条。这是真验收标准，不是装饰。

### "信息有没有丢失？"

| 输入核心信息 | ship_package 中能找到吗 | 状态 |
|------------|:---:|:---:|
| 12 个组件（COMP-001~012） | ✅ 全部映射到 8 个 WP 的 related_modules | ✅ |
| 7 个需求（REQ-001~007） | ✅ requirements_coverage 100%，每个 WP 有 requirements 字段 | ✅ |
| 6 层架构分层 | ✅ project_context.architecture.layers 完整保留 | ✅ |
| SLA 约束（10 项） | ✅ 全部传递到各 WP 的 constraints 字段 | ✅ |
| 三级模型路由（L0~L4） | ✅ WP-006 AC-4 明确列出 5 级路由 | ✅ |
| 置信度评分公式 | ✅ WP-005 AC-5 完整公式 | ✅ |
| 人转接触发条件（4 条） | ✅ WP-007 constraints 完整传递 | ✅ |
| 上下文包内容（6 项） | ✅ WP-007 AC-2 + constraints 完整 | ✅ |
| 合规分层保留策略 | ✅ WP-003 constraints 完整 | ✅ |
| 实施计划（9 个月 5 阶段） | ✅ summary 中有实施计划概览 | ✅ |
| 成本分析 | ✅ summary 中有 CAPEX/OPEX 估算 | ✅ |
| 8 个风险项 | ⚠️ risk_register 有 8 项但 **mitigation 全部为空** | ❌ |

**信息丢失评估**：11/12 项完整传递。唯一问题是风险登记簿的 mitigation 字段全部为空。这不是"信息丢失"，是"信息没生成"。风险描述本身是完整的，但缺了缓解措施——执行者遇到风险时不知道怎么办。

### 忠礼点评

> "8 个 WP 拆得干净。12 个组件→8 个 WP，没有过度拆分也没有遗漏。AC 质量让我满意——41 条 AC 全部 L3+，每条都有验证命令，我拿起来就能跑。依赖图合理，关键路径 WP-001→002→005→006 清晰，并行组也安排得当。
>
> 但有一个问题不能忽视：**8 个风险的 mitigation 全是空的**。RISK-001 说'EU AI Act 合规截止日逼近'，mitigation 是空字符串。这等于告诉执行者'有个雷，但我不告诉你怎么绕'。不可接受。
>
> 输入方案里明确写了缓解策略——'非EU优先上线'、'Qwen自托管为主+GPT兜底'、'KV Cache复用+分层超时降级'——这些信息在 ship_package 的 constraints 和 summary 里都能找到，但 risk_register 里一个字没有。risk_register 是给执行者看的风险手册，mitigation 为空等于废纸。
>
> 另外，summary 里的复杂度分布写 'Critical(complex): 4个' 但列了 5 个 WP（001/003/005/006/008），而实际 complexity 字段值是 'complex' 不是 'critical'。这是 schema 一致性问题，不影响执行但影响信任。"

---

## Case 2: 智能简历生成系统（8 组件 → 6 WP）

### "这个 WP 给 Codex 能干活吗？"

| WP | objective 清晰度 | context_files | outputs | AC 可判 | 忠礼判定 |
|----|:---:|:---:|:---:|:---:|:---:|
| WP-001 输入解析 | ✅ 多格式解析+真相源 | ✅ blueprint+输入格式规格 | ✅ 6个文件+测试目录 | ✅ 6条L3+L4 | 能干 |
| WP-002 JD匹配+知识库 | ✅ 三层匹配35/45/20+30术语 | ✅ blueprint+解析器输出+知识库数据 | ✅ 8个文件+测试目录 | ✅ 7条L3+L4 | 能干 |
| WP-003 优化器+保真度 | ✅ 安全范围优化+分级自检 | ✅ blueprint+解析器+匹配器+知识库 | ✅ 9个文件+测试目录 | ✅ 6条L3+L4 | 能干 |
| WP-004 IR Schema | ✅ 扩展JSON Resume+3个新字段 | ✅ blueprint+优化器+匹配器 | ✅ 6个文件+测试目录 | ✅ 5条L3+L4 | 能干 |
| WP-005 双格式渲染 | ✅ DOCX+PDF+ATS>95% | ✅ blueprint+IR Schema | ✅ 6个文件+测试目录 | ✅ 6条L3+L4 | 能干 |
| WP-006 ATS评分 | ✅ 三维评分40/30/30+可解释 | ✅ blueprint+匹配器+IR Schema | ✅ 6个文件+测试目录 | ✅ 6条L3+L4 | 能干 |

**结论：6 个 WP 全部"能干"。** 线性依赖链 WP-001→002→003→004→005 清晰直接，WP-006 可与 WP-005 并行。每个 WP 的 objective 一句话说清楚要做什么，context_files 告诉执行者该读什么，outputs 精确到文件名。

### "AC 是不是在说人话？"

| 最好的 AC | 最差的 AC | 忠礼评语 |
|-----------|-----------|---------|
| WP-002 AC-2："三层匹配权重 0.35×关键词 + 0.45×语义 + 0.20×术语 的加权结果与系统输出误差 < 0.01" | WP-001 AC-4："DOCX 解析段落数与原始文档一致"（验证命令是 Python one-liner，不够严谨——应该用测试框架） | WP-002 的权重验证是教科书级 AC：公式明确、阈值量化、验证命令可执行。WP-003 的安全范围验证"优化后无新增量化指标/项目/职责，安全违规数=0"也很好——直接验证了"不造假"这个核心承诺。整体 77.8 分比 Case 1 低一些，但仍然是 L3+ 水平，没有废话。 |

### "信息有没有丢失？"

| 输入核心信息 | ship_package 中能找到吗 | 状态 |
|------------|:---:|:---:|
| 8 个组件（COMP-01~08） | ✅ 全部映射到 6 个 WP | ✅ |
| 6 个需求（REQ-001~006） | ✅ requirements_coverage 100% | ✅ |
| 三层可降级架构（Tier 1/2/3） | ✅ constraints 中有速度/依赖/保真度指标 | ✅ |
| 保真度阈值（95%/90%/85%） | ✅ WP-003 AC-4 完整传递 | ✅ |
| 安全优化范围（仅结构化+术语替换） | ✅ WP-003 AC-2 "无新增量化指标/项目/职责" | ✅ |
| 三层匹配权重（35/45/20） | ✅ WP-002 AC-2 完整公式 | ✅ |
| 行业知识库（30+术语/20+工具/10+标准） | ✅ WP-002 AC-5 量化验证 | ✅ |
| ATS 三维评分（40/30/30） | ✅ WP-006 AC-2 完整公式 | ✅ |
| 免责声明 | ✅ WP-006 AC-5 | ✅ |
| source_tag 溯源标签 | ✅ WP-003 AC-3 | ✅ |
| 双格式渲染（DOCX+PDF） | ✅ WP-005 | ✅ |
| 字体回退三策略 | ✅ WP-005 AC-4 | ✅ |
| 代码行数约束（5000-6000行） | ⚠️ constraints 中未显式出现 | ⚠️ |
| 依赖数量约束（≤6/8） | ⚠️ constraints 中未显式出现 | ⚠️ |
| 2 个 known_gaps | ✅ project_context.known_gaps 有记录 | ✅ |
| 5 个风险+缓解策略 | ✅ risk_register 完整，mitigation 非空 | ✅ |

**信息丢失评估**：14/16 项完整，2 项⚠️。代码行数和依赖数量约束在输入方案中反复强调（"轻量级"、"≤6包/0API"、"代码<5000-6000行"），但 ship_package 的 WP 级 constraints 没有显式传递这两个约束。执行者可能不知道整体代码量上限。不过这两个约束更多是项目级约束而非 WP 级约束，放在 project_context.constraints 里也说得过去。

### 忠礼点评

> "这个 ship_package 让我舒服。6 个 WP 线性排列，依赖关系简单清晰，关键路径一目了然。每个 WP 的 AC 都带着具体的测试命令和量化阈值——WP-002 的权重验证误差 < 0.01、WP-003 的安全违规数 = 0、WP-005 的 ATS 字段提取成功率 ≥ 95%——这些都是'通过/不通过'的硬标准，没有模糊空间。
>
> 最让我满意的是 WP-003（优化器+保真度自检器）。输入方案的核心差异化是'零造假保真度承诺'，WP-003 的 AC-2 直接验证'优化后无新增量化指标/项目/职责，安全违规数=0'。这不是在说'请尽量保持真实性'，而是在说'违规数必须为零'。这才叫验收标准。
>
> 两个小问题：代码行数约束（5000-6000行）和依赖数量约束（≤6/8）没有在 WP 级 constraints 里出现。这两个是项目级约束，放在 project_context 里也行，但如果能在 WP-005（最后一个渲染 WP）的 constraints 里加一句'全项目代码量 < 6000 行'，执行者会更清楚边界。
>
> risk_register 的 mitigation 都有内容，这点比 Case 1 好。known_gaps 也诚实记录了两个未决问题。整体质量过关。"

---

## Case 3: 单模块TODO应用（1 组件 → 1 WP）

### "这个 WP 给 Codex 能干活吗？"

| WP | objective 清晰度 | context_files | outputs | AC 可判 | 忠礼判定 |
|----|:---:|:---:|:---:|:---:|:---:|
| WP-001 CRUD | ✅ 增删改查+筛选+本地存储 | ❌ 空数组 | ✅ 7个具体文件 | ✅ 6条可验证 | 能干 |

**结论：1 个 WP，能干活。** 对于一个 TODO 应用，1 个 WP 是唯一正确的选择。拆成 2 个就是过度工程。

### "AC 是不是在说人话？"

| 最好的 AC | 最差的 AC | 忠礼评语 |
|-----------|-----------|---------|
| AC-1："至少 8 个测试通过，覆盖率 ≥ 80%" + AC-3："点击完成复选框后 1 秒内 UI 显示删除线，localStorage 中 completed 字段更新为 true" | AC-6："应用首次加载时间 < 2 秒（Lighthouse Performance Score ≥ 90）" 与 AC-2 重复 | AC-3 最好——行为级验证，说的是用户操作和系统响应的因果关系，不是抽象指标。AC-2 和 AC-6 说的是同一件事（首次加载 < 2 秒），重复了。对于一个 TODO 应用来说，6 条 AC 足够，但不该有重复。 |

### "信息有没有丢失？"

| 输入核心信息 | ship_package 中能找到吗 | 状态 |
|------------|:---:|:---:|
| 3 个需求（新增/完成/删除） | ✅ requirements 字段覆盖 | ✅ |
| React 技术栈 | ✅ constraints 明确 | ✅ |
| SQLite/localStorage 存储 | ✅ constraints 明确 | ✅ |
| 单页应用架构 | ✅ constraints 明确 | ✅ |
| 1 个低风险项 | ✅ risk_register | ✅ |

**信息丢失评估**：5/5 项完整。无丢失。

### 忠礼点评

> "一个 TODO 应用，1 个 WP，够了。谁要是把这个拆成 3 个 WP，我会问他是不是想混工时。
>
> 但有两个问题值得指出。第一，context_files 是空数组——虽然 TODO 应用不需要复杂的设计文档，但至少应该有一个 `blueprint.json` 或需求说明文件告诉执行者这个应用从哪来。第二，AC-2 和 AC-6 重复了——都是说首次加载 < 2 秒，应该合并成一条，把省出来的位置给'筛选器切换后列表即时更新（< 100ms）'这种更有价值的验证。
>
> 这些都是小事。对于一个 simple 级别的单 WP 项目，这个 ship_package 完成了它该做的事。"

---

## 忠礼最终判定

> "三个 Case，复杂度跨度从 1 个组件到 12 个组件，ship_package 都能接住。WP 拆分合理，AC 质量整体在 L3+ 水平，依赖图无环无孤立节点，需求覆盖率三个 100%。这说明 Phase 2 的核心逻辑——从架构方案到可执行工作包的转换——是通的。
>
> 但 Case 1 暴露了一个系统性问题：**risk_register 的 mitigation 全部为空**。8 个风险，0 个缓解措施。这不是'忘了填'的问题——输入方案里有完整的缓解策略，它们在转换过程中没有被传递到 risk_register。如果执行者只看 risk_register 来了解风险应对方案，他会一无所知。这个问题必须在 Phase 2 修复。
>
> Case 2 和 Case 3 通过。Case 2 的 AC 质量尤其好——WP-003 的安全违规数=0、WP-002 的权重误差<0.01，这些都是'声称≠完成，证据=完成'的体现。Case 3 虽然简单，但简单项目就该有简单的 ship_package，不过度拆分本身就是正确的架构决策。
>
> 总体判定：**CONDITIONAL**。Case 1 修复 risk_register.mitigation 后，全部 ACCEPTED。"

---

## 必须修复的问题

1. **Case 1 risk_register.mitigation 全部为空**（8 个风险项，0 个有缓解措施）
   - 输入方案里有完整的缓解策略（非EU优先上线、Qwen自托管+GPT兜底、KV Cache复用+分层超时降级等），需要传递到 risk_register
   - 这是数据丢失 bug，不是设计问题

## 可以改进但不阻塞的

1. **Case 1 summary 复杂度分布计数不一致**：`complexity_distribution` 写 "Critical(complex): 4个" 但列了 5 个 WP，且 complexity 字段值是 "complex" 不是 "critical"——schema 术语需统一
2. **Case 2 项目级约束未下沉到 WP**：代码行数（<5000-6000行）和依赖数量（≤6/8）约束在 project_context.constraints 里有，但没有传递到任何 WP 的 constraints——建议至少在一个 WP 里显式引用
3. **Case 3 context_files 为空**：虽然简单项目不需要复杂文档，但空数组不如放一个 `blueprint.json` 或 `requirements.md`
4. **Case 3 AC-2 与 AC-6 重复**：都是"首次加载 < 2 秒"，应合并
5. **Case 1 WP-007 AC-2 验证命令可改进**："包含完整对话 transcript、意图识别结果..." 应该改为逐字段检查（`assert len(fields) == 6`），而不是只说"包含"
6. **Case 1 WP-008 AC-3 过于宽松**：`grep -E "event_sourcing|cqrs" services/crm/crm_adapter.py` 只检查关键字出现，不检查实现质量——建议改为检查测试通过率

---

*验收人：忠礼（模拟）*
*验收标准：WP 可执行性 + AC 可判性 + 信息完整性 + 人类可理解性*
*判定依据：证据，不声称*
