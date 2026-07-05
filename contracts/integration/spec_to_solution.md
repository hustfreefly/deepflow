# Spec Pro → Solution Pro 数据交接契约

> **版本**: 1.0.0
> **生效日期**: 2026-05-30
> **适用范围**: Spec Pro 产出方与 Solution Pro 消费方之间的 Living Spec 交接

---

## 1. Living Spec 数据格式

### 1.1 序列化格式

- Living Spec 以 **JSON** 格式存储在 Blackboard 路径 `blackboard/{session_id}/spec/living_spec.json`
- Solution Pro 通过 `living_spec: Optional[dict] = None` 参数接收，类型为 `dict`（非字符串）
- 主Agent 负责从 Blackboard 读取 JSON 文件并作为 dict 对象注入 Solution Pro Orchestrator

### 1.2 数据传递方式

| 阶段 | 方式 | 说明 |
|------|------|------|
| Spec Pro 产出 | Blackboard 文件写入 | `living_spec.json` 写入 `spec/` 目录 |
| 跨模块传递 | 构造函数参数 | `SolutionOrchestratorV21(living_spec=...)` |
| Worker 消费 | task_builder 提取注入 | 各 `build_xxx_task()` 函数从 dict 提取关键片段注入 prompt |
| 持久化 | Blackboard 只读 | Solution Pro 不修改 living_spec.json，只读取 |

---

## 2. 字段定义

### 2.1 顶层结构

Living Spec 由以下 6 个顶层字段组成：

```
LivingSpec
├── meta                    # 必填
├── confirmed               # 必填（权威来源）
├── inferred                # 可选（可为空列表）
├── guardrails              # 必填
├── route_recommendation    # 可选（可为 None）
└── solution_pro_hints      # 可选（可为 None）
```

### 2.2 必需字段（MUST 存在且非空）

#### meta（8 个必需子字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `engine` | str | 固定值 "spec_pro" |
| `version` | str | 契约版本号，如 "2.1" |
| `spec_version` | int | Living Spec 版本号 |
| `scenario` | str | genesis/supplement/refine/pivot |
| `created_at` | str | ISO 8601 时间戳 |
| `updated_at` | str | ISO 8601 时间戳 |
| `conversation_rounds` | int | 对话轮次数 |
| `quality_score` | float | 质量评分 0-100 |
| `quality_level` | str | S/A/B/C |

#### confirmed（10 个必需子字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `objective` | str | 核心目标描述 |
| `pain_points` | list[str] | 关键痛点列表 |
| `success_metrics` | list[dict] | 成功指标列表 |
| `users` | list[dict] | 用户角色列表 |
| `key_scenarios` | list[str] | 关键场景列表 |
| `capabilities` | dict | 含 always_do / should_do / never_do 三个子列表 |
| `quality_attributes` | list[dict] | 质量属性（含 category/spec/priority） |
| `constraints` | dict | 约束条件（含 budget/timeline/tech_stack 等） |
| `integration` | dict | 含 existing_systems / requirements 两个子列表 |
| `risks_and_assumptions` | dict | 含 risks / assumptions / dependencies 三个子列表 |

#### guardrails（3 个必需子字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `always_do` | list[str] | 必须做的边界 |
| `ask_first` | list[str] | 需确认后才能做的边界 |
| `never_do` | list[str] | 禁止做的边界 |

### 2.3 可选字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `inferred` | list[dict] | `[]` | AI 推断需求，每项含 id/dimension/content/confidence/basis/status |
| `route_recommendation` | dict / None | `None` | 路由建议，含 suggested_engine/suggested_mode/reasoning/confidence/complexity_score |
| `solution_pro_hints` | dict / None | `None` | 下游参考信息，含 focus_areas/layer2_hints/anti_patterns |

---

## 3. 消费点与字段映射

Solution Pro 各 Stage 从 Living Spec 提取不同字段片段：

| Stage (task_builder) | 使用字段 | 用途 |
|----------------------|----------|------|
| `build_data_collection_task` | `confirmed.objective`, `confirmed.pain_points`, `confirmed.capabilities.always_do` | 生成精准搜索关键词 |
| `build_planner_task` | `confirmed` 全部字段 | 注入完整需求作为规划依据 |
| `build_researcher_task` | `solution_pro_hints.focus_areas`, `guardrails` | 研究边界与重点 |
| `build_reviewer_task` | `confirmed.objective`, `confirmed.capabilities`, `confirmed.quality_attributes`, `confirmed.constraints` | 评审基准 |
| `build_harness_final_task` | `confirmed.capabilities.always_do`, `confirmed.quality_attributes`, `confirmed.constraints` | 需求覆盖度评估 |
| `build_summarizer_task` | `confirmed.capabilities.always_do`, `confirmed.quality_attributes`, `confirmed.constraints` | 最终报告需求覆盖标注 |

---

## 规则

### 必须做（MUST）

