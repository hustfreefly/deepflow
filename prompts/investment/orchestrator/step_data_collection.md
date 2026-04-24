# STEP 1: DataManager 数据采集

## 任务目标
在 spawn Worker Agent 前，DataManager 负责采集所有基础数据，写入 `Blackboard/data/v0/`。

**此步骤必须在任何 Worker Agent spawn 之前完成。**

---

## 执行代码

```python
from data_manager import DataEvolutionLoop, ConfigDrivenCollector
from data_providers.investment import register_providers

# 注册数据源
register_providers()

# 初始化采集器
config_path = "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
collector = ConfigDrivenCollector(config_path)
data_loop = DataEvolutionLoop(collector, blackboard_manager)

# 设置上下文
context = {"code": "300604.SZ", "name": "长川科技"}

# 执行 bootstrap 采集
data_loop.bootstrap_phase(context)

# 验证数据已就绪
import json
index_path = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/INDEX.json"
if os.path.exists(index_path):
    with open(index_path) as f:
        index = json.load(f)
    print(f"✅ 已采集 {len(index)} 个数据集")
else:
    print("⚠️ 数据采集可能失败，请检查日志")
```

---

## 验证清单（执行后必须确认）

- [ ] `blackboard/{session_id}/data/INDEX.json` 存在
- [ ] `blackboard/{session_id}/data/01_financials/key_metrics.json` 存在
- [ ] `blackboard/{session_id}/data/02_market_quote/key_metrics.json` 存在

---

## 数据目录结构

所有采集的数据位于 `Blackboard/data/v{N}/`：

| 目录 | 内容 |
|------|------|
| INDEX.json | 数据索引（机器可读） |
| 01_financials/ | 财务数据（raw.json + key_metrics.json） |
| 02_market_quote/ | 实时行情 |
| 03_industry/ | 行业数据 |
| 04_news/ | 新闻舆情 |
| 05_research_reports/ | 券商研报 |

---

## 迭代间数据更新

每轮迭代结束后调用：

```python
agent_outputs = [...]  # 本轮所有 Agent 的输出
requests = data_loop.collect_requests(agent_outputs)
new_data = data_loop.fulfill_requests(requests, context)
findings = data_loop.ingest_findings(agent_outputs)
data_loop.update_blackboard({**new_data, **findings})
```
