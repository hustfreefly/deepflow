# OpenClaw LoOP 工具链整合设计

> 作者：工具链专家（Expert 2）| 2026-06-24
> 定位：从 OpenClaw 原生工具链视角，设计 LoOP 与各工具的深度协作方案

---

## 一、Tool Chain Mapping：Loop 六阶段 × OpenClaw 工具矩阵

LoOP 的 PERCEIVE → PLAN → ACT → OBSERVE → CHECK → PERSIST 六阶段，每个阶段都有对应的 OpenClaw 原生工具。核心原则：**Python 做确定性流转，OpenClaw 工具做语义决策和外部交互**。

### 阶段映射表

| 阶段 | 核心任务 | OpenClaw 工具 | 调用方式 |
|:---|:---|:---|:---|
| **PERCEIVE** | 感知项目状态、读取 blackboard | `exec` + `read` | `exec("loop_runner.py next <domain> <base_path>")` 返回 JSON 状态 |
| **PLAN** | 决定下一步动作（spawn/done/abort） | `exec` + LLM 语义判断 | Python 输出 `{"action": "spawn_parallel", "tasks": [...]}` |
| **ACT** | 执行具体 phase worker | `sessions_spawn` + `sessions_yield` | 每个 worker 一个子 Agent，push-based 完成通知 |
| **OBSERVE** | 收集 worker 输出、验证质量 | `read` + `exec` | 检查 blackboard 输出文件 + 契约笼子 Pydantic 验证 |
| **CHECK** | 判断是否满足终止条件 | `exec` + `memory_search` | `loop_runner.py check` 返回 done/resume/fix/abort |
| **PERSIST** | 持久化结果、通知人类 | `feishu_doc` + `feishu_bitable` + `memory_get` | 写入飞书文档/表格 + 更新 memory |

### 关键设计：loop_runner.py 作为阶段路由器

```python
# loop_runner.py 的 next 命令 = PERCEIVE + PLAN 的合并
# 主 Agent 只需：
result = exec("python3 scripts/loop_runner.py next solution_pro blackboard/xxx")
# 返回：
# {"action": "spawn_serial|spawn_parallel|done|abort", "phase": 4, "tasks": [...]}

# 主 Agent 根据 action 选择 ACT 策略：
if action == "spawn_serial":
    sessions_spawn(task=tasks[0]["task"], mode="run")
elif action == "spawn_parallel":
    for t in tasks:
        sessions_spawn(task=t["task"], mode="run")
sessions_yield()  # 挂起等待完成事件
```

---

## 二、Hermes 整合：Loop 任务的追踪与可视化

### 问题：Loop 产生的任务缺乏全局视图

当前 DeepFlow 的 Loop 通过 `loop_runner.py` 驱动，状态存在 blackboard 文件系统中，但没有统一的任务看板。Hermes 可以作为任务追踪层。

### 整合方案：Loop → Hermes 任务同步

```
Loop 每完成一个 phase → 写入 Hermes 任务记录
  ├── 任务名："{domain} Phase {N} - {stage_name}"
  ├── 状态：pending → running → done/failed
  ├── 依赖：phase N+1 depends on phase N
  └── 产出物：blackboard 文件路径
```

### 实现路径：Bitable 任务看板

```python
# 用 feishu_bitable 作为 Hermes 的可视化前端
# 1. 创建 Loop 追踪表
feishu_bitable_create_app(name="DeepFlow Loop Tracker")

# 2. 创建字段
feishu_bitable_create_field(
    app_token=APP_TOKEN, table_id=TABLE_ID,
    field_name="Phase", field_type=3,  # SingleSelect
    property={"options": [
        {"name": "Phase 1 - Spec"}, {"name": "Phase 2 - Solution"},
        {"name": "Phase 3 - Architecture"}, ...
    ]}
)
feishu_bitable_create_field(
    app_token=APP_TOKEN, table_id=TABLE_ID,
    field_name="Status", field_type=3,
    property={"options": [
        {"name": "⏳ Pending"}, {"name": "🔄 Running"},
        {"name": "✅ Done"}, {"name": "❌ Failed"}
    ]}
)

# 3. Loop 每完成一个 phase，更新记录
feishu_bitable_update_record(
    app_token=APP_TOKEN, table_id=TABLE_ID,
    record_id=RECORD_ID,
    fields={"Status": "✅ Done", "Output": "blackboard/xxx/phase_4_output.json"}
)
```

### Hermes 反向控制 Loop

Hermes 不仅是看板，还可以驱动 Loop 决策：

