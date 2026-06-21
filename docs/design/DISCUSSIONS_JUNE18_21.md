# DeepFlow 关键讨论与决策记录 (2026-06-18 ~ 2026-06-21)

> 从 session 日志中自动提取，覆盖 4 天内与 DeepFlow 项目相关的关键讨论、决策和产出。

---

## 按日期组织

### 6月18日

#### 主题1: Ship Pro V3 定位与 AI Native 方向讨论
- **用户指示**: 忠礼提出 Ship Pro 的定位问题——Solution Pro 是通用型模块出方案，Ship Pro 负责把方案变成"施工图纸"。讨论 Ship Pro 是否必须存在，最终确认 Ship Pro 作为"通用接口中间层"的价值。
- **讨论过程**: 
  - 忠礼质疑 Ship Pro 是否"脱裤子放屁"，经过分析后确认其必要性
  - 核心定位：Solution Pro → 出 idea/方案（通用），Ship Pro → 方案变施工图纸（编码导向）
  - 忠礼多次强调要用 **AI Native 方式**做事，对当前方案中"非 AI Native"的做法表示不满
  - 讨论 Solution IR 是否是 AI Native 的设计语言，忠礼表示质疑
- **关键决策**: 
  - ✅ Ship Pro 保留，定位为 Solution Pro 到执行层的转换中间层
  - ✅ Solution Pro 主要作用：出 idea 出方案
  - ✅ Ship Pro 主要作用：把方案变成具体施工图纸（WP + AC + 工时 + 约束）
  - ✅ Ship Pro 不挑输入，负责整合 Solution Pro 的各种输出
- **产出文件**: `docs/research/2026-06-18_ship_pro_v3_development_plan.md`

#### 主题2: AI Native 价值观与 Skill 更新
- **用户指示**: 忠礼要求搜索业界 AI Native 先进经验，召集 5-6 个不同模型的专家进行评审，更新 AI Native skill / SOUL.md / AGENTS.md。
- **讨论过程**:
  - 忠礼批评当前 AI Native skill 更新"太敷衍"
  - 要求搜索 Karpathy、Anthropic、OpenAI 等最新 AI Native 理念
  - 讨论"专家评审"本身是否应该用 AI Native 方式——"都 AI native 了为什么还要项目管理专家评估时间估算？"
  - 提出需要让 AI 在下意识层面就想到用 AI Native 方式做事
- **关键决策**:
  - ✅ 召集多模型专家团队（5-6 个 Agent）评审架构设计
  - ✅ AI Native skill 需要基于系统洞察重新更新，不能一股脑堆砌
  - ✅ 需要在记忆中建立约束，让"AI Native"成为默认思维方式
  - ✅ 搜索了 Karpathy Software 3.0、Anthropic、OpenAI、Microsoft、Google 2025-2026 AI Native 理念
- **产出文件**: `docs/research/2026-06-18_ai_native_redesign_proposal.md`, 多份专家报告在 `docs/research/2026-06-18_expert_reports/`

#### 主题3: Ship Pro V3.2 开发与专家评审
- **用户指示**: 忠礼要求按 AI Native 方式召集专家评审 Ship Pro V3.2 方案，然后开始开发。
- **讨论过程**:
  - 忠礼批评专家评审"很业余"——给专家的提示词太差，发挥空间太小
  - 要求专家评审要有任务名称、完成状态要醒目
  - 讨论了是否用"变色龙"方式——忠礼提醒要保持客观中立
- **关键决策**:
  - ✅ Ship Pro V3.2 采用 5 Agent 协作架构：Architect → Decomposer → Specifier → Reviewer → Packager
  - ✅ 基于 `sessions_spawn` + `sessions_yield` 的 push-based 编排
  - ✅ 配置 `maxSpawnDepth: 2`，Workers 用便宜模型
  - ✅ 小项目（≤3 WP）自动降级为单 Agent 模式

