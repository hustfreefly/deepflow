---
id: spec_pro/versioning
version: "1.0.0"
component: spec_pro
role: documentation
updated: "2026-06-02"
---

# Spec Pro 版本语义说明

Spec Pro 有三层版本号，各自独立演进：

| 层级 | 文件 | 当前值 | 含义 |
|------|------|--------|------|
| **Component** | `config/spec_pro.yaml` → `component_version` | `2.3.0` | Python 代码版本（coordinator + merge_spec + models 等） |
| **Prompt** | 各 `prompts/*.md` → `version` | `2.1.0` | Prompt 文件版本，独立于代码演进 |
| **Cage** | `cage/active/spec_pro_v2.0.yaml` → `version` | `2.1` | 契约笼子版本，描述架构约束和红线 |

## 为什么允许不同

- **Component** 跟随代码改动递增（修 bug、加功能）
- **Prompt** 只在 prompt 文本变更时递增（代码修复不影响 prompt）
- **Cage** 只在架构约束变更时递增（红线和 Worker 分工不变则不递增）

## 如何读取

- 代码中：`models.py::_read_spec_pro_version()` 从 `config/spec_pro.yaml` 读取 `component_version`
- Living Spec：`meta.version` 使用 `component_version`
