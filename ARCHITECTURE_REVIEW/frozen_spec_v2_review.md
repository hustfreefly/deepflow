# 架构评审：Spec Pro → Frozen Spec → Solution Pro 链路

> 评审日期：2026-06-02  
> 更新日期：2026-06-03（frozen_spec V2.0 修复记录）
> 评审人：架构专家（Subagent）  
> 范围：`domains/solution_pro/frozen_spec.py` + `domains/solution_pro/task_builder.py` + 消费侧

---

## 更新记录（2026-06-03）

### frozen_spec.py V2.0 修复

本次修复解决了三个结构性遗漏，将信息保留率从 <5% 提升到 ~100%：

1. **constraints 全量遍历**：从硬编码 3 个 key → 遍历 `confirmed_constraints.items()` 所有 key
2. **guardrails.resolved 提取**：新增对用户确认的设计决策的提取（`design_decision` category）
3. **inferred 提取**：新增对 AI 推断需求的提取（`inferred` category）

改动量：`frozen_spec.py` 一个文件，16 行新增代码，下游零影响。
---

## 1. 问题诊断

### 1.1 已修复的问题 ✅

`frozen_spec.py` 的 `build_frozen_spec()` 已修复为**全量消费** living_spec 的 14 个字段（之前仅 7/14）：

| 字段 | 是否消费 | 对应 REQ category |
|------|---------|-------------------|
| `objective` | ✅ | `objective` |
| `capabilities.{always,should,never}_do` | ✅ | `capability` / `prohibition` |
| `quality_attributes` | ✅ | `quality_attribute` |
| `constraints.{budget,timeline,tech_stack}` | ✅ | `constraint` |
| `constraints.*`（全量遍历，新增 platform/input_format/output_format/industry_domain/usage_model/design_philosophy/language） | ✅ | `constraint` |
| `integration.requirements` | ✅ | `integration` |
| `pain_points` | ✅ | `pain_point` |
| `success_metrics` | ✅ | `success_metric` |
| `users` | ✅ | `user` |
| `key_scenarios` | ✅ | `scenario` |
| `risks_and_assumptions.{risks,assumptions}` | ✅ | `risk` / `assumption` |
| `guardrails.{always,never}_do` | ✅ | `guardrail` / `guardrail_prohibition` |
| `guardrails.resolved`（设计决策） | ✅ | `design_decision` |
| `solution_pro_hints` | ✅ | `hint` |
| `inferred`（AI 推断） | ✅ | `inferred` |

### 1.2 更深层的结构性问题 ⚠️

**核心判断：平铺 REQ-ID 列表设计存在结构性瓶颈，但不是致命缺陷。**

问题不在覆盖率，而在**信息编码方式**：

```
living_spec（结构化、有层次、有上下文）
       ↓ build_frozen_spec()
frozen_spec.json（平铺数组、丢失结构、抹平层次）
       ↓ 分发到 Worker
Worker prompt（47 条无组织的清单）
```

#### 三层问题

| 层次 | 问题 | 严重程度 |
|------|------|---------|
| **编码层** | 所有字段被扁平化为同构 REQ-ID 条目，结构层次被抹平 | 🔴 高 |
| **传递层** | frozen_spec.json 无全局摘要，只有 `requirements[]` | 🔴 高 |
| **消费层** | Worker 通过 `covered_req_ids` 反向追踪，但追踪粒度是 REQ-ID 而非结构化意图 | 🟡 中 |

#### 具体症状：上下文丢失

Worker 看到的：
```
REQ-003: 简历生成速度慢，当前需要5分钟
REQ-007: 用户角色: HR经理
REQ-012: 生成时间 < 30秒
```

Worker **应该**看到的：
> "为一个日均处理 10 万份简历的 HR SaaS 平台（HR 经理是决策者），
> 解决简历生成慢（5 分钟 → 目标 <30 秒）、格式不统一（30% 模板失效）的问题。
> 成功标准是生成时间 <30s、模板覆盖率 >95%。"