#### 主题4: Solution Pro 输出格式分析 (Format A/B/C)
- **用户指示**: 忠礼要求分析 Blackboard 中多个 Solution Pro 输出的实际格式差异。
- **讨论过程**:
  - 发现三种 Solution Pro 输出格式：
    - **Format A（final_solution 嵌套型）**：智能简历、中小企业客服、Serenity Skills — 架构信息包裹在 `final_solution.detailed_solution.architecture`
    - **Format B（顶层扁平型）**：跨境AI、企业级客服、电商订单 — 架构信息在顶层 `architecture`
    - **Format C（最小型）**：dryrun、验证PipelineOrchestra — 仅元数据，无架构信息
  - Architect Agent 需要从不同格式中提取统一的架构描述
- **关键决策**:
  - ✅ Architect Agent 负责格式归一化 + 架构识别 + 模块依赖分析
  - ✅ 建议拆出 FormatNormalizer 作为前置步骤（或用确定性代码预处理）

#### 主题5: DeepFlow 命名讨论
- **用户指示**: 忠礼提出不要用"DeepFlow"做产品名，DeepFlow 是品牌，需要另取名字。
- **关键决策**:
  - ✅ 命名格式：形容词+动词 或 形容词+名词
  - ✅ 不用"Deep"前缀

#### 主题6: 契约笼子 (Contract Cage) 设计讨论
- **用户指示**: 忠礼要求按 AI Native 方式设计契约笼子，专家评审后直接执行开发。
- **讨论过程**:
  - 讨论了 Harness 质量门控的设计
  - 确认用"确定性优先（能用代码做的不用LLM）"原则
  - 事件采集不能阻断管线（best-effort）
- **关键决策**:
  - ✅ 直接按长期方案搞，先专家评审再执行
  - ✅ AI Native 开发方式
  - ✅ 不引入外部基础设施，SQLite 存储

---

### 6月19日

#### 主题1: Ship Pro V3 多 Agent 管线测试
- **用户指示**: 执行 Ship Pro V3 的完整 5-Agent 管线测试，使用真实输入数据。
- **讨论过程**:
  - 大量 subagent 被 spawn 执行 Architect、Decomposer、Specifier、Reviewer、Packager 角色
  - 测试了多个案例（TODO、智能简历、AI客服、跨境AI等）
  - 发现 ENOENT 错误问题（路径注入问题）
- **关键决策**:
  - ✅ Fix-1：扩展 `prepare_pipeline` 的 `.replace()` 注入 `{prompts_dir}` + `{deepflow_root}` → 解决 20 次 ENOENT
  - ✅ Fix-2：orchestrator prompt 中增加"读取前先检查存在"的时序保护 → 解决 6 次 ENOENT
  - ✅ Fix-3：验证逻辑增加"空文件/解析失败 → 等 3 秒重试" → 解决 4 次竞态 ENOENT

#### 主题2: REQ 去重方案讨论
- **用户指示**: 忠礼提出 Reviewer 阶段开始做去重，Consolidator 做跨领域去重。认为当前方案不是 AI Native。
- **讨论过程**:
  - 忠礼：reviewer 阶段就开始做去重，Consolidator 做跨领域去重
  - 讨论了领域内去重 vs 跨域去重的分工
  - 当前 3 个 Reviewer 各自输出 54-122 条 REQ，大量重复
- **关键决策**:
  - ✅ Reviewer 负责领域内去重
  - ✅ Consolidator 负责跨域去重
  - ✅ 去重要写入 Reviewer 和 Consolidator 的 prompt
  - ✅ 合并规则：保留最完整的一条，用最低 REQ-ID
  - ✅ 三维检查法：主体+动作+约束（替代模糊的"语义相似度"）
  - ✅ `covered_req_ids[]` 保留全部原始 ID（不丢弃）

#### 主题3: Spec Pro V4.1 修正讨论
- **用户指示**: 评审 Spec Pro V4.1.0 方案，按 AI Native 方式修复。
- **讨论过程**:
  - 识别了 AI Native 认知前提与禁止问题清单的内容重复
  - 讨论了 Step 0 概念理解步骤的可靠性问题
  - "禁止问题清单与评分规则存在内部矛盾：禁止问'技术栈'但技术栈约束占30分"
