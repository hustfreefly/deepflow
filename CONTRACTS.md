# DeepFlow 契约系统规范

> **版本**: 2.0.0
> **生效日期**: 2026-05-30
> **核心原则**: 契约是给 LLM 读的规范文档。LLM 读懂后在具体场景下自觉遵守并生成检查逻辑。

---

## 一、契约分类

DeepFlow 的契约分两层：

| 层级 | 定义 | 谁必须遵守 | 文件格式 |
|------|------|-----------|---------|
| **基础契约** | 全局规范，所有模块/所有开发活动必须遵守 | 所有 Agent、所有模块 | `.md`（自然语言，LLM 可读） |
| **场景契约** | 特定模块的行为定义，该模块开发时必须遵守 | 对应模块的 Agent | `.yaml`（结构化，LLM 可读） |

---

## 二、文件组织规范

### 2.1 目标目录结构

```
.deepflow/
├── contracts/                     # 基础契约（全局规范）
│   ├── directory_structure.md     # 目录结构规范
│   ├── coding_standards.md        # 编码规范
│   ├── development_workflow.md    # 开发流程规范
│   ├── cage_framework.md          # 契约笼子机制定义
│   └── integration/               # 跨模块集成契约
│       └── spec_to_solution.md    # Spec Pro → Solution Pro 数据交接规范
│
├── cage/                          # 场景契约（模块级行为定义）
│   ├── active/                    # 活跃契约（当前开发中的模块）
│   │   ├── spec_pro_v2.0.yaml
│   │   ├── research_pro_v1.0.yaml
│   │   ├── investment_v2.0.yaml
│   │   └── solution_v1.0.yaml
│   └── archive/                   # 已完成/过时的契约
│
├── docs/                          # 参考文档（不是契约）
│   ├── architecture/              # 架构设计文档
│   ├── reports/                   # 审计报告、评审记录
│   ├── research/                  # 调研分析
│   └── guides/                    # 使用指南、教程
```

### 2.2 规则

