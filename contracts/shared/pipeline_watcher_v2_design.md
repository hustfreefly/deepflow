---
id: deepflow/pipeline_watcher_v2
version: "2.0.0"
component: deepflow/shared
updated: "2026-06-20"
status: proposal
author: 小满
review_status: pending
---

# Pipeline Watcher V2 — AI Native 统一组件设计

> **一句话**：用确定性 Python 脚本替代 LLM 做文件巡检，用 JSON 配置替代硬编码，用薄 wrapper prompt 做最小桥接。

---

## 1. 问题本质

当前 Solution Pro 和 Ship Pro 各有一个 ~120 行的 cron_watcher.md prompt，让 LLM 在 isolated session 中做文件检查。

**三个根本性错误**：

| # | 错误 | 后果 |
|---|------|------|
| E1 | 用 LLM 做 `os.path.exists()` | exec 工具调用失败 → 巡检报错（刚才的 Ship Pro 事件就是这个） |
| E2 | 用 LLM 管理 cron 生命周期 | orchestrator 崩溃/重启中断 → cron 成为孤儿 → 持续报错 |
| E3 | 两套独立 prompt 维护 | 改一个 bug 要改两处，circuit breaker 只在 Solution Pro 有 |

**不是代码重复问题，是 AI Native 原则违反问题**：确定性任务不该用 LLM。

---

## 2. 设计方案

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────┐
│  OpenClaw Cron (isolated agentTurn, 每 2-3 分钟)     │
│                                                      │
│  payload.message = 薄 wrapper prompt (~10行)         │
│    → "exec python3 pipeline_watcher.py --config ..." │
│    → "解析 stdout JSON"                              │
│    → "按 action 输出消息或 NO_REPLY"                  │
│                                                      │
│  delivery: { mode: announce, channel: feishu }       │
└──────────────────────┬──────────────────────────────┘
                       │ exec
                       ▼
┌─────────────────────────────────────────────────────┐
│  pipeline_watcher.py (~200行, 100% 确定性)           │
│                                                      │
│  读 JSON 配置 → 扫描目录 → diff → 校验时间戳         │
│  → 计数 → circuit breaker → 格式化消息               │
│  → 输出 JSON 到 stdout                               │
│                                                      │
│  退出码: 0=正常, 1=脚本错误                           │
└──────────────────────┬──────────────────────────────┘
                       │ 消费
                       ▼
┌─────────────────────────────────────────────────────┐
│  各管线 JSON 配置 (watcher_config.json)              │
│                                                      │
│  solution_pro/config/watcher_config.json             │
│  ship_pro/config/watcher_config.json                 │
│  (未来) spec_pro/config/watcher_config.json          │
└─────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
Cron 触发
  → isolated session 启动
  → wrapper prompt 指示 exec(python3 watcher.py ...)
  → Python 脚本运行（确定性，<1s）
  → stdout 输出 JSON:
      {
        "action": "progress|completed|failed|timeout|circuit_break|noop",
        "message": "...",           // 已格式化的用户通知文本
        "should_remove_cron": bool, // 是否应删除 cron
        "progress": {...}           // 可选，结构化进度数据
      }
  → wrapper prompt 指示:
      action=noop → NO_REPLY
      action=其他 → 输出 message 文本（delivery 自动推送）
      should_remove_cron=true → 输出消息后调 cron remove
```

### 2.3 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 脚本语言 | Python 3.9+（系统自带） | 与现有 scripts/ 一致，无额外依赖 |
| 配置格式 | JSON | 与 blackboard 文件一致，Python 原生 |
| LLM 角色 | 薄 wrapper（调 exec + 转发） | 最小化 LLM 自由度，最大化确定性 |
| cron 清理 | 脚本输出 should_remove_cron | 不依赖 orchestrator 清理，脚本自己判断 |
| auto-chain | 文件协议 (.auto_chain_trigger) | 解耦，watcher 不依赖下游管线 |

---

## 3. Python 脚本设计

### 3.1 CLI 接口

```bash
python3 pipeline_watcher.py \
  --config <path_to_watcher_config.json> \
  --base-path <blackboard_dir> \
  --run-start-at <ISO_timestamp> \
  --cron-job-id <cron_id> \
  --state-dir <state_dir>  # 默认 = base-path
```

### 3.2 模块结构

```python
# scripts/pipeline_watcher.py (~200 行)