- **关键决策**:
  - ✅ 改动方向：从"资源导向"转向"约束导向"的评分体系
  - ✅ Step 0 概念理解步骤保留但改进（限制搜索数量）
  - ✅ 修复禁止问题清单的内部矛盾

#### 主题4: Solution Pro 管线运行与 Cron 巡检
- **用户指示**: 启动 Solution Pro 管线，设置 Cron 巡检进度通知。
- **讨论过程**:
  - Solution Pro 10 阶段管线运行
  - 多个 Cron watcher 被设置用于进度通知
  - 发现 Cron 推送格式不统一的问题
- **关键决策**:
  - ✅ 设计统一的管线进度通知格式（Unicode 进度条 + 项目身份 + 紧凑/详细双模式）
  - ✅ 首行即状态：用 ⚡/✅/⚠️ 区分三种状态
  - ✅ 当前阶段突出：▶ 标记，中文名称

---

### 6月20日

#### 主题1: Serenity Skills A股适配 — 全链路质量审查
- **用户指示**: 忠礼要求拿 Serenity Skills A股适配这个真实案例，从 Spec Pro → Solution Pro → Ship Pro 做全链路输出质量审查。
- **讨论过程**:
  - 整理了从 Spec Pro 到 Ship Pro 的所有阶段输出文件
  - 对比了不同版本的输出质量
  - 发现了 task_builder 中 `success_metrics` 类型不匹配的 bug（`list[dict]` vs `list[str]`）
- **关键决策**:
  - ✅ 修复 task_builder 中所有类型不匹配问题
  - ✅ 需要做全链路对齐分析（用户意图→Spec Pro→Solution Pro→Ship Pro 端到端追溯）

#### 主题2: DeepFlow 可观测性系统 — 两次运行对比
- **用户指示**: 忠礼要求对比 DeepFlow 开发者可观测性系统的两次 Ship Pro 运行结果（Run A 去重未生效 vs Run B 去重生效）。
- **讨论过程**:
  - Run A：去重未生效，81 REQ 输入
  - Run B：去重生效，但发现 Solution Pro 分析过程中存在重大缺陷
  - 忠礼：要求找到去重导致差异的源头
  - 多专家对比分析两次 Ship Pro 输出的方案质量
- **关键决策**:
  - ✅ 重点比较 V1 和 V3 的 Ship Pro（共用同一 Living Spec）
  - ✅ 做全链路对齐分析看改进效果
  - ✅ 需要追溯 Solution Pro 分析过程中的去重影响

#### 主题3: Pipeline Watcher 全面 Review
- **用户指示**: 对 Pipeline Watcher 进行全面评审，设计 V2 版本。
- **讨论过程**:
  - 讨论了事件采集管线的架构设计
  - 核心挑战：在不修改 Worker 的前提下实现可靠的事件采集
  - 需要专家设计非阻塞采集、背压处理、故障降级策略
- **关键决策**:
  - ✅ Pipeline Watcher V2 设计：两阶段采集 + 三层 best-effort 防线 + CloudEvents 信封
  - ✅ SQLite 存储模型：5 表设计 + WAL 模式 + 幂等写入
  - ✅ 五层成熟度模型 + 三层分析漏斗
  - ✅ 协议动态适配是架构核心难点
  - ✅ 编写 `pipeline_watcher.py` 脚本

#### 主题4: Cron 稳定性问题
- **用户指示**: 忠礼吐槽 Cron 推送不稳定，Ship Pro 跑完了还持续收到 cron 失败推送。
- **讨论过程**:
  - 多个 cron watcher 失败
  - 主 Agent 在 webchat 会话中错误地硬编码了飞书 open_id
  - Cron 生命周期管理不够可靠
- **关键决策**:
  - ✅ 正确做法：创建 Cron 时设 `delivery.mode = "announce"`，让系统自动路由
  - ✅ 需要系统性复盘 Cron 不稳定问题
  - ✅ 修改步骤顺序：步骤 3 清理 cron → 步骤 4 输出消息（之前步骤 4 永远不可达）

