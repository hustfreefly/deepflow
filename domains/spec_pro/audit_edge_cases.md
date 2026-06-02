# Spec Pro 边界条件与异常恢复审计报告

> 审计日期：2026-06-02 23:31  
> 审计员：边界条件与异常恢复审计员 (subagent)  
> 项目路径：`/Users/allen/.openclaw/workspace/.deepflow/domains/spec_pro/`  
> 审计范围：merge_spec.py, worker_fallback.py, process_guard.py, coordinator.py, spec_pro_api.py, utils.py  

---

## 审计摘要

| 严重性 | 数量 | 说明 |
|:---|:---|:---|
| P0 (Critical) | **3** | 导致崩溃/数据损坏/安全问题的缺陷 |
| P1 (High) | **11** | 导致行为不正确但不会崩溃的缺陷 |
| P2 (Medium) | **3** | 语义不清晰/边界条件处理不完善 |

---

## P0 缺陷

### [P0-1] [P0] [coordinator.py] `_generate_session_id` 使用时间戳 MD5，并发时产生碰撞

**问题描述**  
`_generate_session_id()` 使用 `hashlib.md5(str(time.time()).encode()).hexdigest()[:8]` 生成 session ID。8 个十六进制字符 = 2^32 空间，在快速连续调用（同一秒内）时碰撞率极高。

**复现命令**
```python
import hashlib, time
ids = set()
for i in range(100):
    ts = str(time.time()).encode()
    hash8 = hashlib.md5(ts).hexdigest()[:8]
    ids.add(f'spec_spec_{hash8}')
print(f'{len(ids)} unique IDs out of 100 calls')  # 实际输出: 82 (碰撞 18 次!)
```

**实际行为**：100 次连续调用仅产生 82 个唯一 ID，碰撞率 18%。  
**期望行为**：session ID 应全局唯一。  
**建议修复**：使用 `uuid.uuid4().hex[:16]` 替代 MD5(time.time())。

---

### [P0-2] [P0] [worker_fallback.py / coordinator.py] ParseWorker fallback 不创建 living_spec.json，下游 Worker 读取失败

**问题描述**  
当 ParseWorker 超时时，`worker_fallback.py parse` 只写 `round_01_parse.json`，不创建 `living_spec.json`。但 Orchestrator 的 init 阶段 Step 2 (AssessWorker) 和 Step 3 (QuestionWorker) 都读取 `living_spec.json`，文件不存在会导致 Worker 失败。

**复现场景**  
1. ParseWorker 超时 → fallback 写 `parse.json`
2. Orchestrator 继续执行 Step 2: AssessWorker 读取 `living_spec.json` → **FileNotFoundError**

**实际行为**：后续 Worker 因文件不存在而失败，无 graceful 降级。  
**期望行为**：fallback 应创建一个最小化的 living_spec.json 或 Orchestrator 应在调用后续 Worker 前检测并创建空文件。  
**建议修复**：在 coordinator.py 的 `_init_phase_instructions` Step 1.5 中，当 fallback 被执行后，额外执行创建空 living_spec.json 的逻辑。

---

### [P0-3] [P0] [merge_spec.py / utils.py] 损坏字段类型导致 AttributeError/KeyError 崩溃

**问题描述**  
多个函数假设 living_spec.json 的字段类型正确，当字段被意外修改为非预期类型时直接崩溃：

- `merge_spec.py:merge_confirmed()` — `pain_points` 为字符串时 `AttributeError: 'str' object has no attribute 'append'`
- `merge_spec.py:merge_confirmed()` — `capabilities` 为字符串时 `AttributeError: 'str' object has no attribute 'setdefault'`
- `merge_spec.py:merge_confirmed()` — `integration` 为字符串时 `AttributeError: 'str' object has no attribute 'setdefault'`
- `merge_spec.py:merge_confirmed()` — `constraints` 为字符串时 `TypeError: 'str' object does not support item assignment`
- `utils.py:check_process_guard()` — 轨迹点缺失 `delta` 键时 `KeyError: 'delta'`
- `utils.py:check_process_guard()` — `delta` 为字符串时 `TypeError: '<' not supported between instances of 'str' and 'int'`