| # | 规则 | 说明 |
|---|------|------|
| 1 | **基础契约统一放 `contracts/`** | 不在 cage/、docs/、根目录散落 |
| 2 | **场景契约统一放 `cage/active/`** | 完成后移入 `cage/archive/` |
| 3 | **cage/ 根目录只允许 active/ + archive/** | 不放文件，只放子目录 |
| 4 | **契约 ≠ 文档** | `docs/` 放参考文档，不放契约 |
| 5 | **一个契约一个文件** | 不合并、不拆分 |
| 6 | **契约文件命名** | 基础契约：`snake_case.md`；场景契约：`{module}_v{X.Y}.yaml` |

---

## 三、基础契约文件格式

基础契约是 `.md` 文件，必须包含以下结构：

```markdown
# [契约名称]

> **版本**: X.Y.Z
> **生效日期**: YYYY-MM-DD
> **适用范围**: 一句话说明谁必须遵守

---

## 定义

关键术语定义（避免歧义）

---

## 规则

### 必须做（MUST）
- 规则 1（一句话 + 为什么）
- 规则 2

### 禁止做（MUST NOT / NEVER）
- 禁止 1（一句话 + 为什么）
- 禁止 2

### 建议做（SHOULD）
- 建议 1

---

## 示例

### 正确示例
```
[代码/配置示例]
```

### 错误示例
```
[反例]
```

---

## 验证方式

LLM 如何判断是否违规（自然语言描述，不是脚本）

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
```

**关键要求**：
- 规则用 **MUST / MUST NOT (NEVER) / SHOULD** 三级，LLM 能准确理解优先级
- 每条规则一句话说清 + 一句话说为什么
- 提供正反示例，帮助 LLM 理解边界
- 验证方式描述 LLM 怎么检查，不依赖特定脚本

---

## 四、场景契约文件格式

场景契约是 `.yaml` 文件，必须包含以下字段：

```yaml
# {module}_v{X.Y}.yaml
# 一句话描述模块职责

module: "{module_name}"
version: "{X.Y}"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: "active"              # draft | active | deprecated | archived
complexity: "simple|medium|complex"

description: |
  2-3 句话描述模块职责和核心架构

# ============================================================================
# 红线（P0 — 绝对不可违反）
# ============================================================================
redlines:
  - id: "RED-{PREFIX}-001"
    rule: "一句话自然语言规则"
    reason: "为什么这条是红线"
    check: "LLM 如何验证（自然语言或 grep 命令）"

# ============================================================================
# 接口契约
# ============================================================================
interface:
  python_modules:
    - "模块入口和主要类"
  worker_agents:
    - "Worker 定义"

# ============================================================================
# 行为契约
# ============================================================================
behavior:
  method_name:
    input: "输入约束"
    output: "输出约束"
    success: "成功时行为"
    failure: "失败时行为"

# ============================================================================
# 数据契约
# ============================================================================
data:
  blackboard: "Blackboard 文件结构"
  config: "配置文件路径"

# ============================================================================
# 质量门禁
# ============================================================================
quality_gates:
  p0:
    - "必须通过的检查项"
  p1:
    - "应该通过的检查项"
  p2:
    - "建议通过的检查项"
```

**关键要求**：
- `redlines` 必须有 `check` 字段，告诉 LLM 怎么验证
- `check` 可以是 grep 命令（结构级）或自然语言描述（语义级）
- 文件大小指导：simple ≤ 5KB / medium ≤ 15KB / complex ≤ 30KB（以内容完整性为优先，大小为参考）

---

## 五、契约生命周期

```
草稿 → 活跃 → 废弃 → 归档
 │       │       │       │
 │       │       │       └── 移入 cage/archive/（场景契约）
 │       │       │           或标记 archived（基础契约）
 │       │       │
 │       │       └── 标记 deprecated，保留在 cage/active/
 │       │           给迁移窗口期
 │       │
 │       └── 放在 contracts/（基础）或 cage/active/（场景）
 │
 └── 先写契约，再写代码（契约先行）
```

### 状态说明

| 状态 | 含义 | 位置 |
|------|------|------|
| `draft` | 草稿，尚未正式生效 | contracts/ 或 cage/active/ |
| `active` | 活跃，必须遵守 | contracts/ 或 cage/active/ |
| `deprecated` | 废弃，给迁移窗口期，新代码不应使用 | 原位保留 |
| `archived` | 归档，已完成或过时 | cage/archive/ |

### 变更规则

| 操作 | 规则 |
|------|------|
| 新增契约 | 必须声明 version 和 created |
| 修改契约 | 必须更新 version 和 updated |
| 废弃契约 | 标记 `status: deprecated`，保留原位给迁移窗口 |
| 归档契约 | 场景契约移入 archive/；基础契约标记 `status: archived` |
| 重新激活 | 从 archive/ 移回 active/，更新 version 和 status |
| 删除契约 | 禁止直接删除，只能归档 |

---

## 六、当前契约文件清单

### 基础契约（contracts/）

| 文件 | 来源 | 状态 |
|------|------|------|
| `directory_structure.md` | ← `DIRECTORY_STRUCTURE_CONTRACT.md` | ✅ 已迁入 |
| `coding_standards.md` | ← `docs/design/CODING_STANDARDS.md` | ✅ 已迁入 |
| `development_workflow.md` | ← `docs/design/DEVELOPMENT_RULES.md` | ✅ 已迁入 |
| `cage_framework.md` | ← `cage/README.md` | ✅ 已迁入 |
| `integration/spec_to_solution.md` | 新建 | ✅ 已创建 |

### 场景契约（cage/active/）

| 文件 | 来源 | 状态 |
|------|------|------|
| `spec_pro_v2.0.yaml` | 已有 | ✅ 已精简（24KB） |
| `research_pro_v1.0.yaml` | ← `cage/deepclaw_v1.0.yaml` | ✅ 已重命名+精简（18KB） |
| `investment_v2.0.yaml` | 新建 | ✅ 已创建（5.4KB） |
| `solution_v1.0.yaml` | 新建 | ✅ 已创建（9.7KB） |

### 归档（cage/archive/）

| 文件 | 原因 |
|------|------|
| `DEVELOPMENT_CONTRACT.md` | 设计文档，不是契约 |
| `deepclaw_dev_instructions.md` | 一次性开发指令 |
| `deepflow_navigator_v1.0.yaml` | 已转为 prompt 模板（prompts/system/） |

---

## 七、与其他文件的关系

| 文件 | 定位 | 与契约的关系 |
|------|------|-------------|
| `README.md` | 项目介绍 | 引用契约索引 |
| `CHANGELOG.md` | 变更日志 | 记录契约变更 |
| `SKILL.md` | OpenClaw 技能描述 | 引用相关契约 |
| `pyproject.toml` | 项目配置 | 不是契约 |
| `AGENTS.md`（workspace 级）| Agent 行为规则 | 上层约束，契约不与之冲突 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-05-30 | 初始版本：契约文件系统规范 |
| 2.0.0 | 2026-05-30 | 根据专家反馈修正：补充 integration/、cage 根目录规则、生命周期状态（draft/deprecated/reactivated）、基础契约格式（定义/示例）、场景契约大小限制调整 |
