# S4 下游消费 Adapter — 集成架构评审意见

**评审人**: 集成架构评审专家（Subagent）
**评审日期**: 2026-06-02
**评审对象**: REMEDIATION_PLAN.md → 策略 S4: 下游消费 Adapter

---

## 总评

S4 的方向正确——Spec Pro 产出的元数据层确实存在消费断层。但具体方案设计存在 **架构职责错配** 和 **消费深度不足** 两个核心问题。以下逐条分析。

---

## 评审视角 1：S4 核心决策 — frozen_spec.py 统一消费 vs Spec Pro 侧统一输出

### 现状分析

S4 提议在 `frozen_spec.py` 中新增 `build_living_spec_context()` 函数，作为 Spec Pro → Solution Pro 的统一翻译层。当前 `build_frozen_spec()` 已经做了部分翻译（从 living_spec.confirmed 提取字段转 REQ-IDs），S4 只是扩展这个职责。

### 问题

`frozen_spec.py` 的职责是 **确定性需求冻结** —— 将不稳定的 living_spec 转换为稳定的 REQ-ID 合同。它是一个**纯 Python 确定性模块**（无 LLM 调用、无 I/O），输出格式是固定的 JSON schema。

而 `build_living_spec_context()` 做的是 **元数据翻译** —— 将 Spec Pro 的推理产物（route_recommendation、inferred_pending、user_directives）转换为 Solution Pro 可用的上下文对象。这两者的**数据性质不同**：

| 维度 | frozen_spec 现有工作 | build_living_spec_context 要做的事 |
|:---|:---|:---|
| 输入 | confirmed 层（用户确认的事实） | 元数据层（推理、建议、指令） |
| 输出 | REQ-ID 需求列表（确定性合同） | 上下文对象（指导性信息） |
| 消费方 | task_builder 各 Worker 的"需求理解"部分 | task_builder 各 Worker 的"行为指导"部分 |
| 语义 | "做什么" | "怎么做 / 不做什么 / 注意什么" |

### 判断

**不建议放在 frozen_spec.py 中。** 理由：

1. **职责污染**：frozen_spec 变成"需求冻结 + 元数据翻译 + 上下文构建"三重角色，违反单一职责。
2. **耦合加深**：Spec Pro 的元数据结构变化（如 route_recommendation 增加新字段）会迫使 frozen_spec.py 改动，但 frozen_spec 的 REQ 格式是 Solution Pro 的稳定接口，不应该被 Spec Pro 的元数据演变所影响。
3. **已有先例**：`build_frozen_spec()` 已经在透传 `guardrails` 和 `solution_pro_hints_raw`（原样复制，不翻译），这是正确的做法——**结构透传**与**结构翻译**应该分开。

### 建议方案

**在 `domains/solution_pro/` 下新建 `spec_context.py`**，作为 Solution Pro 侧的"输入适配器"：

```python
# domains/solution_pro/spec_context.py

def build_living_spec_context(living_spec: dict) -> dict:
    """将 Spec Pro 的 living_spec 翻译为 Solution Pro Worker 可用的上下文。
    
    与 frozen_spec.build_frozen_spec() 职责分离：
    - frozen_spec → 需求列表 (REQ-IDs)，回答"做什么"
    - spec_context → 行为指导上下文，回答"怎么做/注意什么"
    """
    return {
        "deliberately_omitted_dimensions": _extract_omitted(living_spec),
        "pending_inferences": _extract_pending(living_spec),
        "route_recommendation": living_spec.get("route_recommendation"),
        "layer2_hints": _extract_layer2_hints(living_spec),
        "anti_patterns": _extract_anti_patterns(living_spec),
        "executive_summary": _unified_summary(living_spec),  # 替代 task_builder 各自重建
    }
```

**好处**：
- frozen_spec.py 保持稳定，只负责 REQ-ID 合同
- spec_context.py 可以独立演进，不影响下游 REQ 消费逻辑
- task_builder 各 Worker 统一调用一个函数获取上下文，而非各自从 confirmed 提取

---

## 评审视角 2：`build_living_spec_context()` 位置是否合适

### 结论：**不合适**，应放在 Solution Pro 侧而非 Spec Pro 侧

更精确地说：