def main():
    args = parse_args()
    config = load_config(args.config)        # 读 JSON 配置
    
    # 1. 运行计数 + 超时检查
    run_state = RunCounter(args.state_dir, config['limits'])
    run_state.increment()
    if run_state.is_timeout():
        output_timeout(config, run_state)
        return
    
    # 2. 完成标记检查（带时间戳校验）
    completion = CompletionChecker(args.base_path, args.run_start_at)
    if completion.is_completed():
        output_completion(config, completion)
        return
    
    # 3. 新阶段检测（diff）
    detector = StageDetector(args.base_path, config['detection'], args.state_dir)
    new_stages = detector.scan()
    if not new_stages:
        # 4. Circuit breaker
        cb = CircuitBreaker(args.state_dir, config['limits'])
        if cb.should_break():
            output_circuit_break(config, cb)
            return
        output_noop()
        return
    
    # 5. 格式化进度消息
    formatter = MessageFormatter(config, detector.all_stages())
    output_progress(formatter, detector, run_state)

# 输出函数：统一 JSON stdout
def output(action, message, should_remove=False, progress=None):
    result = {"action": action, "message": message, "should_remove_cron": should_remove}
    if progress:
        result["progress"] = progress
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)
```

### 3.3 各模块职责

| 模块 | 职责 | 行数 |
|------|------|------|
| `RunCounter` | 读写 .cron_run_count，计数+超时判断 | ~20 |
| `CompletionChecker` | 检查 .completed，时间戳校验，读 status | ~25 |
| `StageDetector` | glob 扫描目录，diff notified_stages，merge_group 合并 | ~40 |
| `CircuitBreaker` | 连续无输出计数，阈值判断 | ~20 |
| `MessageFormatter` | 读配置模板，渲染进度/完成/失败/超时消息 | ~35 |
| `main()` | CLI 入口，编排流程，输出 JSON | ~40 |
| **合计** | | **~200** |

---

## 4. JSON 配置 Schema

### 4.1 完整 Schema

```json
{
  "$schema": "deepflow/pipeline_watcher_config/v2",
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
    "total_stages": 10,
    "final_artifact": "final_solution.md"
  },

  "templates": {
    "progress": "📊 {display_name}进度 ({completed}/{total})\n━━━━━━━━━━━━━━━━━━━━\n{stage_lines}\n\n已耗时: {elapsed_time}",
    "completed": "✅ {display_name}完成！\n\n📊 {completed}/{total} 阶段完成 | 耗时 {elapsed_time}\n📄 方案: {final_artifact}\n🏆 评分: {score}",
    "failed": "⚠️ {display_name}失败\n\n已完成: {completed}/{total} 阶段\n失败原因: {error}",
    "timeout": "⚠️ {display_name}运行超时（已运行 {timeout_minutes} 分钟）\n\norchestrator 可能已崩溃。已完成的阶段结果仍在目录中。\n建议查看已有结果或重新启动。",
    "circuit_break": "⚠️ Cron 巡检连续 {failures} 次无输出\n\n可能 orchestrator 已停止或管线异常。\n请检查 {base_path}/.stage_progress.json"
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
    "trigger_file": ".auto_chain_trigger"
  }
}
```

### 4.2 Ship Pro 配置

```json
{
  "pipeline_id": "ship_pro",
  "display_name": "Ship Pro",
  "limits": {
    "max_runs": 15,
    "timeout_minutes": 30,
    "circuit_breaker_threshold": 3
  },
  "detection": {
    "completed_file": ".completed",
    "completed_timestamp_field": "completed_at",
    "scan_dirs": [
      {
        "path": ".",
        "pattern": "*_output.json",
        "stage_files": {
          "architect_output.json": {"name": "Architect", "seq": 1},
          "decomposer_output.json": {"name": "Decomposer", "seq": 2},
          "specifier_output.json": {"name": "Specifier", "seq": 3},
          "reviewer_output.json": {"name": "Reviewer", "seq": 4},
          "packager_output.json": {"name": "Packager", "seq": 5}
        }
      }
    ],
    "total_stages": 5,
    "final_artifact": "packager_output.json"
  },
  "templates": {
    "completed": "✅ Ship Pro 管线完成！\n\n📊 {completed}/{total} 阶段完成 | 耗时 {elapsed_time}\n📦 输出: {final_artifact}"
  }
}
```

---

## 5. 薄 Wrapper Prompt

### 5.1 所有管线共用的 wrapper prompt (~10 行)

```
你是 DeepFlow 管线巡检执行器。严格按以下步骤执行：

