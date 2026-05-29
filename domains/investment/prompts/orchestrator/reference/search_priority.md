# 搜索工具优先级

## 强制规则

所有需要 web 搜索的 Worker Agent 必须按以下优先级使用工具：

---

## 优先级列表

### 1. Gemini CLI（首选）

```bash
gemini -p "你的搜索问题"
```

**优点**：
- ✅ 内置 Google Search grounding
- ✅ 直接返回 Google 搜索结果摘要
- ✅ 无需额外认证

**示例**：
```python
import subprocess
result = subprocess.run(
    ["gemini", "-p", "半导体测试设备行业 2025 2026 市场规模"],
    capture_output=True, text=True, timeout=30
)
print(result.stdout)
```

---

### 2. DuckDuckGo（Fallback）

```python
from duckduckgo_search import DDGS
results = DDGS().text("你的搜索问题", max_results=5)
```

**适用场景**：
- ✅ 当 Gemini 不可用时使用
- ✅ 文本搜索需求

**示例**：
```python
from duckduckgo_search import DDGS
try:
    results = DDGS().text("长川科技 竞争对手", max_results=5)
    for r in results:
        print(r['title'], r['href'])
except Exception as e:
    print(f"DuckDuckGo failed: {e}")
```

---

### 3. Tushare API（财务/行情专用）

```python
import tushare as ts
pro = ts.pro_api()
pro.daily(ts_code='300604.SZ', start_date='20250101')
```

**适用场景**：
- ✅ 财务数据查询
- ✅ 行情数据查询
- ✅ 财务指标查询

**示例**：
```python
import tushare as ts
pro = ts.pro_api()

# 财务指标
indicators = pro.fina_indicator(ts_code="300604.SZ")

# 利润表
income = pro.income(
    ts_code="300604.SZ",
    fields="ts_code,end_date,total_revenue,net_profit"
)

# 日线行情
daily = pro.daily(ts_code="300604.SZ", start_date="20250101")
```

---

### 4. web_fetch（最后手段）

```python
from openclaw import web_fetch
content = web_fetch(url="https://example.com/article")
```

**警告**：
- ⚠️ 遇到验证码/反爬会失败
- ⚠️ 仅作为最后手段使用

**示例**：
```python
from openclaw import web_fetch
try:
    content = web_fetch(url="https://finance.sina.com.cn/stock/...")
    print(content[:500])  # 前 500 字符
except Exception as e:
    print(f"web_fetch failed: {e}")
```

---

## ❌ 禁止行为

| 禁止 | 原因 | 正确做法 |
|------|------|----------|
| 直接用 web_fetch 作为首选 | 容易遇到反爬失败 | 优先用 Gemini CLI |
| 跳过搜索直接进入分析 | 缺少关键数据 | 按优先级执行搜索 |
| 不使用 Tushare 查财务数据 | 不准确 | 财务数据必须用 Tushare |
| 硬编码搜索结果 | 数据过时 | 实时搜索获取最新信息 |

---

## 决策流程图

```
需要搜索？
  ↓
是财务/行情数据？ → 是 → 用 Tushare API
  ↓ 否
Gemini CLI 可用？ → 是 → 用 Gemini CLI
  ↓ 否
DuckDuckGo 可用？ → 是 → 用 DuckDuckGo
  ↓ 否
有具体 URL？ → 是 → 用 web_fetch
  ↓ 否
⚠️ 无法获取数据，记录日志并继续
```
