# Deliver Pro 调度器修复方案 V2.0（双专家评审后定稿）

> 版本: V2.0（DeepSeek V4 Pro 稳健性评审 + Qwen 3.7 Max 架构评审后修订）
> 日期: 2026-07-29
> V1.0 变更：F1 层次重新裁决、F3 三处补强、新增 Class E 根因、F4 归档化、补充部署策略与监控

---

## 评审意见裁决表（我作为 orchestrator 的仲裁）

| # | 评审意见 | 来源 | 裁决 |
|---|---|---|---|
| 1 | F1 应做结构性修复（mkdir 纯函数化）而非对称清理 | 架构 ❌ | **部分采纳**：F1a+F1b 立即止血（稳健性评审已验证安全），F1c 纯函数化列为后续重构。理由：F1b sweep 扩展使"遗忘清理"也能 5min 自愈，结构性风险已被兜住；纯函数化需验证 worker 契约，不阻塞紧急修复 |
| 2 | F3 守卫必须同时覆盖 ASSEMBLING 分支 | 稳健性 ⚠️ | **采纳**（否则 phase 被直接推导为 ASSEMBLING 时守卫完全旁路） |
| 3 | F3 守卫必须用 `timed_out` 集合而非 `failed` | 稳健性 ⚠️ | **采纳**（MANIFEST-FAILED 任务 retry 逻辑不处理，守卫它们会死锁 WP） |
| 4 | F3 与 `_prepare_worker_retries` 的 `get(task_id, 1)` 语义对齐 | 稳健性 ⚠️ | **采纳** |
| 5 | 新增 Class E：终态文件写入前的守卫（delivery_manifest） | 架构 ⚠️ | **采纳**（F3c，最后一道防线） |
| 6 | F2 映射表提取为模块常量 + 双向引用注释 | 架构 ⚠️ | **采纳**（拒绝"action 自声明"——YAGNI） |
| 7 | F4 先归档再删除 + progress 清理保留真实 task attempts | 架构 ⚠️ | **采纳** |
| 8 | 补充部署顺序/回滚预案/监控指标 | 架构 ⚠️ | **采纳**（见 §5-6） |
| 9 | 口诀 4 修正：Class D 是 A+B 耦合的涌现信号 | 架构 ⚠️ | **采纳** |
| 10 | solution_pro 至少做 grep 级 Class B 扫描 | 架构 ⚠️ | **采纳**（实施时执行，发现"主信号"误用才修） |
| 11 | F1a/F1b 安全性（三层保护/场景穷举/竞态可接受） | 稳健性 ✅ | 维持原方案 |
| 12 | F2 不验证文件内容，靠下一 pulse 的 step2_check_analyze 闭环 | 稳健性 ⚠️ | **采纳**（写入方案注释） |

---

## 0. 事故全景（同 V1.0，略）

时间线、用户两问的真相、五 WP 受害清单——见 V1.0。核心：in_flight=10 全是幽灵（4 个非 worker 超时占位 + 6 个孤儿空目录），真实在途 agent = 0；流水线系统性制造"完成假象"。

---

## 1. 根因分类 V2（4+1 类）

### Class A：副作用先于决策
`_prepare_single_worker_spawn` 构建 params 时即 mkdir + 写 bootstrap（`wp_runner.py:520`），spawn 决策（预算/过滤）在其后。否决时副作用残留 → 孤儿目录。
**爆发点**：`orchestrator.py:635` budget=0 分支无清理（同函数 :649 截断分支有清理，行为不一致）。

### Class B：时间推断代替证据
非 worker dispatch 纯按 30min 超时释放 in-flight 名额，无完成检测。文件系统明明有证据。
**爆发点**：23:37 analyze 全完成仍占 5 名额 → budget=3 → 触发 Class A。

### Class C：弱证据上的不可逆升级
attempts=0（从未运行）的任务超时被判 failed → blocked 级联 → ASSEMBLING → 绕过重试预算 → 假 DONE。
**受害者**：DFM-001（2/10）、CHP-001（2/6）、DFM-003/004（0 产出）、INT-001（险）。

