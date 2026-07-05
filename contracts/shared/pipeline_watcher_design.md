---
id: deepflow/pipeline_watcher_design
version: "1.0.0"
component: deepflow/shared
updated: "2026-06-20"
status: proposal
author: system_architect (subagent review)
---

# DeepFlow Pipeline Watcher 统一组件设计

> **评审范围**: 统一 Solution Pro / Ship Pro (及未来 Spec Pro) 的 cron watcher  
> **核心目标**: 消除重复、提升稳定性、支持 auto-chain 多模块监听  
> **设计原则**: 确定性优先、配置驱动、零 LLM 依赖

---

## 一、现状分析

### 1.1 代码重复度分析

| 逻辑模块 | Solution Pro | Ship Pro | 重复度 |
|----------|:----------:|:--------:|:------:|
| 运行计数 + 超时保护 | ✅ | ✅ | 100% |
| 时间戳校验（防残留误判） | ✅ | ✅ | 100% |
| .completed 检测 + 状态分发 | ✅ | ✅ | 100% |
| 目录扫描 + diff 检测新阶段 | ✅ | ✅ | 90%* |
| 进度消息格式化 | ✅ | ✅ | 70%** |
| Circuit Breaker | ✅ | ❌ | N/A |
| 并行阶段合并 | ✅ | ❌ | N/A |

*目录结构不同：Solution Pro 扫描 `stages/` + `data/`，Ship Pro 扫描根目录 `*_output.json`  
**消息模板结构相同，但阶段名/总数/图标不同

### 1.2 核心问题

| # | 问题 | 影响 |
|---|------|------|
| P1 | LLM 做确定性文件检查 = 不稳定 | exec 工具失败 → 误报/漏报 |
| P2 | 两份 watcher prompt 维护成本 | 改一个 bug 要改两处 |
| P3 | 无法跨模块监听 | auto-chain 场景需要人工衔接 |
| P4 | Circuit Breaker 只在 Solution Pro | Ship Pro 无保护 |
| P5 | 阶段映射硬编码在 prompt 中 | 新增阶段要改 prompt 模板 |

---

## 二、组件设计

### 2.1 接口定义

```
┌─────────────────────────────────────────────────────────┐
│              PipelineWatcher (确定性脚本)                 │
│                                                          │
│  输入:                                                    │
│    --config <pipeline_config.json>   阶段映射+消息模板     │
│    --base-path <blackboard_path>     管线工作目录          │
│    --run-start-at <ISO timestamp>    本次运行启动时间      │
│    --state-dir <state_directory>     状态文件存放目录      │
│                                                          │
│  输出 (stdout JSON):                                      │
│    {                                                     │
│      "action": "progress" | "completed" | "failed"       │
│              | "timeout" | "circuit_break" | "noop",      │
│      "message": "<formatted notification text>",          │
│      "progress": {                                       │
│        "completed": 5,                                   │
│        "total": 10,                                      │
│        "stages": [...],                                  │
│        "elapsed_minutes": 12                             │
│      },                                                  │
│      "should_remove_cron": true | false                  │
│    }                                                     │
│                                                          │
│  退出码:                                                  │
│    0 = 正常（检查 stdout JSON 判断 action）               │
│    1 = 脚本错误（配置缺失/路径不存在）                     │
└─────────────────────────────────────────────────────────┘
```

### 2.2 配置 Schema

每个管线模块提供一个 JSON 配置文件， watcher 脚本消费它：

