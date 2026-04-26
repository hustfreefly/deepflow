# Solution 模块优化建议报告

**日期**: 2026-04-26  
**分析对象**: DeepFlow V2.0 Solution Designer 模块  
**对比参考**: Investment 模块  

---

## 1. 当前设计概览

### 1.1 架构组成
- **配置层**: `domains/solution.yaml` (领域配置), `cage/domain_solution.yaml` (契约笼子)
- **执行层**: `domains/solution/orchestrator.py` (SolutionOrchestrator)
- **提示词层**: `prompts/solution/*.md` (6个角色 Prompt)

### 1.2 Pipeline 阶段
1. **Planning**: 需求分析 (solution_planner)
2. **Research**: 并行研究 (constraint_analyst, best_practice_researcher, tech_evaluator)
3. **Design**: 核心设计 (solution_architect)
4. **Audit**: 迭代审计 (feasibility_auditor, risk_auditor, completeness_auditor)
5. **Fix**: 修复 (solution_fixer)
6. **Deliver**: 最终交付 (solution_designer)

---

## 2. 设计问题分析

### 2.1 配置化程度：过高，导致灵活性不足

**问题表现**:
- `solution.yaml` 中硬编码了 `solution_types` (architecture/business/technical) 的具体 `sections`。
- Orchestrator 的 `_build_worker_prompt` 虽然使用了缓存，但 Prompt 模板本身是静态的。
- `pipeline.stages` 在 YAML 中写死，如果用户想要一个"跳过 Research"的快速方案，目前无法通过配置实现。

**影响**:
- **扩展新类型困难**: 增加一种 "Security Audit" 方案类型，需要修改 YAML 配置、新增 Prompt、甚至修改 Orchestrator 逻辑来识别新的 sections。
- **场景适配性差**: 对于简单技术方案，6个阶段显得冗余；对于复杂业务方案，Research 阶段可能不够深入。

### 2.2 灵活性 vs 确定性：过度偏向确定性

**固定部分过多**:
- **Agent 角色固定**: 永远是 Planner -> Researcher -> Architect -> Auditor -> Fixer -> Designer。
- **审计维度固定**: 永远是 Feasibility/Risk/Completeness。
- **输出格式固定**: 严格遵循 C4 或 Structured Report。

**灵活部分缺失**:
- **缺乏动态 Agent 生成**: Investment 模块有 6 个不同的 Researcher (Finance/Tech/Market/Macro/Management/Sentiment)，而 Solution 只有 3 个通用的 Researcher 实例 (Constraint/BestPractice/Tech)。
- **缺乏上下文感知的收敛策略**: 无论方案复杂度如何，最大迭代次数都是 3 次。

### 2.3 哪些应该固定，哪些应该灵活？

| 维度 | 建议状态 | 理由 |
|:---|:---|:---|
| **Pipeline 骨架** | **半固定** | 保留 Planning/Design/Deliver 核心链路，但 Research/Audit/Fix 应可配置为"可选"或"增强"模式。 |
| **Agent 角色定义** | **灵活** | 应根据 `solution_type` 和 `topic` 动态生成 Researcher 的角度，而非预定义 3 个。 |
| **质量维度** | **固定** | Correctness/Completeness/Feasibility 是通用标准，不应随意变动。 |
| **输出章节** | **半灵活** | 基础章节（摘要、风险）固定，详细章节由 Planner 动态决定。 |
| **数据源/工具** | **灵活** | Solution 模块目前没有集成具体的数据源（如 GitHub, AWS Docs），应允许插件化。 |

---

## 3. 与 Investment 模块对比

### 3.1 Investment 值得借鉴的设计

1. **多角色并行研究 (Specialized Researchers)**:
   - Investment 有 6 个不同领域的 Researcher，每个有独立的 Prompt 和关注点。
   - **Solution 现状**: 3 个 Researcher 实例只是角度不同，但底层能力同质化。
   - **建议**: Solution 也应引入"领域专家"概念，如"安全专家"、"性能专家"、"成本专家"，根据 Topic 动态激活。

2. **数据采集前置 (Data Manager Stage)**:
   - Investment 有专门的 `data_manager` 阶段，使用 `DataEvolutionLoop` 采集结构化数据。
   - **Solution 现状**: Researcher 依赖模型内部知识或隐式搜索，缺乏显式的数据支撑。
   - **建议**: 增加"最佳实践检索"阶段，从内部知识库或外部文档中检索相关案例。

3. **单轮快速模式**:
   - Investment 默认 `max_iterations: 1`，适合快速产出。
   - **Solution 现状**: 默认 `max_iterations: 3`，即使简单方案也要跑完审计循环，耗时过长。
   - **建议**: 引入"快速模式" (Quick Mode)，跳过 Audit/Fix，直接 Deliver。

### 3.2 Investment 不适合 Solution 的设计

1. **强依赖结构化数据**:
   - Investment 依赖 Tushare/Akshare 的财务数据。
   - **Solution 差异**: 方案设计更多依赖非结构化知识（架构模式、业务逻辑），难以用统一 Schema 采集。

2. **股价/评分驱动的收敛**:
   - Investment 用分数决定是否收敛。
   - **Solution 差异**: 方案质量很难用单一分数衡量，更需要"问题覆盖度"作为收敛指标。

### 3.3 Solution 应有的独特设计

1. **C4/架构图可视化支持**:
   - Solution 应集成 Mermaid/PlantUML 生成能力，并在 Deliver 阶段自动渲染。
   - Investment 不需要图表生成。

2. **决策追溯链 (Decision Traceability)**:
   - 方案的每个技术选型都应能追溯到"为什么选它"（基于哪个约束、哪个最佳实践）。
   - Investment 更关注"结果预测"，而非"决策过程"。