**复现命令**
```python
from domains.spec_pro.merge_spec import merge_confirmed
spec = {'confirmed': {'pain_points': 'not a list', ...}}
merge_confirmed(spec, {'pain_points': ['new']})  # → AttributeError
```

**实际行为**：AttributeError / KeyError / TypeError 导致进程崩溃。  
**期望行为**：应检测字段类型异常，重置为默认值或返回错误。  
**建议修复**：
- `merge_confirmed()` 每个 `setdefault()` 前加 `isinstance()` 校验，类型不符则重置
- `utils.py:check_process_guard()` 使用 `.get("delta", 0)` 并校验 `isinstance(delta, (int, float))`

---

## P1 缺陷

### [P1-1] [P1] [merge_spec.py] 空 `parsed_updates={}` 合并仍增加 `conversation_rounds`

**复现**：`merge_spec(response_with_empty_updates, living_spec)` → `status=merged`, `conversation_rounds` 从 0 变为 1。  
**期望**：零变更合并不应增加轮次计数。  
**建议**：merge 前检测 `parsed_updates` 是否为空，空时跳过 meta 更新或标注 `no_changes=true`。

### [P1-2] [P1] [merge_spec.py] 并发 merge 无文件锁保护

**复现**：两个线程同时调用 `merge_spec()` 写入同一 `living_spec.json`。  
**实际**：本次测试中文件未损坏（rounds=2），但存在 lost update 风险——两个写操作可能互相覆盖。  
**建议**：使用 `fcntl.flock(LOCK_EX)` 保护写入，或采用原子写入（写临时文件 + `os.rename`）。

### [P1-3] [P1] [merge_spec.py] `user_directives` 中无效 dimension 被静默接受

**复现**：`{"dimension": "nonexistent_dimension", "directive": "deliberately_omitted"}` → 被合并到 `living_spec.confirmed.user_directives`，无任何警告。下游 AssessWorker 无法识别该维度。  
**建议**：`merge_user_directives()` 添加 dimension 白名单校验（objective, users, capabilities, quality_attributes, constraints, integration, risks），无效值记录 warning。

### [P1-4] [P1] [worker_fallback.py] fallback assess (score=0) 导致负 delta 被 process_guard 检测为"进度过慢"

**复现**：`append_trajectory(..., score=0, ...)` → `delta = 0 - 40 = -40` → process_guard 输出 `第N轮质量提升仅-40分`。  
**问题**：负 delta 语义是"质量回退"，但 error message 说的是"进度过慢"（暗示正增长但不足），语义错误且可能误导 Orchestrator 策略。  
**建议**：`check_progress_rate()` 增加 `delta < 0` 的分支，输出"质量回退"而非"进度过慢"；append_trajectory 对 fallback 点添加 `is_fallback=true` 标记。

### [P1-5] [P1] [worker_fallback.py] append_trajectory 在 quality_report.json 不存在时写入空 `dimension_scores`

**复现**：只有 fallback assess 无 quality_report.json → `dimension_scores={}` → 写入轨迹。  
**问题**：空 dimension_scores 导致 process_guard 的 `check_conversation_balance` 跳过（`len(dim_scores)<2`），后续分析丢失该轮维度信息。  
**建议**：fallback 时写入默认 dimension_scores 或标记 `is_fallback=true`。

### [P1-6] [P1] [coordinator.py] `safety_stop` 后仍可无限调用 `build_next_round_task`

**复现**：mode=quick (max_rounds=5)，连续调用 build_next_round_task 7 次。第 6 次返回 safety_stop，第 7 次继续增加 current_round 并返回新 task。  
**期望**：safety_stop 后应阻止后续调用。  
**建议**：`build_next_round_task()` 开头检查 `self.state == DialogState.KILLED`，若是则 raise RuntimeError。

### [P1-7] [P1] [spec_pro_api.py] `load_coord_state` 未处理 coord_state.json JSON 损坏

**复现**：coord_state.json 内容为 `{ broken` → `json.load()` 抛出 `JSONDecodeError`，未被捕获。  
**建议**：`load_coord_state()` 添加 `try/except json.JSONDecodeError`，转换为 `ValueError("Corrupted state file: ...")`。

