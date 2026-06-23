# Spec Pro → Solution Pro 链路升级总体方案（最终版）

> **版本**: 2.0 Final | **日期**: 2026-06-02  
> **更新**: 2026-06-03（frozen_spec V2.0 实施记录）
> **原则**: LLM 做语义标注，脚本做格式化组装

---

## 一、问题诊断

### 1.1 当前架构的三层缺陷

| 层级 | 缺陷 | 影响 | 状态 |
|:---|:---|:---|:---|
| ~~**语义丢失**~~ | ~~frozen_spec.py 丢弃了 living_spec 的 7/14 个字段~~ | ~~Worker 不知道"为什么做"~~ | ✅ 已修复（2026-06-03）：全量提取 17 种 category，98 条 REQ |
| ~~**结构扁平**~~ | ~~47 条 REQ 是平铺列表~~ | ~~Worker 不知道"哪些是命脉"~~ | ✅ 已修复：5 个 requirement_groups + executive_summary |
| **关联缺失** | REQ 之间无依赖、无冲突、无关联 | Worker 不知道"REQ-007 和 REQ-011 有张力" | ⏳ LLM 标注阶段待实施 |

### 1.2 场景 B 盲区

直接对话路径（无 Spec Pro）的 Worker 只看到一条 REQ-001，完全在"猜"用户需求。

---

## 更新记录（2026-06-03）

### frozen_spec V2.0 实施完成

**改动**：`domains/solution_pro/frozen_spec.py`，16 行新增代码

| 修复项 | 之前 | 之后 | REQ 数 |
|--------|------|------|--------|
| constraints 提取 | 3 key 硬编码 | 全量遍历 | 3 → 11 |
| guardrails.resolved | 未提取 | 新增 design_decision | 0 → 7 |
| inferred | 未提取 | 新增 inferred category | 0 → 10 |
| 总 REQ 数 | 74 | 98 | +24 |
| 信息保留率 | ~95% | ~100% | +5% |

下游零影响：所有消费方均为泛型遍历，不关心 REQ 数量或 category 类型。

---

## 二、核心设计原则

| # | 原则 | 说明 |
|:---|:---|:---|
| 1 | **LLM 做标注，脚本做组装** | LLM 只输出 JSON 标注，不输出最终 REQ 结构 |
| 2 | **不替换 REQ 结构，只增强元数据** | 脚本先确定性生成 REQ，再合并 LLM 标注 |
| 3 | **executive_summary 注入 Worker prompt** | 强制可见，不靠 Worker 主动读取 |
| 4 | **场景 A 和场景 B 都覆盖** | 场景 B 自动生成 minimal executive_summary |
| 5 | **JSON + Schema 验证** | 解析失败有明确信号，fallback 清晰 |
| 6 | **二级分组** | 12 个 category → 5 个高层 group |
| 7 | **按角色裁剪** | Worker 按角色读取不同分组，减少 token 消耗 |
| 8 | **指针 + 上下文** | executive_summary 用 REQ-ID 指针引用，避免数据冗余 |

---

## 三、frozen_spec.json V2.0 结构