1. 运行: exec("python3 {deepflow_root}/scripts/pipeline_watcher.py --config {config_path} --base-path {base_path} --run-start-at {run_start_at} --cron-job-id {cron_job_id} --state-dir {base_path}")
2. 解析 stdout 的 JSON
3. 根据 action 字段：
   - "noop" → 回复 NO_REPLY
   - 其他 → 输出 message 字段的文本（delivery 自动推送）
4. 如果 should_remove_cron = true → 输出消息后执行 cron(action="remove", jobId="{cron_job_id}")

禁止：自行判断进度、编造消息、调用 message tool、跳过任何步骤。
```

### 5.2 与当前 prompt 对比

| 维度 | 当前 watcher prompt | 新 wrapper prompt |
|------|-------------------|-------------------|
| 行数 | ~120 行 | ~10 行 |
| LLM 自由度 | 高（自己判断文件/时间/格式） | 极低（只调 exec + 转发） |
| 出错概率 | 高（exec 失败/格式错误/遗漏步骤） | 低（脚本确定性执行） |
| token 消耗/轮 | ~2000 | ~200 |

---

## 6. Cron 创建集成

### 6.1 start_solution_pro.py 改动

```python
# 当前（~30 行 cron 配置 + 大段 prompt 构造）
cron_watcher_prompt = render_template("cron_watcher.md", ...)
cron_result = cron(action="add", job={
    "payload": {"kind": "agentTurn", "message": cron_watcher_prompt, ...},
    ...
})

# 改为（~10 行，配置驱动）
wrapper_prompt = render_wrapper_prompt(
    config_path=f"{deepflow_root}/domains/solution/config/watcher_config.json",
    base_path=base_path,
    run_start_at=run_start_at,
    cron_job_id="PLACEHOLDER",  # 创建后回填
    deepflow_root=deepflow_root
)
cron_result = cron(action="add", job={
    "name": f"deepflow_watcher_{session_id[:8]}",
    "schedule": {"kind": "every", "everyMs": 180000},
    "sessionTarget": "isolated",
    "payload": {"kind": "agentTurn", "message": wrapper_prompt, "timeoutSeconds": 60, "lightContext": True},
    "delivery": delivery_config,  # 从 session context 自动提取
    "enabled": True
})
# 回填 cron_job_id 到 wrapper prompt（用于 self-remove）
```

### 6.2 delivery 自动提取（解决 P0 问题）

```python
def build_delivery_config(session_context: dict) -> dict:
    """从当前 session 上下文提取 delivery 配置，不硬编码"""
    channel = session_context.get("channel", "feishu")
    return {
        "mode": "announce",
        "channel": channel,
        # feishu 时自动带上 openId（从 inbound_meta 获取）
    }
```

---

## 7. Auto-Chain 支持

### 7.1 文件协议

当 watcher_config.json 中 `auto_chain.enabled = true` 且检测到完成时：

```python
# pipeline_watcher.py 内部
if config['auto_chain']['enabled'] and completion.status == 'completed':
    trigger = {
        "source_pipeline": config['pipeline_id'],
        "completed_at": completion.completed_at,
        "base_path": str(base_path),
        "session_id": session_id,
    }
    trigger_path = base_path / config['auto_chain']['trigger_file']
    trigger_path.write_text(json.dumps(trigger, ensure_ascii=False))
    # 在 message 中附加提示
    message += "\n\n🔗 已触发下游管线: " + config['auto_chain']['next_pipeline']
```

### 7.2 主 Agent 检测

主 Agent 在收到完成通知后，检查 `.auto_chain_trigger` 文件是否存在，如果存在则启动下游管线。

---

## 8. 测试方案

### 8.1 单元测试（确定性，可自动化）

```python
# eval/test_pipeline_watcher.py

class TestRunCounter:
    def test_increment_creates_file_on_first_run(self): ...
    def test_increment_reads_existing_count(self): ...
    def test_timeout_when_exceeds_max_runs(self): ...

class TestCompletionChecker:
    def test_no_completed_file_returns_false(self): ...
    def test_completed_with_valid_timestamp(self): ...
    def test_completed_with_stale_timestamp_ignored(self): ...  # 关键：防残留误判

class TestStageDetector:
    def test_empty_dir_no_new_stages(self): ...
    def test_new_stage_detected(self): ...
    def test_merge_group_combines_parallel(self): ...  # reviewers ×3 → 1 条
    def test_already_notified_stages_excluded(self): ...