### Class E（新增）：状态污染后的不可逆写入
终态文件（`delivery_manifest.json`）一旦写入，derive 即认为"已完成"，回滚只能手动删。即使 A/B/C 全修，未来新来源的伪 failed 仍可污染文件系统。**守卫必须前移到终态写入前**。

### Class D（修正定位）：无阻尼正反馈 = A+B 耦合的涌现信号
不是独立根因，不单独修。**检测口诀修正为**："资源记账环路的恶化 = 先查 A 和 B，不要试图单独修 D"。

---

## 2. 修复方案 V2.0

### F1（P0）：消除孤儿目录

**F1a（1 行，立即止血）**：`orchestrator.py` tick() budget=0 分支 `continue` 前补：
```python
self._drop_worker_param_dirs(wp_id, current_params)
```
稳健性评审已验证安全：`current_params` 只含 ready+timed_out（derive 排除 running），`_drop_task_dir_if_empty` 三层保护（不存在/MANIFEST/非空均跳过），TOCTOU 窗口在 flock 内可忽略。

**F1b（~15 行，结构性兜底）**：`_orphan_sweep` 扩展：
- 空目录 + 无 `task_spawned_at` 记录 + 目录年龄 > 5min → 删除
- 5min = 正常 spawn→首文件写入耗时（<70s）的 4x 余量
- 场景穷举已验证：正常 spawn（非空）/回滚（已删）/慢启动（有记录豁免）/手动 spawn（非空）/平台 crash（有记录）——唯一命中者即 budget=0 孤儿
- **效果**：即使未来新增否决路径忘记清理，5min 内自愈。这是对架构评审"纪律 vs 结构"质疑的结构性回应

**F1c（后续重构，不阻塞本次）**：`_prepare_single_worker_spawn` 拆两步——参数构建纯函数化 + spawn 决策后 mkdir。前置工作：验证全部 worker prompt 的文件写入是否 `parents=True`。列技术债。

### F2（P0）：in_flight 证据化

**改动**：`_count_in_flight` 非 worker dispatch 计数前先做完成检测，映射表提取为模块常量：

```python
# 完成证据映射：action → 阶段产出文件（与 wp_runner.py 各 step 实现保持双向引用）
# analyze ← wp_runner.step2_check_analyze 读取同一文件
# validate ← wp_runner.verify_validate_output 写入同一文件
# package  ← wp_runner.step7_package 写入同一文件
_ACTION_COMPLETION_EVIDENCE = {
    "analyze": "stages/execution_plan.json",
    "validate": "stages/validation_result.json",
    "package": "stages/delivery_manifest.json",
    "package_failed": "stages/delivery_manifest.json",
}
```

- 证据文件存在 → 该 dispatch 不计入 in_flight（立即释放名额）
- **已知边界（评审确认可接受）**：只查存在性不验内容；内容损坏由下一 pulse 的 `step2_check_analyze`（Pydantic 验证）闭环，最多漏报一个名额，不致并发超限
- **部署即见效**：现有 4 个非 worker 幽灵的证据文件都已存在 → 立即释放

### F3（P0）：级联防护（三道守卫）

**F3a（GENERATING 分支守卫）**：`_get_wp_next_action` 中 `all_done` 短路前：
```python
# 只查 timed_out 子集（MANIFEST-FAILED 不归 retry 管，守卫它们会死锁）
retriable = [t for t in timed_out_tasks
             if attempts_map.get(t, 1) < RETRY_BUDGET]  # get 默认值 1，与 _prepare_worker_retries 语义对齐
if retriable:
    all_done = False  # 放行到 _prepare_worker_retries 重试路径
```

**F3b（ASSEMBLING 分支守卫，评审新增）**：phase 已被 derive 为 ASSEMBLING 时同样检查——否则上一 pulse 的状态残留会旁路 F3a。同样条件不满足 → 回退按 GENERATING 处理。