### [P1-8] [P1] [spec_pro_api.py] `cmd_confirm` 未处理无效 revisions JSON

**复现**：`spec_pro_api.py confirm <session_id> revise "not valid json"` → `json.loads()` 抛出 `JSONDecodeError` 未被捕获，主进程收到未格式化的 traceback。  
**建议**：`cmd_confirm()` 中 `json.loads(args.revisions)` 加 try/except，返回 `{"success": false, "error": "Invalid revisions JSON: ..."}`.

### [P1-9] [P1] [merge_spec.py] `apply_revisions` 对未知 dimension/field 静默接受

**复现**：`apply_revisions()` 中 `dimension='unknown_type', field='something'` → revisions_applied=1，但无任何字段被更新。  
**期望**：应记录 warning 或返回部分成功状态。  
**建议**：返回 `{"status": "revised", "revisions_applied": 0, "revisions_skipped": 1, "warnings": [...]}`.

### [P1-10] [P1] [spec_pro_api.py] `load_coord_state` 在 blackboard 目录不存在时抛 FileNotFoundError

**复现**：blackboard 目录被删除后调用 `load_coord_state(session_id)` → `os.listdir(blackboard_dir)` 抛出 `FileNotFoundError` 而非友好的 `ValueError`。  
**建议**：`load_coord_state()` 开头检查 `os.path.exists(blackboard_dir)`，不存在则 `raise ValueError("Blackboard directory not found")`.

### [P1-11] [P1] [merge_spec.py] `apply_revisions` 对 `dimension='inferred'` 且 field 不存在于 inferred 列表中的修订静默跳过

**复现**：`{"dimension": "inferred", "field": "nonexistent_id", "new_value": "x"}` → revisions_applied=1，但 inferred 列表不变。  
**问题**：用户以为修订已应用，实际上被静默忽略。  
**建议**：返回 `revisions_applied` 和 `revisions_skipped` 计数，或在 inferred 未找到时添加 warning。

---

## P2 缺陷

### [P2-1] [P2] [process_guard.py] 负 delta 的错误消息语义不准确

**复现**：`delta=-15` → 输出 `第2轮质量提升仅-15分，预期8-15分，进度过慢`。  
**问题**：说"质量提升仅-15分"语义混乱（-15 不是提升），且归因为"进度过慢"而非"质量回退"。  
**建议**：`delta < 0` 时使用独立分支：`第N轮质量回退{abs(delta)}分（异常）`.

### [P2-2] [P2] [utils.py / worker_fallback.py] NaN/Infinity 分数可被序列化但产生非标准 JSON

**复现**：`cmd_append_trajectory(..., score=float('nan'), ...)` → 输出包含 `NaN` 的 JSON 文件，标准 JSON 解析器无法读取。  
**建议**：`json.dump()` 使用 `allow_nan=False` 或在写入前校验 `math.isfinite(score)`。

### [P2-3] [P2] [coordinator.py] `build_confirmation_task` 接受空 dict 或 `action=None`

**复现**：`build_confirmation_task({})` → 正常生成 task prompt。`user_confirmation.get("action")` 返回 None，state 被设为 `REVISING`（因为 `None != 'confirm'`）。  
**建议**：校验 `action` 字段必须在 `['confirm', 'revise']` 中。

---

## 修复优先级建议

| 优先级 | 缺陷 | 修复复杂度 | 影响面 |
|:---|:---|:---|:---|
| 1 | P0-3: 崩溃缺陷 | 低 (加类型校验) | 所有 merge 操作 |
| 2 | P0-1: session ID 碰撞 | 低 (换 uuid4) | 并发 init |
| 3 | P0-2: fallback 不创建 living_spec | 中 (改 Orchestrator 流程) | ParseWorker 超时场景 |
| 4 | P1-6: safety_stop 后仍可调用 | 低 (加状态检查) | 所有流程 |
| 5 | P1-7/8: API 未处理 JSON 错误 | 低 (加 try/except) | API 调用路径 |
| 6 | P1-2: 并发 merge 无锁 | 中 (加文件锁) | 并发场景 |
| 7 | 其余 P1/P2 | 低 | 边缘场景 |

---

*审计完成。共发现 17 个问题（3 P0 + 11 P1 + 3 P2）。*