| 候选位置 | 评估 |
|:---|:---|
| Spec Pro 侧（domains/spec_pro/） | ❌ 不推荐。Spec Pro 不应该知道 Solution Pro 的内部上下文格式。这是下游依赖上游，增加 Spec Pro 的下游耦合。 |
| frozen_spec.py | ❌ 不推荐（见视角 1）。职责污染。 |
| **Solution Pro 侧新模块（domains/solution_pro/spec_context.py）** | ✅ **推荐**。Solution Pro 作为消费方，定义自己需要的输入格式是合理的。Spec Pro 只需保证 living_spec 的产出格式稳定（由 S1 Schema 层保障）。 |
| 独立的 bridge 层（domains/bridge/ 或 core/） | ⚠️ 过度设计。当前只有两个域之间的适配，不值得引入第三层。 |

### 关键原则

**消费方定义消费接口，生产方保证生产接口稳定。**

Spec Pro 的责任：通过 S1 Schema 层保证 `living_spec.json` 的输出结构稳定。
Solution Pro 的责任：定义自己如何将 living_spec 翻译为 Worker 上下文。

---

## 评审视角 3：`deliberately_omitted_dimensions` 传递后各 Worker 具体怎么用

### S4 方案的不足

S4 说"在 task_builder.py 的各 Worker context 中注入'以下维度已被用户明确放弃'"——**仅注入 context 不够**。

不同 Worker 角色需要**不同的行为**，而非相同的提醒文本：

| Worker 角色 | 对 deliberately_omitted 的应有行为 |
|:---|:---|
| **Auditor** | ❌ **不要审计**这些维度。如果方案缺少 deliberately_omitted 维度，不扣分。 |
| **Researcher** | ❌ **不要研究**这些维度。不分配调研资源。 |
| **Planner** | ⚠️ 记录这些维度，在规划时**不纳入范围**。 |
| **Reviewer** | ⚠️ 评审时**不提出**这些维度相关的改进建议。 |
| **Fixer** | ❌ **不修复**这些维度相关的问题。 |

### 建议方案

**不要只做 context 注入，要做行为差异化处理：**

```python
# spec_context.py 中为每个角色生成差异化提醒
def build_omitted_dimension_instructions(omitted: list, worker_role: str) -> str:
    if not omitted:
        return ""
    dims = [d["dimension"] for d in omitted if d.get("directive") == "deliberately_omitted"]
    if not dims:
        return ""
    
    role_behavior = {
        "auditor": "以下维度已被用户明确放弃，审计时请排除这些维度，不要因为缺少这些维度而扣分。",
        "researcher": "以下维度已被用户明确放弃，请不要分配研究资源到这些领域。",
        "planner": "以下维度已被用户明确放弃，规划时请排除这些维度的范围。",
        "reviewer": "以下维度已被用户明确放弃，请不要针对这些维度提出改进建议。",
        "fixer": "以下维度已被用户明确放弃，请跳过这些维度相关的修复。",
    }
    behavior = role_behavior.get(worker_role, f"以下维度已被用户明确放弃，请注意：")
    dims_text = "、".join(dims)
    return f"\n## 用户明确放弃的维度\n{behavior}\n被放弃的维度: {dims_text}\n"
```

**集成方式**：在 `task_builder.py` 各 `build_*_task()` 函数的 context 拼接阶段调用此函数，追加到 prompt 尾部（类似 guardrails.never_do 的处理位置）。

### 额外风险

如果 `deliberately_omitted_dimensions` 中有维度被 Spec Pro 标记为 deliberately_omitted，但 Solution Pro 的 **Harness Final** 检查全部 P0 覆盖时，这些维度对应的 P0 需求可能来自 confirmed 层——被放弃的维度可能仍有 REQ-ID。需要在 Harness Final 逻辑中排除 deliberately_omitted 维度的 REQ。这**不是仅靠 context 注入能解决的**，需要 harness_final 代码逻辑变更。

---

## 评审视角 4：requirement_annotations 标注管线 — 保留（方案 A）还是移除（方案 B）？

### 分析

