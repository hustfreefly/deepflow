# DeepFlow 架构复盘 — 专家评审材料

> **评审日期**: 2026-06-23
> **评审范围**: Solution Pro → Ship Pro 端到端管线暴露的系统性问题
> **目标**: 评估当前症状诊断的准确性，以及 Contract Layer 方案的可行性

---

## 一、背景：DeepFlow 是什么

DeepFlow 是一个多 Agent 协作的解决方案设计平台。核心流程：

```
用户需求 → Solution Pro（10阶段管线）→ 冻结方案 → Ship Pro（5阶段管线）→ 可执行工作包
```

**Solution Pro 10阶段**：数据收集 → 规划 → 3路评审 → 3路研究 → 整合 → 审计 → 修复 → 专家修复 → 验证 → 总结
**Ship Pro 5阶段**：Architect → Decomposer → Specifier → Reviewer → Packager

每个阶段由独立的 LLM sub-agent 执行，通过 blackboard（文件系统）传递数据。

---

## 二、6/23 端到端执行暴露的 10 个问题

### 🔴 P1 — 阻塞性问题（4个）

**P1-1: ship_package.json Schema 校验失败：128 个错误**
- Packager 输出与 `ship_package_v3.schema.json` 严重不一致
- `_meta` 在顶层（schema 不允许）
- `meta.input_format` 用 `"A"` 但 schema 期望 `"A_final_solution"`
- `work_packages` 有额外字段 `constraints`/`related_modules`/`requirements`
- `model_tier` 用 `"standard"` 但 schema 枚举是 `claude-opus/sonnet/gpt-4o` 等
- `risk_register` 缺 `title`/`likelihood` 必填字段
- **根因**: Packager prompt 的输出 schema 与 JSON schema 文件不同步

**P1-2: Architect Prompt ↔ Gate 契约断裂**
- `gate_architect()` 检查两个 Major 字段：`project_type`（顶层）和 `requirements[].mapped_components`
- 但 `architect.md` prompt 的输出 schema 完全没有这两个字段
- **结果**: 每次运行必然触发 CONDITIONAL，gate 形同虚设

**P1-3: pipeline_status.json 状态机失效**
- 5 个阶段全部完成，但 `pipeline_status.json` 卡在 `current_agent: specifier, state: running`
- **根因**: 主 Agent 手动 spawn 子 Agent，绕过了 `run_pipeline.py` 的状态更新逻辑

**P1-4: Solution Pro 状态文件不一致**
- `.completed.json` 说 `status: completed`，但 `.stage_progress.json` 说 `status: running`
- **根因**: completion_handler 更新了一个文件但没更新另一个

### 🟡 P2 — 功能性问题（4个）

**P2-1: SKILL.md 与 run_pipeline.py 流程版本不一致**
- SKILL.md 描述 V2 流程（Pre-Scanner → Compiler → Reviewer）
- run_pipeline.py 实现 V3 流程（Architect → Decomposer → Specifier → Reviewer → Packager）
- 主 Agent 不知道该遵循哪个

**P2-2: frozen_blueprint.json 未生成**
- Ship Pro SKILL.md Step 0 要求检查此文件
- Solution Pro 的 completion_handler 没有生成此文件的步骤

**P2-3: Solution Pro 缺失 final_solution.md**
- completion_handler 定义了 3 个 required artifacts，只生成了 2 个

**P2-4: Reviewer Prompt 占位符未替换**
- reviewer.md 中有 `{STAGE_REGISTRY["reviewer"]}` 等模板变量未被替换

### 🟢 P3 — 改进建议（2个）

**P3-1: control_contract.json 降级警告**
**P3-2: Ship Pro Cron Watcher 未设置**

---

## 三、历史背景：6/22 已做过一轮系统修复

6/22 修复了 79 个"带病运行"问题，核心手段是 **STAGE_PATH_REGISTRY**——统一文件路径命名。

