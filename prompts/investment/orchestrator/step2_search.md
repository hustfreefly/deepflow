## STEP 2: 统一搜索

**目标**：补充搜索数据

**搜索工具优先级**：
1. Gemini CLI: `gemini -p "{query}"`
2. DuckDuckGo: `DDGS().text(query, max_results=5)`
3. Tushare API: `ts.pro_api()`

**执行搜索**：
- "{name} {code} 2025 2026 业绩预期"
- "{name} SoC测试机 进展"
- "半导体设备行业 国产化率 2025"

**完成后输出**：
```
[PHASE_COMPLETE: search]
```
