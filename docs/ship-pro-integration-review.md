# Ship Pro 上下游集成评审报告

> **评审日期**: 2026-07-29  
> **评审范围**: Solution Pro → Ship Pro → Deliver Pro 信息流与接口契约  
> **评审维度**: 信息守恒、接口契约、数据流完整性、缺失环节

---

## 一、信息流全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DeepFlow 五域数据流                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  frozen_spec.json                                                           │
│       │                                                                     │
│       ▼                                                                     │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │ Solution Pro (V4.0)                                             │       │
│  │  Planning → Research → Summary (9步)                            │       │
│  │                                                                  │       │
│  │  输出:                                                           │       │
│  │  ├── stages/solution_document.json  (完整方案文档, ≥50KB)        │       │
│  │  └── stages/final_solution.json     (轻量元数据, ≥5KB)           │       │
│  │       ├── constraint_coverage                                    │       │
│  │       ├── key_decisions[]                                        │       │
│  │       ├── implementation_phases[]                                │       │
│  │       ├── risk_summary[]                                         │       │
│  │       ├── semantic_anchors[]  ← ⚠️ 格式: {anchor_id, concept}   │       │
│  │       ├── covered_req_ids[]                                      │       │
│  │       └── verification_status                                    │       │
│  └──────────────────────────┬───────────────────────────────────────┘       │
│                             │                                               │
│                   ┌─────────┴──────────┐                                    │
│                   │  build_ship_pro_input()  ← ⚠️ 黑盒转换层               │
│                   │  (domains/ship_pro/__init__.py)                         │
│                   └─────────┬──────────┘                                    │
│                             │                                               │
│                             ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │ Ship Pro (V3.0)                                                 │       │
│  │  Designer → Workers → Consolidator                              │       │
│  │                                                                  │       │
│  │  输入:                                                           │       │
│  │  ├── data/frozen_spec.json (or living_spec.json)                │       │
│  │  └── solution_pro_input.json ← semantic_anchors 来源            │       │
│  │                                                                  │       │
│  │  输出:                                                           │       │
│  │  └── stages/ship_package.json                                   │       │
│  │       ├── work_packages[]     (WP 列表)                         │       │
│  │       ├── dependency_graph    (依赖图)                          │       │
│  │       ├── semantic_anchors[]  ← 从 solution_pro_input 透传      │       │
│  │       ├── anchor_coverage{}   ← 统计各 anchor 被哪些 WP 引用    │       │
│  │       ├── key_decisions[]     ← Optional, 实际未填充            │       │
│  │       ├── architecture        ← Optional, 实际未填充            │       │
│  │       ├── risk_summary        ← Optional, 实际未填充            │       │
│  │       └── metadata{}          (统计信息)                        │       │
│  └──────────────────────────┬───────────────────────────────────────┘       │
│                             │                                               │
│                   ┌─────────┴──────────┐                                    │
│                   │  WP 分发层 ← ⚠️ 未定义的隐式转换                        │
│                   │  (ship_package → 单个 wp.json)                          │
│                   └─────────┬──────────┘                                    │
│                             │                                               │
│                             ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │ Deliver Pro                                                     │       │
│  │  Analyze → Execute (Workers)                                    │       │
│  │                                                                  │       │
│  │  输入: 单个 WP (wp_data_path)                                   │       │
│  │  ├── wp_id, title, objective                                    │       │
│  │  ├── scenario (code|report|mixed)                               │       │
│  │  ├── acceptance_criteria[] ← 结构化对象 [{id,description,priority}] │   │
│  │  ├── constraints{}                                              │       │
│  │  ├── dependencies[]                                             │       │
│  │  ├── semantic_anchors[]  ← 含 constraint + source_quote         │       │
│  │  └── serving_principles[] ← 含 obligation + anti_patterns       │       │
│  │                                                                  │       │
│  │  输出: 4文件 (DELIVERABLE.md, EVIDENCE.md, ISSUES.md, MANIFEST.json) │  │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、接口契约检查

### 2.1 Solution Pro → Ship Pro

| 检查项 | 状态 | 说明 |
|--------|------|------|
| frozen_spec 存在性 | ✅ OK | Ship Pro orchestrator Step 0 显式检查 |
| solution_document 消费 | ⚠️ **隐式** | Ship Pro 不直接读 solution_document.json，而是通过 `solution_pro_input.json` 间接消费 |
| final_solution 消费 | ⚠️ **隐式** | final_solution.json 的 key_decisions/risk_summary 等未被 Ship Pro 显式读取 |
| semantic_anchors 来源 | 🔴 **模糊** | consolidator 从 `solution_pro_input.json` 读取，但该文件的 semantic_anchors 从何而来未明确 |