| 维度 | 6/22 修了吗 | 6/23 现状 |
|:---|:---:|:---:|
| **Where** — 文件放哪 | ✅ 统一了路径 | ✅ 已解决 |
| **What** — 数据长什么样 | ❌ 未触及 | 🔴 128 个 schema 错误 |
| **How** — 怎么跑 | ❌ 未触及 | 🔴 主 Agent 绕过管线引擎 |
| **When** — 状态何时变 | ❌ 未触及 | 🔴 状态不一致 |

---

## 四、当前诊断：1 个架构缺陷，4 个投影

### 核心论点

> **DeepFlow 是一个分布式系统，但没有合同层（Contract Layer）。**

5 个组件独立维护对"系统应该怎样工作"的理解，没有任何机制确保一致：

```
Prompt (Markdown)  ──→ "我觉得输出应该长这样"
Gate (Python)      ──→ "我觉得应该检查这些字段"  
Schema (JSON)      ──→ "我觉得最终产物应该长这样"
Orchestrator (Py)  ──→ "我觉得状态应该这样流转"
SKILL.md (Markdown)──→ "我觉得流程应该是这样"
```

### 为什么打地鼠会无限循环

每修一个问题，只是在 5 份文档的某两份之间做一次性对齐：

| 修复行为 | 改了什么 | 没改什么 | 下次断裂点 |
|:---|:---|:---|:---|
| 给 Architect prompt 加 `project_type` | Prompt | Gate 可能又加新检查 | Gate ↔ Prompt 再次分裂 |
| 对齐 Packager prompt 和 Schema | Prompt + Schema | Gate 不知道 | Gate ↔ Schema 分裂 |
| 修状态更新逻辑 | completion_handler | run_pipeline.py 的状态机 | 两个状态机分裂 |
| 统一 SKILL.md 和 run_pipeline | SKILL.md | orchestrator.py 还是第三条路 | 三条路分裂 |

---

## 五、提议方案：Contract Layer

### Phase 1 — 合同注册表（Contract Registry）

每个 Agent 定义一个 `contract.yaml`，从中自动生成 Prompt schema 段落、Gate 检查代码、JSON Schema。

```yaml
# agents/architect/contract.yaml
name: architect
version: "2.0"
output:
  required_fields:
    project_type: { type: string, enum: [web_app, data_pipeline, ...] }
    modules: { type: array, minItems: 1 }
    requirements: 
      type: array
      items:
        mapped_components: { type: array, required: true }
```

### Phase 2 — 单一执行引擎
消灭 3 条执行路径（SKILL.md / run_pipeline.py / orchestrator.py），只留 `run_pipeline.py` CLI。

### Phase 3 — 跨域合同
Solution Pro → Ship Pro 的交接定义为 formal contract。

### 修复优先级

| 层面 | 现状 | 系统性修复 |
|:---|:---|:---|
| Where (路径) | ✅ 已修 | STAGE_PATH_REGISTRY |
| What (格式) | 🔴 5份独立文档 | Contract Registry → 自动生成 |
| How (流程) | 🔴 3条执行路径 | 单一引擎 + CLI-only |
| When (状态) | 🔴 多处独立管理 | 集中式状态机 |
| Who (交接) | 🔴 无正式定义 | 跨域合同 |

---

## 六、评审要求

请从您的专业角度，回答以下问题（不限于此，欢迎提出盲点）：

1. **诊断准确性**: "缺少合同层"是否真的是根因？还是有更深层的问题？
2. **方案可行性**: Contract Layer 在 LLM Agent 场景下是否可行？LLM 输出天然不确定，contract 能约束到什么程度？
3. **方案完整性**: 方案是否有遗漏？实施顺序是否合理？
4. **替代方案**: 是否有更简单/更有效的解决路径？
5. **风险与代价**: 实施 Contract Layer 本身可能引入什么新问题？
6. **优先级判断**: 在有限资源下，应该先修什么？

请自由发挥，给出真实判断，不需要迎合提案。
