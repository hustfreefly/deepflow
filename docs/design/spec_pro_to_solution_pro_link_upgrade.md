# Spec Pro → Solution Pro 链路升级方案

> **更新**: 2026-06-03（frozen_spec V2.0 实施记录）

## 一、问题背景

### 当前架构缺陷（已修复 2026-06-03）

Solution Pro 的 `frozen_spec.py` ~~把 Spec Pro 的 `living_spec` 展平成 REQ-ID 列表（47条平铺）~~ → **已修复**：V2.0 现已提取 98 条 REQ（17 种 category），全量覆盖 living_spec 所有字段。

| 原问题 | 状态 |
|--------|------|
| Worker 缺乏全局理解 | ✅ 已修复：executive_summary + requirement_groups 注入 worker prompt |
| REQ 之间没有关联性 | ⏳ LLM 标注阶段待实施 |
| REQ 没有重要性分级 | ✅ 已修复：P0/P1/P2 优先级体系已建立 |

### 根本原因
`living_spec` 只有一层（结构化字段），缺乏"真实需求上下文"。`frozen_spec.py` 是纯脚本，只能机械转换，无法理解需求语义。

---

## 二、解决方案（两期实施）

### 第一期：frozen_spec 补全（立即可做）
**目标**：不改 REQ 结构，保持向后兼容，给 Worker 增加全局理解

#### 2.1 新增 executive_summary（全局摘要）
在 `frozen_spec.json` 顶层新增 `executive_summary` 字段，包含：
```json
{
  "executive_summary": {
    "one_liner": "为半导体封装领域的 HR 经理和猎头提供一个智能简历定制系统",
    "objective": "基于 OpenClaw 平台，输入猎头职位信息+公司信息，产出定制化 PDF 简历",
    "why": ["HR 每天收到 10+ 猎头职位，手动改简历效率低", "现有简历无法匹配不同 JD"],
    "for_whom": [
      {"role": "HR 经理", "description": "需要快速定制简历响应猎头"},
      {"role": "猎头", "description": "需要匹配候选人到不同职位"}
    ],
    "success_criteria": ["简历生成时间 < 60 秒", "JD 匹配度 > 85%"],
    "constraints": {"budget": "无预算限制", "timeline": "尽快上线"},
    "key_scenarios": ["收到猎头推送新职位，快速定制简历", "批量生成多份简历应对不同职位"]
  }
}
```

**实现方式**：`frozen_spec.py` 脚本从 `confirmed` 字段提取（确定性逻辑，不依赖 LLM）

#### 2.2 新增 requirement_groups（需求分组）
在 `frozen_spec.json` 顶层新增 `requirement_groups` 字段：
```json
{
  "requirement_groups": {
    "目标与定位": ["REQ-001"],
    "输入处理": ["REQ-002", "REQ-003", "REQ-004"],
    "内容生成": ["REQ-005", "REQ-006", "REQ-007", "REQ-011"],
    "输出格式": ["REQ-008", "REQ-009", "REQ-010"],
    "质量保障": ["REQ-012", "REQ-013", "REQ-014"],
    "平台约束": ["REQ-015", "REQ-016"]
  }
}
```

**实现方式**：`frozen_spec.py` 脚本基于 REQ 的 `category` 字段自动分组（确定性逻辑）

#### 2.3 新增 guardrails 和 solution_pro_hints 透传
```json
{
  "guardrails": {
    "always_do": ["保持简历真实性", "确保 ATS 兼容性"],
    "ask_first": ["修改原始简历内容前需确认"],
    "never_do": ["编造虚假经历", "降低信息保真度"]
  },
  "solution_pro_hints": {
    "priority_focus": "保真度和 ATS 兼容性是核心",
    "avoid": "不要过度工程化，保持轻量"
  }
}
```

**实现方式**：直接从 `living_spec` 透传

#### 2.4 修改范围
| 文件 | 改动 | 行数预估 |
|------|------|----------|
| `domains/solution/frozen_spec.py` | 新增 `_build_executive_summary()` 和 `_build_requirement_groups()` 函数 | ~80 行 |
| `domains/solution/task_builder.py` | 更新 Worker prompt，引导先读 executive_summary | ~10 行 |

#### 2.5 向后兼容性
- ✅ 新增字段，不改 REQ 结构
- ✅ 现有 Worker 忽略新字段即可，不会报错
- ✅ `control_contract.py` 无需改动
- ✅ 旧版 `frozen_spec.json` 仍然能正常工作