**pain_points、users、scenarios、success_metrics 这些字段，本质不是"需求"，而是"需求的上下文"**。
将它们和 capability 混在同一个 `requirements[]` 数组里，等于把"问题描述"和"解决方案要求"混为一谈。

#### 现有补救措施分析

`task_builder.py` 中，部分函数已经注入了 `living_spec_context`（`build_planner_task`、`build_reviewer_task`、`build_harness_final_task`、`build_researcher_task`），但存在三个问题：

1. **不统一**：每个 `build_*_task` 函数的注入逻辑不同，字段覆盖不一致
2. **冗余**：同样的 living_spec 数据在 frozen_spec 中有一份、在 prompt 注入中又有一份
3. **维护成本高**：每次 living_spec 新增字段，需要修改 N 个 `build_*_task` 函数

---

## 2. 改进方案

### 设计原则

1. **向后兼容**：不改变 `requirements[]` 结构和 `covered_req_ids` 追踪机制
2. **单一权威源**：Worker 从 `frozen_spec.json` 读取全局上下文，而非依赖 prompt 注入
3. **最小侵入**：只需修改 `build_frozen_spec()` 的 return 字典 + Worker prompt 模板

### 方案：frozen_spec.json v2 结构

#### 新结构

```json
{
  "version": "2.0",
  "generated_at": "2026-06-02T18:00:00",
  "topic": "智能简历生成系统",
  "source": "living_spec.confirmed+topic+constraints",

  "executive_summary": {
    "objective": "构建智能简历生成系统，将 HR 手动 5 分钟/份缩短至 <30 秒",
    "why": [
      "简历生成速度慢，HR 手动编辑每份需 5 分钟",
      "格式不统一，30% 模板失效",
      "缺少行业关键词提取，匹配准确率低"
    ],
    "for_whom": [
      {"role": "HR经理", "key_needs": "批量处理、模板统一、数据导出"},
      {"role": "求职者", "key_needs": "个性化展示、行业关键词匹配"}
    ],
    "success_criteria": [
      {"metric": "生成时间", "target": "<30秒", "current": "5分钟"},
      {"metric": "模板覆盖率", "target": ">95%", "current": "70%"},
      {"metric": "关键词匹配准确率", "target": ">85%", "current": "未知"}
    ],
    "constraints": {
      "budget": "50万人民币",
      "timeline": "3个月",
      "tech_stack": ["Python", "FastAPI", "PostgreSQL"]
    },
    "key_scenarios": ["HR 批量导入 1000 份简历并自动生成标准化简历", "求职者上传旧简历自动优化格式"]
  },

  "guardrails": {
    "always_do": ["方案需包含量化指标", "每个设计决策需有数据或竞品支撑"],
    "ask_first": ["引入新数据库类型前确认", "超过预算 20% 前确认"],
    "never_do": ["不使用未经安全审计的第三方 API", "不在方案中承诺无法验证的性能指标"]
  },

  "solution_pro_hints": {
    "focus_areas": [
      {"area": "简历解析引擎", "weight": 0.4, "reason": "核心瓶颈，直接影响生成速度"},
      {"area": "模板管理系统", "weight": 0.3, "reason": "30% 模板失效需根因分析"}
    ],
    "architecture_patterns": ["Pipeline 模式（解析→标准化→渲染）", "模板引擎分离"]
  },

  "requirements": [
    {"id": "REQ-001", "category": "objective", "description": "...", "priority": "P0", "source": "...", "measurable": ""},
    ...
  ],

  "coverage_policy": {
    "worker_field": "covered_req_ids",
    "matrix_path": "requirements_traceability_matrix.json",
    "harness_final_must_check_all_p0": true
  }
}
```

#### 设计决策说明