**关键问题**: `build_ship_pro_input()` 是黑盒转换层，其内部逻辑决定了 semantic_anchors 是否能正确传递。从 SKILL.md 看，它只合并 `frozen_spec.md` + 可选 supplemental，**没有显式提取 final_solution.json 的 semantic_anchors**。

### 2.2 Ship Pro → Deliver Pro（核心断裂点）

| Ship Pro WP 字段 | Deliver Pro WP 字段 | 匹配状态 | 问题 |
|------------------|---------------------|----------|------|
| `id` (str) | `wp_id` (str) | ⚠️ 别名兼容 | Ship Pro 有 `_map_wp_id` 别名，但 Deliver Pro 不识别 `id` |
| `title` (str) | `title` (str) | ✅ 匹配 | — |
| `description` (str, ≥100字) | `objective` (str) | 🔴 **字段名不匹配** | Ship Pro 输出 `description`，Deliver Pro 期望 `objective` |
| — | `scenario` (code\|report\|mixed) | 🔴 **缺失** | Ship Pro WP 无 scenario 字段，Deliver Pro 必须有 |
| `acceptance_criteria` (List[str]) | `acceptance_criteria` (List[AcceptanceCriterion]) | 🔴 **类型不匹配** | Ship Pro 输出字符串列表，Deliver Pro 期望结构化对象 `[{id, description, priority}]` |
| — | `constraints` (dict) | 🔴 **缺失** | Ship Pro WP 无 constraints 字段 |
| `dependencies` (List[str]) | `dependencies` (List[str]) | ✅ 匹配 | — |
| — | `interface_contract` (str) | ⚠️ Optional | Ship Pro pipeline_plan 有 interface_provides/requires，但未传入 WP |
| — | `context` (dict) | 🔴 **缺失** | Ship Pro 不向 WP 注入 Solution Pro 上下文 |
| `anchored_to` (List[str]) | `semantic_anchors` (List[dict]) | 🔴 **类型不匹配** | Ship Pro 只有 anchor 名称列表，Deliver Pro 期望完整 anchor 对象（含 constraint + source_quote） |
| — | `serving_principles` (List[dict]) | 🔴 **缺失** | Ship Pro 无此字段，Deliver Pro 期望含 obligation + anti_patterns |
| `effort_hours` (int) | — | ⚠️ 未消费 | Ship Pro 提供但 Deliver Pro 不使用 |
| `covered_req_ids` (List[str]) | — | ⚠️ 未消费 | Ship Pro 提供但 Deliver Pro 不使用 |
| `deliverables` (List[str]) | — | ⚠️ 未消费 | Ship Pro 提供但 Deliver Pro 不使用（Deliver Pro 自己生成 expected_outputs） |
| `source_worker` (str) | — | ⚠️ 未消费 | Ship Pro 提供但 Deliver Pro 不使用 |

### 2.3 ShipPackage Schema 中的 N1-FIX 透传字段

Ship Pro ShipPackage 定义了以下 Optional 透传字段（N1-FIX）：
- `key_decisions: Optional[List[str]]`
- `architecture: Optional[str]`
- `risk_summary: Optional[str]`
- `implementation_phases: Optional[List[str]]`

**实际状态**: consolidator.md 的 6 步法中**没有任何步骤填充这些字段**。它们保持默认值（空列表/None），Solution Pro 的关键决策、架构、风险、实施阶段信息在 Ship Pro 层面**事实丢失**。

---

## 三、semantic_anchors 信息守恒深度分析

### 3.1 三段传递链

| 段 | 源 | 目标 | 格式 | 状态 |
|----|-----|------|------|------|
| 段1 | planning_convergence (Solution Pro) | final_solution.semantic_anchors | `{anchor_id, concept, doc_section}` | ⚠️ 轻量，无 constraint/source_quote |
| 段2 | final_solution / solution_pro_input | consolidator 读取 | 未知（取决于 build_ship_pro_input） | 🔴 来源不明确 |
| 段3 | ship_package.semantic_anchors | Deliver Pro WP.semantic_anchors | 期望 `{name, category, constraint, source_quote}` | 🔴 格式不匹配 |

### 3.2 格式断裂

**Solution Pro 输出格式**（from json_extractor）:
```json
{
  "anchor_id": "SA-001",
  "concept": "核心概念",
  "doc_section": "Section 2"
}
```

