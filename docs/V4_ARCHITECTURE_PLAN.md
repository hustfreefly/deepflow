# DeepFlow V4.0 架构重构方案

> **历史文档**: 本文档为 V4.0 架构设计阶段的历史记录，当前实现见 [ARCHITECTURE.md](ARCHITECTURE.md)
>
> **当前版本**: 0.1.0 (V4.0 内部代号)
## DataManager Worker 化 + Agent 编程范式回归

**日期**: 2026-04-22  
**版本**: V4.0  
**状态**: 方案制定阶段

---

## 一、核心问题诊断

### 当前 V3.0 的问题
1. **Orchestrator 是指南而不是代码** → LLM 自己决定怎么执行，不可控
2. **Workers 收到的是简单文本** → 缺乏上下文，质量不稳定
3. **DataManager 只是文本提示词** → 无法执行真正的 bootstrap 代码

### bak 文件（V1.0）的先进之处
1. **Orchestrator 执行 Python 代码** → 可预测、可验证
2. **DataManager 本地执行 bootstrap** → 真正采集数据
3. **统一搜索层** → 工具优先级代码化
4. **Workers 只负责分析** → 数据已准备好

### 用户的新需求
> "DataManager 还是 worker 来做，可以让 data manager 执行 bootstrap"

这意味着：
- DataManager 作为 Worker spawn（不是本地执行）
- 但 DataManager Worker **能执行 Python 代码**（真正的 bootstrap）
- 其他 Workers 也回到 Agent 编程范式

---

## 二、V4.0 架构设计

### 架构图

```
主Agent(depth-0)
  └── sessions_spawn → Orchestrator Agent(depth-1)
        ├── 本地执行：生成 session_id、创建目录
        ├── sessions_spawn → DataManager Worker(depth-2)
        │     └── 执行 Python bootstrap 代码
        │     └── 写入 blackboard/{session_id}/data/
        ├── sessions_spawn → Planner Worker(depth-2)
        │     └── 读取 data/ 制定研究计划
        ├── sessions_spawn → Researchers ×6(depth-2) 并行
        │     └── 读取 data/ + planner_output 分析
        ├── sessions_spawn → Auditors ×3(depth-2) 并行
        │     └── 读取 researcher_outputs 审计
        ├── sessions_spawn → Fixer Worker(depth-2)
        │     └── 读取所有输出修正
        └── sessions_spawn → Summarizer Worker(depth-2)
              └── 生成最终报告
```

### 关键变更

| 组件 | V3.0（当前） | V4.0（新方案） |
|:---|:---|:---|
| **Orchestrator** | 文本指南，LLM 自己决策 | **Python 代码执行**，可预测 |
| **DataManager** | 简单文本提示词 | **完整 Python 代码**，执行 bootstrap |
| **Workers** | 简单 task 文本 | **完整上下文 + 能力定义** |
| **搜索工具** | Workers 自己选 | **统一搜索层代码** |

---

## 三、详细设计

### 3.1 Orchestrator Agent（depth-1）

**不再是文本指南，而是可执行的 Python 代码。**

#### 核心能力
1. **本地执行**：生成 session_id、创建目录、读取配置
2. **spawn Workers**：使用 sessions_spawn 工具创建 depth-2 Workers
3. **等待机制**：使用 sessions_yield 等待 Workers 完成
4. **错误处理**：捕获异常，记录日志，继续执行

#### 执行流程（代码化）

```python
# orchestrator_agent.py - V4.0
import sys, os, json, uuid
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

def main():
    # 1. 初始化
    session_id = generate_session_id()
    create_blackboard(session_id)
    
    # 2. 加载配置
    config = load_domain_config("investment")
    
    # 3. 执行 DataManager Worker（spawn，但给它完整代码）
    data_manager_task = build_data_manager_task(session_id, config)
    spawn_worker("data_manager", data_manager_task)
    wait_for_completion("data_manager")
    
    # 4. 执行统一搜索（本地执行，或 spawn 搜索 Worker）
    run_supplement_search(session_id, config)
    
    # 5. 执行 Planner Worker
    planner_task = build_planner_task(session_id, config)
    spawn_worker("planner", planner_task)
    wait_for_completion("planner")
    
    # 6. 执行 Researchers ×6（并行）
    for researcher in config.researchers:
        task = build_researcher_task(session_id, researcher)
        spawn_worker(researcher.role, task)
    wait_for_all_completion(config.researchers)
    
    # 7. 执行 Auditors ×3（并行）
    # ...
    
    # 8. 执行 Fixer
    # ...
    
    # 9. 执行 Summarizer
    # ...
    
    return generate_report(session_id)
```

### 3.2 DataManager Worker（depth-2）

**关键变化：不再只是文本提示词，而是完整的 Python 代码。**

#### 任务描述（完整代码）

```python
"""
你是 DataManager Agent。你的任务是执行数据采集 bootstrap。

## 环境
你已导入以下模块：
- data_manager.DataEvolutionLoop
- data_manager.ConfigDrivenCollector
- data_providers.investment.register_providers

## 执行代码

```python
from data_providers.investment import register_providers
from data_manager import DataEvolutionLoop, ConfigDrivenCollector
from blackboard_manager import BlackboardManager

