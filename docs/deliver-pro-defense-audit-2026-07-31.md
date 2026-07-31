# Deliver Pro 防御性审计报告

> 审计时间: 2026-07-31 08:33
> 审计范围: `.deepflow/domains/deliver_pro/` 全目录
> 方法论: FixFlow Phase 1 结构化诊断

---

## 高危（会导致 Pulse 卡死）— 3 个

| # | 文件:行号 | 缺陷 | 影响 | 修复方向 |
|---|-----------|------|------|----------|
| H1 | orchestrator.py:955 `_filter_spawnable_tasks` | MANIFEST.json 损坏时静默 `continue` 不重试。`try/except: pass` 使 `exempt=False`，任务被跳过但 attempts 未递增、无 MANIFEST 写入、无告警 | Worker 永久 stuck，永不重派。下游 blocked 级联卡死整个 WP | 代码修 |
| H2 | orchestrator.py:215 `_load_progress` | `batch_progress.json` 损坏/不可读 → `return {}` 全损。丢失所有 `terminal_failed`, `task_attempts`, `task_spawned_at` | terminal_failed WP 重新进入流水线触发无意义重派；task_attempts 归零突破 retry budget 上限 | 代码修 |
| H3 | phase_deriver.py:182-190 `_validate_delivery_manifest` | `delivery_manifest.json` 损坏 → 回退 `PACKAGING` → Package Agent 重试 → LLM 可能再写坏 → **无限回退循环**。无重试次数上限 | WP 无限在 PACKAGING↔DONE 震荡，永不终态 | 代码修 |

### 高危根因共性
**LLM 输出损坏 → 代码静默吞掉异常 → 状态不一致 → Pulse 卡死**

---

## 中危（会导致任务失败）— 8 个

| # | 文件:行号 | 缺陷 | 影响 | 修复方向 |
|---|-----------|------|------|----------|
| M1 | wp_runner.py:1581,1601,1621,1641 | `verify_package_output` 方法**四次完全相同的定义**。第 4 次生效 | 维护陷阱——修改前三处不会生效 | 代码修 |
| M2 | driver.py:165 `step4_check_workers` | MANIFEST.json 用 `json.loads()` 直接读，只检查 `status=="FAILED"`，无 Pydantic schema | Worker 输出字段错位 → 静默跳过质量门 | 混合修 |
| M3 | orchestrator.py:1190 `_prepare_worker_retries` | MANIFEST 读入后只做 `dict.get()`，无 Pydantic。字段名变更不回显 | 重试逻辑静默跳过 quality_failure | 代码修 |
| M4 | orchestrator.py:433 `_has_unexecuted_tasks` | MANIFEST 缺 `failure_class` 字段 → `None in (...)` 为 False → 豁免路径不进 | 可恢复的任务被终态判死 | 代码修 |
| M5 | orchestrator.py:1375 `_count_in_flight` | `json.loads` 直接读 execution_plan.json（LLM 输出），无 Pydantic | 损坏 → in_flight 计数错误 → 并发控制失效 | 代码修 |
| M6 | orchestrator.py:1419 `_update_pulse_state` | `_pulse_state.json` 损坏 → `state = {}` → zero_progress_count 归零 | 告警延迟或永不触发 | 代码修 |
| M7 | orchestrator.py:625 `_get_wp_next_action` (VALIDATING) | Validate Agent 输出损坏 → 直接判 `package_failed`（跳过 fix loop） | LLM 可修复的小问题被升级为不可恢复失败 | 混合修 |
| M8 | phase_deriver.py:236-250 `derive_phase` | execution_plan.json 用裸 `json.load()`，无 Pydantic | 不兼容格式 → phase 推导停滞在 GENERATING | 代码修 |

---

## 低危（边缘场景）— 6 个

| # | 文件:行号 | 缺陷 | 修复方向 |
|---|-----------|------|----------|
| L1 | orchestrator.py:963 `_is_stale_dispatch` | evidence 路径依赖隐式字符串拼接 | 代码修 |
| L2 | orchestrator.py:400 VALIDATING→package_failed | `except Exception` 捕获范围过大，瞬态 I/O 错误也判死 | 代码修 |
| L3 | phase_deriver.py:370-415 `migrate_legacy_worker_outputs` | `wp_dir.parent` 语义依赖，symlink 下搬迁方向错误 | 代码修 |
| L4 | driver.py:163 `step4_check_workers` | glob 匹配可能遗漏极深嵌套目录 | 代码修 |
| L5 | orchestrator.py:1456 `pulse()` | `_orphan_sweep()` 多机部署无跨节点锁 | 设计约束声明 |
| L6 | phase_deriver.py:106-110 `derive_worker_progress` | `rglob("*")` 全量扫描，I/O 随产出线性膨胀 | 代码修（低优） |

---

## 统计

| 严重度 | 数量 | 修复方向 |
|:------:|:----:|:--------:|
| 🔴 高危 | 3 | 全部代码修 |
| 🟡 中危 | 8 | 6 代码修 + 2 混合修 |
| 🟢 低危 | 6 | 5 代码修 + 1 设计约束 |
| **合计** | **17** | **14 代码修 + 2 混合修 + 1 设计约束** |

---

## 根因模式归纳

### 模式 A: LLM 输出无校验直接消费（H1, M2, M3, M5, M8）
```
json.loads(llm_output) → dict.get() → 静默使用
```
**根治**: 统一 `SafeJsonLoader` — `json.load()` + `Pydantic.model_validate()` + 损坏时写合成 fallback

### 模式 B: 异常吞掉后状态丢失（H2, M6）
```
except Exception: return {} / state = {}
```
**根治**: 损坏时备份 + 从文件证据重建关键字段，不丢光

### 模式 C: 无限重试无上限（H3）
```
损坏 → 回退 → 重试 → 再损坏 → 无限循环
```
**根治**: 加 retry counter，超过 N 次 → terminal_failed

### 模式 D: 异常分类过粗（M7, L2）
```
except Exception → 一刀切判死
```
**根治**: 区分瞬态错误（重试）vs 逻辑错误（判死）

---

## 修复优先级建议

### Wave 1: 防卡死（高危 3 个）
- H1: MANIFEST 损坏 → 写合成 FAILED MANIFEST + 告警
- H2: batch_progress 损坏 → 备份 + 从文件证据重建
- H3: manifest 损坏循环 → 加 retry counter + terminal_failed

### Wave 2: 防误判（中危 8 个）
- M1-M8: 统一引入 SafeJsonLoader + Pydantic 校验

### Wave 3: 边缘加固（低危 6 个）
- L1-L6: 路径显式化 + 异常分类 + I/O 优化
