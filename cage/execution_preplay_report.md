# DeepFlow V4 逐行预演分析报告
## 分析日期: 2026-04-23

---

## 一、代码结构概览

```
master_agent.py (depth-0)
  ├── init_session()           # 生成session_id，创建目录
  ├── generate_tasks()         # 调用task_builder生成所有Worker Tasks
  ├── save_tasks()             # 保存tasks.json
  ├── save_execution_plan()    # 保存execution_plan.json
  └── generate_orchestrator_task()  # 读取orchestrator指南

task_builder.py
  ├── read_original_prompt()   # 读取prompt文件
  ├── extract_data_summary()   # 从blackboard提取数据
  ├── extract_planner_focus()  # 从planner输出提取重点
  ├── build_data_manager_task()    # 构建DataManager Task（含Python代码）
  ├── build_planner_task()         # 构建Planner Task
  ├── build_researcher_task()      # 构建Researcher Task
  ├── build_auditor_task()         # 构建Auditor Task
  ├── build_fixer_task()           # 构建Fixer Task
  └── build_summarizer_task()      # 构建Summarizer Task

data_manager_worker.py (depth-2 Worker)
  ├── run_bootstrap()          # 执行bootstrap采集
  ├── gemini_search()          # Gemini CLI搜索
  ├── duckduckgo_search()      # DuckDuckGo搜索
  ├── unified_search()         # 统一搜索接口
  ├── run_supplement_search()  # 补充搜索
  ├── ensure_key_metrics()     # 确保key_metrics.json存在
  └── run()                    # 主流程
```

---

## 二、逐行执行预演（以 688981.SH 中芯国际为例）

### Phase 1: Master Agent (depth-0)

```python
# 执行: python3 master_agent.py --code 688981.SH --name 中芯国际 --industry 半导体制造

# Step 1: init_session()
# 输入: company_code="688981.SH", company_name="中芯国际", industry="半导体制造"
# 处理: code_clean="688981", uuid生成8位hex
# 输出: session_id="中芯国际_688981_a1b2c3d4"
# 副作用: 创建 blackboard/中芯国际_688981_a1b2c3d4/{data,stages}/
```

**质量评估**: ✅ 清晰，无副作用风险

---

```python
# Step 2: generate_tasks()
# 调用 task_builder 的各函数

tasks = {
    "data_manager": build_data_manager_task(session_id, "688981.SH", "中芯国际", "半导体制造"),
    # 返回: 字符串，包含完整的Python代码（bootstrap + 搜索 + key_metrics生成）
    # 长度: ~3000字符
    
    "planner": build_planner_task(session_id, "688981.SH", "中芯国际"),
    # 返回: 字符串，包含上下文 + investment/planner.md 内容
    # 注意: extract_data_summary() 此时 blackboard/data/key_metrics.json 还不存在！
    # 结果: 返回默认值 {"company_code": "未知", ...}
    
    "researchers": {
        "finance": build_researcher_task("finance", ...),
        "tech": build_researcher_task("tech", ...),
        # ... 共6个
    },
    # 注意: extract_planner_focus() 此时 planner_output.json 还不存在！
    # 结果: 返回 "综合分析"
    
    "auditors": {...},  # 3个
    "fixer": build_fixer_task(...),
    "summarizer": build_summarizer_task(...),
}
```

**⚠️ 发现问题1**: 执行顺序问题
- Planner Task 生成时，`key_metrics.json` 还不存在 → 返回默认值
- Researcher Tasks 生成时，`planner_output.json` 还不存在 → 返回 "综合分析"
- 这会导致初始 Task 中的上下文数据是占位符

**影响**: 中等。Worker 执行时会重新读取，但初始 prompt 中的 "未知" 可能影响 Worker 的首次判断。

---

```python
# Step 3: save_tasks()
# 保存 tasks.json 到 blackboard/{session_id}/
# 格式: JSON，包含所有 Worker 的 Task 字符串
```

**质量评估**: ✅ 标准操作

---

```python
# Step 4: save_execution_plan()
# 保存 execution_plan.json
# 定义6个phase的执行顺序和超时时间
```

**质量评估**: ✅ 清晰。但注意 phase 定义和实际执行可能有差异（Orchestrator 可能不按此顺序）。

---

```python
# Step 5: generate_orchestrator_task()
# 读取 orchestrator_agent.py（7KB的指南文件）
# 替换 {session_id} 占位符
# 保存到 orchestrator_task.txt
```

**质量评估**: ✅ 但 orchestrator_agent.py 文件本身需要检查

