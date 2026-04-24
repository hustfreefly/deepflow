## Prompt 工程评审报告

### 结构完整性评估

当前 prompt 采用 **身份→初始化→步骤→规则→契约** 的线性结构，整体合理但存在明显的"信息冗余"和"权重稀释"问题。

**核心问题诊断**：
1. **重复定义**：数据采集、搜索工具优先级、Worker Agent 映射在多处出现（STEP 1/2 vs "数据采集层"章节；STEP 2 vs "2.3 搜索工具优先级"；"管线流程列表" vs "Worker Agent 映射表"）。
2. **指令权重不均**：关键约束（如 Blackboard 数据流、收敛检测≥2轮）淹没在大量代码示例中，而代码示例本身并非"指令"，只是"实现参考"。
3. **反模式**：将"执行代码"直接嵌入 prompt，导致 Agent 可能混淆"这是要我执行的代码"还是"这是我应该理解的逻辑"。Agent 不是解释器，代码块应作为"契约接口"而非"执行脚本"。

**删除重复章节后的结构完整性**：
- ✅ 保持完整：删除"数据采集层"独立章节（与 STEP 1 完全重复）、删除第二处搜索工具优先级（与 STEP 2 重复）、删除 Worker Agent 映射表（与管线流程列表重叠）后，核心指令链仍然完整。
- ⚠️ 风险点：删除"错误示例"可能导致 Agent 失去"负面约束"的直观理解。错误示例的价值在于"明确禁止什么"，而非"展示错误本身"。建议保留错误示例的核心禁令，但压缩为清单格式。

**比"删除"更好的优化方式**：
- **引用替代复制**：对于"搜索工具优先级"、"Worker Agent Label 命名规则"等标准化内容，改为"参见 `docs/search_priority.md`"或"参见 `config/label_naming.yaml`"，prompt 中只保留关键摘要。
- **分层加载**：将 prompt 拆分为"核心指令层"（身份+契约+收敛规则，~3K）和"执行参考层"（代码示例+错误案例，~9K），根据任务阶段动态注入。例如，STEP 1 执行前只加载数据采集相关片段。

---

### 逐条评审

