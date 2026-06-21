# Python 架构评审报告 — Research Pro 改进计划 V1.0

> **评审人**: Python 架构师（Subagent）
> **评审日期**: 2026-06-11
> **评审范围**: IMPROVEMENT_PLAN_v1.md 中的代码架构设计
> **评审对象**: orchestrator.py 状态机、reasoning.py、quality_reviewer.py、source_registry.py

---

## 总体评价: 良好（4/5）

改进计划整体思路清晰，问题诊断精准（5 条根因分析到位），方案设计与现有代码风格一致。但存在 **3 个架构级风险** 需要在实施前解决：状态机回退路径不完整、reasoning.py 职责边界模糊、quality_reviewer 定位矛盾。

---

## 逐项评审

### 1. orchestrator.py 新增 quality_review 状态机阶段

**评分: 3/5 — 需要改进**

#### 问题

**P0: 状态回退路径设计缺陷**

改进计划中的状态机转换：
```
reporting → quality_review → completed (pass)
quality_review → reporting (revise, score 18-23)
quality_review → reporting (rewrite, score <18)
```

当前 orchestrator.py 的状态转换逻辑（L200-500）是**单向线性**的：
```python
planning → confirming → executing → reporting → completed
```

`_update_state()` 方法（L260-275）只做 `state.update(updates)`，没有状态转换验证。`confirm_plan()` 有阶段守卫（`if current_stage != "confirming"`），但 `generate_report()` 的守卫只检查 `current_stage != "reporting"`。

**风险**: quality_review → reporting 的回退需要：
1. 重置 `stage_status` 为 `in_progress`
2. 清理已生成的 `final.md`（否则下次 generate_report 会覆盖）
3. 重新进入 `_generate_report_draft()` 时，需要知道哪些维度需要重写

但改进计划中的 `_run_quality_review()` 伪代码只做了 `_transition_to("reporting")`，没有处理上述清理逻辑。

**P1: `_review_retry_count` 状态持久化缺失**

改进计划引用了 `self._review_retry_count`，但这个计数器：
- 不在 `state.json` schema 中
- 不在 `_load_or_create_state()` 的初始化逻辑中
- 如果 orchestrator 进程重启，计数器丢失，可能导致无限回退

**P2: 与现有 `_evaluate_completion()` 的职责重叠**

当前 `generate_report()` 已有 completion_check 逻辑（L1050-1080），包括：
- `citation_verification_rate`
- `tier_1_source_ratio`
- `url_reachability`

改进计划的 `quality_review` 新增 6 维评分，但 `completion_criteria.json` 的 `quality_scoring` 字段已存在 5 维权重。两套评分体系共存会导致：
- 调用方不知道以哪个为准
- 权重配置分散在两处

#### 改进建议

1. **状态转换表显式化**：在 orchestrator.py 顶部定义 `VALID_TRANSITIONS` 集合，所有 `_transition_to` 调用必须经过验证：
   ```python
   VALID_TRANSITIONS = {
       ("planning", "confirming"),
       ("confirming", "executing"),
       ("confirming", "cancelled"),
       ("executing", "reporting"),
       ("reporting", "quality_review"),
       ("quality_review", "completed"),
       ("quality_review", "reporting"),  # 回退重写
   }
   ```

2. **retry_count 持久化到 state.json**：在 state schema 中新增 `quality_review_retries: int` 字段，通过 `_update_state()` 管理。

3. **合并评分体系**：将 `completion_criteria.json` 的 `quality_scoring` 与改进计划的 6 维评分统一为一套，保留 `degradation_rules` 作为硬性底线。

---

### 2. reasoning.py 模块设计

**评分: 3/5 — 需要改进**

#### 问题

**P0: 职责边界模糊 — "推理"还是"格式化"？**

改进计划中 `EngineeringReasoner.apply()` 的 4 个方法：
- `_build_causal_chains()` — 5 Whys 因果链
- `_analyze_temporal_logic()` — 时序推理
- `_assess_actionability()` — 可操作性评估
- `_reason_failure_modes()` — 失效模式推理

这些方法的输入是 `research_data: dict`，输出也是 `dict`。但关键问题是：

**这些方法是 LLM prompt 编排，还是纯 Python 逻辑？**

如果是 LLM 编排（调用 LLM 对已有数据做因果推理），那它本质上是一个 **prompt chain**，应该放在 `prompts/` 目录，而不是独立 Python 模块。

如果是纯 Python 逻辑（基于规则提取因果链），那需要明确规则来源 — 从哪里获取"因果关系"的知识图谱？

从改进计划的伪代码看，4 个方法体都是 `pass`，说明设计者自己也没想清楚实现路径。**这是最大的架构风险**。

**P1: 与 orchestrator 的耦合方式不明确**

改进计划说 orchestrator.py 需要新增 `_apply_engineering_reasoning()` 方法。但当前 orchestrator 的 `execute_research()` 流程是：
```
搜索 → 注册 → 完成检查 → 进入 reporting
```