#### 主题5: Ship Pro 信息保真度评审
- **用户指示**: 评审从 final_result.json 到 ship_package.json，信息在 5 个 Agent 传递过程中有没有丢失或扭曲。
- **讨论过程**:
  - 信息增益评估：Ship Pro 相比 Solution Pro 增加了什么有价值的信息？丢失了什么？
  - 下游可消费性评估：AI Coding Agent 拿到 WP 能不能直接开工？
  - 语义保真度评估：Ship Pro 的输出是否忠实保留了 Solution Pro 的原始意图？
- **关键决策**:
  - ✅ WP 结构需要从"人类开发者思维"转向"AI Coding Agent 思维"
  - ✅ 当前 WP 结构缺少 AI Agent 真正需要的结构化字段
  - ✅ outputs/context_files/acceptance_tests 全空是核心问题

#### 主题6: Blackboard 系统设计讨论
- **用户指示**: 评审 DeepFlow Blackboard 重构方案。
- **讨论过程**:
  - 讨论了集中式 vs 分布式控制
  - 当前方案：LLM Orchestrator 做文件 I/O → 仍然不可靠
  - 改为"Orchestrator 集中式控制"模式
- **关键决策**:
  - ✅ 借鉴 Solution Pro 的成熟设计，改为 Orchestrator 集中式控制
  - ✅ 确定性优先（能用代码做的不用 LLM）
  - ✅ Worker 零改动（绝对红线）

---

### 6月21日

#### 主题1: Solution Pro 管线持续运行与监控
- **用户指示**: 继续监控 Solution Pro 管线运行，处理异常告警。
- **讨论过程**:
  - Solution Pro 10 阶段管线运行（DeepFlow 可观测性系统架构设计）
  - 多个 cron watcher 持续巡检
  - 处理阶段失败和重试
- **关键决策**:
  - ✅ 管线进度通知格式统一化
  - ✅ 异常告警机制优化

#### 主题2: REQ 去重效果验证
- **用户指示**: 忠礼要求验证 REQ 去重效果，分析去重的重要性。
- **讨论过程**:
  - 忠礼质疑：100 多个 REQ 中哪些是必须去重的？不去重有什么严重后果？
  - 分析了具体案例中的重复 REQ
  - 21 个合并簇（三维检查法：主体+动作+约束）
  - 去重后从 71 个变成 8 个（忠礼对此表示惊讶）
- **关键决策**:
  - ✅ 去重是显性问题，需要写入 Reviewer 和 Consolidator 的 prompt
  - ✅ 验证脚本：`validate_req_dedup.py` 检查一致性 + 软性去重率警告
  - ✅ 去重安全性验证：`POST /api/login` vs `POST /api/logout` 不能误判

#### 主题3: Ship Pro V3.1.x 迭代测试
- **用户指示**: 执行 Ship Pro V3.1.1 → V3.1.2 → V3.1.3 → V3.1.4 的多轮迭代测试。
- **讨论过程**:
  - V3.1.1: 初始版本
  - V3.1.2: 修复 prompt 问题
  - V3.1.3: 增加 implementation_blueprint 字段
  - V3.1.4: 修复打包器问题
  - 对比 4 个案例的输出，验证每轮修复效果
- **关键决策**:
  - ✅ 每轮迭代用 4 个案例验证
  - ✅ 信息净值评估方法：信息增益 + 语义保真度 + 下游可消费性
  - ✅ 分工逻辑清晰（Architect→Decomposer→Specifier→Packager + Reviewer 旁路审核）

#### 主题4: UI/UX 进度通知设计
- **用户指示**: 忠礼要求找 UI 设计专业团队设计管线进度通知。
- **讨论过程**:
  - 忠礼反馈手机飞书上看进度通知体验差——项目名被截断、状态不醒目
  - UI/UX 设计师出了三套模板
  - 讨论了手机适配问题
- **关键决策**:
  - ✅ 项目名完整显示，不截断
  - ✅ 短别名方案：每个项目设一个短别名（4 字以内）
  - ✅ 手机适配：紧凑模式 + 详细模式
  - ✅ Unicode 进度条 + 项目身份 + 紧凑/详细双模式