```json
{
  "$schema": "deepflow/pipeline_watcher_config",
  "pipeline_id": "solution_pro",
  "display_name": "方案设计",
  
  "limits": {
    "max_runs": 20,
    "timeout_minutes": 60,
    "circuit_breaker_threshold": 3
  },

  "detection": {
    "completed_file": ".completed",
    "completed_timestamp_field": "completed_at",
    "scan_dirs": [
      {
        "path": "stages",
        "pattern": "*.json",
        "stage_files": {
          "planning.json": {"name": "Planning", "seq": 2},
          "reviewer_technical.json": {"name": "Reviewers", "seq": 3, "merge_group": "reviewers"},
          "reviewer_business.json": {"name": "Reviewers", "seq": 3, "merge_group": "reviewers"},
          "reviewer_risk.json": {"name": "Reviewers", "seq": 3, "merge_group": "reviewers"},
          "research_expert_1.json": {"name": "Research", "seq": 4, "merge_group": "research"},
          "research_expert_2.json": {"name": "Research", "seq": 4, "merge_group": "research"},
          "research_expert_3.json": {"name": "Research", "seq": 4, "merge_group": "research"},
          "consolidator.json": {"name": "Consolidator", "seq": 5},
          "audit.json": {"name": "Audit", "seq": 6},
          "fix.json": {"name": "Fix", "seq": 7},
          "fixer_expert.json": {"name": "Fixer Expert", "seq": 8},
          "harness_final.json": {"name": "Harness Final", "seq": 9},
          "summarizer.json": {"name": "Summarizer", "seq": 10}
        }
      },
      {
        "path": "data",
        "pattern": "*.json",
        "stage_files": {
          "collection.json": {"name": "Data Collection", "seq": 1}
        }
      }
    ],
    "final_artifact": "final_solution.md"
  },

  "templates": {
    "progress": "📊 {display_name}进度 ({completed}/{total})\n━━━━━━━━━━━━━━━━━━━━\n{stage_lines}\n\n已耗时: {elapsed_time}",
    "completed": "✅ {display_name}完成！\n\n📊 共 {completed}/{total} 阶段完成\n📄 方案: {base_path}/{final_artifact}\n🏆 评分: {score}",
    "failed": "⚠️ {display_name}失败\n\n状态: {status}\n已完成: {completed_stages}/{total} 阶段\n失败原因: {error}",
    "timeout": "⚠️ {display_name}运行超时（已运行 {timeout_minutes} 分钟）\n\norchestrator 可能已崩溃。已完成的阶段结果仍在目录中。\n建议查看已有结果或重新启动。",
    "circuit_break": "⚠️ Cron 巡检连续 {failures} 次无输出。可能 orchestrator 已停止或管线异常。"
  },

  "stage_symbols": {
    "done": "✅",
    "running": "⏳",
    "pending": "⬜"
  },

  "auto_chain": {
    "enabled": false,
    "next_pipeline": null,
    "trigger_on": "completed",
    "trigger_config": null
  }
}
```

Ship Pro 配置对比：

```json
{
  "pipeline_id": "ship_pro",
  "display_name": "Ship Pro 管线",
  "limits": {"max_runs": 15, "timeout_minutes": 30, "circuit_breaker_threshold": 3},
  "detection": {
    "scan_dirs": [{
      "path": ".",
      "pattern": "*_output.json",
      "stage_files": {
        "architect_output.json": {"name": "Architect", "seq": 1},
        "decomposer_output.json": {"name": "Decomposer", "seq": 2},
        "specifier_output.json": {"name": "Specifier", "seq": 3},
        "reviewer_output.json": {"name": "Reviewer", "seq": 4},
        "packager_output.json": {"name": "Packager", "seq": 5}
      }
    }],
    "final_artifact": "packager_output.json"
  }
}
```

### 2.3 适配方式

**配置即适配**。新增管线模块只需：

1. 创建 `domains/<module>/config/watcher_config.json`
2. 定义阶段映射 + 消息模板
3. 启动脚本中调用统一 watcher

无需修改 watcher 脚本本身。

---

## 三、实现方案

### 3.1 确定性脚本 vs LLM 判断

| 功能 | 实现方式 | 理由 |
|------|---------|------|
| 文件存在性检查 | **确定性 Python** (`pathlib.exists()`) | 100% 可靠，无 exec 失败风险 |
| 目录扫描 + diff | **确定性 Python** (`pathlib.glob()` + set 差集) | 纯 IO + 集合运算 |
| 时间戳校验 | **确定性 Python** (`datetime.fromisoformat()`) | 精确比较，无歧义 |
| 运行计数 | **确定性 Python** (JSON read/write) | 原子操作 |
| 进度消息格式化 | **确定性 Python** (`str.format()` + 模板) | 模板驱动 |
| Circuit Breaker | **确定性 Python** (计数器) | 简单状态机 |
| 完成状态判定 | **确定性 Python** (读 JSON status 字段) | 结构化数据 |
| auto-chain 触发 | **确定性 Python** (写触发文件) | 文件协议 |

**结论：整个 watcher 100% 确定性，零 LLM 依赖。**

当前用 LLM 做文件检查是根本性设计错误 — 用千亿参数模型做 `os.path.exists()` 既不可靠又浪费资源。

### 3.2 脚本架构

```
scripts/pipeline_watcher.py          # 统一入口（~150 行）
  │
  ├── PipelineWatcherConfig          # 配置加载 + schema 校验
  ├── StageDetector                  # 目录扫描 + diff + 合并组
  ├── TimestampValidator             # 时间戳校验逻辑
  ├── RunCounter                     # 计数 + 超时判定
  ├── CircuitBreaker                 # 连续失败计数
  ├── MessageFormatter               # 模板渲染
  └── main()                         # CLI 入口，输出 JSON
```

