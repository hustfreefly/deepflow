---
id: contracts/version_control
version: "1.0.0"
component: deepflow_core
updated: "2026-06-01"
status: active
---

# 版本控制契约（Version Control Contract）

> DeepFlow 全项目版本管理的基础性契约
> 所有 prompt/cage/contract/domain/Python 文件的版本标识、更新规则、运行时行为必须遵守本契约

---

## 一、三层版本架构

| 层级 | 标识位置 | 格式 | 作用域 | 更新触发 |
|------|---------|------|--------|---------|
| **L1: 全局版本** | `CHANGELOG.md` + `git tag` | SemVer `X.Y.Z` | 整个 DeepFlow 项目 | 重大发布/破坏性变更 |
| **L2: 组件版本** | `domains/{name}.yaml` 的 `component_version` | SemVer `X.Y.Z` | 单个领域组件 | 该领域 prompt/cage/逻辑变更 |
| **L3: 文件版本** | 文件头部的 YAML Front Matter | SemVer `X.Y.Z` | 单个文件 | 文件内容修改时 |

---

## 二、文件级版本标识规范

### 2.1 格式：YAML Front Matter

所有 `.md`、`.yaml` 文件的版本标识**必须**使用 YAML Front Matter 格式：

```yaml
---
id: <domain>/<name>
version: "<X.Y.Z>"
component: <component_name>
updated: "<YYYY-MM-DD>"
---

# 文件原有内容...
```

### 2.2 必填字段

| 字段 | 说明 | 格式约束 |
|------|------|---------|
| `id` | 文件唯一标识 | `{domain}/{name}` |
| `version` | 语义化版本号 | `X.Y.Z`，三段式 |
| `component` | 所属组件名 | 小写下划线，如 `investment` |
| `updated` | 最后更新日期 | `YYYY-MM-DD` |

### 2.3 可选字段（按需添加）

| 字段 | 适用场景 | 说明 |
|------|---------|------|
| `role` | Prompt .md 文件 | Agent 角色，如 `planner`、`auditor` |
| `status` | Cage .yaml / Prompt | `active` / `deprecated` / `experimental` |
| `requires` | 有依赖关系的 Prompt | 声明对其他 prompt/cage 的版本要求 |
| `deprecated_by` | 已废弃文件 | 指向替代者文件 id |

### 2.4 文件类型差异

**Prompt .md 文件**：
```yaml
---
id: investment/planner
version: "2.0.0"
component: investment
role: planner
updated: "2026-06-01"
status: active
---
```

**Cage .yaml 文件**（已有结构，补充字段）：
```yaml
cage_version: "2.0.0"
component: investment
status: active
# 原有内容...
```

**Contract .md 文件**：
```yaml
---
id: contracts/version_control
version: "1.0.0"
updated: "2026-06-01"
status: active
---
```

**Domain .yaml 文件**（补充字段）：
```yaml
component_version: "2.0.0"
component_name: "Investment"
domain: investment
# 原有内容...
```

---

## 三、SemVer 更新规则

### 3.1 触发条件

| 版本位 | 触发条件 | 示例 |
|--------|---------|------|
| **MAJOR** | 破坏性变更：输出格式改变、新增必需输入、角色定位改变 | 1.x → 2.0.0 |
| **MINOR** | 新增能力：新增可选功能、优化指令措辞、增加维度 | x.0 → x.1.0 |
| **PATCH** | 修复：修正错别字、调整格式、澄清歧义但不改变行为 | x.x.0 → x.x.1 |

### 3.2 更新协议

每次修改文件时，**必须**执行以下步骤：

1. **递增文件 `version`** — 按 SemVer 规则
2. **更新 `updated`** — 当天日期
3. **如属于某组件** — 递增该组件的 `component_version`（`domains/*.yaml`）
4. **更新 `CHANGELOG.md`** — 记录变更描述
5. **如 registry.yaml 注册了此文件** — 同步 registry 中的版本号

**最小变更**（仅改错别字）：只改文件 version + updated，不改组件版本。

---

## 四、运行时行为约束

### 4.1 Prompt 加载

- `read_prompt()` **必须自动剥离** YAML Front Matter，确保 LLM 不看到元数据
- 剥离规则：`content.split('---', 2)` → 返回第三部分（strip）
- 剥离失败时**降级返回原始内容**（不阻断）

### 4.2 版本校验

- `prompt_registry.validate()` **不得**对正确的 Front Matter 报 warning
- `validate()` 应检查：文件版本与 registry 版本是否一致（不一致报 warning）
- `cage_loader` 加载 Cage 时，**必须校验** `cage_version` 字段存在