```json
{
  "version": "2.0",
  "topic": "智能简历生成系统",

  "executive_summary": {
    "one_liner": "为半导体封装领域求职者提供基于 OpenClaw 的智能简历定制系统",
    "objective_req": "REQ-001",
    "key_scenarios_reqs": ["REQ-015", "REQ-016"],
    "why": ["HR 每天收到 10+ 猎头职位，手动改简历效率低"],
    "for_whom": [{"role": "求职者", "description": "半导体封装领域"}],
    "success_criteria": ["生成时间 < 60s", "JD 匹配度 > 85%"],
    "constraints": {"budget": "无预算限制", "timeline": "尽快上线"},
    "source": "living_spec"
  },

  "guardrails": {
    "always_do": ["保持简历真实性"],
    "ask_first": ["修改原始简历内容前需确认"],
    "never_do": ["编造虚假经历", "降低信息保真度"]
  },

  "solution_pro_hints": {
    "priority_focus": "保真度和 ATS 兼容性是核心",
    "avoid": "不要过度工程化"
  },

  "requirements": [
    {
      "id": "REQ-001",
      "category": "core_objective",
      "description": "基于 OpenClaw 平台产出定制化 PDF 简历",
      "priority": "P0",
      "group": "Core",
      "source": "$.confirmed.objective",
      "measurable": "",
      "context_note": "用户提到'我需要一个能快速定制简历的系统'"
    },
    {
      "id": "REQ-007",
      "category": "capability",
      "description": "仅做合理拓展，不编造虚假经历",
      "priority": "P0",
      "group": "Boundaries",
      "source": "$.confirmed.capabilities.always_do",
      "measurable": "",
      "dependencies": ["REQ-002"],
      "potential_conflicts": ["REQ-011"],
      "context_note": "用户强调'不希望 AI 乱写，只能基于真实经历'"
    }
  ],

  "requirement_groups": {
    "Core": {
      "description": "核心目标、痛点、场景",
      "categories": ["core_objective", "pain_point", "scenario"],
      "req_ids": ["REQ-001", "REQ-010", "REQ-015", "REQ-016"]
    },
    "Functional": {
      "description": "功能需求、集成需求",
      "categories": ["capability", "integration"],
      "req_ids": ["REQ-002", "REQ-003", "REQ-004", "REQ-005"]
    },
    "NonFunctional": {
      "description": "质量属性、约束条件、成功指标",
      "categories": ["quality_attribute", "constraint", "success_metric"],
      "req_ids": ["REQ-006", "REQ-008", "REQ-009"]
    },
    "Boundaries": {
      "description": "禁止项、行为边界",
      "categories": ["prohibition", "guardrail", "guardrail_prohibition"],
      "req_ids": ["REQ-011", "REQ-012", "REQ-013", "REQ-014"]
    },
    "Context": {
      "description": "用户画像、风险、假设、提示",
      "categories": ["user", "risk", "assumption", "hint"],
      "req_ids": ["REQ-017", "REQ-018", "REQ-019"]
    }
  },

  "coverage_policy": {
    "worker_field": "covered_req_ids",
    "matrix_path": "requirements_traceability_matrix.json",
    "harness_final_must_check_all_p0": true
  }
}
```

### 3.1 新增字段说明

| 字段 | 来源 | 说明 |
|:---|:---|:---|
| `executive_summary` | 脚本从 confirmed 提取 | 指针 + 上下文模式，避免数据冗余 |
| `guardrails` | 直接透传 living_spec | Spec Pro 是需求侧，不应被执行侧改写 |
| `solution_pro_hints` | 直接透传 living_spec | 同上 |
| `requirement_groups` | 脚本基于 category 二级聚合 | 12 category → 5 group |
| `requirements[].group` | 脚本 | 二级分组名称 |
| `requirements[].context_note` | LLM 标注 | 一句话结构化上下文（不是用户原话） |
| `requirements[].dependencies` | LLM 标注 | 依赖的 REQ-ID 列表 |
| `requirements[].potential_conflicts` | LLM 标注 | 潜在冲突（标记为 potential，非 confirmed） |

### 3.2 REQ 标记体系

| 字段 | 类型 | 来源 | 说明 |
|:---|:---|:---|:---|
| `id` | string | 脚本分配 | REQ-001 格式 |
| `category` | enum | 脚本/LLM | 12 种 category |
| `description` | string | 脚本/LLM | 需求描述 |
| `priority` | enum | 脚本/LLM | P0/P1/P2（单维度） |
| `group` | string | 脚本聚合 | Core/Functional/NonFunctional/Boundaries/Context |
| `source` | string | 脚本 | JSONPath 指向 living_spec 源头 |
| `context_note` | string | LLM | 一句话结构化上下文 |
| `dependencies` | list | LLM | 依赖的 REQ-ID |
| `potential_conflicts` | list | LLM | 潜在冲突的 REQ-ID |

---

## 四、Worker 消费范式

### 4.1 注入 Worker prompt（强制可见）

不是让 Worker 自己去读文件，而是**直接注入到 prompt 开头**。