- **MUST-001**: Spec Pro 产出前必须确保 `confirmed.objective` 非空字符串（≥5 字符）—— 没有核心目标的 Living Spec 对 Solution Pro 无意义
- **MUST-002**: `confirmed` 层所有 10 个子字段必须存在（可为空列表/空字典，但不能缺失键）—— Solution Pro 的 task_builder 直接访问这些键，KeyError 会导致管线崩溃
- **MUST-003**: `meta.version` 和 `meta.spec_version` 必须与实际契约版本一致 —— 下游通过版本号判断兼容性
- **MUST-004**: `guardrails` 必须包含 always_do / ask_first / never_do 三个子字段 —— Solution Pro 的 research 和 review 阶段依赖 guardrails 做边界控制
- **MUST-005**: `inferred` 中每一项的 `status` 必须为 "pending"、"confirmed" 或 "rejected" 之一 —— Solution Pro 需要区分已确认和待确认推断
- **MUST-006**: Solution Pro 消费 Living Spec 时，`living_spec=None` 必须完全回退到原有行为（向后兼容）—— Orchestrator 中已有此设计，不得破坏
- **MUST-007**: Solution Pro 禁止修改 living_spec.json 文件 —— 写者协议规定只有 Spec Pro Orchestrator 和 ResponseWorker 可写
- **MUST-008**: `confirmed.capabilities` 必须同时包含 always_do / should_do / never_do 三个子键 —— task_builder 代码直接引用这三个键

### 禁止做（NEVER）

- **NEVER-001**: 禁止将 Living Spec 以纯字符串而非 dict 传入 Solution Pro —— task_builder 函数期望 dict 类型，字符串会导致 `in` 操作符行为错误
- **NEVER-002**: 禁止在 Living Spec 中混入 Solution Pro 专属字段（如 session_id、stage 状态等）—— 跨模块数据污染会导致调试困难
- **NEVER-003**: 禁止 Solution Pro 各 Worker 直接读取 living_spec.json 文件 —— 必须由 Orchestrator 统一读取并通过 task prompt 注入
- **NEVER-004**: 禁止 Spec Pro 在未完成 Harness Output Guard 的情况下产出 Living Spec —— 质量低于阈值的 Spec 会误导 Solution Pro 方案设计
- **NEVER-005**: 禁止将 `inferred` 中 status="pending" 的推断当作 confirmed 需求传递给 Solution Pro —— 未确认推断应通过 `solution_pro_hints` 传递

### 建议做（SHOULD）

- **SHOULD-001**: `confirmed.success_metrics` 中的每个指标应包含 metric/target/current 三个子字段 —— Planner 阶段需要完整的指标三元组做规划
- **SHOULD-002**: `confirmed.users` 中的每个角色应包含 role/count/key_needs 三个子字段 —— 评审阶段需要用户画像做合理性验证
- **SHOULD-003**: `solution_pro_hints.focus_areas` 中每个条目应包含 area/weight/reason 三个子字段 —— researcher 阶段需要权重做优先级排序
- **SHOULD-004**: `confirmed.quality_attributes` 中的每个属性应包含 category/spec/priority 三个子字段 —— Harness Final 需要这些做覆盖度检查
- **SHOULD-005**: `meta.quality_score ≥ 75`（standard 模式阈值）才建议传递给 Solution Pro —— 低质量 Spec 应在 Spec Pro 内继续收敛
- **SHOULD-006**: `route_recommendation` 应在 Spec Pro 完成后生成并填充 —— Solution Pro 可参考 suggested_mode 调整运行模式

---

## 验证方式

Solution Pro 通过以下自然语言规则判断 Living Spec 有效性（非脚本检查）：

### 2.0.0: 结构完整性检查（EntryHarness / Orchestrator init）

当 Solution Pro Orchestrator 收到 living_spec 参数时：
- 检查是否为 dict 类型（非 None、非字符串、非 list）
- 检查 `meta` 存在且包含 `engine`、`version`、`quality_score` 三个关键字段
- 检查 `confirmed` 存在且 `confirmed.objective` 为非空字符串
- 检查 `confirmed.capabilities` 存在且包含 `always_do` 键
- 检查 `guardrails` 存在且为字典类型

**违规判定**: 如果任一检查失败，Solution Pro 应记录 WARNING 日志并回退到无 Living Spec 模式（`living_spec=None` 行为），而非崩溃。

### 2.0.0: 质量阈值检查（Orchestrator init）

当 `meta.quality_score` 存在时：
- ≥ 75（standard 阈值）: 完全信任 confirmed 层
- 60-74（B 级）: 信任 confirmed 层，但对 inferred 层保持警惕
- < 60（C 级）: 仅参考 confirmed 中的 objective 和 constraints，其余字段降级为建议

**违规判定**: 如果质量评分 < 60 但 Solution Pro 完全按照 inferred 内容做规划（未标注不确定性），视为目标一致性违规。

### 2.0.0: 推断处理检查（各 Worker task）

- `inferred` 列表中 status="pending" 的项不得作为确定性需求被引用
- status="confirmed" 的推断应在输出中标注"来自推断-确认"
- status="rejected" 的推断不得被引用

**违规判定**: 如果 Worker 输出中使用了 pending 推断但未标注不确定性，评审阶段可标记为"推断越权"。

### 2.0.0: Guardrails 遵守检查（research / review / harness_final）

- `guardrails.always_do` 中的条目应在方案中得到体现
- `guardrails.never_do` 中的条目不应在方案中出现

**违规判定**: Harness Final 阶段对比方案内容与 guardrails.never_do，发现越界内容标记为 MISALIGNED。

### 2.0.0: 向后兼容检查（`living_spec=None`）

当 `living_spec=None` 时：
- Orchestrator 的 `init()` 必须正常完成
- `get_all_tasks()` 必须正常生成全部 Stage
- 不得出现 AttributeError 或 KeyError

**违规判定**: 如果传入 None 时出现异常，视为破坏向后兼容，必须立即修复。

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-05-30 | 初始版本：定义 Living Spec 数据结构、传递方式、消费点映射、MUST/NEVER/SHOULD 规则、验证方式 |