#### 主题5: 全链路 E2E 测试
- **用户指示**: 忠礼要求重新跑一次完整的 DeepFlow 流程（Spec Pro → Solution Pro → Ship Pro）。
- **讨论过程**:
  - 用 DeepFlow 可观测性系统任务重新跑全流程
  - 对比新旧版本输出差异
  - 验证修复效果
- **关键决策**:
  - ✅ 全链路 E2E 测试作为质量验证的标准方法
  - ✅ 同一 Living Spec 跑两次对比（A/B 测试）

#### 主题6: Git 仓库管理
- **用户指示**: 忠礼提供 GitHub 仓库地址 `https://github.com/hustfreefly/deepflow.git`
- **关键决策**:
  - ✅ 代码需要推送到 GitHub 仓库备份

---

## 关键决策汇总

| # | 决策 | 日期 | 内容 | 影响 |
|:--|:-----|:-----|:-----|:-----|
| 1 | Ship Pro 定位确认 | 6/18 | Solution Pro 出方案，Ship Pro 变施工图纸，作为通用接口中间层 | 架构方向 |
| 2 | AI Native 开发原则 | 6/18 | 确定性优先、不引入外部基础设施、渐进交付 | 全局约束 |
| 3 | 5 Agent 协作架构 | 6/18 | Architect→Decomposer→Specifier→Reviewer→Packager | Ship Pro 核心 |
| 4 | push-based 编排 | 6/18 | 基于 sessions_spawn + sessions_yield | 技术选型 |
| 5 | Format A/B/C 归一化 | 6/18 | Architect 负责从不同格式提取统一架构描述 | 数据流设计 |
| 6 | REQ 去重分工 | 6/19 | Reviewer 领域内去重 + Consolidator 跨域去重 | 数据质量 |
| 7 | 三维检查法 | 6/19 | 主体+动作+约束 替代语义相似度 | 去重算法 |
| 8 | ENOENT 三连修 | 6/19 | Fix-1/2/3 解决路径注入和时序问题 | 管线稳定性 |
| 9 | Spec Pro V4.1 修正 | 6/19 | 从资源导向转向约束导向评分体系 | Spec Pro 进化 |
| 10 | 统一进度通知格式 | 6/19 | ⚡/✅/⚠️ + Unicode 进度条 + 双模式 | 用户体验 |
| 11 | 全链路质量审查 | 6/20 | Spec Pro→Solution Pro→Ship Pro 端到端追溯 | 质量保障 |
| 12 | Pipeline Watcher V2 | 6/20 | 两阶段采集 + CloudEvents + SQLite WAL | 可观测性 |
| 13 | Cron 路由修复 | 6/20 | delivery.mode=announce 自动路由，不硬编码 channel | 通知可靠性 |
| 14 | WP 结构 AI 化 | 6/20 | 从人类开发者思维转向 AI Coding Agent 思维 | Ship Pro 输出质量 |
| 15 | Orchestrator 集中式 | 6/20 | 借鉴 Solution Pro 成熟设计，Worker 零改动 | Blackboard 架构 |
| 16 | 去重效果验证 | 6/21 | validate_req_dedup.py + 软性去重率警告 | 数据质量保障 |
| 17 | V3.1.x 迭代验证 | 6/21 | 4 案例 × 多版本对比，信息净值评估 | 质量迭代方法 |
| 18 | 手机适配 | 6/21 | 紧凑/详细双模式，项目名不截断 | 用户体验 |
| 19 | 全链路 E2E 测试 | 6/21 | 同一 Living Spec A/B 对比 | 质量验证标准 |
| 20 | Git 备份 | 6/21 | github.com/hustfreefly/deepflow.git | 代码安全 |

---

## 核心架构决策详情

### A. Ship Pro V3 架构

```
Depth 0: Main Agent（触发+交付）
  Depth 1: Ship Pro Orchestrator（解析+拆分+组装）
    Depth 2: WP Workers（并行细化）
```

**5 Agent 管线**:
1. **Architect**: 从 Solution Pro 输出提取统一架构描述 → `blueprint.json`
2. **Decomposer**: 把架构模块拆成可执行工作包 → `wp_structure.json`
3. **Specifier**: 为每个 WP 写验收标准和技术约束 → `wp_specs.json`
4. **Reviewer**: 质量审核 + 领域内去重 → `review_report.json`
5. **Packager**: 组装标准化输出 → `ship_package.json` + `summary.md`