---

### Phase 2: Orchestrator Agent (depth-1)

**触发方式**: 主Agent通过 sessions_spawn 创建 Orchestrator Agent

**Orchestrator 执行流程**:
```
读取 orchestrator_task.txt
  ├── 理解指南（5条强制契约）
  ├── 读取 tasks.json
  ├── 读取 execution_plan.json
  └── 按 phase 执行
       ├── Phase 1: sessions_spawn DataManager Worker
       │    └── 等待完成（Blackboard轮询或yield）
       ├── Phase 2: sessions_spawn Planner Worker
       ├── Phase 3: sessions_spawn 6 Researchers（并行）
       ├── Phase 4: sessions_spawn 3 Auditors（并行）
       ├── Phase 5: sessions_spawn Fixer Worker（可选）
       └── Phase 6: sessions_spawn Summarizer Worker
```

**⚠️ 关键风险点**:

1. **Orchestrator 能否正确执行 sessions_spawn?**
   - 文件是 "指南" 而非可执行代码
   - Orchestrator 是 LLM，需要理解指南并正确调用工具
   - 历史问题: Orchestrator 曾经 spawn 失败

2. **Blackboard 轮询机制**
   - 代码中没有显示具体的轮询实现
   - 依赖 Orchestrator 自行检测 Worker 完成
   - 风险: Orchestrator 可能误判完成状态

---

### Phase 3: DataManager Worker (depth-2)

**Task 内容**: 包含完整的 Python 代码字符串

**执行路径**:
```python
# Worker Agent 收到 Task（字符串）
# 需要识别并执行其中的 Python 代码

# Step 1: Bootstrap
from data_providers.investment import register_providers
from core.data_manager import DataEvolutionLoop, ConfigDrivenCollector
from core.blackboard_manager import BlackboardManager

register_providers()
collector = ConfigDrivenCollector(config_path)
blackboard = BlackboardManager(session_id)
data_loop = DataEvolutionLoop(collector, blackboard)
data_loop.bootstrap_phase(context)
```

**⚠️ 发现问题2**: import 路径问题
- `core.data_manager` 中的类在运行时可能无法正确导入
- 因为 Worker 是在独立环境中执行，PYTHONPATH 可能不包含 `.deepflow/`

**影响**: 高。可能导致 bootstrap 完全失败。

---

```python
# Step 2: 统一搜索
# Gemini CLI 搜索
subprocess.run(["gemini", "-p", query], ...)

# 风险: gemini 命令可能不存在
# Fallback: DuckDuckGo
from duckduckgo_search import DDGS
results = DDGS().text(query, max_results=5)

# 风险: duckduckgo_search 可能未安装
```

**⚠️ 发现问题3**: 外部依赖
- `gemini` CLI 工具是否安装？
- `duckduckgo_search` Python 包是否安装？
- 如果都失败，补充搜索将完全不可用

**影响**: 高。但这是已知设计（fallback机制）。

---

```python
# Step 3: 确保 key_metrics.json
# 尝试从 realtime_quote.json 读取
# 如果失败，生成最小化版本（全为 None）
```

**质量评估**: ✅ 有降级策略

---

### Phase 4-9: 其他 Workers

**Planner Worker**:
- 读取 key_metrics.json（此时应已存在）
- 读取 investment/planner.md
- 生成 planner_output.json

**⚠️ 发现问题4**: Prompt 模板变量
- planner.md 包含 `{{code}}`, `{{name}}`, `{{session_id}}` 等占位符
- 但 task_builder.py 中使用的是 f-string，不是模板替换
- 结果: planner.md 中的 `{{code}}` 不会被替换，会原样保留

**影响**: 高。Worker 看到的 prompt 包含未替换的模板变量。

---

**Researcher Workers**:
- 6个并行执行
- 每个读取对应的 researcher_{angle}.md
- 生成 researcher_{angle}_output.json

**质量评估**: ✅ 设计合理

---

**Auditor Workers**:
- 3个并行执行
- 读取所有 researcher_*_output.json
- 生成 auditor_{type}_output.json

**⚠️ 发现问题5**: 输入依赖
- Auditor 依赖 Researcher 的输出
- 如果某个 Researcher 失败或超时，Auditor 可能缺少输入
- 代码中没有显示错误处理

---

**Summarizer Worker**:
- 读取所有 Worker 输出
- 生成最终报告

**质量评估**: ✅ 设计合理，但依赖前面所有 Worker 成功

---

## 三、代码质量评估