---

## 4. "固定 + 灵活"模式设计

### 4.1 固定部分 (Core Kernel)

1. **Pipeline 骨架**:
   ```yaml
   core_stages:
     - planning    # 必须：理解需求
     - design      # 必须：产出方案
     - deliver     # 必须：格式化输出
   optional_stages:
     - research    # 可选：深度研究
     - audit       # 可选：质量审计
     - fix         # 可选：迭代修复
   ```

2. **Agent 角色基类**:
   - `Planner`: 负责分解任务。
   - `Architect`: 负责核心设计。
   - `Designer`: 负责文档整合。
   - *注：Researcher/Auditor/Fixer 作为插件角色，不硬编码在基类中。*

3. **质量维度**:
   - Correctness, Completeness, Feasibility, Clarity (权重可配，维度固定)。

### 4.2 灵活部分 (Plugin Layer)

1. **动态 Researcher 生成**:
   - Planner 阶段不仅输出"关键维度"，还输出"需要的研究专家列表"。
   - 例如：Topic 涉及"高并发"，则动态生成"性能专家"；涉及"支付"，则生成"安全专家"。

2. **可配置的审计策略**:
   - 简单模式：无审计。
   - 标准模式：Feasibility + Risk。
   - 严格模式：Feasibility + Risk + Completeness + Security。

3. **分层配置实现**:
   - **L1 (domain.yaml)**: 定义 `modes` (quick/standard/rigorous)，每个模式关联不同的 `pipeline_profile`。
   - **L2 (orchestrator.py)**: 读取 `mode`，动态组装 `StageConfig`。
   - **L3 (prompts/***.md)**: 使用 Jinja2 模板，根据上下文注入不同的指令。

### 4.3 配置示例

```yaml
# domains/solution.yaml 新增
modes:
  quick:
    pipeline: [planning, design, deliver]
    max_iterations: 0
  standard:
    pipeline: [planning, research, design, audit, fix, deliver]
    max_iterations: 2
  rigorous:
    pipeline: [planning, research, design, audit, fix, audit, fix, deliver]
    max_iterations: 3
    auditors: [feasibility, risk, completeness, security, cost]
```

---

## 5. 优化建议

### 5.1 短期改进 (1-2 天)

1. **引入"模式"选择**:
   - 在 `user_context` 中增加 `mode: quick|standard`。
   - Orchestrator 根据 mode 跳过不必要的阶段（如 Quick 模式跳过 Audit/Fix）。
   - **收益**: 提升简单任务的响应速度，减少用户等待。

2. **优化 Researcher 并行策略**:
   - 目前 3 个 Researcher 是固定的。改为由 Planner 输出"研究重点"，动态调整 Researcher 的 Prompt。
   - **收益**: 提高研究的相关性，避免通用型研究的空泛。

3. **增强 Blackboard 的可读性**:
   - 目前 Blackboard 存的是 JSON。增加一个 `blackboard_viewer` 工具，能将中间产物转换为 Markdown 预览，方便调试。

### 5.2 中期架构调整 (1 周)

1. **实现动态 Agent 注册**:
   - 重构 `orchestrator.py`，使其能从 `prompts/solution/experts/` 目录动态加载专家角色。
   - 增加"安全专家"、"性能专家"、"云原生专家"等专用 Prompt。
   - **收益**: 提升方案的专业深度，接近 Investment 的多维度研究能力。

2. **集成 Mermaid 图表生成**:
   - 在 `solution_architect` 和 `solution_designer` 中，强制要求输出 Mermaid 代码块。
   - 在 Deliver 阶段，调用外部工具（或 Canvas）将 Mermaid 转为图片嵌入文档。
   - **收益**: 提升方案的可读性和专业度。

3. **完善收敛检测逻辑**:
   - 目前的收敛仅依赖分数。增加"问题覆盖率"指标：如果 Audit 发现的 P0/P1 问题数为 0，则提前收敛。
   - **收益**: 避免无效迭代，提高收敛效率。

### 5.3 长期演进方向 (1 月)

1. **构建"方案知识库" (Solution KB)**:
   - 类似 Investment 的 `data_manager`，建立 Solution 的"最佳实践库"。
   - 存储历史优秀方案、常见架构模式、反模式案例。
   - Researcher 阶段先从 KB 中检索相似案例，再结合当前需求设计。
   - **收益**: 实现经验的复用，避免每次从零开始。

2. **支持"协同设计"模式**:
   - 允许用户在 Planning 或 Design 阶段介入，提供反馈。
   - Orchestrator 支持"暂停-人工干预-继续"的工作流。
   - **收益**: 提升人机协作体验，避免全自动黑盒带来的不信任感。

3. **自动化验证闭环**:
   - 对于"技术方案"，尝试生成简单的原型代码或 Terraform 脚本，并运行基本测试。
   - **收益**: 从"纸上谈兵"进化到"可执行方案"，大幅提升可行性评分。

---

## 6. 总结

Solution 模块目前是一个**结构完整但略显僵化**的设计系统。它在"确定性"上做得很好（严格的 Pipeline、清晰的契约），但在"灵活性"和"深度"上不如 Investment 模块。

**核心优化方向**:
1. **从"固定角色"转向"动态专家"**：让 Researcher 更懂行。
2. **从"单一模式"转向"多模式适配"**：让简单任务更快，复杂任务更深。
3. **从"纯文本"转向"图文结合"**：发挥架构设计的可视化优势。

通过上述改进，Solution 模块可以从一个"通用文档生成器"进化为一个真正的"智能架构师助手"。