| 决策 | 理由 |
|------|------|
| `executive_summary` 为顶层字段 | Worker 在读 frozen_spec.json 时第一眼看到的内容，建立全局理解 |
| `requirements[]` 保持不变 | 向后兼容，现有 `covered_req_ids`、`_acceptance_from_frozen_spec` 零改动 |
| `guardrails` / `solution_pro_hints` 提升为顶层 | 它们不是"需求"，而是"行为约束"和"设计提示"，语义独立 |
| `version` "1.0" → "2.0" | 标记结构升级，下游可做版本判断 |

---

## 3. 具体代码改动

### 3.1 `frozen_spec.py` — `build_frozen_spec()` 新增辅助函数 + 修改 return

```python
# 新增：构建 executive_summary
def _build_executive_summary(confirmed: dict) -> dict:
    """从 living_spec.confirmed 构建全局摘要，供 Worker 建立上下文理解。"""
    
    # Objective（一句话核心目标）
    objective = confirmed.get("objective", "")
    
    # Why（痛点 = 为什么做）
    why = [p for p in (confirmed.get("pain_points") or []) if p]
    
    # For whom（用户画像）
    users = confirmed.get("users") or []
    for_whom = []
    for u in users:
        if isinstance(u, dict):
            entry = {"role": u.get("role", "")}
            # 聚合 key_needs / description
            needs = u.get("key_needs") or u.get("description", "")
            if needs:
                entry["key_needs"] = needs
            for_whom.append(entry)
        elif u:
            for_whom.append({"role": str(u)})
    
    # Success criteria（做对的标准）
    success_criteria = []
    for m in (confirmed.get("success_metrics") or []):
        if isinstance(m, dict):
            success_criteria.append({
                "metric": m.get("metric", ""),
                "target": m.get("target", ""),
                "current": m.get("current", "未知"),
            })
        elif m:
            success_criteria.append({"metric": str(m), "target": "", "current": "未知"})
    
    # Constraints（约束条件）
    raw_constraints = confirmed.get("constraints") or {}
    constraints = {}
    if raw_constraints.get("budget"):
        constraints["budget"] = raw_constraints["budget"]
    if raw_constraints.get("timeline"):
        constraints["timeline"] = raw_constraints["timeline"]
    tech_stack = raw_constraints.get("tech_stack") or []
    if tech_stack:
        constraints["tech_stack"] = tech_stack
    
    # Key scenarios
    key_scenarios = [s for s in (confirmed.get("key_scenarios") or []) if s]
    
    return {
        "objective": objective,
        "why": why,
        "for_whom": for_whom,
        "success_criteria": success_criteria,
        "constraints": constraints,
        "key_scenarios": key_scenarios,
    }


# 修改 build_frozen_spec() 的 return 部分：
    return {
        "version": "2.0",
        "generated_at": datetime.now().isoformat(),
        "topic": topic,
        "source": "living_spec.confirmed+topic+constraints",

        "executive_summary": _build_executive_summary(confirmed),

        "guardrails": (living_spec or {}).get("guardrails", {}),

        "solution_pro_hints": (living_spec or {}).get("solution_pro_hints"),

        "requirements": requirements,

        "coverage_policy": {
            "worker_field": "covered_req_ids",
            "matrix_path": "requirements_traceability_matrix.json",
            "harness_final_must_check_all_p0": True,
        },
    }
```

### 3.2 `task_builder.py` — 统一 REQ 追踪指令

修改 `REQ_TRACEABILITY_INSTRUCTION`，让 Worker 读取完整 frozen_spec 而不仅是 requirements：