| 精简项 | Prompt 工程视角 | 建议 |
|--------|----------------|------|
| 1. 删除"数据采集层"章节 | ✅ **高价值删除**。该章节与 STEP 1 完全重复，且包含大量代码示例，稀释了指令权重。Agent 只需知道"STEP 1 必须执行 DataManager"，不需要看到完整的 Python 代码。 | **删除**，但在 STEP 1 末尾保留一行："详细实现参见 `.deepflow/data_manager.py`，此处不重复代码。" |
| 2. 删除搜索工具优先级第二处 | ✅ **高价值删除**。STEP 2 已明确列出优先级（Gemini CLI → DuckDuckGo → Tushare → web_fetch），"2.3 搜索工具优先级"章节是冗余复述。 | **删除**，但在 STEP 2 开头加粗强调："⚠️ 所有 Worker Agent 必须遵守此搜索优先级，不得自行选择工具。" |
| 3. 删除 Worker Agent 映射表 | ⚠️ **中等价值删除**。映射表与管线流程列表有重叠，但映射表提供了"角色→Prompt 文件"的明确对应关系，对 Agent 理解"如何加载 prompt"有帮助。 | **压缩为单行表格**，或删除后在"执行流程"中增加一句："Worker Agent prompt 路径遵循 `{domain}_{role}.md` 约定，详见 `prompts/` 目录。" |
| 4. 代码中文注释精简 | ✅ **高价值压缩**。代码注释是给人类读的，Agent 不需要"中文注释"来理解代码逻辑。注释应精简为"关键变量说明"，而非逐行解释。 | **删除所有中文注释**，仅保留关键函数的 docstring（如果函数名本身不够清晰）。例如，`gemini_search(query)` 无需注释，函数名已自解释。 |
| 5. 搜索函数 docstring 删除 | ⚠️ **低价值删除**。Docstring 对 Agent 理解函数用途有帮助，尤其是当函数名不够直观时（如 `fulfill_requests` vs `collect_requests`）。 | **保留关键函数的单行 docstring**，删除冗长的多行说明。例如：`def fulfill_requests(requests, context): """根据请求列表获取数据"""` 即可。 |
| 6. ❌ 错误示例删除 | 🔴 **高风险删除**。错误示例的价值在于"明确禁止什么"，这是负面约束的最有效表达方式。删除后，Agent 可能忽略关键禁令（如"禁止 mock"、"禁止跳过收敛检测"）。 | **压缩为清单格式**，而非完全删除。例如：<br>`❌ 禁止：sessions_spawn 无 label 参数`<br>`❌ 禁止：单轮迭代即收敛（除非分数≥0.95）`<br>`❌ 禁止：通过 prompt 手动嵌入前置 Agent 输出（必须用 Blackboard）` |
| 7. Fallback 代码块简化 | ✅ **高价值简化**。Fallback 逻辑是"策略"，不是"代码"。Agent 需要知道"quota exceeded 时切换模型"，不需要看到完整的 Python try-except 代码块。 | **压缩为规则描述**：<br>`当 sessions_spawn 返回 quota exceeded 时：`<br>`1. 立即切换到 fallback_model (bailian/kimi-k2.5)`<br>`2. 若仍失败，切换到 secondary_fallback (kimi/kimi-code)`<br>`3. 全部失败 → 标记阶段为 failed，继续执行后续阶段` |
| 8. 身份声明+必复述合并 | ✅ **高价值合并**。"身份"章节和"每次任务前必复述"内容高度重叠。合并后可减少 ~200 字符，且强化记忆锚点。 | **合并为单一区块**：<br>`## 身份与强制复述`<br>`你是 DeepFlow V1.0 PipelineEngine Orchestrator Agent。`<br>`每次任务开始前，必须在内心复述以下约束（不输出给用户）：`<br>`- 禁止 mock，禁止跳过，禁止硬编码`<br>`- 所有 sessions_spawn 必须设置 label`<br>`- 收敛检测必须≥2轮`<br>`- 最终输出必须是合法 JSON` |

---

### 业界最佳实践对标

| 维度 | 现状 | 最佳实践 | 差距 |
|------|------|----------|------|
| **角色定义清晰度** | ✅ 明确声明"你是 PipelineEngine Orchestrator Agent"，并区分 depth-1/depth-2 | 角色定义应包含"职责边界"和"非职责" | 缺少"你不做什么"的明确声明（如"你不直接执行审计，你调度 Worker Agent"） |
| **指令优先级** | ⚠️ 关键指令（如 Blackboard 数据流）淹没在代码示例中 | 使用**加粗**、编号、⚠️/🔴 符号突出高权重指令 | 指令权重视觉层次不清晰，Agent 难以识别"必须遵守"vs"可以参考" |
| **负面约束表达** | ✅ 有"错误示例"章节，但篇幅过长 | 负面约束应以**清单格式**呈现，每条以"❌ 禁止"开头 | 错误示例以代码块形式呈现，Agent 可能误认为"这是可执行的代码"而非"禁令" |
| **模块化/可维护性** | ❌ 所有内容内联在一个文件中，~18K | Prompt 应拆分为"核心指令"+"可引用模块"，支持动态加载 | 无法按需加载，每次调用都消耗完整 18K token |
| **契约明确性** | ✅ 有"契约约束"章节，明确 Blackboard 数据流、输出格式 | 契约应以**JSON Schema**或**TypeScript 接口**形式定义，而非自然语言 | 输出格式用 JSON 示例表示，但未提供 Schema 验证规则，Agent 可能生成不合规 JSON |
| **错误恢复策略** | ✅ 有 Fallback 模型策略 | 错误恢复应包含"重试次数"、"超时策略"、"降级方案" | 缺少明确的重试次数限制（只说"最多 2 次"，但未说明在哪一层重试） |

---

### 替代优化方案

如果目标是节省 quota，除了删除内容，还有以下替代方案：