### 3.3 与 OpenClaw cron 的集成方式

**当前模式（LLM-based）**:
```
cron(action="create", mode="isolated", agentTurn=<LLM prompt>, ...)
→ LLM 读 prompt → LLM 调 exec/read → LLM 生成消息 → delivery
```

**目标模式（确定性脚本 + 薄 LLM 包装）**:
```
cron(action="create", mode="isolated", agentTurn=<wrapper prompt>, ...)
→ wrapper prompt 指示: exec(python3 pipeline_watcher.py --config ...)
→ 解析 stdout JSON → 按 action 类型输出消息或 NO_REPLY
```

**wrapper prompt 模板（~10 行，所有管线共用）**:

```markdown
你是 DeepFlow 管线巡检执行器。执行以下命令并根据输出决定行为：

1. 用 exec 运行: python3 {deepflow_root}/scripts/pipeline_watcher.py --config {config_path} --base-path {base_path} --run-start-at {run_start_at} --state-dir {base_path}
2. 解析 stdout 的 JSON 输出
3. 根据 action 字段决定：
   - "noop" → NO_REPLY
   - "progress" / "completed" / "failed" / "timeout" / "circuit_break" → 输出 message 字段内容
4. 如果 should_remove_cron = true，输出消息后执行 cron(action="remove", jobId="{cron_job_id}")

禁止：自行判断进度、编造消息内容、跳过任何步骤。
```

**关键改进**:
- LLM 只做两件事：调 exec + 转发消息
- 所有判断逻辑在 Python 脚本中，100% 可测试
- wrapper prompt 10 行，所有管线共用一份

### 3.4 状态文件协议

所有状态文件统一为 JSON，放在 `--state-dir`（即 base_path）：

| 文件 | 用途 | 格式 |
|------|------|------|
| `.cron_run_count` | 运行计数 | `{"count": 5, "run_start_at": "2026-06-20T12:00:00+08:00"}` |
| `.notified_stages.json` | 已通知阶段 | `["planning.json", "collection.json"]` |
| `.cron_consecutive_failures` | Circuit breaker | `{"count": 0}` |
| `.completed` | 完成标记（已有协议，不变） | `{"status": "completed", "completed_at": "...", ...}` |

---

## 四、Auto-Chain 支持

### 4.1 多模块监听设计

auto-chain 场景：Solution Pro 完成 → 自动触发 Ship Pro。

**方案：文件协议触发（无额外 cron）**

```json
// solution_pro watcher_config.json 的 auto_chain 部分
{
  "auto_chain": {
    "enabled": true,
    "next_pipeline": "ship_pro",
    "trigger_on": "completed",
    "trigger_config": {
      "trigger_file": ".auto_chain_trigger",
      "payload": {
        "source_pipeline": "solution_pro",
        "session_id": "{session_id}",
        "completed_at": "{completed_at}",
        "base_path": "{base_path}"
      }
    }
  }
}
```

**流程**:
```
Solution Pro watcher 检测完成
  → 写 .auto_chain_trigger 文件（JSON payload）
  → 通知用户 "方案设计完成，正在启动 Ship Pro..."
  → 主 agent 的 orchestrator 检测到 trigger 文件
  → 调用 start_ship_pro.py
```

### 4.2 跨模块监听（可选扩展）

如果需要一个 watcher 同时监听多个模块（如 Solution Pro + Ship Pro 并行运行）：

```json
{
  "pipeline_id": "composite_monitor",
  "watch_targets": [
    {"config": "domains/solution_pro/config/watcher_config.json", "base_path": "..."},
    {"config": "domains/ship_pro/config/watcher_config.json", "base_path": "..."}
  ],
  "aggregation": "independent"  // 或 "sequential"（等 A 完成后才监 B）
}
```

**建议**: 2.0.0 不做复合监听。auto-chain 通过触发文件 + 主 agent 编排实现，保持 watcher 单一职责。

---

## 五、迁移路径

### Phase 1: 脚本开发 + Solution Pro 迁移（优先级最高）

| 步骤 | 内容 | 风险 |
|:----:|------|------|
| 1.1 | 编写 `scripts/pipeline_watcher.py`（~150 行） | 低 |
| 1.2 | 编写 Solution Pro `watcher_config.json` | 低 |
| 1.3 | 编写薄 wrapper prompt（~10 行） | 低 |
| 1.4 | 单元测试：模拟各阶段文件，验证输出 JSON | 低 |
| 1.5 | 灰度：Solution Pro 新 runner 用新脚本，旧 prompt 保留 | 低 |
| 1.6 | 验证：跑一个完整案例，对比新旧输出 | 中 |