```python
REQ_TRACEABILITY_INSTRUCTION = """
## REQ-ID 需求追踪要求

在开始任务前，读取 `{blackboard_path}/data/frozen_spec.json`。

### Step 1: 读取全局上下文
首先读取 `executive_summary` 字段，理解：
- **目标**: `executive_summary.objective`（方案的核心目标）
- **为什么做**: `executive_summary.why`（要解决的痛点）
- **为谁做**: `executive_summary.for_whom`（用户画像）
- **做对的标准**: `executive_summary.success_criteria`（成功指标）
- **约束**: `executive_summary.constraints`（预算/时间/技术栈）
- **关键场景**: `executive_summary.key_scenarios`

同时读取 `guardrails` 字段，了解行为边界（always_do / never_do）。

### Step 2: 读取需求清单
再读取 `requirements[]` 数组，了解具体需求条目。

### Step 3: 需求追踪
你的输出 JSON 顶层必须包含：

```json
{{
  "covered_req_ids": ["REQ-001"],
  "requirement_evidence": [
    {{
      "req_id": "REQ-001",
      "status": "covered|partial|missing",
      "evidence": "说明你在本阶段如何覆盖或未覆盖该需求"
    }}
  ]
}}
```

规则：
- 只允许使用 `frozen_spec.json` 中存在的 REQ-ID。
- 如果某个 P0 需求与你的任务相关但无法覆盖，必须写入 `status="missing"` 并说明原因。
- 不要臆造新的 REQ-ID；需要新增需求时写入建议，但不要改变 frozen spec。
"""
```

### 3.3 `control_contract.py` — 兼容性保障

`_acceptance_from_frozen_spec()` 只读 `frozen.get("requirements", [])`，**不需要任何改动**。新增的顶层字段不会被读取，向后兼容。

---

## 4. 影响评估

### 向后兼容性

| 组件 | 是否需要改动 | 原因 |
|------|-------------|------|
| `frozen_spec.py` | ✅ 是 | 新增顶层字段 + 辅助函数 |
| `task_builder.py` | ✅ 是 | 更新 `REQ_TRACEABILITY_INSTRUCTION` 模板 |
| `control_contract.py` | ❌ 否 | 只读 `requirements[]`，不受影响 |
| `orchestrator_agent.py` | ❌ 否 | 调用 `write_frozen_spec()` 接口不变 |
| Harness V3 / Auditor | ❌ 否 | 通过 `frozen_spec.json` 文件读取，自动获得新字段 |
| 现有 Worker | ❌ 否（可选适配） | 旧 Worker 忽略新字段即可；适配后获得全局理解 |

### 收益

| 维度 | 改进 |
|------|------|
| **Worker 理解质量** | 从"47 条平铺清单" → "先读灵魂，再看骨架" |
| **方案一致性** | 全局摘要作为单一权威源，避免各 Worker 独立理解偏差 |
| **维护成本** | 减少 `task_builder.py` 中 N 个 `living_spec_context` 注入逻辑 |
| **Harness Final** | 最终门禁可直接对比 `executive_summary.success_criteria` vs 实际方案 |

---

## 5. 长期演进建议

### V3 阶段目标

| 目标 | 说明 |
|------|------|
| **需求依赖图** | 在 frozen_spec 中增加 `dependencies: [{"from": "REQ-001", "to": "REQ-003", "type": "blocks"}]`，让 Planner 能识别关键路径 |
| **优先级层级分组** | `requirements` 可按 P0/P1/P2 分组为 `p0_requirements[]` / `p1_requirements[]`，Worker 优先覆盖 P0 |
| **场景-需求映射** | `scenario_coverage: {"场景1": ["REQ-001", "REQ-005"]}`，让 Harness Final 按场景维度验证覆盖度 |
| **structured_requirements.json** | 作为 living_spec → frozen_spec 的中间层，保留原始结构 + 派生 REQ-ID |

### 不推荐的做法

| 做法 | 为什么不推荐 |
|------|-------------|
| 删除 `requirements[]`，完全用 `executive_summary` 替代 | 破坏 `covered_req_ids` 追踪机制，现有 Harness 体系全部需要重写 |
| 在 prompt 中注入完整 living_spec JSON | 浪费 token，Worker 难以从原始 JSON 中提取上下文 |
| 让 Spec Pro 直接输出给 Worker 的 prompt | 违反 Spec Pro → Solution Pro 的契约边界 |