reasoning.py 的 `apply()` 应该在哪个环节介入？
- 选项 A: executing 之后、reporting 之前（增强数据）
- 选项 B: reporting 内部（增强报告生成 prompt）

两种选择的架构影响完全不同：
- 选项 A: reasoning 输出写入 blackboard，reporting 读取 → 数据流清晰
- 选项 B: reasoning 作为 report prompt 的一部分 → 耦合在 LLM 调用中

**P2: 10h 工时估算偏高（如果走 prompt 路线）或偏低（如果走规则路线）**

- Prompt 路线：4 个方法 = 4 个 prompt 模板 + 编排逻辑 ≈ 4-6h
- 规则路线：需要领域知识图谱 + 推理引擎 ≈ 40h+

#### 改进建议

1. **明确实现路径**：在实施前确定 reasoning.py 是 prompt 编排还是规则引擎。建议走 **prompt 编排路线**（与现有架构一致），此时：
   - 文件应命名为 `reasoning_chain.py` 或 `prompt_reasoning.py`
   - 4 个方法改为 4 个 prompt 模板（放在 `prompts/reasoning/` 目录）
   - `apply()` 方法改为串行调用 4 个 LLM 请求

2. **数据流显式化**：
   ```python
   # 推荐的数据流
   executing → research_data (dict)
           ↓
   reasoning_chain.apply(research_data) → enhanced_data (dict)
           ↓
   reporting → 读取 enhanced_data 生成报告
   ```

3. **增加超时控制**：4 次 LLM 调用串行执行，每次 30s = 120s 总耗时。需要在 `_apply_engineering_reasoning()` 中设置硬超时。

---

### 3. quality_reviewer.py — 独立 Agent vs 内嵌函数

**评分: 4/5 — 设计合理，但需明确定位**

#### 分析

改进计划将 quality_reviewer 定位为**独立 Python 模块**（`quality_reviewer.py`），但评审逻辑是 **LLM prompt 驱动**（`prompts/quality_review.md`）。

这产生了一个定位矛盾：

| 维度 | 独立 Agent | 内嵌函数 | 改进计划（现状） |
|------|-----------|---------|----------------|
| 生命周期 | 独立进程 | orchestrator 内部 | 独立文件，orchestrator 调用 |
| 状态访问 | 通过 blackboard | 直接访问 self.state | 需要传入 report_path |
| 回退控制 | 需要回调机制 | 直接调用 `_transition_to` | 直接调用（内嵌风格） |
| prompt 管理 | 独立 prompt 文件 | 可内嵌 | 独立 prompt 文件 |

**我的建议：保持"独立模块 + orchestrator 调用"模式，但明确接口契约**。

理由：
- quality_review 需要读取完整报告（`final.md`）→ 需要文件访问能力
- quality_review 需要控制状态回退 → 需要 orchestrator 回调
- quality_review prompt 可能较长（6 维度 × 5 级描述）→ 独立文件便于维护

#### 问题

**P1: 接口签名不够**

改进计划只展示了 `_run_quality_review()` 在 orchestrator 内部的伪代码，没有定义 `quality_reviewer.py` 的公共接口。

建议的接口：
```python
class QualityReviewer:
    def __init__(self, prompt_path: str, completion_criteria: dict):
        ...
    
    def review(self, report_path: Path, research_data: dict) -> ReviewResult:
        """
        Returns:
            ReviewResult: {
                total_score: int,
                dimensions: dict[str, int],
                verdict: "pass" | "revise" | "rewrite",
                weak_dimensions: list[str],
                revision_instructions: str
            }
        """
```

**P2: `revision_instructions` 如何驱动局部重写？**

改进计划中 `_revise_weak_dimensions()` 方法未展开设计。局部重写需要：
- 定位报告中对应维度的章节
- 重新生成该章节内容
- 合并回完整报告

这比"整体重写"复杂得多。建议 Phase 2 先只支持"整体重写"，局部重写作为 Phase 3 优化。

#### 改进建议

1. **定义清晰的 ReviewResult 数据类**，避免 dict 散弹式传参
2. **Phase 2 只做 pass/rewrite 二元判定**，revise（局部重写）推迟到 Phase 3
3. **quality_reviewer.py 不持有 orchestrator 引用**，通过返回值驱动状态转换

---

### 4. source_registry.py 新增字段的向后兼容性

**评分: 4/5 — 兼容性良好，但需迁移策略**

#### 分析

改进计划新增字段：
```python
{
    "confidence_score": 0.95,      # 新增
    "source_type": "academic_paper", # 新增
    "peer_reviewed": true,          # 新增
    "author_credentials": "TSMC R&D", # 新增
}
```

当前 `source_registry.py` 的 `register()` 方法（L55-95）签名为：
```python
def register(self, url, title, content, quality_tier, summary="") -> int
```

新增字段不在 `register()` 参数列表中，说明需要修改 `register()` 签名或新增方法。

#### 问题

**P1: register() 签名膨胀风险**

当前 `register()` 有 5 个参数（+1 默认值）。如果新增 4 个字段，变成 9 个参数。后续可能继续增加（`retraction_status`、`correction_notice` 等）。

