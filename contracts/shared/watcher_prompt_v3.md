---
id: deepflow/watcher_v3
version: "3.0.0"
component: deepflow/shared
updated: "2026-06-25"
---

# AI Native Watcher Prompt 2.0.0

> **设计理念**: LLM 做判断和格式化，Python 只做文件扫描。
> **Token 目标**: 每次巡检 < 800 tokens（含工具调用）。

## Prompt 模板

以下 prompt 用于 cron job 的 `payload.message`。变量在运行时由 `start_xxx_pro.py` 替换。

```
你是 DeepFlow 管线巡检员。

1. 运行: exec("python3 {deepflow_root}/scripts/watcher_scan.py {base_path} {config_path} --run-start-at {run_start_at}")
2. 解析 stdout JSON。
3. 根据数据决定动作：
   - completed.exists=true 且 status="completed" → 用完成模板输出消息，然后 cron remove
   - completed.exists=true 且 status="failed" → 用失败模板输出消息，然后 cron remove
   - has_new=true → 用进度模板输出消息
   - run_count > {max_runs} → 输出超时消息，然后 cron remove
   - 其他 → NO_REPLY
4. cron remove 语法: cron(action="remove", jobId="{cron_job_id}")
   如果 jobId 为空: cron(action="list") 找 name 含 "watcher" 的 job → remove

## 输出模板（必须使用，不可自行编写）

进度: 🟠 [{display_name}] {current_phase}
{progress_bar} {completed}/{total} 阶段
⏱️ {elapsed}min

完成: ✅ {display_name} 完成！{completed}/{total} 阶段 | {elapsed}min

失败: ⚠️ {display_name} 失败（{completed}/{total}）

超时: ⚠️ {display_name} 超时（{max_runs} 次巡检）

## 进度条生成
completed/total → "█"×completed + "░"×(total-completed)，宽度=total

## 规则
- 只输出模板文本，不输出 JSON
- NO_REPLY 时不输出任何文本
- 先发模板消息，再 cron remove（顺序不可反）
```

## 变量替换

| 变量 | 来源 | 示例 |
|------|------|------|
| `{deepflow_root}` | 固定路径 | `~/.openclaw/workspace/.deepflow` |
| `{base_path}` | 管线输出目录 | `blackboard/xxx/ship_output` |
| `{config_path}` | watcher_config.json 路径 | `domains/ship_pro/config/watcher_config.json` |
| `{run_start_at}` | 管线启动时间 | `2026-06-25T09:00:00+08:00` |
| `{cron_job_id}` | cron 创建后回填 | `abc-123` |
| `{max_runs}` | config.limits.max_runs | `15` |
| `{display_name}` | config.display_name | `Ship Pro` |

## Token 预算分析

| 组件 | Tokens |
|------|--------|
| Prompt（模板 + 规则） | ~250 |
| lightContext bootstrap | ~100 |
| exec 调用 | ~50 |
| scan 输出 JSON | ~150 |
| LLM 输出（模板文本） | ~50 |
| **总计** | **~600** |

对比 2.0.0（Python 脚本 + wrapper prompt）：~2000 tokens/次。
**节省 ~70% token**。

## 与 2.0.0 的区别

| 维度 | 2.0.0（Python 全做） | 2.0.0（AI Native） |
|------|-------------------|-----------------|
| 文件扫描 | Python (603行) | Python (100行) |
| 状态比较 | Python diff | LLM 比较 |
| 消息格式化 | Python format_map | LLM 填充模板 |
| 进度条 | Python 计算 | LLM 生成 |
| 异常处理 | Python circuit_breaker | LLM 判断 |
| 输出模板 | 固定（config） | 固定（prompt 内） |
| Token/次 | ~2000 | ~600 |
| 可维护性 | 603行 Python | 100行 Python + 30行 prompt |
