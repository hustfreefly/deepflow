# DeepFlow 配置指南

> **版本**: 0.4.0 (Spec Pro v2.4 + Solution Pro 2.0.0 + Research Pro)
> **变更**: Investment 模块已移除，框架不再需要外部 Python 依赖

---

## 零配置启动

**OpenClaw 用户 clone 后无需任何额外配置。**

| 依赖 | 状态 |
|------|------|
| pyyaml | ✅ OpenClaw 自带 |
| pandas | ✅ OpenClaw 自带 |
| requests | ✅ OpenClaw 自带 |
| sessions_spawn | ✅ OpenClaw 运行时提供 |
| web_search | ✅ OpenClaw 工具提供 |

**不需要安装的：**
- ❌ tushare（投资数据，模块已移除）
- ❌ duckduckgo_search（OpenClaw 有 web_search）
- ❌ google-genai（OpenClaw 有 web_search）

---

## 前置要求

- **OpenClaw** ≥ 2026.4.x（必需，核心调度依赖 `sessions_spawn`）
- **Python** 3.10+

---

## 快速开始

```bash
# 1. Clone 到 OpenClaw workspace
cd ~/.openclaw/workspace
git clone https://github.com/hustfreefly/deepflow.git .deepflow

# 2. 在 OpenClaw 中使用
# 方案一：通过对话触发
"帮我梳理需求：我要做一个 AI 算力调度平台"     → Spec Pro
"帮我设计一个智能物流仓储系统升级方案"          → Solution Pro

# 方案二：通过代码触发
# 详见 README.md Quick Start
```

---

## 配置项（可选）

DeepFlow v0.4.0 开箱即用，以下配置均为**可选**：

### Solution Pro 模式

Solution Pro 使用固定 10 阶段管线，无需额外配置。可选参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| `solution_type` | 方案类型 | `architecture`, `code`, `general` |
| `constraints` | 约束条件 | `["预算500万", "周期6个月"]` |
| `stakeholders` | 利益相关者 | `["技术团队", "财务总监"]` |
| `living_spec` | 从 Spec Pro 传递的 Living Spec | `{"confirmed": {...}}` |

### 飞书输出

如果需要将报告推送到飞书：

```bash
# 飞书凭证从 OpenClaw 配置自动读取（~/.openclaw/openclaw.json）
# 无需手动配置
```

---

## 旧版配置迁移（v0.3.0 → v0.4.0）

如果你之前使用过 Investment 模块：

| 旧配置项 | 新状态 | 说明 |
|---------|--------|------|
| `TUSHARE_TOKEN` | ❌ 不再需要 | Investment 模块已移除 |
| `GEMINI_API_KEY` | ❌ 不再需要 | 搜索使用 OpenClaw web_search |
| `config/data/credentials.yaml` | ❌ 不再需要 | 凭证由 OpenClaw 管理 |
| `config/data/search_config.yaml` | ❌ 不再需要 | 搜索由 OpenClaw web_search 处理 |

---

## 历史

- **v0.4.0 (2026-06-05)**: Investment 模块移除，零外部依赖
- **v0.3.0 (2026-06-03)**: 四域架构完成
- **v0.1.0 (2026-05-06)**: 初始版本
