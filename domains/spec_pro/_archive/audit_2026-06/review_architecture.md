# Spec Pro 系统性修复计划 — 架构评审意见

**评审角色**: 架构评审专家  
**评审日期**: 2026-06-02  
**评审输入**: REMEDIATION_PLAN.md + 4 份审计报告（data_flow / edge_cases / prompt_contracts / downstream）

---

## 一、根因分析评审（RC1-RC5）

### RC1: Prompt 指令缺乏显式写操作

**✅ 根因准确。**

审计报告 data_flow 中 P0-01、P0-02 清晰证实：init 阶段和 collecting 分支 C 的 round_result.json 写指令缺失，conversation_log.json 的 update 命令缺失。30 个问题中有 2 个 P0 直接归因于此。根因定位精确，无遗漏。

---

### RC2: Prompt-Code 数据契约不一致

**✅ 根因准确。**

这是 30 个问题中影响面最大的根因（9 个问题，含 3 个 P0）。审计 prompt_contracts 中 P0-1（4 个 confirmed 字段断裂）、P0-2（meta_signals 字段名不匹配）、P0-3（quality 对象结构不一致）全部验证了这一点。

**补充观察**: RC2 还隐含了一个更深层的问题——**没有单一可信源（Single Source of Truth）**。当前 schema 散落在 7 个 prompt 文件 + models.py + merge_spec.py 中，任何一处修改都需要手动同步其余 6 处。这正是后续 S1 要解决的核心问题。

---

### RC3: 防御性编程不足

**✅ 根因准确。**

审计 edge_cases 中 3 个 P0 中有 2 个（P0-1 session ID 碰撞、P0-3 类型崩溃）直接归因于此，11 个 P1 中至少 6 个也是防御性不足（API JSON 损坏、safety_stop 后仍可调用、负 delta 语义等）。

**补充观察**: RC3 实际上覆盖了两类不同的问题：
1. **输入校验缺失**（类型检查、边界处理、NaN 校验）— 这部分 S3 修复计划完整
2. **状态机保护缺失**（safety_stop 后仍可调用 build_next_round_task）— 这是状态机生命周期问题，不完全等同于"防御性编程"，但归入 RC3 可以接受

---

### RC4: Spec Pro → Solution Pro 下游消费断层

**✅ 根因准确，且是最有洞察力的一个。**

审计 downstream 完整证实了 9 个字段的消费断裂。其中 3 个 P0（route_recommendation、user_directives、inferred_pending）是"写了没人看"的典型。这个根因的价值在于它不是 Spec Pro 内部的问题，而是**跨域集成边界**问题——Spec Pro 认为自己在产出丰富数据，Solution Pro 实际上只用了 10 个核心字段。

**补充观察**: 还有一个未被单独列为根因但值得注意的问题——**requirement_annotations 的"半消费"状态**（frozen_spec.py 读取并合并了 annotations，但 task_builder.py 的 Worker prompt 不使用）。这属于"消费了但没有产生价值"，与 RC4 的"完全没消费"略有不同，但归入 RC4 的修复范围是合理的。

---

### RC5: 代码冗余

**⚠️ 根因准确但范围过窄。**

RC5 只列了 3 个问题（process_guard 双份实现、user_confirmation.md 扩展名、Round 1 自引用循环）。但审计中发现的其他冗余问题——如 executive_summary 与 task_builder 各自重建上下文（downstream [7]）、solution_pro_hints 展平为字符串 REQ（downstream [8]）——也应该归入"代码冗余/设计不一致"这个根因。

**建议**: RC5 的描述应扩展为"代码冗余与架构不一致"，覆盖更多结构性问题。但不影响修复计划的执行——这些问题大多会在 S4/S5 修复中一并处理。

---

### 是否有遗漏的根因？

**有一个边界根因未被显式列出**:

**RC6（建议补充）: 错误传播链断裂** — API 层（spec_pro_api.py）对 JSON 损坏、目录不存在等异常不做结构化处理，导致调用方收到的是 Python traceback 而非友好错误。这影响了 P1-7、P1-8、P1-10 等 3 个问题。虽然归入 RC3（防御性编程）在技术上也说得通，但**错误传播**是一个独立关注点——它不是输入校验，而是输出规范化。

**结论**: RC1-RC5 覆盖了 30/30 问题，无遗漏。但 RC6 可作为 RC3 的补充维度，帮助理解"防御性编程"在不同层（数据层 vs API 层）的不同表现形式。

---

## 二、修复策略评审（S1-S5）

### S1: 引入 Schema 契约层（解决 RC2）

## ⚠️ 有改进建议

**同意方向，但 Schema 定义方式需要重新考量。**

修复计划提议用 **Python dict** 定义所有 Schema。评审意见如下：

#### Python dict vs JSON Schema 对比

| 维度 | Python dict | JSON Schema |
|------|-------------|-------------|
| 可读性 | Python 开发者友好 | 标准规范，任何语言可读 |
| 验证库 | 需自建校验逻辑 | pydantic / jsonschema / cerberus 等成熟库 |
| 自文档化 | 需要额外文档 | schema 即文档，可生成 OpenAPI |
| LLM 消费 | 需序列化后展示 | 原生 JSON 格式，LLM 更易理解 |
| 维护成本 | 低（纯 Python） | 中（需额外依赖和工具链） |
| 类型约束 | 弱（依赖运行时校验） | 强（required / type / enum / pattern） |

**改进建议**:

考虑到当前项目的实际约束（~3K LOC Python 项目、Python-only 消费者、LLM 需要理解 schema），推荐采用 **Pydantic BaseModel** 而非纯 dict 或纯 JSON Schema：

```python
# schemas.py
from pydantic import BaseModel, Field
from typing import Literal, Optional

class UserDirective(BaseModel):
    dimension: str = Field(..., description="维度名，如 'users'")
    directive: Literal["deliberately_omitted"] = Field(...)
    reason: str = Field(..., description="用户原话或原因")
    status: Literal["confirmed", "pending"] = "confirmed"

class LivingSpecConfirmed(BaseModel):
    objective: str
    pain_points: list[str] = []
    success_metrics: list[dict] = []
    user_directives: list[UserDirective] = []
    # ... 其他字段
```

**理由**:
1. Pydantic v2 的 `model_json_schema()` 可同时输出 JSON Schema（供 LLM 消费和文档生成）和运行时校验（供代码层使用）
2. 解决了"单一可信源"问题——Prompt 从 `model_json_schema()` 生成，Code 从 BaseModel 实例化校验
3. 比纯 dict 多了类型安全，比纯 JSON Schema 多了 Python 原生集成

**如果不引入 Pydantic**（避免新增依赖），至少应在 Python dict 基础上增加一个 `validate_against_schema(data, schema)` 函数，在 merge_spec.py 入口统一校验，而非在 7 个地方各自校验。

---

### S2: 统一 Prompt 写入协议（解决 RC1）

## ✅ 同意

**这是 P0 级别问题，必须修，且 S2 的方案直接有效。**

每个需要写入的 Step 都添加显式的 `write` 或 `exec` 命令，消除 Orchestrator Worker 的"猜测空间"。

**改进建议（不改变方案，只增强鲁棒性）**:

1. **写入后验证**: 在每个 write 命令后添加一行验证指令，如 `验证: 确认 round_result.json 已创建且为合法 JSON`。这不是过度工程——audit data_flow 显示多个 P0 都是因为"以为写了但实际没写"导致的。

2. **考虑将写入逻辑从 LLM 手中移出**: 当前方案是让 Orchestrator Worker（LLM Agent）执行 write 工具。更彻底的方案是在 coordinator.py 中，关键文件（round_result.json、conversation_log.json）由 **Python 代码直接写入**，而非依赖 LLM 调用 write 工具。但这属于更大的架构变更，可作为 Phase 2 之后的优化项，不阻塞当前修复。

---