**F3c（Class E 守卫，终态写入前，评审新增）**：package/assembly 写 `delivery_manifest.json` 前验证：
```python
zero_attempt = [t for t in plan_tasks
                if not (worker_outputs/t/MANIFEST.json).exists()
                and attempts_map.get(t, 0) == 0]
if zero_attempt:
    # 拒绝写终态文件，WP 回 GENERATING + CRITICAL 告警
    # 有真实产出的任务（MANIFEST 存在）不受此限——它们的信息是守恒的
```

### F4（P1）：状态修复（归档优先版）

前置：cron 已暂停。部署 F1+F2 后执行：

```bash
# 每个受害 WP 先归档（信息守恒，derive 忽略 dotfile 目录）
mkdir -p {wp_dir}/.incident_archive_20260729/
mv delivery_manifest.json FAILURE_REPORT.md .incident_archive_20260729/ 2>/dev/null
```

| WP | 动作 |
|---|---|
| DFM-001 | 归档终态文件；删孤儿空目录 T-003/4/5；progress 中**只清孤儿 task 的 attempts**（T-001/T-002 的真实记录保留）；清 last_spawned_action |
| CHP-001 | 同上（T-003 孤儿） |
| INT-001 | 删空孤儿目录 T-001/T-004（F2 部署后 analyze 幽灵自动释放） |
| DFM-003/004 | 归档；删残留空目录；清 progress（全部 task 均未真跑，无真实 attempts 可保留） |

**铁律不变**：有真实产出的目录/MANIFEST 一律不动。

### F5（P2）：worker label 加 WP ID（含 confirm 解析修复）

`wp_runner.py:496`：`f"deliver-worker-{wp_id.lower()}-{task.task_id.lower()}"`

`orchestrator.py:1042` confirm 回滚解析（评审给出的完整实现）：
```python
wp_id_lower = wp_id.lower()
prefix = f"deliver-worker-{wp_id_lower}-"
if label.lower().startswith(prefix):
    tid = label[len(prefix):]
else:  # 向后兼容旧格式
    tid = label.replace("deliver-worker-", "")
```
（评审发现：不修复此处则 matched 永远为空 → 回滚静默失效 + 失败目录不清理）

---

## 3. 泛化审计 V2

### 3.1 自查（本次新增代码）
L1 filter 三道检查的被过滤任务均有归属（产出/真 worker/终态证据），不产生无归属空目录——架构评审复核成立。⚠️ 若未来给 filter 加第四道检查需重新审计（写入代码注释）。

### 3.2 solution_pro Class B 扫描（实施时执行）
grep `pulse.py` 全部 `st_mtime` 使用点，逐个标注"主信号/兜底"：
- 兜底用途（stale lock 等）：可接受，不动
- 主信号用途（用时间判断任务状态）：列入修复
结果写入本方案附录。

### 3.3 spec/ship/research_pro
无调度结构，确认无需行动（V1.0 结论维持）。

### 3.4 泛化口诀 V2（写 MEMORY）
1. 先 mkdir 后决定 = 孤儿温床（副作用必须在最终决策后，或否决路径对称清理 + sweep 兜底）
2. 纯 timeout 释放 = 幽灵名额（时间推断是兜底，文件系统有证据就用证据）
3. attempts=0 的 failed = 冤案（终态转换/终态写入前必须验证执行证据）
4. 资源环路恶化 = 先查 A 和 B，不要单独修 D（涌现问题的归因原则）
5. 终态文件写入 = 不可逆点，写入前的守卫是最后防线（Class E）

---

## 4. 验证方案

### 4.1 单元测试
| 测试 | 内容 |
|---|---|
| `test_budget_zero_no_orphans` | budget=0 后无新增空目录 |
| `test_orphan_sweep_recordless` | 无记录空目录>5min 被扫；有 task_spawned_at 豁免；非空豁免 |
| `test_inflight_evidence_based` | 三类 action 证据存在→不计；不存在→计 |
| `test_cascade_guard_generating` | timed_out(attempts<3) → 不进 ASSEMBLING，走重试 |
| `test_cascade_guard_assembling` | phase 已是 ASSEMBLING 但守卫不满足 → 回退 |
| `test_manifest_write_guard` | zero_attempt 存在 → 拒绝写 delivery_manifest + 告警 |
| `test_manifest_failed_no_deadlock` | MANIFEST-FAILED 任务不触发守卫（防死锁回归） |
| `test_label_wp_roundtrip` | 新 label 格式 confirm 解析正确；旧格式兼容 |
| 回归 | 现有 256 全绿 |