**Ship Pro consolidator 期望格式**（from consolidator.md）:
```json
{
  "name": "sessions_spawn",
  "category": "platform_api",
  "constraint": "..."
}
```

**Deliver Pro 期望格式**（from work_package.py）:
```json
// semantic_anchors 字段：含 constraint + source_quote
```

**结论**: 三个阶段的 semantic_anchor 格式各不相同，没有统一的 schema 约束。信息在每次转换中都有损失。

### 3.3 anchor_coverage 的可靠性

consolidator 计算 `anchor_coverage` 的逻辑是：统计每个 anchor name 被哪些 WP 的 `anchored_to` 字段引用。

**问题**: Ship Pro Worker 的 `anchored_to` 是 `List[str]`（只有 anchor 名称），但 anchor 的名称来源是 `context.json` 中的 `semantic_anchors`。如果 context.json 中的 anchor 格式与 final_solution 不一致（字段名不同），Worker 可能无法正确引用。

---

## 四、问题清单

### P0 — 阻断性问题（必须修复，否则数据流断裂）

| # | 问题 | 影响 | 位置 |
|---|------|------|------|
| P0-1 | **Ship Pro WP → Deliver Pro WP 字段名不匹配**: `description` vs `objective` | Deliver Pro 无法读取 WP 目标 | worker_deliverable.py vs deliver_pro/contracts/work_package.py |
| P0-2 | **acceptance_criteria 类型不匹配**: Ship Pro 输出 `List[str]`，Deliver Pro 期望 `List[{id, description, priority}]` | Deliver Pro 无法解析验收标准 | worker_deliverable.py vs deliver_pro/contracts/work_package.py |
| P0-3 | **scenario 字段缺失**: Ship Pro WP 无 scenario 字段，Deliver Pro 必须有 | Deliver Pro 无法确定执行场景（code/report） | worker_deliverable.py |
| P0-4 | **WP 分发层未定义**: ship_package.json → 单个 wp.json 的转换逻辑不存在 | Deliver Pro 无法获取输入 | 架构层面缺失 |

### P1 — 重要问题（导致信息丢失或质量下降）

| # | 问题 | 影响 | 位置 |
|---|------|------|------|
| P1-1 | **semantic_anchors 格式不统一**: 三段传递链中格式各异 | Deliver Pro 收到的 anchor 可能缺少 constraint/source_quote | json_extractor → consolidator → work_package |
| P1-2 | **N1-FIX 透传字段未填充**: key_decisions/architecture/risk_summary/implementation_phases 在 consolidator 中无填充逻辑 | Solution Pro 关键信息在 Ship Pro 层面事实丢失 | consolidator.md + ship_package.py |
| P1-3 | **serving_principles 完全缺失**: Deliver Pro 期望但 Ship Pro 无此概念 | Deliver Pro Worker 无法遵循服务原则 | deliver_pro/contracts/work_package.py |
| P1-4 | **constraints 字段缺失**: Ship Pro WP 无 constraints 字段 | Deliver Pro 无法获取技术约束 | worker_deliverable.py |
| P1-5 | **build_ship_pro_input() 是黑盒**: semantic_anchors 如何从 Solution Pro 输出进入 solution_pro_input.json 未明确 | 信息守恒无法验证 | domains/ship_pro/__init__.py |
| P1-6 | **interface_contract 未从 pipeline_plan 传入 WP**: pipeline_plan 有 interface_provides/requires 但 WP 级别无此字段 | Deliver Pro Worker 缺少接口契约信息 | planner_output.py → worker_deliverable.py |

### P2 — 改进建议（提升可追溯性和健壮性）

| # | 问题 | 影响 | 位置 |
|---|------|------|------|
| P2-1 | **effort_hours/deliverables/source_worker 未被 Deliver Pro 消费**: Ship Pro 产出但下游不用 | 信息冗余，但不影响功能 | worker_deliverable.py |
| P2-2 | **covered_req_ids 在 Deliver Pro 中未使用**: 信息守恒追踪在 Deliver Pro 层面断裂 | 无法端到端追踪 REQ 覆盖率 | deliver_pro/contracts/work_package.py |
| P2-3 | **Ship Pro WP 的 anchored_to 只是名称列表**: 缺少 anchor 的完整约束信息 | Deliver Pro Worker 只知道"关联了什么"但不知道"约束是什么" | worker_deliverable.py |
| P2-4 | **solution_document.json 未被 Ship Pro 直接消费**: 通过 solution_pro_input 间接消费，增加了一层转换风险 | 完整方案文档的保真依赖 MD-first 架构 | ship_pro/__init__.py |