# 1. 注册数据源
register_providers()  # 注册 tushare/akshare/sina/web_fetch

# 2. 初始化采集器
config_path = "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
collector = ConfigDrivenCollector(config_path)

# 3. 初始化 Blackboard
blackboard = BlackboardManager("{session_id}")
data_loop = DataEvolutionLoop(collector, blackboard)

# 4. 设置上下文
context = {"code": "{company_code}", "name": "{company_name}"}

# 5. 执行 bootstrap 采集
print("开始执行 bootstrap 采集...")
data_loop.bootstrap_phase(context)
print("Bootstrap 完成！")

# 6. 验证数据
import os
index_path = "blackboard/{session_id}/data/INDEX.json"
if os.path.exists(index_path):
    with open(index_path) as f:
        index = json.load(f)
    print(f"✅ 已采集 {len(index)} 个数据集")
else:
    print("⚠️ INDEX.json 不存在，检查采集日志")
```

## 输出要求
- 数据写入 blackboard/{session_id}/data/
- 生成 INDEX.json 数据索引
- 返回采集结果摘要
"""
```

#### 为什么这样设计？

1. **Worker 是真正的 Agent**：不只是"读提示词回复文本"，而是"执行代码完成任务"
2. **bootstrap 真正执行**：`data_loop.bootstrap_phase(context)` 会真实调用 API 采集数据
3. **可验证**：执行后检查文件是否存在

### 3.3 统一搜索层

**在 DataManager 或专门的 Search Worker 中执行。**

```python
# 搜索工具优先级（代码化）
SEARCH_TOOLS = [
    ("gemini", lambda q: gemini_search(q)),
    ("duckduckgo", lambda q: duckduckgo_search(q)),
    ("tushare", lambda q: tushare_financial(q)),
]

def unified_search(query: str, search_type: str = "auto") -> dict:
    """
    统一搜索接口
    
    优先级：
    1. Gemini CLI（内置 Google Search）
    2. DuckDuckGo（fallback）
    3. Tushare（财务专用）
    """
    for tool_name, tool_fn in SEARCH_TOOLS:
        if search_type == "auto" or search_type == tool_name:
            result = tool_fn(query)
            if result:
                return {"source": tool_name, "data": result}
    
    return {"source": "failed", "data": None}
```

### 3.4 其他 Workers

**所有 Workers 都采用"上下文注入 + 原始提示词"模式。**

#### 通用 Task 构建模板

```python
def build_worker_task(agent_role, session_id, config, extra_context=None):
    """
    构建 Worker Task（V4.0 标准格式）
    """
    # 1. 读取原始提示词
    prompt_file = config.get_prompt_file(agent_role)
    with open(prompt_file) as f:
        original_prompt = f.read()
    
    # 2. 读取数据摘要
    data_summary = extract_data_summary(session_id)
    
    # 3. 读取研究计划（Planner 输出）
    planner_output = read_planner_output(session_id)
    
    # 4. 构建完整 Task
    task = f"""
# 🎯 任务上下文（Orchestrator 注入）

## 目标公司信息
- 股票代码：{config.company_code}
- 公司名称：{config.company_name}
- 所属行业：{data_summary.get('industry', '未知')}
- 最新股价：{data_summary.get('latest_price', '未知')}
- 市值：{data_summary.get('market_cap', '未知')}
- 市盈率(PE)：{data_summary.get('pe_ratio', '未知')}

## 研究重点（来自 Planner）
{planner_output.get('objectives', '综合分析')}

## 输入数据路径
- 数据目录：blackboard/{session_id}/data/
- 研究计划：blackboard/{session_id}/stages/planner_output.json
{extra_input_paths}

## 输出要求
- 输出文件：blackboard/{session_id}/stages/{agent_role}_output.json
- 格式：JSON
- 要求：必须包含具体数字和数据来源

---

# 原始提示词（{agent_role}）
{original_prompt}
"""
    
    return task
```

### 3.5 关键改进点

| 改进项 | 之前（V3.0） | 现在（V4.0） |
|:---|:---|:---|
| **DataManager** | 文本提示词 | **完整 Python 代码执行 bootstrap** |
| **搜索工具** | Workers 自己选 | **统一搜索层，代码控制优先级** |
| **上下文注入** | 部分 Worker 有 | **所有 Worker 强制注入** |
| **数据验证** | 无 | **执行后检查文件存在性** |
| **错误处理** | 无 | **try/except + 降级方案** |

---

## 四、执行流程（详细）

### Phase 1: Orchestrator 初始化（本地执行）

```python
# 1. 生成 session_id
session_id = f"{company_name}_{code_clean}_{uuid.uuid4().hex[:8]}"

# 2. 创建目录
os.makedirs(f"blackboard/{session_id}/data", exist_ok=True)
os.makedirs(f"blackboard/{session_id}/stages", exist_ok=True)

# 3. 加载配置
config = ConfigLoader().load_domain("investment")
```