| 维度 | 方案 A（保留并接入消费） | 方案 B（移除整条管线） |
|:---|:---|:---|
| **成本** | Spec Pro 多 1 轮 LLM 调用（build_annotation_task），约 1-2h 额外 token | 移除后 Spec Pro 减少一轮 LLM 调用，节省 token 和时间 |
| **收益** | context_note 提供需求间的语义关联；dependencies 提供依赖关系；potential_conflicts 预警冲突 | 无直接收益，但减少维护成本和代码复杂度 |
| **当前状态** | 生产→合并→写入完整链路，但消费断裂（写入 frozen_spec.json 后无 Worker 使用） | 完整链路但零消费 |
| **潜在价值** | Planner 可用 dependencies 排序任务；Auditor 可用 potential_conflicts 做冲突审计；Reviewer 可用 context_note 理解需求背景 | 移除后可以专注于更直接有价值的元数据传递 |

### 判断

**倾向方案 A（保留并接入消费），但需降级处理。** 理由：

1. **已经存在的管线，移除不等于零成本**。coordinator.py 中的 build_annotation_task、apply_annotations、frozen_spec.py 中的 _merge_annotations 都需要清理，且未来如需恢复需要重写。
2. **标注信息有实际价值，但当前优先级低于其他元数据**。`context_note`、`dependencies`、`potential_conflicts` 对 Planner 和 Auditor 有指导意义，但不如 `route_recommendation` 和 `user_directives` 紧迫。
3. **S4 的"保持不变（但后续可消费）"是正确态度**——本次 S4 只需要确保标注数据透传到 frozen_spec.json，**不需要**在 task_builder 中全部接入消费。可以作为 S4 的 Phase 2 后续工作。

### 具体建议

**S4 阶段**：
- `_merge_annotations()` 继续工作（已有），确保 requirement_annotations 数据完整写入 frozen_spec.json
- 在 `spec_context.py` 中新增 `requirement_annotations` 字段透传
- **不在本次 S4 中让各 Worker 消费这些标注**

**后续阶段（Phase 2 / 独立任务）**：
- Planner 使用 `dependencies` 做任务排序
- Auditor 使用 `potential_conflicts` 做冲突检查
- 如果经过实际运行发现标注的 ROI 太低（LLM token 消耗 vs 实际帮助），再考虑方案 B

---

## 评审视角 5：route_recommendation 透传后 Solution Pro 真的能用上吗

### 现状

`route_recommendation` 包含：
- `suggested_engine`: 推荐引擎（solution_pro）
- `suggested_mode`: 推荐模式（standard/full）
- `confidence`: 推荐置信度（0.85）
- `complexity_score`: 复杂度评分（0-100）
- `complexity_factors`: 复杂度因子列表

### 透传后的实际可用性分析

**能用上的部分**：

1. **`complexity_score` → 动态调整研究深度**（✅ 有价值）
   - 当前 Solution Pro 的研究者数量是固定的（expert_1/2/3）
   - 如果 `complexity_score > 80`，可以增加研究者数量或研究轮次
   - 如果 `complexity_score < 30`，可以跳过部分研究阶段
   - 这需要在 **Orchestrator 级别** 决策（coordinator/solution orchestrator），不在 Worker prompt 层面

2. **`suggested_mode` → Worker 深度控制**（✅ 有价值）
   - `mode="full"` → Auditor 启用更严格的审计标准
   - `mode="standard"` → 正常审计
   - 可以在 `inject_layer2_constraints()` 中根据 mode 调整约束严格度

3. **`complexity_factors` → 研究者方向指导**（⚠️ 部分价值）
   - 告知研究者哪些维度复杂度高，优先研究
   - 但这与 `solution_pro_hints.focus_areas` 功能重叠

**很难用上的部分**：

4. **`suggested_engine` → 已无意义**（❌ 透传即到达，已经是 Solution Pro 了）
   - 当 Solution Pro 启动时，引擎选择已经发生，不需要知道"为什么选了自己"
   - 这个字段对 Solution Pro 的 Worker 没有行为指导价值

5. **`confidence` → 决策辅助有限**（⚠️ 边际价值）
   - 低置信度时可以增加验证环节，但需要 Orchestrator 逻辑变更
   - 仅在 prompt 中注入"置信度 0.85"不会改变 LLM 行为

### 判断

**route_recommendation 的透传有价值，但主要价值在 Orchestrator 级别而非 Worker prompt 级别。**

具体建议：
- `complexity_score` 和 `suggested_mode` 应该在 **Solution Pro Orchestrator** 入口读取，用于动态配置研究者数量和审计深度——这涉及 Orchestrator 代码变更，不是简单的 prompt 注入。
- 如果当前阶段不打算做 Orchestrator 级别的动态调整，**`route_recommendation` 的透传优先级应该降低**——因为它对 prompt 层面的行为改变有限。
- **不建议在 S4 中只做 prompt 注入**（例如在 context 中加一句"复杂度评分：68"），这对 LLM Worker 几乎没有行为指导作用，反而增加 prompt 噪音。