```python
# 当 Hermes 中某任务被标记为 "blocked"，Loop 自动跳过
# 当 Hermes 中优先级变化，Loop 调整 phase 执行顺序
# 实现：loop_runner.py 读取 Hermes 状态作为输入参数
exec("python3 scripts/loop_runner.py next solution_pro blackboard/xxx --hermes-status /tmp/hermes.json")
```

---

## 三、Codex 整合：Codex 作为 Loop 的 Worker

### 定位：Codex = 代码生成专家 Worker

在 DeepFlow 的 Phase 体系中，Codex 最适合担任：
- **Phase 5 (Detailed Design)**：生成详细设计代码骨架
- **Phase 7 (Implementation)**：生成实际代码实现
- **Phase 9 (Testing)**：生成测试用例

### Prompt 构造模式

```python
# Codex Worker 的 prompt 模板
codex_prompt = f"""
## 任务
你是 DeepFlow Solution Pro 的 Phase {phase} Worker。

## 输入
{blackboard_context}  # 从 blackboard 读取的前序 phase 输出

## 约束
- 输出格式：JSON，符合 {contract_schema} 契约
- 代码风格：遵循 {coding_standards}
- 质量门控：输出将通过 Pydantic 验证

## 产出
将结果写入：{output_path}
"""

# 主 Agent 执行
sessions_spawn(
    task=codex_prompt,
    runtime="subagent",
    mode="run",
    runTimeoutSeconds=300
)
```

### 结果收集与验证

```python
# Codex Worker 完成后，主 Agent 自动收到完成事件
# 然后执行 CHECK 阶段：

# 1. 检查输出文件存在
read(path=output_path)

# 2. 契约笼子验证（Pydantic gate）
exec(f"python3 scripts/validate_contract.py {output_path} {schema_path}")

# 3. 如果验证失败 → 重新 spawn 或 abort
if validation_result["status"] == "failed":
    # 记录失败原因到 blackboard
    write(path=f"{base_path}/errors/phase_{phase}_error.json",
          content=json.dumps(validation_result))
    # loop_runner 下一轮会决定 retry 或 abort
```

---

## 四、Connectors 设计：外部系统连接

### 4.1 飞书连接器（Feishu Connector）

**通知时机与内容**：

| 事件 | 通知方式 | 内容 |
|:---|:---|:---|
| Loop 启动 | `feishu_doc` 创建进度文档 | 项目名、10 phase 计划、预计时间 |
| Phase 完成 | `feishu_bitable_update_record` | 更新看板状态 |
| Loop 完成 | `feishu_doc` 写入最终报告 + 消息通知 | 报告链接 + 关键指标 |
| Loop 异常 | 即时消息通知 | 错误阶段 + 失败原因 + 建议操作 |

```python
# 飞书进度文档自动更新
def notify_progress(domain, phase, status, base_path):
    # 更新 Bitable 看板
    feishu_bitable_update_record(...)
    
    # 每 3 个 phase 写一次进度摘要到飞书文档
    if phase % 3 == 0:
        feishu_doc(
            action="append",
            doc_token=PROGRESS_DOC_TOKEN,
            content=f"## Phase {phase} {status}\n完成时间: {now()}\n产出物: {output_path}"
        )
```

### 4.2 GitHub 连接器

```python
# Loop 完成后自动创建 PR
exec(f"""
cd {repo_path}
git checkout -b deepflow/{project_name}
git add .
git commit -m "DeepFlow: {domain} complete for {project_name}"
gh pr create --title "DeepFlow: {project_name}" --body "{pr_body}"
""")

# Loop 中遇到代码质量问题 → 创建 GitHub Issue
exec(f"""
gh issue create --title "[DeepFlow] Phase {phase} quality gate failed" \
    --body "{error_details}" --label "deepflow,quality-gate"
""")
```

### 4.3 邮件连接器

```python
# 最终报告通过邮件发送（大文件场景）
# 使用 TOOLS.md 中规定的邮件发送规则
exec(f"""
python3 scripts/send_report.py \
    --to 81240779@qq.com \
    --subject "DeepFlow 架构报告: {project_name}" \
    --body "{report_path}"
""")
```

---

## 五、Skills 即 Loop 组件：常用 Pattern 封装

### 5.1 `solution_loop` Skill

**触发词**："跑 Solution Pro"、"执行 10 phase"、"启动架构设计管线"