### 优点 ✅

| 方面 | 评估 |
|:---|:---|
| **架构清晰** | depth-0/1/2 分层明确 |
| **职责分离** | Master/Builder/Orchestrator/Worker 各司其职 |
| **数据流** | Blackboard 作为唯一数据通道 |
| **降级策略** | DataManager 有 fallback（最小化 key_metrics）|
| **并发设计** | Researchers 和 Auditors 可以并行 |
| **Prompt 质量** | 详细、结构化、有强制检查清单 |

### 问题 ⚠️

| # | 问题 | 严重程度 | 影响 |
|:---|:---|:---:|:---|
| 1 | **执行顺序**: Planner/Researcher Task 生成时数据尚未就绪 | 中 | 初始 prompt 含占位符 |
| 2 | **import 路径**: Worker 环境中的 PYTHONPATH | 高 | Bootstrap 可能失败 |
| 3 | **外部依赖**: gemini CLI / duckduckgo_search | 高 | 补充搜索不可用 |
| 4 | **模板变量**: planner.md 中的 `{{}}` 未被替换 | 高 | Prompt 含未替换变量 |
| 5 | **错误处理**: 缺少 Worker 失败的处理逻辑 | 中 | 单点故障可能影响整体 |
| 6 | **Orchestrator 可靠性**: 指南 vs 可执行代码 | 高 | 历史曾出现 spawn 失败 |
| 7 | **收敛检测**: 代码中有定义但 Orchestrator 是否执行？| 中 | 可能跳过收敛 |

### 建议修复

1. **延迟 Task 生成**: DataManager 完成后再生成 Planner/Researcher Tasks
2. **环境注入**: 在 Worker Task 中明确设置 PYTHONPATH
3. **依赖检查**: 启动前检查 gemini / duckduckgo_search 可用性
4. **模板替换**: 统一使用 f-string 或 jinja2 模板
5. **错误处理**: 为每个 Worker 添加 try/except 和降级策略

---

## 四、可预期执行效果

### 最佳场景（所有条件满足）

```
✅ DataManager: Bootstrap 成功，采集5+数据集
✅ 补充搜索: Gemini/DuckDuckGo 至少2/4成功
✅ Planner: 生成完整研究计划（含objectives/stages）
✅ 6 Researchers: 全部完成，各生成findings
✅ 3 Auditors: 验证通过，发现少量矛盾
✅ Fixer: 整合矛盾，输出统一视图
✅ Summarizer: 生成论点驱动报告，含三情景目标价

耗时: 15-25分钟
质量: 高（有数据支撑，结构完整）
```

### 典型场景（部分条件不满足）

```
⚠️ DataManager: Bootstrap 失败，生成最小化 key_metrics
⚠️ 补充搜索: 全部失败（gemini/duckduckgo 不可用）
✅ Planner: 仍能生成计划（使用默认值）
✅ Researchers: 依赖自行搜索，质量不确定
⚠️ Auditors: 可能缺少数据支撑
✅ Summarizer: 生成报告，但数据质量标注为"低"

耗时: 10-15分钟
质量: 中（缺少基础数据，依赖Worker自行搜索）
```

### 最坏场景（关键失败）

```
❌ DataManager: Bootstrap 失败，且无法生成 key_metrics
❌ Orchestrator: spawn Worker 失败（历史问题）
❌  Researchers: 全部超时（360秒可能不够）

耗时: 5分钟（快速失败）
质量: 无输出或部分输出
```

---

## 五、结论

### 当前状态: **可运行，但有风险**

| 维度 | 评分 | 说明 |
|:---|:---:|:---|
| 代码质量 | 7/10 | 结构清晰，但缺少错误处理 |
| Prompt 质量 | 8/10 | 详细、结构化，但模板变量有问题 |
| 执行可靠性 | 5/10 | 依赖外部环境（gemini/duckduckgo）|
| 预期效果 | 6/10 | 典型场景下可用，但质量不稳定 |

### 建议

1. **立即修复**: 模板变量替换（planner.md）
2. **高优先级**: Worker 环境 PYTHONPATH 设置
3. **中优先级**: 添加错误处理和降级策略
4. **长期**: 将 Orchestrator 指南转为可执行代码

### 是否可以运行？

**可以，但预期效果不稳定。**

- 最佳场景: 高质量报告 ✅
- 典型场景: 中等质量报告（缺少基础数据）⚠️
- 最坏场景: 失败或超时 ❌

**建议**: 修复问题1、2、4后再正式运行。