#### 2.6 验证方式
1. 单元测试：`frozen_spec.py` 生成包含新字段的 `frozen_spec.json`
2. Golden test：运行一次完整的 Solution Pro pipeline，检查 Worker 是否正确使用了 `executive_summary`
3. 回归测试：现有 golden case 仍然通过

---

### 第二期：Spec Pro 升级（需要 Spec Pro 配合）
**目标**：Spec Pro 直接生成结构化 REQ，`frozen_spec.py` 改为透传模式

#### 3.1 Spec Pro 新增 RequirementStructuringWorker
**触发时机**：Spec Pro 收尾阶段（用户确认"需求已完整"后）

**输入**：`living_spec.confirmed`（已收集的结构化字段）

**输出**：`living_spec.confirmed.requirements`（结构化 REQ 列表）

```json
{
  "confirmed": {
    "requirements": [
      {
        "id": "REQ-001",
        "category": "core_objective",
        "description": "基于 OpenClaw 平台，输入猎头职位信息+公司信息，产出定制化 PDF 简历",
        "priority": "P0",
        "group": "目标与定位",
        "dependencies": [],
        "conflicts": [],
        "source_story": "用户提到'我需要一个能快速定制简历的系统'"
      },
      {
        "id": "REQ-007",
        "category": "capability",
        "description": "仅做合理拓展，不编造虚假经历",
        "priority": "P0",
        "group": "内容生成",
        "dependencies": ["REQ-002"],
        "conflicts": [],
        "source_story": "用户提到'我不希望 AI 乱写，只能基于真实经历'"
      }
    ]
  }
}
```

**REQ 字段定义**：
- `id`: REQ-001 格式，顺序递增
- `category`: core_objective / capability / quality_attribute / constraint / integration
- `description`: 需求描述
- `priority`: P0（必须）/ P1（应该）/ P2（可以）
- `group`: 需求分组（中文，如"内容生成"、"质量保障"）
- `dependencies`: 依赖的 REQ-ID 列表（如 ["REQ-002"]）
- `conflicts`: 互斥的 REQ-ID 列表（**初期只接受用户显式声明，不做推断**）
- `source_story`: 用户原话（溯源链接回第一层）

**JSON Schema 校验**：
```json
{
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "category", "description", "priority", "group"],
    "properties": {
      "id": {"type": "string", "pattern": "^REQ-\\d{3}$"},
      "category": {"enum": ["core_objective", "capability", "quality_attribute", "constraint", "integration"]},
      "description": {"type": "string"},
      "priority": {"enum": ["P0", "P1", "P2"]},
      "group": {"type": "string"},
      "dependencies": {"type": "array", "items": {"type": "string"}},
      "conflicts": {"type": "array", "items": {"type": "string"}},
      "source_story": {"type": "string"}
    }
  }
}
```

**重试机制**：
- LLM 生成 JSON → JSON Schema 校验 → 失败则重试（最多 3 次）
- 3 次失败 → fallback 到第一期方案（`frozen_spec.py` 脚本生成）

#### 3.2 frozen_spec.py 改为透传模式
```python
def build_frozen_spec(topic, constraints, living_spec):
    confirmed = living_spec.get("confirmed", {})
    
    # 检查是否有 Spec Pro 生成的结构化 REQ
    if confirmed.get("requirements"):
        # 透传模式：直接使用 Spec Pro 的 REQ
        requirements = confirmed["requirements"]
        requirement_groups = _build_groups_from_requirements(requirements)
    else:
        # Fallback 模式：现有的机械转换逻辑
        requirements = []
        _add_requirement(requirements, "objective", ...)
        # ... 其他字段
        requirement_groups = _build_requirement_groups(requirements)
    
    return {
        "version": "2.0",
        "executive_summary": _build_executive_summary(confirmed),
        "guardrails": living_spec.get("guardrails", {}),
        "solution_pro_hints": living_spec.get("solution_pro_hints"),
        "requirements": requirements,
        "requirement_groups": requirement_groups,
        "coverage_policy": {...}
    }
```