**建议**：改用 `**kwargs` 或 `metadata: dict` 参数吸收扩展字段：
```python
def register(
    self,
    url: str,
    title: str,
    content: str,
    quality_tier: str,
    summary: str = "",
    metadata: Optional[dict] = None,  # 吸收扩展字段
) -> int:
```

**P2: 已有 source_registry.json 文件的迁移**

现有 blackboard 目录中已有 `source_registry.json` 文件（不含新字段）。代码中 `self._sources` 直接 `json.load()` 加载，没有 schema 验证。

新增字段后：
- 旧文件加载不会报错（dict 不检查 schema）
- 但 `source.get("confidence_score")` 返回 `None`，下游代码需要处理

**P3: tier_classifier.py 的联动改动未展开**

改进计划说 tier_classifier.py 需要"增强分级（新增 Tier 0）"，但当前 `TierClassifier.classify()` 的输入是 `hostname`，输出是 `tier_1|tier_2|tier_3|unverified`。

新增 Tier 0（学术论文）需要：
- 学术论文的识别不靠 hostname（arxiv.org 只是预印本），需要 `source_type` 字段
- 但 `source_type` 在 `register()` 时才知道，`classify()` 在 `register()` 之前调用

**时序矛盾**：先 classify（确定 tier）再 register（确定 source_type），但 tier 0 的判断需要 source_type 信息。

#### 改进建议

1. **register() 使用 metadata dict 吸收扩展**，保持签名稳定
2. **新增 `update_metadata(source_id, metadata)` 方法**，支持 register 后补充字段
3. **tier_classifier 改为两阶段**：
   - 阶段 1: `classify(hostname)` → 初始 tier（现有逻辑）
   - 阶段 2: `refine_tier(initial_tier, source_type, peer_reviewed)` → 最终 tier
4. **所有 `source.get("new_field")` 调用使用默认值**：`source.get("confidence_score", 0.5)`

---

## 代码层面的具体风险

### 风险 1: 状态机死锁（严重度: 高）

**场景**: quality_review 评分 18-23 → 回退到 reporting → 重新生成报告 → 再次 quality_review → 仍然 18-23 → 再次回退...

**根因**: `_review_retry_count` 未持久化，orchestrator 重启后计数器归零。

**修复**: retry_count 写入 state.json，每次回退前检查。

### 风险 2: reasoning.py 的 LLM 调用成本失控（严重度: 中）

**场景**: 4 个推理方法 × 每次 2000 token 输入 = 8000 token/次研究。如果 research_data 很大（50 个来源 × 平均 1000 token = 50K token），4 次调用 = 200K token。

**修复**: 每个推理方法设置输入 token 上限，超出时截断或摘要。

### 风险 3: completion_criteria.json 的权重之和不一致（严重度: 低）

**现状**: 当前 `quality_scoring.weights` 之和 = 0.30+0.20+0.20+0.15+0.15 = 1.00。

**改进计划**: 新增权重 = 0.15+0.10+0.25+0.15+0.15+0.10+0.10 = 1.00。

**问题**: 两套权重共存，调用方不知道用哪套。

**修复**: 改进计划应明确"替换"还是"共存"。建议**替换**，保留 `degradation_rules` 作为硬性底线。

---

## Top 3 改进建议

### 建议 1: 状态机转换表显式化（优先级: P0）

在 orchestrator.py 顶部定义 `VALID_TRANSITIONS` 集合，所有状态转换必须经过验证。这是防止 quality_review 回退导致状态混乱的基础设施。

**工时估算**: 2h（定义 + 改造 `_update_state` + 单元测试）

### 建议 2: reasoning.py 降级为 prompt 编排（优先级: P0）

明确 reasoning.py 不做"推理"，只做"prompt 链式调用"。4 个方法改为 4 个 prompt 模板，串行调用 LLM。这样：
- 与现有架构一致（orchestrator 本身就是 prompt 编排器）
- 工时从 10h 降到 4-6h
- 可测试性提升（每个 prompt 可独立验证）

### 建议 3: quality_review Phase 2 只做二元判定（优先级: P1）

局部重写（revise）的实现复杂度远超预期（需要章节定位 + 内容合并 + 引用更新）。建议 Phase 2 只做 pass/rewrite 二元判定，max_retries=2。Phase 3 再考虑局部重写。

---

## 附录: 改进计划工时修正建议

| 改进项 | 原估算 | 修正估算 | 理由 |
|--------|--------|---------|------|
| #1 研究类型识别 | 2h | 2h | 合理 |
| #2 信息质量评估 | 6h | 8h | tier_classifier 两阶段改造未计入 |
| #3 技术工艺框架 | 3h | 3h | 合理（纯 prompt 文件） |
| #4 工程推理 | 10h | 6h | 走 prompt 编排路线可缩减 |
| #5 质量评审 | 8h | 10h | 状态机回退逻辑 + 测试 |
| **总计** | **29h** | **29h** | 总量不变，分配调整 |

---

*评审完成 | 2026-06-11 | Python 架构师 Subagent*