### 4.2 现场验证（手动 pulse 模式，cron 保持暂停）
1. 部署 F1+F2 → 手动 pulse × 3：in_flight = 真实 agent 数（预期首轮即降到 0~2）
2. F4 状态修复 → 手动 pulse：DFM-001 重派 T-003/4/5、INT-001 重派 T-001/2（真 spawn 非孤儿）
3. 部署 F3+F5 → 手动 pulse × 2 确认无异常
4. 恢复 cron → 观察 5 轮：actions vs budget 吻合、无新增孤儿、无 attempts=0 的 failed

### 4.3 独立验证
全部部署后 spawn 独立 Agent（不同模型）grep 证据验证（FixFlow Phase 3 模式）。

---

## 5. 部署顺序与回滚预案（评审新增）

### 部署顺序
```
Step 1: git commit -m "checkpoint before ghost-slot fix"（回滚锚点）
Step 2: 部署 F1+F2 → 手动 pulse × 3 观察（cron 保持暂停）
Step 3: F4 状态修复（归档 → 清理 → 手动 pulse 验证重派）
Step 4: 部署 F3+F5 → 手动 pulse × 2
Step 5: 单测全绿 + 独立验证通过 → 恢复 cron
Step 6: 观察 5 轮 cron pulse + 监控指标
```

### 回滚预案
- 代码：`git checkout <checkpoint>` 即回滚（F1 删除的都是空目录，无需逆操作；F4 归档文件在 `.incident_archive_20260729/` 可手动恢复）
- 若 F2 证据映射有误（analyze 被误判完成）：症状为 in_flight 偏低、并发略超——无害降级，修映射表即可，无需回滚
- 若 F3 守卫误判：症状为 WP 卡在 GENERATING 不进 ASSEMBLING——告警可见，回退 F3 单点即可

### 灰度策略
当前仅一个活跃 project（事故现场本身）→ 手动 pulse 模式即灰度。cron 恢复后首轮即全量，风险已由 Step 2-4 的手动验证覆盖。

---

## 6. 监控指标（评审新增，pulse 报告内嵌）

每轮 pulse 在 report 中增加 `health` 字段：
| 指标 | 告警阈值 | 含义 |
|---|---|---|
| `ghost_delta` = in_flight − 真实 agent 数 | > 2 → WARN | 幽灵残留检测 |
| `new_empty_dirs` | > 0 → WARN | 孤儿复发检测 |
| `zero_attempt_failed` | > 0 → CRITICAL | 冤案检测（F3 应拦截，此为双保险） |

---

## 7. 改动量估算 V2

| 修复 | 改动量 |
|---|---|
| F1a budget=0 清理 | ~2 行 |
| F1b sweep 扩展 | ~15 行 |
| F2 证据化 + 常量 | ~18 行 |
| F3a+b+c 三道守卫 | ~25 行 |
| F5 label + confirm 解析 | ~8 行 |
| 监控 health 字段 | ~15 行 |
| 测试 | ~120 行 |
| **生产代码合计** | **~83 行** |

## 8. 明确不做的事 V2

1. F1c mkdir 纯函数化 → 技术债（附 worker 契约验证清单）
2. action 自声明完成证据 → YAGNI
3. 调 MAX_IN_FLIGHT/MAX_SPAWN 参数 → 调参是掩盖不是修复
4. 事件驱动调度 → 与稳健性无关，另行决策
5. solution_pro 主信号级问题（如扫描发现）→ 另开专项

---

*V1.0 → V2.0：12 项评审意见，11 项采纳（2 项部分采纳），0 项拒绝*