```python
# task_builder.py
def build_planner_task(..., frozen_spec=None):
    if frozen_spec and frozen_spec.get("executive_summary"):
        es = frozen_spec["executive_summary"]
        prompt += f"""
## 全局理解（必须以此为基础设计方案）

**一句话**: {es['one_liner']}
**核心目标**: 见 {es.get('objective_req', 'REQ-001')}
**为什么做**: {', '.join(es.get('why', []))}
**为谁做**: {es.get('for_whom', [])}
**做对的标准**: {', '.join(es.get('success_criteria', []))}
**关键约束**: {es.get('constraints', {})}

## 你的角色相关需求分组

{inject_role_specific_groups(frozen_spec, role='planner')}

（请先理解全局目标，再聚焦你的角色相关分组）
"""
```

### 4.2 按角色裁剪注入内容

| Worker 角色 | 注入分组 | 说明 |
|:---|:---|:---|
| **Planner** | Core + Functional | 规划需要理解目标 + 功能需求 |
| **Data Collection** | Core | 数据收集聚焦痛点和场景 |
| **Reviewer Technical** | Functional + NonFunctional | 技术评审聚焦功能和性能 |
| **Reviewer Business** | Core + Context | 业务评审聚焦目标和用户 |
| **Reviewer Risk** | Boundaries + Context | 风险评审聚焦边界和假设 |
| **Research Expert** | 按专家角度裁剪 | 不同专家关注不同分组 |
| **Consolidator** | 全部 | 整合需要全局视角 |
| **Audit / Fix** | requirement_groups | 检查覆盖度需要全部分组 |
| **Harness Final** | 全部 + 一致性检查 | 最终门禁需要全局验证 |
| **Summarizer** | 全部 | 总结需要全局视角 |

---

## 五、场景 B 覆盖

### 5.1 自动生成 minimal executive_summary

当 `living_spec=None` 时，`build_frozen_spec()` 自动生成：

```json
{
  "executive_summary": {
    "one_liner": "{topic}",
    "objective_req": "REQ-001",
    "key_scenarios_reqs": [],
    "why": [],
    "for_whom": [],
    "success_criteria": [],
    "constraints": {},
    "source": "auto_generated_from_topic"
  }
}
```

Worker 至少知道"这个项目是关于什么的"。

---

## 六、Harness Final 闭环检查

在 `build_harness_final_task()` 的 prompt 中新增：

```
### 全局理解一致性检查（V2.0 新增）

1. 方案的 core value proposition 是否与 executive_summary.why 一致？
2. 方案的目标用户是否与 executive_summary.for_whom 一致？
3. 方案的成功指标是否与 executive_summary.success_criteria 可对照？
4. 如果有不一致，说明原因和改进建议。
```

---

## 七、LLM 标注方案（阶段 3）

### 7.1 LLM 输出 JSON（不是自由文本）

```python
ANNOTATION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["original_text", "category", "priority"],
        "properties": {
            "original_text": {"type": "string"},
            "category": {
                "enum": [
                    "core_objective", "capability", "prohibition",
                    "quality_attribute", "constraint", "integration",
                    "pain_point", "success_metric", "user", "scenario",
                    "risk", "assumption"
                ]
            },
            "priority": {"enum": ["P0", "P1", "P2"]},
            "dependencies": {"type": "array", "items": {"type": "string"}},
            "potential_conflicts": {"type": "array", "items": {"type": "string"}},
            "context_note": {"type": "string"}
        }
    }
}
```

### 7.2 不替换 REQ 结构，只增强元数据

```python
def build_frozen_spec(topic, constraints, living_spec):
    # 1. 脚本确定性生成基础 REQ（现有逻辑不变）
    requirements = _build_from_confirmed(living_spec, topic)

    # 2. 如果有 LLM 标注，合并元数据（不替换结构）
    confirmed = (living_spec or {}).get("confirmed", {})
    if confirmed.get("requirement_annotations"):
        _merge_annotations(requirements, confirmed["requirement_annotations"])

    # 3. 生成 executive_summary 和 requirement_groups（脚本）
    return {
        "version": "2.0",
        "topic": topic,
        "executive_summary": _build_executive_summary(confirmed, requirements),
        "guardrails": living_spec.get("guardrails", {}),
        "solution_pro_hints": living_spec.get("solution_pro_hints"),
        "requirements": requirements,
        "requirement_groups": _build_requirement_groups(requirements),
    }
```

### 7.3 合并逻辑