### Phase 2: Ship Pro 迁移

| 步骤 | 内容 | 风险 |
|:----:|------|------|
| 2.1 | 编写 Ship Pro `watcher_config.json` | 低 |
| 2.2 | 替换 Ship Pro cron 注册为薄 wrapper | 低 |
| 2.3 | 验证 | 低 |

### Phase 3: Auto-Chain 集成

| 步骤 | 内容 | 风险 |
|:----:|------|------|
| 3.1 | 在 Solution Pro config 中启用 auto_chain | 低 |
| 3.2 | 主 agent 增加 trigger 文件检测逻辑 | 中 |
| 3.3 | 端到端测试：Solution Pro 完成 → Ship Pro 自动启动 | 中 |

### Phase 4: 清理

| 步骤 | 内容 |
|:----:|------|
| 4.1 | 删除 `domains/solution_pro/prompts/cron_watcher.md` |
| 4.2 | 删除 `domains/ship_pro/prompts/cron_watcher.md` |
| 4.3 | 更新 SKILL.md 中的 cron watcher 注册说明 |

---

## 六、收益量化

| 指标 | 当前 | 目标 | 改善 |
|------|:----:|:----:|:----:|
| watcher 代码文件数 | 2 个 prompt | 1 脚本 + N 配置 | -50%+ |
| 单管线 watcher 行数 | ~120 行 prompt | ~5 行 wrapper | -95% |
| exec 调用次数/轮 | 2-3 次（test -f, ls） | 1 次（python3） | -66% |
| LLM token 消耗/轮 | ~2000 tokens | ~200 tokens | -90% |
| 误报率 | 依赖 exec 可靠性 | 零（纯 Python） | → 0 |
| 新管线接入成本 | 改 prompt + 测试 | 写 JSON 配置 | 从小时级→分钟级 |
| Circuit Breaker | 仅 Solution Pro | 所有管线 | +100% 覆盖 |

---

## 七、决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 配置格式 | JSON（非 YAML/TOML） | 与现有 blackboard 文件一致，Python 原生支持 |
| 脚本语言 | Python 3.9+ | 系统自带，与现有 scripts/ 一致 |
| 消息模板位置 | 配置文件中（非代码中） | 各模块可独立定制，无需改代码 |
| auto-chain 协议 | 文件触发（非直接调用） | 解耦，watcher 不依赖 Ship Pro 启动脚本 |
| wrapper prompt 策略 | 薄包装（~10行） | 最小化 LLM 自由度，最大化确定性 |
| 状态文件位置 | base_path 下 | 与现有协议一致，无需迁移 |

---

## 八、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|:----:|------|
| OpenClaw cron 不支持 exec 后解析 JSON | 低 | 中 | wrapper prompt 保留 fallback：如果 JSON 解析失败，直接输出 stdout 原文 |
| Python 脚本异常导致 cron 无输出 | 中 | 低 | Circuit Breaker 兜底（3次无输出→告警→自删） |
| 配置文件 schema 错误 | 低 | 高 | 脚本启动时先校验 config，失败则 exit 1 + stderr 报错 |
| 迁移期间新旧 watcher 并存 | 中 | 低 | 用 feature flag（环境变量）切换，不删除旧 prompt 直到验证通过 |

---

## 九、与现有架构的关系

```
                    ┌─────────────────────────────┐
                    │   OpenClaw Cron (isolated)    │
                    │   agentTurn = wrapper prompt  │
                    └──────────────┬──────────────┘
                                   │
                                   │ exec
                                   ▼
                    ┌─────────────────────────────┐
                    │  pipeline_watcher.py          │
                    │  (确定性 Python, ~150 行)     │
                    │                              │
                    │  读配置 → 扫描目录 → diff     │
                    │  → 校验时间戳 → 格式化消息    │
                    │  → 输出 JSON                  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                              │
           ┌────────┴────────┐          ┌──────────┴──────────┐
           │ solution_pro/   │          │ ship_pro/           │
           │ config/         │          │ config/             │
           │ watcher_config  │          │ watcher_config      │
           │ .json           │          │ .json               │
           └─────────────────┘          └─────────────────────┘
```

---

## 十、总结

**核心洞察**: 当前 watcher 的根本问题不是"代码重复"，而是"用 LLM 做确定性工作"。

**解决方案的本质**:
1. 把确定性逻辑还给确定性代码（Python 脚本）
2. 把 LLM 缩减为薄执行器（调脚本 + 转发结果）
3. 把模块差异外化为配置（JSON 文件）

这不是"重构"，是**架构纠偏** — 回归 AI Native 原则：确定性任务用代码，语义任务才用 LLM。
