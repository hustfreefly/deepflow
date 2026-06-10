> ⚠️ **本文件是 AI Agent 内部执行指南**，不是用户入口。  
> 用户入口 → [`skills/research-pro/SKILL.md`](../../../skills/research-pro/SKILL.md)（`/research-pro` 触发）  
> 项目概览 → [`README.md`](README.md)

# Research Pro - Agent 执行指南

> **版本**: V1.1 | **最后更新**: 2026-06-11  
> **架构**: 四阶段状态机 (planning → confirming → executing → reporting) + 多源搜索 + 引用验证

---

## 🚀 主 Agent 执行步骤

### Step 0: 参数解析与模式选择

**触发条件**: 用户输入包含触发词

**触发词**:
- "深度研究"
- "research"
- "研究一下"
- "帮我调研"
- "deep research"

**参数解析**:
```python
{
  "query": str,      # 必填: 研究主题
  "mode": str,       # 可选: "quick" | "standard", 默认 "standard"
}
```

**模式选择逻辑**:
- **Mode A (快速模式)**: `mode == "quick"` → 单Agent串行执行，≤10分钟
- **Mode B (标准模式, ≤2子任务)**: `mode == "standard"` 且子任务数 ≤ 2 → 单Agent串行
- **Mode C (标准模式, ≥3子任务)**: `mode == "standard"` 且子任务数 ≥ 3 → 并行子Agent

---

### Step 1: 生成研究计划 + spawn_params

```bash
cd ~/.openclaw/workspace/.deepflow && python3 -c "
import json
from domains.research_pro import run_research_pro
result = run_research_pro(
    query='{QUERY}',
    mode='{MODE}',
)
print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
"
```

`run_research_pro()` 会完成：
- 初始化 ResearchProOrchestrator
- 执行 Planning 阶段，生成分析计划
- 清理旧状态文件（`.completed` 等）
- 初始化通知状态文件
- 返回 `spawn_params`（可直接传给 `sessions_spawn`）

---

### Step 2: 启动管线

```python
# 从 Step 1 的返回值中获取 spawn_params
sessions_spawn(**result["spawn_params"])
```

子 Agent 会自动完成：
1. ✅ 加载已有计划
2. ✅ 自动确认计划（auto-approve）
3. ✅ 执行搜索与研究（Mode A/B/C 自动选择）
4. ✅ 生成研究报告
5. ✅ 写入 `.completed` 标记

---

### Step 3: 等待完成 + 通知用户

子 Agent 完成后，读取报告：
```bash
cat {base_path}/report/final.md | head -100
```

将报告摘要通过 `message` 工具推送给用户。

---

## 📁 Blackboard 布局

```
blackboard/{session_id}/
├── state.json              # 状态机状态
├── source_registry.json    # 来源注册表
├── research/               # 研究数据
│   ├── batch_01/
│   ├── batch_02/
│   └── ...
├── report/                 # 报告输出
│   ├── draft.md
│   └── final.md
└── .completed              # 完成标记
```

---

## 🔧 搜索架构

| 优先级 | 引擎 | 说明 |
|--------|------|------|
| 1 (主路径) | OpenClaw `web_search` | 通过 `web_search_fn` 注入，支持 Brave/Perplexity 等 |
| 2 (降级) | DuckDuckGo (DDGS) | `ddgs_client.py`，仅在 web_search 不可用时使用 |
| 3 (最终降级) | 关键词结构化数据 | `_fallback_search_results()`，无真实搜索结果时 |

---

## 🔒 安全特性

- **SSRF 防护**: DNS 预解析 + IP 黑名单 + 重定向验证 (`safe_fetcher.py`)
- **引用验证**: 五步循环验证 (`citation_verifier.py`)
- **来源分级**: Tier 1/2/3 + 黑名单 (`tier_classifier.py`)
- **URL 安全**: 协议白名单 + 私网拒绝 (`url_utils.py`)

---

## ⚙️ 配置

| 文件 | 用途 |
|------|------|
| `config/research_pro.yaml` | 组件版本、Agent 定义、超时 |
| `config/time_budgets.json` | quick/standard 模式时间预算 |
| `config/completion_criteria.json` | 质量分数、降级规则 |
| `config/tier_domains.json` | 数据源分级（Tier 1/2/3） |

---

## 📊 与 Solution Pro 对齐

| 维度 | Solution Pro | Research Pro |
|------|-------------|-------------|
| 入口函数 | `run_solution_pro(topic)` | `run_research_pro(query)` |
| 返回值 | `{spawn_params, session_id, ...}` | `{spawn_params, session_id, ...}` |
| 启动方式 | `sessions_spawn(**spawn_params)` | `sessions_spawn(**spawn_params)` |
| 子 Agent | Orchestrator 跑 10 阶段 | Orchestrator 跑 4 阶段 |
| 完成标记 | `.completed` 文件 | `.completed` 文件 |
| Cron 巡检 | ✅ 支持 | ✅ 支持（可选） |
