# DeepFlow V4.0 最终方案

> **历史文档**: 本文档为 V4.0 架构设计阶段的历史记录，当前实现见 [ARCHITECTURE.md](ARCHITECTURE.md)
>
> **当前版本**: 0.1.0 (V4.0 内部代号)
## DataManager 统一数据入口 + Orchestrator 纯调度

**版本**: 4.0 Final  
**日期**: 2026-04-22 23:27  
**核心原则**: Orchestrator 只调度，数据由 DataManager 负责

---

## 一、架构职责划分

### 1.1 三层职责清晰分离

```
┌─────────────────────────────────────────────────────────┐
│  Orchestrator Agent (depth-1)                           │
│  ─────────────────────────────                          │
│  职责: 纯调度                                            │
│  - 生成 session_id                                      │
│  - 创建 blackboard 目录                                  │
│  - 按顺序 spawn Workers                                  │
│  - 等待 Workers 完成                                     │
│  - 检查收敛条件                                          │
│  - 汇总结果                                             │
│                                                         │
│  ❌ 不执行数据采集                                       │
│  ❌ 不执行搜索                                          │
│  ❌ 不执行分析                                          │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ DataManager  │  │   Planner    │  │ Researchers  │
│  Worker      │  │   Worker     │  │  ×6 Workers  │
└──────────────┘  └──────────────┘  └──────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ 统一搜索层    │  │  制定计划    │  │  分析研究    │
│ (补充数据)   │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  blackboard/{session_id}/data/                          │
│  ─────────────────────────────                          │
│  - INDEX.json (数据索引)                                 │
│  - key_metrics.json (核心指标)                           │
│  - 01_financials/ (财务数据)                             │
│  - 02_market_quote/ (行情数据)                           │
│  - 03_industry/ (行业数据)                               │
│  - 05_supplement/ (补充搜索数据)                          │
│    - 行业趋势.json                                       │
│    - 竞品对比.json                                       │
│    - 券商预期.json                                       │
│    - 风险因素.json                                       │
└─────────────────────────────────────────────────────────┘
```

### 1.2 职责矩阵

| 组件 | 数据采集 | 搜索 | 分析 | 调度 | 输出 |
|:---|:---:|:---:|:---:|:---:|:---|
| **Orchestrator** | ❌ | ❌ | ❌ | ✅ | 最终报告 |
| **DataManager** | ✅ | ✅ | ❌ | ❌ | data/ |
| **Planner** | ❌ | ❌ | ✅ | ❌ | planner_output.json |
| **Researchers** | ❌ | ✅(按需) | ✅ | ❌ | researcher_*.json |
| **Auditors** | ❌ | ✅(按需) | ✅ | ❌ | auditor_*.json |
| **Fixer** | ❌ | ❌ | ✅ | ❌ | fixer_output.json |
| **Summarizer** | ❌ | ❌ | ✅ | ❌ | final_report.md |

---

## 二、DataManager Worker 设计

### 2.1 核心职责

DataManager 是**唯一的数据入口**，负责：

1. **Bootstrap 采集**（基础数据）
   - 财务数据（tushare/akshare）
   - 行情数据（sina）
   - 行业数据

2. **统一搜索**（补充数据）
   - 行业趋势
   - 竞品对比
   - 券商预期
   - 风险因素

3. **数据整理**
   - 生成 INDEX.json
   - 生成 key_metrics.json
   - 统一数据格式

### 2.2 Task 设计（含完整代码）

```python
"""
你是 DataManager Agent。你是唯一的数据入口，负责所有数据采集和补充搜索。

## 职责
1. 执行 bootstrap 采集基础数据
2. 执行统一搜索补充数据
3. 整理并写入 blackboard/data/

## 执行代码

```python
import sys
import os
import json

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

# ========== STEP 1: Bootstrap 采集 ==========
print("[DataManager] STEP 1: Bootstrap 采集")

from data_providers.investment import register_providers
from data_manager import DataEvolutionLoop, ConfigDrivenCollector
from blackboard_manager import BlackboardManager

# 注册数据源
register_providers()

# 初始化采集器
config_path = "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
collector = ConfigDrivenCollector(config_path)

# 初始化 Blackboard
blackboard = BlackboardManager("{session_id}")
data_loop = DataEvolutionLoop(collector, blackboard)