### S3: 防御性编程加固（解决 RC3）

## ✅ 同意（但需补充 1 项）

S3 的 7 项行动覆盖了 10 个问题的修复，全面且务实。

**需要补充的一项**:

**`load_coord_state()` 和 `cmd_confirm()` 的错误传播规范化**（对应 P1-7、P1-8、P1-10）。修复计划中提到了"所有 json.load()/json.loads() 加 try/except"，但这还不够——需要统一错误输出格式。建议：

```python
# spec_pro_api.py
def _safe_json_load(path: str) -> dict:
    """统一 JSON 加载入口，返回结构化错误而非 traceback"""
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Corrupted JSON in {path}: {e}") from e
    except FileNotFoundError:
        raise ValueError(f"File not found: {path}") from None
```

这样 API 调用方收到的是 `ValueError` 而非 `JSONDecodeError`，主进程可以统一处理并返回友好错误。

**其他认可**:
- session ID 改用 `uuid4().hex[:16]` — 正确，碰撞率从 18% 降至可忽略
- fallback 补全缺失字段 — 正确，消除了未来维护风险
- process_guard 负 delta 分支 — 正确，语义修复
- safety_stop 状态检查 — 正确，状态机保护

---

### S4: 下游消费 Adapter（解决 RC4）

## ⚠️ 有改进建议 — 抽象层选择需要论证

这是评审中最需要深入讨论的策略。修复计划选择在 **frozen_spec.py（Solution Pro 侧）** 建立统一 adapter。

#### 两个方案对比

| 维度 | S4: frozen_spec.py 消费 | 替代: Spec Pro 侧统一输出 |
|------|------------------------|--------------------------|
| 耦合性 | Spec Pro 不知道 Solution Pro 的存在 | Spec Pro 需要知道下游消费格式 |
| 扩展性 | 新增下游消费方只需新增 adapter | Spec Pro 输出格式需适配所有下游 |
| 数据丢失 | adapter 可能误解 Spec Pro 产出语义 | Spec Pro 最了解自己的数据语义 |
| 维护责任 | Solution Pro 维护 adapter | Spec Pro 维护输出格式 |
| 当前项目适用性 | ✅ 两个域同仓库、同一团队 | N/A |

#### 评审结论: **同意 S4 的方案，但需增加一个约束**

在当前架构下（Spec Pro 和 Solution Pro 同属 .deepflow/domains/，同一团队维护），frozen_spec.py 作为 adapter 是**正确的选择**。理由：

1. **Spec Pro 的契约是 living_spec.json**，它不应该被特定下游消费者的需求所约束
2. **frozen_spec.py 已经是转换层**（living_spec → frozen_spec），在它上面增加 adapter 职责是自然的职责扩展
3. **如果未来有第三个域消费 Spec Pro 产出**（如一个新的 domain），只需新增一个 adapter 即可，不需要改 Spec Pro

**但需要增加的约束**:

adapter 函数 `build_living_spec_context()` 必须有**自动化测试覆盖**，确保每个 Spec Pro 新增字段如果需要在下游消费，adapter 不会被遗忘。建议：

```python
def build_living_spec_context(living_spec: dict) -> dict:
    """
    将 living_spec 的所有产出结构化透传给 Solution Pro。
    
    ⚠️ 维护规则:
    - living_spec 新增顶层字段时，必须更新此函数
    - 每个透传字段必须有对应的 test
    - 运行 `pytest domains/spec_pro/test_schema_passthrough.py` 验证
    """
```

**关于 requirement_annotations 的建议**:

修复计划中未明确 requirement_annotations 的处理方式（P1-4）。建议采用**方案 B（移除标注管线）**——理由：
- 该管线已完成"生产→合并→写入"但没有下游消费
- 保留它增加了 Spec Pro 的收尾开销（额外的 LLM 调用）
- 如果未来确实需要，可以从 git history 恢复或按需重建

---

### S5: 代码清理（解决 RC5）

## ✅ 同意