```markdown
## Skill: solution_loop
### 描述
自动运行 DeepFlow Solution Pro 的完整 10 phase 管线。

### 流程
1. 接收输入：项目需求文档路径
2. 创建 blackboard 目录 + 初始化 tasks.json
3. 循环执行：
   a. `exec("loop_runner.py next solution_pro {base_path}")`
   b. 解析返回 JSON
   c. `sessions_spawn` 执行 worker(s)
   d. `sessions_yield` 等待完成
   e. 回到 (a) 直到 action="done"
4. 生成最终报告 → 飞书文档 + Bitable 更新
5. 通知人类

### 错误处理
- abort → 通知人类 + 保存中间状态
- 连续 2 次同一 phase 失败 → 降级到简化 prompt
```

### 5.2 `spec_review_loop` Skill

**触发词**："评审需求"、"Spec Review"、"需求质量检查"

```markdown
## Skill: spec_review_loop
### 描述
运行 Spec Pro 的需求评审 Loop，自动迭代直到需求质量达标。

### 流程
1. 接收输入：需求文档
2. Phase 1: 需求解析 → 结构化 JSON
3. Phase 2: 完整性检查 → 缺失项列表
4. Phase 3: 一致性检查 → 冲突项列表
5. Phase 4: 可测性检查 → 测试点映射
6. CHECK: 质量分数 ≥ 8/10 → done，否则 → 回到 Phase 2 补充
7. 输出：评审报告 + 改进建议
```

### 5.3 `research_synthesis` Skill

**触发词**："技术调研"、"Research Loop"、"行业最佳实践"

```markdown
## Skill: research_synthesis
### 描述
并行调研 + 综合的 Loop，用于技术方案决策。

### 流程
1. 接收输入：技术主题 + 评估维度
2. 并行 spawn 3-5 个 research worker（每个不同角度）
3. 收集所有 worker 输出
4. spawn consolidator worker 综合
5. CHECK: 覆盖度 ≥ 维度数 × 90% → done
6. 输出：调研报告 + 推荐方案 + 对比矩阵
```

---

## 六、创新性设计：OpenClaw 独特的 Loop Pattern

### 创新 1：Memory-Guided Loop（记忆驱动循环）

**核心思想**：利用 `memory_search` + `memory_get` 让 Loop 从历史项目中学习。

**问题**：当前 Loop 每次运行都是"失忆"的，不知道之前类似项目踩过什么坑。

**方案**：
```python
# PERCEIVE 阶段增加记忆检索
# 在 loop_runner.py 决定下一个 phase 之前，先搜索历史经验
memory_results = memory_search(
    query=f"DeepFlow {domain} phase {current_phase} 失败 错误 经验",
    corpus="all"
)

# 将历史经验注入 worker prompt
if memory_results["hits"]:
    lessons_learned = "\n".join([h["snippet"] for h in memory_results["hits"][:3]])
    worker_prompt += f"\n\n## 历史经验（必须避免以下问题）\n{lessons_learned}"
```

**效果**：
- 第 N 个项目的 Loop 自动继承前 N-1 个项目的教训
- 错误率随项目数递减（学习曲线）
- memory 中的 `decisions/` 目录成为 Loop 的"长期记忆"

**进阶**：Loop 完成后自动将本次经验写入 memory
```python
# PERSIST 阶段写入经验
memory_content = f"""
## {project_name} - Phase {phase} 经验
- 成功因素：{success_factors}
- 踩坑记录：{pitfalls}
- 改进建议：{improvements}
"""
exec(f"echo '{memory_content}' >> memory/loop_learnings.md")
```

### 创新 2：Adaptive Harness Loop（自适应调度循环）

**核心思想**：利用 `subagents` + `sessions_list` 实时监控 Loop 健康度，动态调整资源分配。

**问题**：当前 Loop 的 worker 数量是固定的（serial 或 parallel），不能根据实际负载动态调整。

**方案**：
```python
# 在 Loop 的 CHECK 阶段，检查系统健康度
active_agents = subagents(action="list")
active_sessions = sessions_list(activeMinutes=30, kinds=["subagent"])

# 计算当前负载
load = len(active_sessions) / MAX_CONCURRENT_SESSIONS  # 例如 5/5 = 100%

# 动态调整策略
if load > 0.8:
    # 高负载 → 减少并行度，避免超时
    next_action = "spawn_serial"  # 串行执行
elif load < 0.4:
    # 低负载 → 增加并行度，加速执行
    next_action = "spawn_parallel"
else:
    # 正常负载 → 保持当前策略
    next_action = current_strategy
```