# 执行 bootstrap
context = {"code": "{company_code}", "name": "{company_name}"}
data_loop.bootstrap_phase(context)

print("[DataManager] Bootstrap 完成")

# ========== STEP 2: 统一搜索（补充数据） ==========
print("[DataManager] STEP 2: 统一搜索补充数据")

import subprocess

def gemini_search(query):
    try:
        result = subprocess.run(
            ["gemini", "-p", query],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout if result.returncode == 0 else None
    except:
        return None

def duckduckgo_search(query):
    try:
        from duckduckgo_search import DDGS
        return DDGS().text(query, max_results=5)
    except:
        return None

# 补充搜索任务
search_tasks = [
    ("行业趋势", "{industry} 行业 2025 2026 市场规模 增长趋势"),
    ("竞品对比", "{company_name} 竞争对手 市场份额 对比"),
    ("券商预期", "{company_name} {company_code} 券商 一致预期 目标价 2026"),
    ("风险因素", "{company_name} 风险 挑战 问题"),
]

supplement_dir = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/05_supplement"
os.makedirs(supplement_dir, exist_ok=True)

for name, query in search_tasks:
    print(f"  搜索: {name}")
    result = gemini_search(query)
    if not result:
        result = duckduckgo_search(query)
    
    if result:
        with open(f"{supplement_dir}/{name}.json", "w") as f:
            json.dump({"query": query, "result": str(result)}, f, ensure_ascii=False)
        print(f"  ✅ {name}")
    else:
        print(f"  ⚠️ {name} 失败")

# ========== STEP 3: 验证数据 ==========
print("[DataManager] STEP 3: 验证数据")

index_path = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/INDEX.json"
key_metrics_path = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/key_metrics.json"

if os.path.exists(index_path):
    with open(index_path) as f:
        index = json.load(f)
    print(f"✅ 已采集 {len(index)} 个数据集")
elif os.path.exists(key_metrics_path):
    print("✅ 关键指标数据已就绪")
else:
    print("⚠️ 数据采集可能不完整")

print("[DataManager] 任务完成！")
```

## 输出要求
- 所有数据写入 blackboard/{session_id}/data/
- 必须生成 INDEX.json 或 key_metrics.json
- 补充搜索写入 data/05_supplement/
- 返回执行结果摘要
"""
```

---

## 三、Orchestrator 设计（纯调度）

### 3.1 核心原则

Orchestrator **只负责调度**，不做任何数据相关操作：

```python
"""
DeepFlow V4.0 Orchestrator Agent
=================================

## 身份
你是 Orchestrator Agent。你的职责是**纯调度**。

## 你能做的
✅ 生成 session_id
✅ 创建 blackboard 目录
✅ spawn Workers（使用 sessions_spawn 工具）
✅ 等待 Workers（使用 sessions_yield 工具）
✅ 检查 Workers 输出是否存在
✅ 按顺序执行管线

## 你不能做的
❌ 执行数据采集
❌ 执行搜索
❌ 执行分析
❌ 修改 Worker 的输出

## 执行流程
```

### 3.2 简化后的执行流程

```python
def run_pipeline(session_id, company_code, company_name):
    """
    Orchestrator 纯调度流程
    """
    # Phase 0: 初始化（本地执行）
    init_blackboard(session_id)
    
    # Phase 1: DataManager Worker（数据采集 + 搜索）
    dm_task = build_data_manager_task(session_id, company_code, company_name)
    spawn_worker("data_manager", dm_task)
    wait_for_completion("data_manager")
    
    # 检查数据是否就绪
    if not check_data_ready(session_id):
        return error("DataManager 失败")
    
    # Phase 2: Planner Worker
    planner_task = build_planner_task(session_id, company_code, company_name)
    spawn_worker("planner", planner_task)
    wait_for_completion("planner")
    
    # Phase 3: Researchers ×6（并行）
    for researcher in RESEARCHERS:
        task = build_researcher_task(researcher, session_id)
        spawn_worker(researcher, task)
    wait_for_all_completion(RESEARCHERS)
    
    # Phase 4: Auditors ×3（并行）
    for auditor in AUDITORS:
        task = build_auditor_task(auditor, session_id)
        spawn_worker(auditor, task)
    wait_for_all_completion(AUDITORS)
    
    # Phase 5: Fixer Worker
    fixer_task = build_fixer_task(session_id)
    spawn_worker("fixer", fixer_task)
    wait_for_completion("fixer")
    
    # Phase 6: Summarizer Worker
    summarizer_task = build_summarizer_task(session_id)
    spawn_worker("summarizer", summarizer_task)
    wait_for_completion("summarizer")
    
    return success(session_id)
```

---

## 四、Workers Task 设计

### 4.1 通用结构

所有 Workers（除 DataManager）的 Task 结构：

```
# 🎯 任务上下文（Orchestrator 注入）

## 目标公司
- 股票代码: {code}
- 公司名称: {name}
- 行业: {industry}

## 输入数据（DataManager 已准备）
- 基础数据: blackboard/{session_id}/data/
- 补充搜索: blackboard/{session_id}/data/05_supplement/

## 自行搜索（按需）
如现有数据不足，请使用：
1. Gemini CLI: gemini -p "查询"
2. DuckDuckGo: DDGS().text("查询")
3. Tushare: ts.pro_api()

## 输出
- blackboard/{session_id}/stages/{worker}_output.json

---

# 原始提示词
{read_prompt_file()}
```

### 4.2 各 Worker 特点

| Worker | 输入 | 搜索 | 输出 |
|:---|:---|:---|:---|
| **Planner** | data/key_metrics.json | ❌ | planner_output.json |
| **Researchers** | data/ + planner_output | ✅(按需) | researcher_*.json |
| **Auditors** | researcher_*.json | ✅(按需验证) | auditor_*.json |
| **Fixer** | researcher_*.json + auditor_*.json | ❌ | fixer_output.json |
| **Summarizer** | fixer_output.json + key_metrics.json | ❌ | final_report.md |

---

## 五、数据流设计

### 5.1 单一流向

```
DataManager Worker
  ├── [采集] 财务/行情/行业数据
  ├── [搜索] 行业趋势/竞品/券商预期/风险
  └── 写入 → blackboard/{session_id}/data/
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  Planner Worker    Researchers ×6    Auditors ×3
        │                 │                 │
        ▼                 ▼                 ▼
  planner_output    researcher_*      auditor_*
        │            (按需搜索)       (按需搜索)
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                   Fixer Worker
                          │
                          ▼
                   Summarizer Worker
                          │
                          ▼
                   final_report.md
```

### 5.2 数据所有权

| 目录 | 所有者 | 说明 |
|:---|:---|:---|
| `blackboard/{session_id}/data/` | DataManager | 唯一写入者 |
| `blackboard/{session_id}/stages/` | 各 Workers | 各自写入自己的输出 |
| `blackboard/{session_id}/final_report.md` | Summarizer | 最终输出 |

---

## 六、实施计划（简化版）

### Step 1: 重写 DataManager Worker（2小时）
- 包含 bootstrap 代码
- 包含统一搜索代码
- 包含数据验证逻辑

### Step 2: 重写 Orchestrator（1.5小时）
- 删除所有数据相关代码
- 纯调度逻辑
- 检查点机制

### Step 3: 更新其他 Workers Task（1小时）
- 添加上下文注入
- 添加搜索指引
- 统一输出格式

### Step 4: 验证测试（1.5小时）
- DataManager 完整测试
- Orchestrator 调度测试
- 端到端流程测试

**总计：6小时**

---

## 七、关键改进

| 改进项 | V3.0 | V4.0 |
|:---|:---|:---|
| **Orchestrator 职责** | 混乱（调度+搜索+上下文构建） | 纯调度 |
| **DataManager 职责** | 简单文本提示 | 数据采集 + 统一搜索 |
| **Workers 搜索** | 无指引 | 按需搜索，有工具优先级 |
| **数据入口** | 多个 | **单一入口（DataManager）** |
| **架构清晰度** | 低 | **高（三层分离）** |

---

## 八、确认清单

- [x] Orchestrator 只做调度，不采集数据
- [x] DataManager 是数据唯一入口（采集 + 搜索）
- [x] Workers 可以按需自行搜索
- [x] 三层职责清晰分离

**确认后开始实施？**