class TestCircuitBreaker:
    def test_resets_on_output(self): ...
    def test_breaks_after_threshold(self): ...

class TestMessageFormatter:
    def test_progress_format_matches_template(self): ...
    def test_completed_format_includes_score(self): ...
    def test_symbols_match_config(self): ...

class TestIntegration:
    def test_full_run_no_progress_returns_noop(self): ...
    def test_full_run_with_new_stages_returns_progress(self): ...
    def test_full_run_completed_returns_completed(self): ...
    def test_full_run_timeout_returns_timeout(self): ...
```

### 8.2 集成测试

```bash
# 模拟一个完整的 Solution Pro 运行过程
python3 eval/simulate_pipeline.py --pipeline solution_pro --create-stages

# 每创建一个 stage 文件，跑一次 watcher，验证输出
for stage in collection planning reviewer_* research_* consolidator audit fix fixer_expert harness_final summarizer; do
    touch stages/${stage}.json
    python3 pipeline_watcher.py --config ... --base-path ... 2>&1
    # 验证 JSON 输出
done
```

---

## 9. 契约笼子 — 开发声明

### 9.1 功能声明（必须实现）

| ID | 功能 | 验证标准 |
|----|------|---------|
| F1 | RunCounter: 读写 .cron_run_count | 首次创建文件，后续递增，超限返回 timeout |
| F2 | CompletionChecker: 检查 .completed + 时间戳校验 | 有效时间戳→完成，过期时间戳→忽略 |
| F3 | StageDetector: glob 扫描 + diff + merge_group | 新文件检测，并行合并，已通知排除 |
| F4 | CircuitBreaker: 连续无输出计数 | 有输出重置，超阈值触发 |
| F5 | MessageFormatter: 模板渲染 | 进度/完成/失败/超时/熔断 5 种消息格式正确 |
| F6 | CLI: 参数解析 + JSON stdout | 所有输出为合法 JSON，exit code 0 |
| F7 | Wrapper prompt: 所有管线共用 | Solution Pro 和 Ship Pro 用同一个 prompt 模板 |
| F8 | Auto-chain: 触发文件写入 | 完成时写 .auto_chain_trigger |

### 9.2 质量判据（AI Native，非结构映射）

| 判据 | 标准 |
|------|------|
| **确定性** | 脚本执行无任何 LLM 调用，所有逻辑为纯 Python |
| **幂等性** | 同一状态下多次运行结果一致（不产生副作用累积） |
| **可测试性** | 所有模块可独立 mock 测试，无需真实文件系统 |
| **零配置代码** | 新管线接入只需写 JSON，不改 Python |
| **防御性** | 配置缺失/路径不存在 → 优雅退出 + stderr 报错，不 crash |

### 9.3 不做的事（YAGNI）

- ❌ 不做复合监听（一个 watcher 监多个管线）
- ❌ 不做 Web UI 进度展示
- ❌ 不做历史运行统计
- ❌ 不做远程通知（webhook/email）

---

## 10. 迁移路径

| Phase | 内容 | 验证 |
|-------|------|------|
| **P1: 脚本开发** | 写 pipeline_watcher.py + 单元测试 | 8/8 单元测试 PASS |
| **P2: Solution Pro 配置** | 写 watcher_config.json + wrapper prompt | 模拟运行输出正确 JSON |
| **P3: Ship Pro 配置** | 写 watcher_config.json | 模拟运行输出正确 JSON |
| **P4: 集成** | 修改 start_solution_pro.py + start_ship_pro.py | 真实管线端到端 PASS |
| **P5: 清理** | 删除旧 cron_watcher.md（两个） | 无残留引用 |

---

## 11. 量化收益

| 指标 | 当前 | 目标 | 改善 |
|------|:----:|:----:|:----:|
| watcher prompt 行数 | 120+120=240 | 10（共用） | -96% |
| LLM token/轮 | ~2000 | ~200 | -90% |
| exec 调用/轮 | 2-3 | 1 | -66% |
| 误报率 | 依赖 exec 可靠性 | 0（纯 Python） | → 0 |
| 新管线接入 | 写 prompt + 测试 | 写 JSON 配置 | 小时→分钟 |
| Circuit Breaker 覆盖 | 仅 Solution Pro | 所有管线 | +100% |
| 孤儿 cron 风险 | 依赖 orchestrator 清理 | 脚本 self-remove | 消除 |