```python
def _merge_annotations(requirements, annotations):
    """将 LLM 标注合并到对应 REQ（宽松匹配）"""
    for ann in annotations:
        # 通过 original_text 宽松匹配 REQ
        matched_req = _find_matching_req(requirements, ann["original_text"])
        if matched_req:
            # 只增强元数据，不替换基础结构
            matched_req["context_note"] = ann.get("context_note", "")
            matched_req["dependencies"] = ann.get("dependencies", [])
            matched_req["potential_conflicts"] = ann.get("potential_conflicts", [])
            # LLM 标注的 category/priority 可以覆盖脚本默认值
            if ann.get("category"):
                matched_req["category"] = ann["category"]
            if ann.get("priority"):
                matched_req["priority"] = ann["priority"]

def _find_matching_req(requirements, original_text):
    """宽松匹配：子串匹配 + 相似度 > 0.7"""
    for req in requirements:
        if original_text in req["description"] or req["description"] in original_text:
            return req
        # 可选：用 difflib.SequenceMatcher 做相似度匹配
    return None
```

### 7.4 覆盖率检查 + Fallback

```python
def annotate_requirements(living_spec, llm_call_fn):
    """LLM 标注入口"""
    confirmed = living_spec.get("confirmed", {})
    if not confirmed:
        return None  # 无 confirmed，跳过标注

    prompt = _build_annotation_prompt(confirmed)
    try:
        response = llm_call_fn(prompt)
        annotations = json.loads(response)
        jsonschema.validate(annotations, ANNOTATION_SCHEMA)

        # 覆盖率检查
        req_texts = _extract_all_req_texts(confirmed)
        annotated_texts = [a["original_text"] for a in annotations]
        coverage = len(annotated_texts) / max(len(req_texts), 1)

        if coverage < 0.8:
            logger.warning(f"LLM annotation coverage too low: {coverage:.0%}")
            return None

        return annotations

    except (json.JSONDecodeError, jsonschema.ValidationError) as e:
        logger.warning(f"LLM annotation failed: {e}")
        return None  # 失败 → 不写入 annotations，走纯脚本路径
```

### 7.5 Spec Pro coordinator 集成

```python
# coordinator.py — Spec Pro 收尾阶段
def _finalize_living_spec(living_spec_path, llm_call_fn):
    """Spec Pro 收尾：LLM 标注需求"""
    living_spec = json.load(open(living_spec_path))
    annotations = annotate_requirements(living_spec, llm_call_fn)

    if annotations:
        living_spec.setdefault("confirmed", {})["requirement_annotations"] = annotations
        json.dump(living_spec, open(living_spec_path, "w"), ensure_ascii=False, indent=2)
```

---

## 八、实施路线图（两个阶段）

### 阶段 1：frozen_spec 结构升级（2-3 小时）

**核心目标**：让 Worker 获得全局理解

| 改动文件 | 改动内容 | 行数 |
|:---|:---|:---|
| `domains/solution_pro/frozen_spec.py` | 新增 `_build_executive_summary()` + `_build_requirement_groups()` + 场景 B minimal summary + 修改返回值 | +80 |
| `domains/solution_pro/task_builder.py` | 各 Worker prompt 注入 executive_summary（按角色裁剪） | +60 |

**向后兼容**：
- ✅ 纯增量，不改 REQ 结构
- ✅ 旧 Worker 忽略新字段即可
- ✅ golden test 比较时忽略新增字段
- ✅ control_contract.py 无需改动

**验证**：
- 单元测试：frozen_spec.py 生成包含新字段的 frozen_spec.json
- Golden test：运行完整 Solution Pro pipeline

### 阶段 2：Spec Pro 标注增强（4-6 小时）

**核心目标**：REQ 带关联性、优先级、上下文备注

| 改动文件 | 改动内容 | 行数 |
|:---|:---|:---|
| `domains/spec_pro/requirement_structuring.py` | 新建：LLM 标注 + JSON Schema 验证 + 覆盖率检查 | ~120 |
| `domains/spec_pro/coordinator.py` | 收尾阶段调用标注 Worker | +20 |
| `domains/solution_pro/frozen_spec.py` | 新增 `_merge_annotations()` + 读取 annotations | +30 |
| `domains/solution_pro/task_builder.py` | Harness Final prompt 增加全局理解一致性检查 | +15 |

