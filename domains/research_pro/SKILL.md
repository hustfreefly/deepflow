---
name: research-pro
description: "DeepFlow Research Pro — 深度研究引擎。触发：深度研究、技术调研、竞品分析。"
version: "2.0.0"
---

> ⚠️ **本文件是 AI Agent 内部执行指南**，不是用户入口。  
> 用户入口 → [`skills/research-pro/SKILL.md`](../../../skills/research-pro/SKILL.md)（`/research-pro` 触发）  
> 项目概览 → [`README.md`](README.md)

# Research Pro - Agent 执行指南

> **版本**: 2.0.0 | **最后更新**: 2026-06-22  
> **架构**: Python 管线 + 子 Agent 原生搜索 + Python 辅助验证  
> **报告模板**: 2.0.0 (见 `prompts/report_writer.md`)

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

`run_research_pro()` 返回 `spawn_params`（可直接传给 `sessions_spawn`）。

---

### Step 2: 即时反馈 + 启动管线

**🔴 必须先给用户确认消息（在 spawn 之前）：**

```
🔬 收到！正在启动深度研究引擎…
━━━━━━━━━━━━━━━━━━━━
📋 生成研究计划…     ⏳ ~1分钟
🔍 多源搜索…          ⏳ ~5-15分钟
📊 综合分析…          ⏳ ~2-5分钟
📝 生成报告…          ⏳ ~1-3分钟
━━━━━━━━━━━━━━━━━━━━
预计 10 分钟 (快速) / 30 分钟 (标准) 内完成
```

**然后 spawn + yield：**

```python
sessions_spawn(**result["spawn_params"])
sessions_yield()
```

---

### Step 3: 子 Agent 完成 → 质量评估 → 推送结果（🔴 不可跳过）

子 Agent 完成后，**必须在同一个 turn 内完成三步：**

#### 3a. 读取报告
通过 BlackboardManager 2.0.0 API `bm.read("report/final.md")`

#### 3b. 质量评估（LLM-as-Judge）
读取 `prompts/quality_reviewer.md` 中的评估维度，对报告进行语义评估：

```
核心问题：这份报告，你敢不敢拿给投资人看？

5 个维度：
1. 结构完整性 — 叙事结构是否清晰
2. 来源可信度 — 是否有 Tier 标注（🟢🟡🔵）
3. 数据支撑 — 关键结论是否有来源
4. 风险披露 — 不确定性是否标注
5. 可操作性 — 是否有具体建议

输出：deliver / deliver_with_caveats / needs_revision
```

#### 3c. 根据评估结果推送

| Verdict | 动作 |
|---------|------|
| `deliver` | 直接推送核心发现 + 完整报告 |
| `deliver_with_caveats` | 推送 + 附带缺口说明（如"参考资料未标注 Tier"） |
| `needs_revision` | 告知用户当前状态 + 启动补充研究 |

**交付铁律**：推送是 turn 的最后一个动作，禁止 yield / 等待 / 什么都不做。

---

## 子 Agent 执行流程（2.0.0 路径 B）

子 Agent 直接用 OpenClaw 原生工具搜索，Python 只在验证环节辅助。

```
子 Agent
  1. 加载分析计划（读 state.json）
  2. web_search(关键词) → 收集 URL
  3. web_fetch(URL) → 获取内容
  4. LLM 分析 → 写 blackboard/research/
  5. exec → SourceRegistry.register()（Python 防幻觉）
  6. exec → CitationVerifier.verify_all()（Python 引用验证）
  7. 写报告 → .completed
```

### 数据流

```
子 Agent (web_search + web_fetch + LLM)
  │
  ├── 搜索：web_search → 真实结果
  ├── 抓取：web_fetch → 完整内容
  ├── 分析：LLM 能力 → 结构化洞察
  │
  └── 验证（Python 辅助）：
      ├── SourceRegistry — 登记所有来源（防幻觉）
      ├── CitationVerifier — 五步引用验证
      └── TierClassifier — 来源质量分级
```

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

## 📝 Prompt 文件索引

| 文件 | 用途 | 版本 |
|------|------|------|
| `prompts/planning.md` | 研究规划器 — 将查询分解为结构化分析计划 | 2.0.0 |
| `prompts/search.md` | 数据搜索器 — 三阶段多源融合搜索 | 2.0.0 |
| `prompts/tech_analysis.md` | 技术工艺分析 — 技术/工艺/制造类研究 | 2.0.0 |
| `prompts/finance_analysis.md` | 金融分析器 — 投资/财务类研究 | 2.0.0 |
| `prompts/citation_verify.md` | 引用验证器 — 五步引用验证循环 | 2.0.0 |
| `prompts/report_writer.md` | **报告撰写器 — 2.0.0 报告模板 (SCR/叙事框架/置信度/条件项)** | 2.0.0 |

> **report_writer.md** 是报告结构的唯一权威定义，包含：SCR 执行摘要、维度叙事框架、置信度标注、待验证假设、条件项机制、叙事防幻觉约束。

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
