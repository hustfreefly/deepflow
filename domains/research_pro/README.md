# DeepFlow Research Pro

> Multi-source deep research pipeline with citation verification.  
> Runs on [OpenClaw](https://openclaw.ai) platform.

---

## ⚡ 5 分钟上手

### 前提条件

1. 安装 [OpenClaw](https://docs.openclaw.ai)（AI Agent 运行时）
2. 配置 OpenClaw 的搜索 provider（Brave Search / Perplexity 等，参见 [搜索配置](#搜索配置)）
3. 将 DeepFlow 放到 OpenClaw workspace 下：
   ```bash
   # 假设 OpenClaw workspace 在 ~/.openclaw/workspace
   cd ~/.openclaw/workspace
   git clone https://github.com/deepflow/deepflow .deepflow
   ```

### 方式 1：对话触发（推荐）

在 OpenClaw 对话中直接说：

```
深度研究 贵州茅台2024年投资价值
```

或：

```
/research-pro 分析AI芯片市场趋势
```

OpenClaw 会自动识别触发词，启动 Research Pro 流程。

### 方式 2：Python API

```python
from domains.research_pro import run_research_pro

# Step 1: 生成计划
result = run_research_pro(query="分析贵州茅台2024年投资价值", mode="standard")

# Step 2: 启动子 Agent 执行
sessions_spawn(**result["spawn_params"])
```

> **注意**：`sessions_spawn` 是 OpenClaw 的 Agent 工具，不能在普通 Python 脚本中调用。
> 这个 API 是给 OpenClaw 主 Agent 内部使用的。

### 方式 3：DeepFlow 统一入口

```python
from core.unified_entry import UnifiedEntry

entry = UnifiedEntry()
result = entry.run(domain="research_pro", context={"query": "AI芯片市场分析"})
```

---

## 触发方式汇总

| 方式 | 示例 | 说明 |
|------|------|------|
| `/research-pro` | `/research-pro 分析茅台` | OpenClaw Skill 入口 |
| `/research` | `/research 芯片市场` | 别名 |
| 自然语言 | `深度研究 XXX` / `帮我调研 XXX` | 自动识别 |
| Python API | `run_research_pro(query=...)` | 程序化调用 |
| UnifiedEntry | `entry.run(domain="research_pro")` | DeepFlow 统一入口 |

---

## 架构

四阶段状态机：

```
Planning → Confirming → Executing → Reporting
（生成计划）（用户确认）（搜索研究）（生成报告）
```

三种执行模式（自动选择）：

| 模式 | 条件 | 执行方式 | 耗时 |
|------|------|---------|------|
| Mode A (快速) | `mode="quick"` | 单 Agent 串行 | ≤10 分钟 |
| Mode B (标准) | `mode="standard"` + ≤2 子任务 | 单 Agent 串行 | ≤30 分钟 |
| Mode C (标准并行) | `mode="standard"` + ≥3 子任务 | 并行子 Agent | ≤30 分钟 |

---

## 搜索架构

| 优先级 | 引擎 | 说明 |
|--------|------|------|
| **主路径** | OpenClaw `web_search` | 支持 Brave/Perplexity/Gemini 等，通过 `web_search_fn` 注入 |
| **降级** | DuckDuckGo (DDGS) | `ddgs_client.py`，仅在 web_search 不可用时使用 |
| **最终降级** | 关键词结构化数据 | 无真实搜索结果时的 fallback |

### 搜索配置

在 OpenClaw 的 `openclaw.json` 中配置搜索 provider：

```json
{
  "web": {
    "search": {
      "provider": "brave",
      "apiKey": "YOUR_BRAVE_API_KEY"
    }
  }
}
```

支持的 provider：`brave`（推荐）、`perplexity`、`gemini`、`duckduckgo`

---

## 配置

所有配置文件在 `config/` 目录：

| 文件 | 用途 | 示例 |
|------|------|------|
| `research_pro.yaml` | 组件版本、Agent 定义 | `component_version: "1.0.0"` |
| `time_budgets.json` | quick/standard 模式时间预算 | `{"quick_mode": {"total_timeout": 600}}` |
| `completion_criteria.json` | 质量分数阈值、降级规则 | `{"min_sources": 5, "min_citations": 5}` |
| `tier_domains.json` | 数据源分级（Tier 1/2/3） | `{"tier_1": ["reuters.com", "sec.gov"]}` |

---

## 安全特性

- **SSRF 防护**: DNS 预解析 + IP 黑名单 + 重定向验证（`safe_fetcher.py`）
- **URL 安全**: 协议白名单 + 私网拒绝（`url_utils.py`）
- **引用验证**: 五步循环验证 + 可信度评分（`citation_verifier.py`）
- **来源分级**: Tier 1/2/3 + 黑名单域名（`tier_classifier.py`）

---

## 测试

```bash
# 安装测试依赖
pip install -r requirements.txt
pip install pytest

# 运行全量测试
cd domains/research_pro
pytest tests/ -v
```

---

## 目录结构

```
domains/research_pro/
├── README.md                 # ← 你在看的文件
├── SKILL.md                  # Agent 执行指南（主 Agent 内部使用）
├── orchestrator.py           # 核心编排器（四阶段状态机）
├── keyword_generator.py      # 搜索关键词生成
├── safe_fetcher.py           # 安全 HTTP 获取（SSRF 防护）
├── source_registry.py        # 来源注册表（防幻觉核心）
├── citation_verifier.py      # 引用验证（五步循环）
├── tier_classifier.py        # 域名质量分级
├── url_utils.py              # URL 安全验证工具
├── ddgs_client.py            # DuckDuckGo 搜索客户端（fallback）
├── config/                   # 配置文件
├── prompts/                  # Agent Prompt 模板
└── tests/                    # 单元测试
```

OpenClaw Skill 入口（`/research-pro` 触发）：
```
skills/research-pro/SKILL.md  # OpenClaw 用户入口
```

---

## 文档导航

| 文档 | 面向 | 说明 |
|------|------|------|
| **本文件** (README.md) | 所有人 | 项目概览 + 快速上手 |
| `SKILL.md` | OpenClaw 主 Agent | 执行指南（Step 1-3 流程） |
| `skills/research-pro/SKILL.md` | OpenClaw 用户 | `/research-pro` 触发入口 |
| `_overview.md` | 开发者 | 代码索引 + 模块说明 |
| `../../README.md` | 所有人 | DeepFlow 整体架构 |

---

## License

MIT — see [LICENSE](LICENSE)