---

## 对各 S4 行动项的具体评价

### 行动项 1：`frozen_spec.py` 新增 `build_living_spec_context()` 

**评价**：⚠️ 方向正确，位置不当。

**改进**：改为在 `domains/solution_pro/spec_context.py` 中新增此函数（详见视角 2）。

### 行动项 2：task_builder.py 各 Worker context 注入 deliberately_omitted_dimensions

**评价**：⚠️ 仅注入 context 不够，需要角色差异化行为指导（详见视角 3）。

**改进**：使用角色差异化指令模板，同时需修改 Harness Final 的 P0 覆盖检查逻辑以排除 deliberately_omitted 维度的 REQ。

### 行动项 3：移除 hints 展平为字符串 REQ 的逻辑

**评价**：✅ 完全同意。

`frozen_spec.py` 第 142-148 行将结构化 hints 拍平为 `"key: value"` 字符串，既丢失结构又产生冗余。已有 `solution_pro_hints_raw` 的完整结构透传（第 178 行），展平逻辑应移除。

**补充**：移除展平后，需要确保 task_builder.py 各 Worker 确实使用结构化版本而非依赖展平后的 hint REQ。当前 `build_researcher_task()` 已经在读取 `hints.get("focus_areas")`，所以移除展平不会影响它。

---

## S4 改进方案（综合建议）

### 架构调整

```
Spec Pro (living_spec.json)
         │
         ├──→ frozen_spec.build_frozen_spec()      → frozen_spec.json (REQ-IDs)
         │
         └──→ solution.spec_context.build_living_spec_context() → context dict
                    │
                    ├── deliberately_omitted_dimensions (角色差异化)
                    ├── pending_inferences
                    ├── route_recommendation (Orchestrator 级别消费)
                    ├── layer2_hints (按角色注入)
                    ├── anti_patterns (注入到各 Worker)
                    ├── requirement_annotations (透传，暂不消费)
                    └── executive_summary (替代 task_builder 各自重建)
```

### 执行顺序调整

| 优先级 | 行动 | 工作量 | 说明 |
|:---|:---|:---|:---|
| **P0-1** | 新建 `spec_context.py`，提取 deliberately_omitted_dimensions | 1h | 最危险的断层，防止 Solution Pro 追问已拒绝维度 |
| **P0-2** | task_builder 各 Worker 注入 deliberately_omitted_dimensions（角色差异化） | 2h | 需为 5+ 个 Worker 角色生成差异化指令 |
| **P0-3** | 移除 hints 展平逻辑（frozen_spec.py:142-148） | 0.5h | 低风险改动 |
| **P1-1** | layer2_hints 按角色注入 task_builder | 2h | 替代/补充 DEFAULT_LAYER2_CONSTRAINTS |
| **P1-2** | anti_patterns 注入各 Worker context | 1h | 类似 guardrails.never_do |
| **P1-3** | unified executive_summary 替代 task_builder 各自重建 | 2h | 解决审计 [7] 不一致问题 |
| **P2-1** | pending_inferences 透传 + Harness Final 排除检查 | 1h | 需修改 Harness Final 逻辑 |
| **P2-2** | route_recommendation 透传（Orchestrator 级别预留接口） | 0.5h | 本次仅透传，动态调整后续实现 |
| **Phase 2** | requirement_annotations 消费接入 | 后续 | 本次仅透传 |

---

## 总结

S4 的核心问题识别准确（元数据层消费断层），但具体方案存在两个架构级偏差：

1. **位置偏差**：`build_living_spec_context()` 不应放在 frozen_spec.py，应在 Solution Pro 侧新建 `spec_context.py`。
2. **深度偏差**：deliberately_omitted_dimensions 仅注入 context 不够，需要角色差异化行为指导；route_recommendation 的主要价值在 Orchestrator 级别而非 prompt 注入。

**优先级最高的行动项是 deliberately_omitted_dimensions 的角色差异化注入**——这是唯一可能造成**用户可见伤害**的问题（Solution Pro 追问用户已明确拒绝的维度）。其他元数据传递是"增值"，这个是"止损"。