---

## 五、修复建议

### 5.1 P0 修复方案

#### P0-1/2/3: 定义 WP 转换适配器

**方案**: 在 Ship Pro 和 Deliver Pro 之间增加显式的 WP 转换层（Adapter Pattern）。

```
ship_package.json (Ship Pro 输出)
       │
       ▼
  wp_adapter.py (新增)
  ├── description → objective
  ├── acceptance_criteria: List[str] → List[{id, description, priority}]
  ├── 从 pipeline_plan 注入 scenario (基于 deliverables 类型推断)
  ├── 从 solution_pro_input 注入 constraints
  └── 从 ship_package.semantic_anchors 过滤出本 WP 相关的 anchor 对象
       │
       ▼
  wp.json (Deliver Pro 输入)
```

**实现位置**: `domains/ship_pro/contracts/wp_adapter.py` 或 `domains/deliver_pro/contracts/wp_adapter.py`

#### P0-4: 定义 WP 分发协议

**方案**: 明确 ship_package → 单个 WP 的分发机制。

```python
# 建议在 Deliver Pro 入口增加
def distribute_work_packages(ship_package_path: str, output_dir: str) -> List[str]:
    """将 ship_package.json 拆分为单个 wp.json 文件"""
    ship_package = json.loads(Path(ship_package_path).read_text())
    wp_paths = []
    for wp in ship_package["work_packages"]:
        wp_path = Path(output_dir) / f"wp_{wp['wp_id']}.json"
        wp_path.write_text(json.dumps(adapt_wp(wp), ensure_ascii=False))
        wp_paths.append(str(wp_path))
    return wp_paths
```

### 5.2 P1 修复方案

#### P1-1: 统一 semantic_anchors Schema

定义全局统一的 `SemanticAnchor` schema:

```python
class SemanticAnchor(BaseModel):
    anchor_id: str          # SA-001
    name: str               # sessions_spawn
    category: str           # platform_api
    constraint: str         # 具体约束描述
    source_quote: str       # 原始引用
    doc_section: Optional[str]  # 文档章节
```

在 Solution Pro json_extractor、Ship Pro consolidator、Deliver Pro WP 三处统一使用此 schema。

#### P1-2: 激活 N1-FIX 透传字段

在 consolidator.md 的 Step 5（Semantic Anchors 透传）之后增加 Step 5.1:

```
Step 5.1: Solution Pro 关键信息透传
1. read solution_pro_input，提取 key_decisions, architecture, risk_summary, implementation_phases
2. 原样写入 ShipPackage 的对应字段
3. 这些字段将注入每个 WP 的 context 中，供 Deliver Pro 使用
```

#### P1-5: 显式定义 build_ship_pro_input 的 semantic_anchors 来源

在 `build_ship_pro_input()` 中增加:
1. 读取 `final_solution.json` 的 `semantic_anchors`
2. 读取 `planning_convergence.json` 的约束体系
3. 合并为统一的 semantic_anchors 列表写入 solution_pro_input.json

### 5.3 P2 修复方案

#### P2-2: 端到端 REQ 追踪

在 Deliver Pro MANIFEST.json 中增加 `covered_req_ids` 字段（当前已有但未被 Ship Pro 传入），并在 Deliver Pro 最终汇总中计算端到端 REQ 覆盖率。

---

## 六、总结

| 维度 | 评分 | 说明 |
|------|------|------|
| 信息守恒 | 🔴 3/10 | semantic_anchors 三段格式不一，N1-FIX 字段未填充，key_decisions/risk_summary 事实丢失 |
| 接口契约 | 🔴 2/10 | Ship Pro WP 与 Deliver Pro WP 有 4 个字段名/类型不匹配，scenario 字段完全缺失 |
| 数据流完整性 | 🟡 5/10 | 主流程可走通，但 WP 分发层未定义，多个 Optional 字段未填充 |
| 缺失环节 | 🔴 2/10 | 缺少 WP 转换适配器、统一 semantic_anchor schema、WP 分发协议 |

**最高优先级修复**: P0-1/2/3/4（WP 字段适配 + 分发协议），不修复则 Deliver Pro 无法正确消费 Ship Pro 输出。

---

*评审完成: 2026-07-29 | 评审人: 系统集成评审专家 (Subagent)*