### B. REQ 去重策略

- **Reviewer 层**: 领域内去重（同一 WP 内的重复 REQ）
- **Consolidator 层**: 跨域去重（跨 WP 的重复 REQ）
- **算法**: 三维检查法（主体+动作+约束），非纯语义相似度
- **安全约束**: `POST /api/login` vs `POST /api/logout` 不能误合并
- **ID 保留**: `covered_req_ids[]` 保留全部原始 ID

### C. 可观测性系统设计要点

- **事件协议动态适配**: 只认协议不认业务结构
- **SQLite 存储**: WAL 模式 + 幂等写入 + OTel 兼容
- **Best-effort 采集**: 不阻断管线
- **数据生命周期**: 分信号 TTL (logs 7天/metrics 30天/traces 3天)

### D. AI Native 核心原则（从讨论中提炼）

1. **确定性优先**: 能用代码做的不用 LLM
2. **理解优于穷举**: 用语义描述让 LLM 理解意图，不穷举关键词
3. **渐进交付**: 分阶段实现，不一次性做完
4. **不引入外部基础设施**: SQLite 存储，不依赖外部数据库
5. **Worker 零改动**: 绝对红线，所有改进在编排层完成
6. **代码的角色**: 从"写代码"转变为"指导AI、设计规范、验证结果"
7. **Karpathy 四原则**: Think Before Coding → Simplicity First → Surgical Changes → Goal-Driven Execution

---

## 关键产出文件索引

| 文件路径 | 内容 | 日期 |
|:---------|:-----|:-----|
| `docs/research/2026-06-18_ship_pro_v3_development_plan.md` | Ship Pro V3 开发计划 | 6/18 |
| `docs/research/2026-06-18_ai_native_redesign_proposal.md` | AI Native 重设计提案 | 6/18 |
| `docs/research/2026-06-18_expert_reports/` | 多专家评审报告集 | 6/18 |
| `docs/research/2026-06-19_v3.1_review_ai_native.md` | V3.1 AI Native 评审 | 6/19 |
| `docs/research/2026-06-19_v3.1_review_feasibility.md` | V3.1 可行性评审 | 6/19 |
| `docs/design/spec_pro_to_solution_pro_link_upgrade.md` | Spec Pro→Solution Pro 链接升级 | 6/20 |
| `docs/design/spec_solution_link_v2.md` | Spec-Solution 链接 V2 | 6/20 |
| `docs/design/RECOVERY_DATA.md` | 恢复数据（1812行） | 6/21 |
| `docs/design/PROTOCOLS.md` | 协议设计文档 | 6/21 |
| `docs/design/SYSTEM_PROMPT.md` | 系统提示词设计 | 6/21 |
| `contracts/shared/pipeline_watcher_design.md` | Pipeline Watcher 设计文档 | 6/20 |
| `domains/ship_pro/prompts/*.md` | Ship Pro Agent Prompts | 6/18-21 |
| `blackboard/DeepFlow_开发者可观测性系统架构_architecture_*/` | 可观测性系统 Blackboard | 6/20-21 |

---

## 未解决问题 / 待跟进

1. **ADR 传播衰减**: 架构决策在 Agent 传递过程中信息丢失，需要追踪机制
2. **Cron 生命周期管理**: 孤儿 cron 持续报错问题需要系统性解决
3. **WP 结构优化**: 当前 WP 结构对 AI Coding Agent 不够友好，需要进一步迭代
4. **去重率阈值**: 从 71→8 的去重率是否过于激进？需要更多案例验证
5. **Frozen Blueprint 退役**: 讨论中提到但尚未正式执行退役
6. **Blackboard 重构**: 方向已定（Orchestrator 集中式），实施待启动

---

*文档生成时间: 2026-06-21 17:33 CST*
*数据来源: `/Users/allen/.openclaw/agents/main2/sessions/*.jsonl` (6月18-21日)*
*提取方法: jq 流式处理 role=user/assistant 消息，关键词过滤 + 人工整理*