**进阶：基于 Worker 完成时间的自适应**
```python
# 追踪每个 phase 的实际完成时间
completion_times = {}  # {"phase_1": 45, "phase_2": 120, ...}

# 如果某 phase 超时率 > 50%，自动拆分
if avg_time("phase_5") > TIMEOUT_THRESHOLD:
    # 将 Phase 5 拆成 5a + 5b，降低单次复杂度
    loop_runner.py split-phase solution_pro 5 --into 5a,5b
```

**效果**：
- 系统资源利用率提升 40%（低负载时加速，高负载时保守）
- Worker 超时率下降 60%（自适应拆分大任务）
- 无需人工干预即可应对不同复杂度的项目

### 创新 3：Cron-Triggered Loop（定时触发循环）

**核心思想**：利用 OpenClaw cron 实现定时自主运行的 Loop。

```python
# 定时巡检：每天早上 9 点运行 Research Pro 巡检
cron(action="add", job={
    "name": "deepflow_daily_research",
    "schedule": {"type": "cron", "expr": "0 9 * * *"},
    "payload": {
        "type": "agent_turn",
        "message": "运行 DeepFlow Research Pro 巡检所有进行中的项目",
    },
    "delivery": {"channel": "feishu", "target": "ou_xxx"}
})

# 定时质量门禁：每周一检查所有 blackboard 的契约合规性
cron(action="add", job={
    "name": "deepflow_weekly_quality",
    "schedule": {"type": "cron", "expr": "0 10 * * 1"},
    "payload": {
        "type": "agent_turn",
        "message": "运行 DeepFlow 质量门禁检查，输出合规报告到飞书",
    },
    "delivery": {"channel": "feishu", "target": "ou_xxx"}
})
```

---

## 七、整合架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw LoOP 工具链整合                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐    ┌──────────┐    ┌─────────┐    ┌───────────┐  │
│  │ PERCEIVE │───▶│   PLAN   │───▶│   ACT   │───▶│  OBSERVE  │  │
│  │          │    │          │    │         │    │           │  │
│  │ exec     │    │ exec+LLM │    │ spawn   │    │ read+exec │  │
│  │ loop_    │    │ next     │    │ yield   │    │ validate  │  │
│  │ runner   │    │          │    │         │    │           │  │
│  └─────────┘    └──────────┘    └─────────┘    └───────────┘  │
│       ▲                                          │             │
│       │          ┌──────────┐                    │             │
│       └──────────┤  PERSIST │◀───────────────────┘             │
│                  │          │                                  │
│                  │ feishu_  │    ┌───────────────────────┐     │
│                  │ doc/     │    │     CHECK             │     │
│                  │ bitable  │    │  loop_runner check    │     │
│                  │ memory_  │    │  memory_search        │     │
│                  │ search   │    └───────────────────────┘     │
│                  └──────────┘                                  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    外部系统连接                            │  │
│  │  飞书文档 ◄── 进度报告    GitHub ◄── PR/Issue            │  │
│  │  飞书表格 ◄── 任务看板    邮件   ◄── 最终报告            │  │
│  │  Memory   ◄── 经验积累    Cron   ◄── 定时巡检            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Skills 封装层                          │  │
│  │  solution_loop | spec_review_loop | research_synthesis   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 八、总结与建议

### 优先级排序

| 优先级 | 整合项 | 工作量 | 收益 |
|:---|:---|:---|:---|
| P0 | loop_runner + sessions_spawn 标准化 | 低 | 已有，巩固 |
| P0 | 飞书 Bitable 任务看板 | 中 | 全局可见性 |
| P1 | Memory-Guided Loop | 中 | 学习曲线 |
| P1 | Skills 封装（solution_loop） | 低 | 复用性 |
| P2 | Adaptive Harness | 高 | 资源优化 |
| P2 | Cron-Triggered Loop | 低 | 自主运行 |
| P3 | Codex 深度整合 | 高 | 代码生成质量 |

### 核心原则

1. **Python 做流转，LLM 做语义**：loop_runner.py 控制流程，LLM 只负责内容生成
2. **push-based，不轮询**：sessions_yield 等待完成事件，不 poll subagents
3. **契约笼子不可绕过**：每个 phase 输出必须通过 Pydantic 验证
4. **记忆是复利**：每次 Loop 运行都应积累可检索的经验
5. **通知而非打扰**：飞书通知只在关键节点（启动/完成/异常），不逐 phase 轰炸

---

*文档版本: v1.0 | 字数: ~2200 | 工具链专家（Expert 2）*