#### 3.3 修改范围
| 文件 | 改动 | 行数预估 |
|------|------|----------|
| `domains/spec_pro/requirement_structuring_worker.py` | 新增 LLM Worker | ~150 行 |
| `domains/spec_pro/coordinator.py` | 在收尾阶段调用新 Worker | ~20 行 |
| `domains/spec_pro/worker_prompts.py` | 新增 Worker prompt | ~100 行 |
| `domains/solution/frozen_spec.py` | 改为透传模式 | ~30 行 |

#### 3.4 向后兼容性
- ✅ `frozen_spec.py` 有 fallback 逻辑，旧版 `living_spec` 仍然能工作
- ✅ REQ 结构扩展（新增字段），不改现有字段
- ⚠️ `task_builder.py` 需要更新 Worker prompt，引导使用 `dependencies` 和 `conflicts`
- ⚠️ `REQ_TRACEABILITY_INSTRUCTION` 需要更新，支持 `dependency_aware` 输出

#### 3.5 验证方式
1. 单元测试：RequirementStructuringWorker 生成符合 Schema 的 REQ
2. Golden test：运行完整的 Spec Pro → Solution Pro pipeline
3. 回归测试：第一期方案仍然能工作（fallback 模式）

---

## 三、实施计划

### 第一期（立即可做）
**时间**：2-3 小时
**风险**：低（纯增量，不改 REQ 结构）
**收益**：Worker 获得全局理解，方案质量提升

**步骤**：
1. 修改 `frozen_spec.py`，新增 `_build_executive_summary()` 和 `_build_requirement_groups()`
2. 修改 `task_builder.py`，更新 Worker prompt
3. 编写单元测试
4. 运行 Golden test 验证

### 第二期（需要 Spec Pro 配合）
**时间**：4-6 小时
**风险**：中（涉及 Spec Pro 改动，LLM 生成 JSON 可能不稳定）
**收益**：REQ 带关联性、分组、优先级，方案设计更精准

**步骤**：
1. 设计 RequirementStructuringWorker 的 prompt
2. 实现 Worker + JSON Schema 校验 + 重试机制
3. 修改 `coordinator.py`，在收尾阶段调用新 Worker
4. 修改 `frozen_spec.py`，改为透传模式
5. 编写单元测试
6. 运行完整的 Spec Pro → Solution Pro pipeline 验证

---

## 四、关键决策（待确认）

### 4.1 REQ 优先级：单维度 vs 双维度？
**专家建议**：合并为一个维度（避免 priority 和 importance 语义重叠）

**方案**：只保留 `priority`（P0/P1/P2），不新增 `importance`

**理由**：
- P0 = 必须做 = 核心命脉
- P1 = 应该做 = 重要
- P2 = 可以做 = 锦上添花

### 4.2 conflicts 字段：推断 vs 显式声明？
**专家建议**：初期只接受用户显式声明，不做推断（避免误报）

**方案**：
- RequirementStructuringWorker 只在用户明确说"A 和 B 冲突"时才标注 `conflicts`
- 不主动推断冲突关系

**理由**：误报成本高（Worker 看到冲突后可能放弃本可兼容的实现）

### 4.3 场景 B（直接对话路径）：轻量 Spec Agent
**专家建议**：第二期完成后，再实现轻量 Spec Agent

**方案**：
- 第二期完成后，如果用户没有运行 Spec Pro，主 Agent 调用轻量 Spec Agent
- 轻量 Spec Agent 基于 `topic + constraints` 推断 `living_spec`（一次 LLM 调用）
- 然后走正常的 Spec Pro → Solution Pro 链路

**时间**：第二期完成后再做（预估 2-3 小时）

---

## 五、预期收益

### 第一期收益
1. **Worker 获得全局理解**：先读 `executive_summary`，再看 REQ 清单
2. **方案质量提升**：方案设计更贴合用户真实意图
3. **零风险**：不改 REQ 结构，向后兼容

### 第二期收益
1. **REQ 带关联性**：Worker 知道 REQ 之间的依赖和冲突
2. **方案设计更精准**：按分组执行，优先级清晰
3. **需求追溯更完整**：每条 REQ 都有 `source_story` 链接回用户原话

---

## 六、下一步行动

**立即执行第一期**：
1. 修改 `frozen_spec.py`，新增 `_build_executive_summary()` 和 `_build_requirement_groups()`
2. 修改 `task_builder.py`，更新 Worker prompt
3. 编写单元测试
4. 运行 Golden test 验证

**第一期完成后，再启动第二期**。
