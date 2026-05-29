# STEP 2: 统一搜索（补充基础数据）

## 任务目标
在数据采集完成后，通过多种搜索工具补充缺失的行业、竞品、券商预期等信息。

---

## 搜索工具优先级（强制按顺序）

详见 `reference/search_priority.md`，核心规则：

| 优先级 | 工具 | 适用场景 |
|--------|------|----------|
| 1 | **Gemini CLI** | 首选，内置 Google Search grounding |
| 2 | **DuckDuckGo** | Fallback，当 Gemini 不可用时 |
| 3 | **Tushare API** | 财务/行情专用数据 |
| 4 | **web_fetch** | 最后手段，遇到验证码/反爬会失败 |

---

## 执行代码

```python
import subprocess
import json
import os

# Gemini CLI 搜索
def gemini_search(query):
    """使用 Gemini CLI 搜索（内置 Google Search grounding）"""
    try:
        result = subprocess.run(
            ["gemini", "-p", query],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout
    except Exception as e:
        print(f"Gemini search failed: {e}")
        return None

# DuckDuckGo 搜索
def duckduckgo_search(query, max_results=5):
    """DuckDuckGo 文本搜索"""
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=max_results)
        return results
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}")
        return None

# Tushare 财务数据
def tushare_financial(ts_code):
    """Tushare 财务数据查询"""
    try:
        import tushare as ts
        pro = ts.pro_api()
        # 财务指标
        indicators = pro.fina_indicator(ts_code=ts_code)
        # 利润表
        income = pro.income(ts_code=ts_code, fields="ts_code,end_date,total_revenue,net_profit")
        return {"indicators": indicators.to_dict(), "income": income.to_dict()}
    except Exception as e:
        print(f"Tushare query failed: {e}")
        return None

# 执行搜索
search_queries = [
    ("财务数据", lambda: tushare_financial("300604.SZ")),
    ("行业趋势", lambda: gemini_search("半导体测试设备行业 2025 2026 市场规模 国产化率")),
    ("竞品对比", lambda: gemini_search("长川科技 华峰测控 对比 市场份额 技术优势")),
    ("券商预期", lambda: gemini_search("长川科技 300604.SZ 券商 一致预期 目标价 2026")),
]

supplement_dir = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/05_supplement"
os.makedirs(supplement_dir, exist_ok=True)

for name, search_fn in search_queries:
    print(f"搜索: {name}")
    result = search_fn()
    if result:
        output_path = os.path.join(supplement_dir, f"{name}.json")
        with open(output_path, "w") as f:
            json.dump({"query": name, "result": str(result)}, f, ensure_ascii=False, indent=2)
        print(f"✅ {name} → {output_path}")
    else:
        print(f"⚠️ {name} 搜索失败")
```

---

## 验证清单

- [ ] `blackboard/{session_id}/data/05_supplement/` 目录存在
- [ ] 至少 3 个搜索结果文件
- [ ] 每个文件包含有效 JSON

---

## ❌ 禁止行为

| 禁止 | 原因 | 正确做法 |
|------|------|----------|
| 跳过搜索直接进入 Worker | 缺少关键行业/竞品数据 | 必须执行搜索补充 |
| 只用 web_fetch | 容易遇到反爬失败 | 优先用 Gemini CLI |
| 不验证搜索结果有效性 | 可能写入空文件 | 检查文件大小和内容 |
