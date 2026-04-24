# DeepFlow V4.0 修正方案
## Workers 自主搜索 + Orchestrator 补充搜索

**修正日期**: 2026-04-22 23:21
**修正内容**: Workers 可以自行搜集数据，统一搜索层是 Orchestrator 补充搜索

---

## 一、正确的数据流

```
Phase 1: DataManager Worker
  └── 采集基础数据（财务、行情、行业）
  └── 写入 blackboard/{session_id}/data/

Phase 2: Orchestrator 统一搜索（补充）
  └── 补充行业趋势、竞品对比、券商预期
  └── 写入 blackboard/{session_id}/data/05_supplement/
  └── ⚠️ 这是"打底"，不是替代 Workers 搜索

Phase 3+: Workers（分析 + 按需搜索）
  ├── 读取 blackboard/data/ 基础数据
  ├── 按需使用搜索工具补充数据
  │   ├── Gemini CLI（首选）
  │   ├── DuckDuckGo（fallback）
  │   ├── Tushare（财务专用）
  │   └── web_fetch（最后手段）
  └── 写入 blackboard/{session_id}/stages/
```

---

## 二、Workers 的任务定义（修正版）

### 2.1 DataManager Worker

```python
"""
你是 DataManager Agent。执行数据采集 bootstrap。

## 职责
1. 采集基础数据（财务、行情、行业）
2. 写入 blackboard/{session_id}/data/

## 执行代码
```python
from data_providers.investment import register_providers
from data_manager import DataEvolutionLoop, ConfigDrivenCollector
# ... bootstrap 代码
```

## 输出
- data/INDEX.json
- data/key_metrics.json
- data/01_financials/
- data/02_market_quote/
- ...
"""
```

### 2.2 Researcher Workers

```python
"""
你是 {angle} 研究员。负责 {angle} 分析。

## 输入
1. **基础数据**（强制读取）
   - data/key_metrics.json
   - data/01_financials/
   - data/02_market_quote/

2. **补充数据**（Orchestrator 已准备）
   - data/05_supplement/行业趋势.json
   - data/05_supplement/竞品对比.json

3. **自行搜索**（按需）
   - 如现有数据不足，使用搜索工具补充
   - 搜索工具优先级：
     1. Gemini CLI: gemini -p "你的搜索问题"
     2. DuckDuckGo: from duckduckgo_search import DDGS
     3. Tushare: ts.pro_api()
     4. web_fetch: 最后手段

## 输出
- stages/researcher_{angle}_output.json
"""
```

---

## 三、统一搜索层（Orchestrator 补充搜索）

### 3.1 为什么需要？

从 bak 文件原文：

> ### STEP 2: 统一搜索（补充基础数据）
> **只有在 STEP 1 和 STEP 2 完成后**，才能开始 spawn Worker Agent。

**目的**：
1. **补充 DataManager 可能缺失的数据**
   - DataManager 主要采集财务/行情数据
   - 行业趋势、竞品对比、券商预期需要搜索补充

2. **提前准备通用信息**
   - 所有 Workers 可能都需要行业背景
   - Orchestrator 提前搜索，避免 Workers 重复搜索

3. **不是替代 Workers 搜索**
   - Workers 仍然可以按需搜索
   - 只是"打底"，减少 Workers 的重复工作

### 3.2 搜索内容

```python
search_tasks = [
    ("行业趋势", f"{industry} 2025 2026 市场规模 增长趋势"),
    ("竞品对比", f"{company_name} 竞争对手 市场份额 对比"),
    ("券商预期", f"{company_name} 券商 一致预期 目标价 2026"),
    ("风险因素", f"{company_name} 风险 挑战 问题"),
]
```

### 3.3 与 Workers 搜索的关系

| 搜索层 | 执行者 | 时机 | 内容 | 目的 |
|:---|:---|:---|:---|:---|
| **统一搜索** | Orchestrator | spawn Workers 前 | 行业趋势、竞品对比 | 补充基础数据 |
| **Worker 搜索** | Workers | 分析过程中 | 按需补充 | 特定分析需要 |

---

## 四、Task 构建器（修正版）

### 4.1 Workers Task 包含搜索指引

```python
def build_researcher_task(angle, session_id, config):
    """
    构建 Researcher Task（含搜索指引）
    """
    task = f"""
# 🎯 任务上下文

## 目标公司
- 股票代码: {config.code}
- 公司名称: {config.name}
- 行业: {config.industry}

## 输入数据（已准备）
- 基础数据: blackboard/{session_id}/data/
- 补充搜索: blackboard/{session_id}/data/05_supplement/

## 自行搜索（按需）
如果现有数据不足，请使用以下工具搜索补充：

1. **Gemini CLI**（首选）
   ```bash
   gemini -p "你的搜索问题"
   ```

2. **DuckDuckGo**（fallback）
   ```python
   from duckduckgo_search import DDGS
   DDGS().text("你的搜索问题", max_results=5)
   ```

3. **Tushare**（财务专用）
   ```python
   import tushare as ts
   pro = ts.pro_api()
   ```

4. **web_fetch**（最后手段）
   直接抓取 URL

## 输出
- blackboard/{session_id}/stages/researcher_{angle}_output.json

---

# 原始提示词
{read_prompt(f"investment_researcher_{angle}.md")}
"""
    return task
```

---

## 五、修正后的架构

```
主Agent(depth-0)
  └── sessions_spawn → Orchestrator Agent(depth-1)
        ├── [本地] 初始化
        ├── sessions_spawn → DataManager Worker
        │     └── 执行 bootstrap（基础数据）
        ├── [本地] 统一搜索（补充数据）
        │     └── 行业趋势、竞品对比、券商预期
        ├── sessions_spawn → Planner Worker
        │     └── 读取 data/ → 制定计划
        ├── sessions_spawn → Researchers ×6（并行）
        │     ├── 读取 data/（基础数据）
        │     ├── 读取 05_supplement/（补充数据）
        │     └── [按需] 自行搜索（Gemini/DDG/Tushare）
        ├── sessions_spawn → Auditors ×3（并行）
        │     ├── 读取 researcher 输出
        │     └── [按需] 自行搜索验证数据
        ├── sessions_spawn → Fixer Worker
        │     └── 读取所有输出 → 修正
        └── sessions_spawn → Summarizer Worker
              └── 生成最终报告
```

---

## 六、关键修正点

| 我的错误理解 | 正确理解 |
|:---|:---|
| Workers **只**分析不采集 | Workers **主要**分析，但可以**按需搜索**补充 |
| 统一搜索层替代 Workers 搜索 | 统一搜索层是 Orchestrator **补充搜索**，Workers 仍可自行搜索 |
| Workers 完全依赖注入的数据 | Workers 读取基础数据 + **按需自行搜索** |

---

## 七、实施调整

基于修正，实施方案调整：

### 保留统一搜索层（Orchestrator 补充搜索）
- 搜索行业趋势、竞品对比等通用信息
- 写入 `data/05_supplement/`
- Workers 可以读取这些补充数据

### Workers Task 增加搜索指引
- 告诉 Workers 可以使用搜索工具
- 提供搜索工具优先级
- Workers 按需搜索，不是强制

### DataManager 不变
- 仍然执行 bootstrap 采集基础数据
- Workers 在基础数据之上分析 + 按需补充

---

**这个理解对吗？**