### 4.3 运行时版本报告

每次 Pipeline 执行时，**必须**在 blackboard 输出 `version_snapshot.json`：

```json
{
  "global_version": "0.1.3",
  "components": {
    "investment": "2.0.0",
    "solution": "3.2.0"
  },
  "prompts_loaded": {
    "investment/planner": "2.0.0"
  },
  "session_id": "xxx",
  "timestamp": "2026-06-01T08:00:00+08:00"
}
```

### 4.4 硬编码禁止

- **禁止**在 Python 代码中硬编码版本号（如 `"version": "4.0"`）
- 全局版本必须从 `CHANGELOG.md` 动态读取
- 组件版本必须从 `domains/*.yaml` 读取

---

## 五、新增文件规则

### 5.1 新 Prompt/Cage 文件

创建新文件时**必须**包含完整的 Front Matter：

```yaml
---
id: domain/new_feature
version: "1.0.0"
component: domain
role: new_role
updated: "<today>"
status: active
---
```

### 5.2 新组件

新增领域组件时，**必须**创建 `domains/{name}.yaml` 并设置：

```yaml
component_version: "1.0.0"
component_name: "组件名称"
domain: new_component
```

### 5.3 注册

如新文件会被 `prompt_registry` 加载，**必须**同步到 `prompts/registry.yaml`。

---

## 六、废弃文件处理

### 6.1 标记废弃

```yaml
---
id: investment/old_planner
version: "1.8.0"
component: investment
status: deprecated
deprecated_by: investment/planner
updated: "2026-06-01"
---
```

### 6.2 归档

deprecated 文件在 N 个版本周期后（建议 2 个 major 版本）移至 `archive/` 目录或删除。

---

## 七、兼容性规则

### 7.1 向后兼容

- MINOR/PATCH 更新**必须保持**向后兼容（现有调用方不需要修改）
- MAJOR 更新**必须**在 CHANGELOG 中明确标注 breaking changes

### 7.2 依赖声明

有跨文件依赖的 Prompt，必须在 Front Matter 中声明：

```yaml
requires:
  - prompt: solution/cage_harness_v2
    min_version: "1.0.0"
```

### 7.3 版本漂移检测

`prompt_registry.validate()` 检测到文件版本与 registry 不一致时：
- 报 warning（不阻断）
- 建议运行迁移脚本同步

---

## 八、CHANGELOG 格式

保持单 `CHANGELOG.md`，每次发布包含：

```markdown
## [0.1.3] - 2026-06-01

### Component Versions
- Spec Pro: 2.3.0 → 2.4.0
- Solution Pro: 3.2.0 → 3.3.0
- Investment: 2.0.0 (no change)

### Added
- 新功能描述

### Changed
- 变更描述

### Fixed
- 修复描述
```

---

## 九、Git 策略

| 事件 | 操作 |
|------|------|
| PATCH 修复 | `git commit -m "fix: description"`, 可选 tag |
| MINOR 功能 | `git commit -m "feat: description"`, `git tag vX.Y.0` |
| MAJOR 破坏 | `git commit -m "BREAKING: description"`, `git tag vX.0.0` |
| 版本迁移 | `git commit -m "chore: migrate version headers"` |

---

## 十、违反本契约的行为

以下行为视为**违反契约**，必须在 code review 中拦截：

| 违规行为 | 严重程度 |
|---------|---------|
| 修改文件不更新 `version` | 🔴 高 |
| Prompt 文件加载未剥离 Front Matter 导致 LLM 看到元数据 | 🔴 高 |
| Python 代码硬编码版本号 | 🟠 中 |
| Cage 文件无 `cage_version` 字段 | 🟠 中 |
| 新文件创建时不含 Front Matter | 🟠 中 |
| MAJOR 变更未在 CHANGELOG 标注 | 🟡 低 |

---

## 附录：标准模板速查

### Prompt .md
```yaml
---
id: {domain}/{name}
version: "{X.Y.Z}"
component: {component}
role: {role}
updated: "{YYYY-MM-DD}"
status: active
---
```

### Cage .yaml
```yaml
cage_version: "{X.Y.Z}"
component: {component}
status: active
```

### Contract .md
```yaml
---
id: contracts/{name}
version: "{X.Y.Z}"
updated: "{YYYY-MM-DD}"
status: active
---
```

### Domain .yaml
```yaml
component_version: "{X.Y.Z}"
component_name: "{Name}"
domain: {domain}
```