3 项清理工作都是低风险高收益的改动：
- 删除 process_guard 双份实现 → 消除 divergence 风险
- 扩展名修正 → 消除维护者困惑
- 删除自引用循环 → 消除 LLM 认知混乱

**补充建议**:

S5 可以同时处理审计 downstream [8] 中提到的 **solution_pro_hints 展平为字符串 REQ 的问题**（移除 142-148 行的 `_add_requirement` 展平逻辑）。这本质上也是"代码清理"——删除一段产生了冗余且语义丢失的代码。

---

## 三、"不做的事"边界评审

| 不做项 | 评审 | 理由 |
|--------|------|------|
| Direct Driver 架构迁移 | ✅ 同意不做 | 当前嵌套 spawn 能跑，迁移收益不抵成本。但建议在 VERSION.md 中记录为"已知架构债" |
| 版本号统一 | ✅ 同意不做 | 已文档化，不需要代码改动 |
| 并发文件锁 | ⚠️ **建议 reconsider** | 审计 edge_cases P1-2 明确指出存在 lost update 风险。虽然当前是单用户，但 **原子写入（写临时文件 + os.rename）只需 2 行代码**，不需要引入 fcntl.flock。建议将"完整文件锁"不做，但"原子写入"纳入 S3 修复范围 |

**建议补充一个"不做的事"**:

- ❌ **不引入新的外部依赖库**（除非 Pydantic 被采纳为 S1 的实现方式）— 保持项目轻量，避免依赖地狱

---

## 四、执行顺序评审

| 阶段 | 评审 | 说明 |
|------|------|------|
| Phase 1: S1 | ✅ 合理 | 无依赖，优先建立 Schema 契约 |
| Phase 2: S2 | ✅ 合理 | 依赖 S1 的 quality schema 统一，顺序正确 |
| Phase 3: S3 | ✅ 合理 | 可并行于 S1，但串行执行更安全 |
| Phase 4: S4 | ✅ 合理 | 依赖 S1 的 user_directives schema，顺序正确 |
| Phase 5: S5 | ✅ 合理 | 独立清理，可提前但放最后也不影响 |

**建议**: Phase 1 和 Phase 3 实际上没有互相依赖（S1 改 schema 定义，S3 改防御性代码），可以**并行执行**以缩短总时间。但考虑到同一开发者执行时串行的上下文切换成本，当前串行计划也是合理的。

---

## 五、总体评价

### 评分: ⭐⭐⭐⭐☆ (4/5) — 优秀，有少量改进空间

**强项**:
1. **根因分析质量高**: 5 个根因覆盖了 30/30 问题，没有遗漏，每个根因都有明确的审计证据支撑
2. **策略-根因映射清晰**: S1-S5 与 RC1-RC5 一一对应，没有"策略找不到根因"或"根因没有策略"的情况
3. **务实的边界设定**: 明确列出了"不做的事"，避免了范围蔓延
4. **验证标准明确**: 每个 Phase 完成后有 3 项验证，不是一句"测试通过"就完事

**可改进之处**:
1. **S1 的 Schema 定义方式**: 建议采用 Pydantic 或至少增加 validate 函数，纯 dict 在 3 个月后就会变成"又一个需要手动同步的散列文件"
2. **S4 的 adapter 缺少自动化保障**: build_living_spec_context() 必须有测试，否则 3 个月后新增字段时 adapter 又会被遗忘
3. **"不做的事"中的文件锁**: 原子写入只需 2 行代码，应该做
4. **遗漏了 error propagation 作为独立关注点**: RC3 可以拆分为"输入校验"和"错误传播"两个维度

**最终建议**: 修复计划可以按当前方案执行。上述改进建议（Pydantic、原子写入、adapter 测试）可以纳入对应 Phase 的具体实施细节中，不阻塞计划启动。

---

*评审完成。共审查 5 个根因 + 5 个策略 + 3 个不做项 + 执行顺序。*
*核心结论: 方向正确，细节可微调。建议立即启动 Phase 1。*