#### 方案 A：分层 Prompt 架构（推荐）
将 prompt 拆分为三层：
1. **Core Layer (~3K)**：身份 + 核心契约 + 收敛规则 + 负面约束清单
2. **Execution Layer (~6K)**：各 STEP 的执行逻辑（按需加载，例如执行 STEP 1 前只加载数据采集相关片段）
3. **Reference Layer (~9K)**：代码示例、错误案例、详细配置（不直接注入 prompt，而是作为"外部文档"供 Agent 查阅）

**优势**：
- 首次调用只消耗 3K token
- 后续步骤按需加载，总消耗可能低于 12K
- 可维护性强，修改某一层不影响其他层

**实现方式**：
```python
# Core Layer 始终加载
core_prompt = read_file("prompts/orchestrator_core.md")

# Execution Layer 按阶段加载
if current_stage == "data_collection":
    execution_prompt = read_file("prompts/orchestrator_step1_data.md")
elif current_stage == "worker_dispatch":
    execution_prompt = read_file("prompts/orchestrator_step2_dispatch.md")

# Reference Layer 通过工具调用按需读取
# Agent 可以调用 read_file 查看详细信息
```

#### 方案 B：外部化配置（中等推荐）
将"搜索工具优先级"、"Worker Agent Label 命名规则"、"Fallback 模型列表"等内容提取为 YAML/JSON 配置文件，prompt 中只保留"参见配置文件"的引用。

**优势**：
- Prompt 体积减少 ~30%
- 配置变更无需修改 prompt
- Agent 可以通过 `read_file` 工具动态读取配置

**劣势**：
- 增加 Agent 的工具调用次数（每次需要读配置文件）
- 依赖文件系统的可靠性

#### 方案 C：指令压缩（保守方案）
保留所有内容，但通过以下方式压缩：
- 删除所有中文注释
- 将代码块压缩为伪代码
- 将错误示例压缩为清单
- 合并重复章节

**优势**：
- 实现成本低，无需架构改动
- 预计可从 18K 压缩到 ~12K

**劣势**：
- 仍是单体 prompt，无法按需加载
- 压缩后可能损失部分可读性

---

### 最终推荐

**推荐方案：方案 A（分层 Prompt 架构） + 方案 C（指令压缩）的组合**

**理由**：
1. **短期收益**：通过指令压缩（方案 C）可立即从 18K 降至 ~12K，满足当前瘦身目标。
2. **长期收益**：引入分层架构（方案 A）后，首次调用可降至 ~3K，后续步骤按需加载，总消耗可能低于 10K。
3. **可维护性**：分层后，修改某一层（如更新搜索工具优先级）不影响其他层，降低维护成本。

**具体执行步骤**：
1. **立即执行**（方案 C）：
   - 删除"数据采集层"独立章节
   - 删除第二处搜索工具优先级
   - 压缩 Worker Agent 映射表为单行
   - 删除所有中文注释
   - 压缩错误示例为清单格式
   - 简化 Fallback 代码块为规则描述
   - 合并身份声明+必复述

2. **中期规划**（方案 A）：
   - 将 prompt 拆分为 `orchestrator_core.md`、`orchestrator_step1.md`、`orchestrator_step2.md` 等文件
   - 修改 PipelineEngine 代码，支持按阶段动态加载 prompt 片段
   - 将配置类内容（搜索优先级、Label 命名、Fallback 模型）提取为 YAML 文件

3. **验证指标**：
   - 首次调用 token 消耗：从 18K 降至 ≤3K（分层后）
   - 总调用 token 消耗：从 18K 降至 ≤10K（分层+按需加载）
   - Agent 遵从率：关键指令（Blackboard 数据流、收敛检测≥2轮）的违反率应从 0% 保持为 0%

**风险提示**：
- 分层架构需要修改 PipelineEngine 的代码加载逻辑，可能引入新的 bug
- 建议在测试环境先验证分层后的 prompt 效果，再部署到生产环境
- 保留原始 18K prompt 作为 fallback，以便快速回滚
