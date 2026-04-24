## 正确性审计报告

| 精简项 | 影响 | 评级 | 理由 |
|--------|------|------|------|
| 1. 删除"数据采集层"整个章节（和 STEP 1 重复，~2K字符） | **中等风险** | ⚠️ WARNING | "数据采集层"章节包含 STEP 1 未覆盖的关键内容：<br>- `DataEvolutionLoop.collect_requests()` / `fulfill_requests()` / `ingest_findings()` / `update_blackboard()` 等迭代间数据更新方法<br>- 数据目录结构说明（INDEX.json、01_financials/ 等）<br>- 行业配置加载逻辑（从 domains/investment.yaml 读取 industry，加载 industries/*.yaml）<br>STEP 1 只展示了 bootstrap 采集代码，但"数据采集层"章节描述了**完整的 DataManager 生命周期**。删除后，Orchestrator 可能不知道如何在迭代间更新 Blackboard 数据。 |
| 2. 删除搜索工具优先级第二处（和 STEP 2 重复，~800字符） | **低风险** | ✅ SAFE | STEP 2 已完整展示搜索工具优先级代码（Gemini CLI → DuckDuckGo → Tushare → web_fetch），且包含完整的执行示例。第 2.2 节的文字描述是冗余的。LLM 对代码示例的注意力远高于纯文字描述，保留代码即可。 |
| 3. 删除 Worker Agent 映射表（冗余，~500字符） | **中等风险** | ⚠️ WARNING | 该映射表提供了 stage → role → prompt 文件的快速查找关系。虽然 `domains/investment.yaml` 也定义了 agents 列表，但映射表是**人类可读的速查表**。删除后，Orchestrator 需要额外解析 YAML 才能确定每个 stage 对应的 prompt 文件路径。对于 LLM 来说，表格形式的映射比 YAML 嵌套结构更容易快速定位。建议保留或合并到 STEP 3 的配置读取代码注释中。 |
| 4. STEP 1 代码注释精简：删除逐行中文注释，保留代码逻辑（-250字符） | **低风险** | ✅ SAFE | LLM 对 Python 代码的理解不依赖中文注释。关键逻辑（如 `register_providers()`、`bootstrap_phase()`）已有函数名自解释。删除逐行注释不会影响 Orchestrator 的执行理解。 |
| 5. STEP 2 搜索代码精简：删除 docstring 和 try/except 的 print（-200字符） | **低风险** | ✅ SAFE | docstring 和异常打印是调试辅助，不影响核心逻辑。LLM 能从函数签名和返回值推断行为。但建议保留函数名和关键注释（如 `"使用 Gemini CLI 搜索（内置 Google Search grounding）"`），这些是语义锚点。 |
| 6. Label 错误示例删除：只保留正确示例（-100字符） | **低风险** | ✅ SAFE | 对比学习中，正例的效用远大于负例。保留正确示例足以让 LLM 学会正确的 label 命名规则。删除错误示例反而减少 token 消耗。 |
| 7. Fallback 代码块用注释替代完整 if/else（-100字符） | **中等风险** | ⚠️ WARNING | 2.3 节的 Fallback 模型策略是**关键容错机制**。如果用注释替代完整代码，LLM 可能忽略 fallback 逻辑的重要性。当前代码块清晰展示了三级 fallback 链（primary → fallback → secondary_fallback）。建议保留完整代码，或至少保留伪代码结构（而非纯注释）。 |
| 8. 身份+必复述合并（-200字符） | **低风险** | ✅ SAFE | "身份"章节和"每次任务前必复述"内容有重叠。合并后可以减少冗余，只要保留关键的契约约束声明（禁止 mock、禁止跳过、Blackboard 写入要求、收敛检测规则）即可。 |

## 最终结论
**FAIL**

## 关键风险

### 🔴 高风险项（必须修复后才能瘦身）

1. **"数据采集层"章节不能全删**（精简项 1）
   - **问题**：该章节包含迭代间数据更新的核心 API（`collect_requests`、`fulfill_requests`、`ingest_findings`、`update_blackboard`），这些在 STEP 1 中完全缺失。
   - **后果**：Orchestrator 只知道如何做初始 bootstrap 采集，但不知道如何在每轮迭代结束后更新 Blackboard 数据。这将导致多轮迭代时数据无法演进，researcher 第二轮拿不到第一轮的分析结果。
   - **修复建议**：保留"迭代间数据更新"子章节和"数据目录结构"说明，删除与 STEP 1 重复的 bootstrap 代码。预计可节省 ~1.2K 字符而非 2K。

2. **Fallback 代码块不能用注释替代**（精简项 7）
   - **问题**：模型 quota exceeded 是高频故障场景。如果 fallback 逻辑被弱化为注释，LLM 可能在实现时忽略它，导致单个模型失败就终止整个管线。
   - **后果**：管线鲁棒性大幅下降，遇到 bailian/qwen3.5-plus quota 耗尽时直接失败，而不是切换到 kimi-k2.5。
   - **修复建议**：保留完整的 if/else 代码块，但可以精简注释。预计可节省 ~50 字符而非 100。

### 🟡 中风险项（建议优化）

3. **Worker Agent 映射表建议保留或重构**（精简项 3）
   - **问题**：映射表提供了 stage → prompt 文件的 O(1) 查找能力。删除后，Orchestrator 需要解析 YAML 或记忆映射关系。
   - **后果**：增加 LLM 的认知负担，可能导致 spawn Worker 时使用错误的 prompt 文件路径。
   - **修复建议**：将映射表合并到 STEP 3 的代码注释中，作为 `ConfigLoader` 读取结果的示例输出。这样既保留信息，又避免独立章节的冗余。

### ✅ 安全项（可以执行）

4. **精简项 2、4、5、6、8 可以安全执行**
   - 搜索工具优先级：STEP 2 代码已完整覆盖
   - 代码注释精简：LLM 不依赖中文注释理解代码
   - Label 错误示例：正例足够学习
   - 身份+必复述合并：关键契约约束保留即可

## 推荐瘦身方案（修正版）

| 操作 | 预期节省 | 风险等级 |
|------|---------|---------|
| 删除"数据采集层"中与 STEP 1 重复的 bootstrap 代码，保留迭代间数据更新 + 数据目录结构 | ~1.2K | ✅ 安全 |
| 删除搜索工具优先级第二处（2.2 节文字描述） | ~800 | ✅ 安全 |
| 将 Worker Agent 映射表合并到 STEP 3 代码注释中 | ~300 | ✅ 安全 |
| STEP 1 代码注释精简（删除逐行注释） | ~250 | ✅ 安全 |
| STEP 2 搜索代码精简（保留关键 docstring） | ~150 | ✅ 安全 |
| Label 错误示例删除 | ~100 | ✅ 安全 |
| **保留 Fallback 完整代码块** | ~0 | ✅ 安全 |
| 身份+必复述合并 | ~200 | ✅ 安全 |
| **总计** | **~3.0K** | **18K → 15K（17%压缩）** |

**结论**：原方案的 33% 压缩率过于激进，会破坏关键功能。修正后的 17% 压缩率是安全上限。如需进一步压缩，应优先精简重复的配置示例代码，而非删除架构说明章节。