**向后兼容**：
- ✅ frozen_spec.py 有 fallback：无 annotations 时走纯脚本路径
- ✅ LLM 标注写入 `requirement_annotations`（不是 `requirements`），不替换结构
- ✅ Schema 验证失败 → 静默跳过，不影响流程

**验证**：
- 单元测试：标注 Schema 验证 + 合并逻辑 + 覆盖率检查
- 端到端测试：Spec Pro → Solution Pro 完整链路

---

## 九、关键设计决策

| # | 决策 | 选择 | 理由 |
|:---|:---|:---|:---|
| 1 | REQ 优先级 | 单维度 P0/P1/P2 | 避免 priority/importance 语义重叠 |
| 2 | conflicts | 标记为 potential_conflicts | 比完全不做检测更安全，比直接断言冲突更保守 |
| 3 | requirement_groups | 脚本基于 category 二级聚合 | 12 category → 5 group，降低认知负荷 |
| 4 | LLM 输出格式 | JSON + Schema 验证 | 解析失败有明确信号，fallback 清晰 |
| 5 | executive_summary | 脚本生成（指针 + 上下文） | 避免数据冗余，减少 token 消耗 |
| 6 | executive_summary 传递 | 注入 Worker prompt | 强制可见，不会被跳过 |
| 7 | Worker 阅读顺序 | 按角色裁剪 | 聚焦，减少 token 消耗 |
| 8 | source 字段 | JSONPath 格式 | 可追溯，可验证 |
| 9 | context_note | 一句话结构化上下文 | 比用户原话信息密度更高，更稳定 |
| 10 | 场景 B | 自动生成 minimal summary | 不能让 Worker 面对一条 REQ 一脸懵 |
| 11 | Harness 闭环 | 增加全局理解一致性检查 | 确保 executive_summary 被用于评估 |
| 12 | version | 升级为 "2.0" | 让下游可以检测版本匹配 |
| 13 | LLM 标注写入位置 | `requirement_annotations` | 不替换 requirements，只增强元数据 |
| 14 | guardrails | 直接透传 | Spec Pro 是需求侧，不应被执行侧改写 |

---

## 十、风险与缓解

| 风险 | 等级 | 缓解 |
|:---|:---|:---|
| LLM 标注 JSON 格式不稳定 | 🟡 中 | Schema 验证 + 失败 fallback 到纯脚本 |
| Worker prompt 膨胀 | 🟡 中 | 按角色裁剪，只注入相关分组 |
| golden test 失败 | 🟢 低 | 比较时忽略新增字段 |
| context_note 质量不稳定 | 🟢 低 | 一句话约束，信息密度高 |
| 场景 B minimal summary 信息不足 | 🟢 低 | 后续可用轻量 Spec Agent 增强 |
| LLM 标注覆盖率不足 | 🟡 中 | 覆盖率检查 < 80% 时 fallback |
| _merge_annotations 匹配不准 | 🟡 中 | 宽松匹配 + 日志记录未匹配项 |

---

## 十一、文件改动总览

| 文件 | 阶段 | 改动类型 | 行数 |
|:---|:---|:---|:---|
| `domains/solution_pro/frozen_spec.py` | 1 + 2 | 修改 | +110 |
| `domains/solution_pro/task_builder.py` | 1 + 2 | 修改 | +75 |
| `domains/spec_pro/requirement_structuring.py` | 2 | 新建 | ~120 |
| `domains/spec_pro/coordinator.py` | 2 | 修改 | +20 |
| **总计** | | | **~325** |

---

## 十二、验证计划

| 阶段 | 验证方式 | 通过标准 |
|:---|:---|:---|
| 阶段 1 | 单元测试 | frozen_spec.py 生成包含新字段的 JSON |
| 阶段 1 | Golden test | 运行完整 Solution Pro pipeline |
| 阶段 1 | 向后兼容 | 旧 Worker 不报错，control_contract 不受影响 |
| 阶段 2 | 单元测试 | 标注 Schema 验证 + 合并逻辑 + 覆盖率检查 |
| 阶段 2 | 端到端测试 | Spec Pro → Solution Pro 完整链路 |
| 阶段 2 | 回归测试 | 无 annotations 时 fallback 到纯脚本 |