### Phase 2: DataManager Worker（spawn + 代码执行）

```python
# 构建 DataManager Task（包含完整代码）
data_manager_code = """
from data_providers.investment import register_providers
from data_manager import DataEvolutionLoop, ConfigDrivenCollector
# ... bootstrap 代码
"""

# spawn DataManager Worker
task = f"""
你是 DataManager Agent。执行以下 Python 代码完成数据采集：

```python
{data_manager_code}
```

执行完成后，验证 blackboard/{session_id}/data/INDEX.json 是否存在。
"""

sessions_spawn(
    runtime="subagent",
    mode="run",
    label="data_manager",
    task=task,
    timeout_seconds=300
)

# 等待完成
sessions_yield()
```

### Phase 3: 统一搜索（本地或 spawn）

```python
# 方案 A：本地执行（Orchestrator 自己执行）
for query in search_queries:
    result = unified_search(query)
    save_to_blackboard(result)

# 方案 B：spawn Search Worker（如果搜索复杂）
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="search_coordinator",
    task="执行统一搜索...",
    timeout_seconds=120
)
```

### Phase 4: Planner Worker（spawn + 上下文注入）

```python
planner_task = build_worker_task("planner", session_id, config)

sessions_spawn(
    runtime="subagent",
    mode="run",
    label="planner",
    task=planner_task,
    timeout_seconds=180
)

sessions_yield()
```

### Phase 5-9: Researchers → Auditors → Fixer → Summarizer

同 Phase 4，每个 Worker 都使用 `build_worker_task` 构建完整 Task。

---

## 五、契约笼子

### 5.1 契约文件

```yaml
# cage/v4_architecture_contract.yaml
module: "deepflow_v4"
version: "4.0"

architecture:
  orchestrator:
    type: "agent_with_code_execution"
    capabilities:
      - "本地执行 Python 代码"
      - "spawn Workers（sessions_spawn）"
      - "等待 Workers（sessions_yield）"
    
  data_manager:
    type: "worker_with_bootstrap"
    capabilities:
      - "执行 DataManager.bootstrap_phase()"
      - "注册数据源（tushare/akshare/sina）"
      - "写入 blackboard/data/"
    
  workers:
    type: "context_enhanced"
    requirements:
      - "必须包含公司信息注入"
      - "必须包含研究重点注入"
      - "必须包含数据路径"
      - "必须读取 blackboard 数据"
```

### 5.2 验证清单

```python
def verify_v4_execution(session_id: str) -> dict:
    """
    V4.0 执行验证
    """
    checks = {
        "data_manager_executed": os.path.exists(f"blackboard/{session_id}/data/INDEX.json"),
        "planner_output_exists": os.path.exists(f"blackboard/{session_id}/stages/planner_output.json"),
        "researchers_all_completed": count_researcher_outputs(session_id) == 6,
        "auditors_all_completed": count_auditor_outputs(session_id) == 3,
        "fixer_output_exists": os.path.exists(f"blackboard/{session_id}/stages/fixer_output.json"),
        "final_report_exists": os.path.exists(f"blackboard/{session_id}/final_report.md"),
    }
    
    return {
        "all_passed": all(checks.values()),
        "checks": checks,
        "score": sum(checks.values()) / len(checks)
    }
```

---

## 六、实施计划

### Step 1: 重写 orchestrator_agent.py（1-2小时）
- 删除文本指南
- 改为可执行 Python 代码
- 包含 `build_worker_task` 函数
- 包含统一搜索层

### Step 2: 重写 DataManager Worker 提示词（1小时）
- 包含完整 bootstrap 代码
- 包含数据验证逻辑
- 包含错误处理

### Step 3: 更新其他 Worker 提示词（2小时）
- 确保所有提示词支持上下文注入
- 删除过时指令
- 统一输出格式

### Step 4: 验证测试（2-3小时）
- 测试 DataManager bootstrap 执行
- 测试所有 Workers 上下文注入
- 测试完整流程

**总预计时间：6-8小时**

---

## 七、风险与对策

| 风险 | 对策 |
|:---|:---|
| DataManager Worker 无法 import 模块 | 提供降级方案（直接搜索） |
| Workers 在隔离环境无法写入文件 | 使用 blackboard 标准路径 |
| 搜索工具不可用 | 统一搜索层自动 fallback |
| 执行时间过长 | 设置合理 timeout，允许部分失败 |

---

## 八、决策点

**请确认以下事项**：

1. **DataManager 作为 Worker spawn**（不是本地执行）？
   - ✅ 是（用户已确认）

2. **DataManager Worker 执行 Python 代码**（真正的 bootstrap）？
   - 需要确认：是否给 Worker 完整的 Python 代码执行？

3. **统一搜索层放在哪里**？
   - 选项 A：Orchestrator 本地执行（推荐）
   - 选项 B：spawn 专门的 Search Worker

4. **其他 Workers 是否也需要代码执行能力**？
   - 选项 A：只需要上下文注入（推荐）
   - 选项 B：所有 Workers 都执行代码

**请回复确认，我开始实施。**