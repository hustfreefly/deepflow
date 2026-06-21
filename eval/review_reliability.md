---
review_type: reliability_and_failure_modes
reviewer: 可靠性评审员 (Subagent)
design_doc: pipeline_watcher_v2_design.md
date: 2026-06-20
status: complete
---

# Pipeline Watcher V2 — 可靠性与失败模式评审

---

## 1. Python 脚本的失败模式

### 1.1 并发写状态文件竞争

- **问题**：多个 cron 触发的 isolated session 可能同时运行 `pipeline_watcher.py`，对 `.cron_run_count` / `.notified_stages.json` / `.cron_consecutive_failures` 进行读写，无文件锁保护，导致数据丢失或写入撕裂。
- **严重度**：🔴 必须修
- **修复建议**：
  - 所有状态文件写入使用 `fcntl.flock()` 文件锁（macOS/Linux 均支持），锁粒度为整个 state_dir。
  - 或使用原子写入模式：先写临时文件 `.tmp_xxx`，再 `os.rename()` 覆盖目标文件（POSIX rename 是原子的）。
  - 推荐两者结合：锁保护读-改-写序列，原子 rename 保护单次写入。

### 1.2 JSON 解析异常未处理

- **问题**：设计文档提到脚本读取 JSON 配置和状态文件，但未明确描述当 JSON 文件损坏（被截断、被其他进程写到一半）时的处理逻辑。`json.load()` 会抛 `JSONDecodeError`，如果未被 catch，脚本以 exit code 1 崩溃，wrapper prompt 无法解析 stdout JSON。
- **严重度**：🔴 必须修
- **修复建议**：
  - 所有 `json.load()` / `json.loads()` 调用必须包在 `try/except json.JSONDecodeError` 中。
  - 损坏的状态文件 → 视为空/初始状态（如 `.notified_stages.json` 损坏 → 当作空列表，重新通知所有阶段），并在 stderr 输出警告。
  - 损坏的配置文件 → exit code 1 + stderr 明确报错（配置损坏不可恢复，但应给出清晰错误信息）。

### 1.3 脚本 stdout 被非 JSON 内容污染

- **问题**：如果 Python 脚本内部有未预期的 `print()` 语句、warning 输出、或 Python 自身的 deprecation warning 被打印到 stdout，wrapper prompt 要求 LLM "解析 stdout JSON"，混合内容会导致 JSON 解析失败，LLM 可能自行"理解"内容并编造结果。
- **严重度**：🔴 必须修
- **修复建议**：
  - 脚本内所有日志输出走 `sys.stderr`，`sys.stdout` 只用于最终 JSON 输出。
  - 在脚本入口加 `warnings.filterwarnings('ignore')` 或用 `PYTHONWARNINGS=ignore` 环境变量。
  - Wrapper prompt 中增加防御指令："如果 stdout 不是合法 JSON，输出错误消息并 NO_REPLY，不要自行推断。"

---

## 2. Cron 生命周期管理

### 2.1 should_remove_cron 信号丢失

- **问题**：`should_remove_cron=true` 依赖 wrapper prompt 中的 LLM 正确执行 `cron(action="remove")`。如果 LLM 执行到第 3 步（输出消息）后 session 超时（`timeoutSeconds: 60` 耗尽），cron remove 调用永远不会执行，cron 成为孤儿。
- **严重度**：🔴 必须修
- **修复建议**：
  - **方案 A（推荐）**：Python 脚本自己调 cron remove。脚本通过 `--cron-job-id` 参数拿到 cron ID，在输出 timeout/completed/circuit_break 时，脚本内部直接通过 OpenClaw API 或写一个信号文件 `.should_remove_cron` 通知系统清理。但这引入了脚本对 OpenClaw API 的依赖。
  - **方案 B（更实际）**：在 wrapper prompt 中将 `should_remove_cron` 的处理提前到消息输出之前（先 remove，再输出消息）。即使消息输出失败，cron 已被清理。Prompt 改为：
    ```
    3. 如果 should_remove_cron = true → 先执行 cron(action="remove")
    4. 然后根据 action 输出消息或 NO_REPLY
    ```
  - **方案 C（兜底）**：Python 脚本在输出 timeout 后，下一次 cron 触发时 `RunCounter.is_timeout()` 仍为 true，会再次输出 timeout + should_remove_cron。只要有一次 LLM 成功执行 remove，就能清理。但 `timeoutSeconds: 60` 如果每次都耗尽，仍会无限循环。需要配合 `max_runs` 硬上限兜底。
  - **综合建议**：采用 B + C 组合。Prompt 调整顺序 + max_runs 作为终极兜底。

### 2.2 Wrapper prompt 执行超时

- **问题**：`timeoutSeconds: 60` 对于 "exec + 解析 JSON + 输出消息 + 可能调 cron remove" 来说看似充足，但如果 exec 工具本身排队等待（系统繁忙时），或 LLM 响应慢，可能超时。超时后 session 被 kill，消息未推送，cron 未清理。
- **严重度**：🟡 建议修
- **修复建议**：
  - 将 `timeoutSeconds` 提高到 90 或 120（脚本本身 <1s，余量给 LLM 调度）。
  - 在 wrapper prompt 中明确："如果 exec 调用失败，输出 '⚠️ 巡检脚本执行失败' 并 NO_REPLY，不要重试或自行判断。"

### 2.3 Cron 创建后 cron_job_id 回填问题

- **问题**：设计文档 6.1 节提到 `cron_job_id="PLACEHOLDER"` 创建后回填，但未说明回填机制。Wrapper prompt 在 cron 创建时已经作为 payload.message 固化，后续无法修改 prompt 中的 `{cron_job_id}`。LLM 在 isolated session 中不知道自己的 cron_job_id，无法执行 self-remove。
- **严重度**：🔴 必须修
- **修复建议**：
  - **方案 A**：cron 创建 API 返回的 job 对象中包含 `jobId`，可以在创建后将 jobId 写入一个已知路径的文件（如 `{state_dir}/.cron_job_id`），Python 脚本读取该文件获取自己的 cron ID，然后在输出中携带 `cron_job_id_to_remove` 字段，wrapper prompt 用这个字段执行 remove。
  - **方案 B（更简洁）**：cron 创建分两步：先创建（disabled），拿到 jobId，再构造包含真实 jobId 的 wrapper prompt，最后 enable。但这需要 cron API 支持 create-then-enable。
  - **方案 C（最简单）**：Python 脚本不依赖 cron_job_id，而是输出 `should_remove_cron=true` + 当前 cron 的 `name` 字段（通过 `--cron-job-name` 参数传入，创建时已知）。Wrapper prompt 用 name 查找并 remove。
  - **推荐方案 A**：写文件协议，解耦最彻底。

---

## 3. 状态文件一致性

### 3.1 .cron_run_count 读写非原子

- **问题**：RunCounter 的逻辑是 "读文件 → +1 → 写回"。如果两个实例同时读到 N，都写回 N+1，实际运行了 2 次但计数只 +1。对 timeout 判断影响较小（多跑几次而已），但对 `max_runs` 精确性有影响。
- **严重度**：🟡 建议修
- **修复建议**：使用 `fcntl.flock()` 独占锁保护读-改-写序列。锁文件可以用 `.cron_run_count.lock`。

### 3.2 .notified_stages.json 并发写

- **问题**：StageDetector 扫描后需要将新发现的阶段写入 `.notified_stages.json`。如果与另一个实例并发写，可能丢失已通知记录，导致重复通知。
- **严重度**：🟡 建议修（重复通知比丢失通知好，但仍应修复）
- **修复建议**：同 3.1，文件锁保护。或使用原子 append-only 日志格式（每行一个 stage name），用 `O_APPEND` 写入，POSIX 保证 < PIPE_BUF 的 append 是原子的。

### 3.3 .cron_consecutive_failures 与 .cron_run_count 语义混淆

- **问题**：设计中同时有 `.cron_run_count`（总运行次数，用于 timeout）和 `.cron_consecutive_failures`（连续无输出次数，用于 circuit breaker），但文档未明确两者的重置逻辑。如果 circuit breaker 触发后 cron 未被移除，下次运行时 `.cron_consecutive_failures` 是否被重置？如果不重置，circuit breaker 永远触发。
- **严重度**：🟡 建议修
- **修复建议**：在文档中明确：
  - `.cron_consecutive_failures` 在检测到新阶段（有输出）时重置为 0。
  - Circuit breaker 触发时输出 `should_remove_cron=true`，确保 cron 被清理。
  - 如果 cron 未被清理（信号丢失），circuit breaker 持续触发，每次都有输出 → 不算"静默失败"，但会持续推送消息。可接受。

---

## 4. 时间戳校验漏洞

### 4.1 时钟偏移导致误判

- **问题**：`CompletionChecker` 用 `run_start_at`（cron 创建时间）与 `.completed` 文件中的 `completed_at` 比较，防止残留的旧 .completed 文件被误判为本次运行完成。但如果系统时钟被 NTP 回调（`completed_at` 比 `run_start_at` 早几秒），合法完成会被误判为"过期"。
- **严重度**：🟡 建议修
- **修复建议**：
  - 比较时加容差：`completed_at >= run_start_at - 30s`（30 秒容差）。
  - 或使用单调时钟：`run_start_at` 不用 ISO 时间戳，改用 cron 创建时的 `time.monotonic()` 值（但这跨进程不可行）。
  - 实际推荐：`completed_at >= run_start_at - tolerance`，tolerance 可配置，默认 60s。

### 4.2 ISO 格式不兼容

- **问题**：`completed_at` 的 ISO 格式可能带时区（`2026-06-20T13:00:00+08:00`）或不带（`2026-06-20T13:00:00`），Python `datetime.fromisoformat()` 在 3.9 中对带时区的格式支持有限（3.11 才完善）。格式不匹配会导致 `ValueError`。
- **严重度**：🔴 必须修
- **修复建议**：
  - 使用 `dateutil.parser.parse()` 代替 `datetime.fromisoformat()`，兼容性最好。
  - 或在脚本中自定义解析函数，支持多种 ISO 格式变体。
  - 如果不想引入第三方依赖，用 `datetime.fromisoformat()` 但先 strip 时区后缀（`completed_at.replace('+08:00', '').replace('Z', '')`），统一按 naive datetime 比较。

### 4.3 completed_at 字段缺失

- **问题**：`.completed` 文件存在但 JSON 中没有 `completed_at` 字段（旧版管线写入、或写入被中断），`completion.completed_at` 为 None，时间戳校验逻辑会抛 TypeError。
- **严重度**：🔴 必须修
- **修复建议**：
  - `completed_at` 缺失时，视为"无时间戳校验信息"。策略二选一：
    - 保守：视为本次运行完成（文件存在即完成，不校验时间）。适用于 .completed 文件由本次管线的 orchestrator 写入的场景。
    - 激进：视为无效，忽略。适用于担心残留文件的场景。
  - 推荐：缺失时检查文件 mtime（`os.path.getmtime()`）作为 fallback 时间戳，与 `run_start_at` 比较。

---

## 5. Wrapper Prompt 的 LLM 自由度

### 5.1 LLM 可能跳过 exec 直接编造结果

- **问题**：Wrapper prompt 说"解析 stdout JSON"，但如果 exec 调用失败（工具限流、系统繁忙），LLM 可能"好心"自行编造一个 JSON 结果，导致用户收到虚假进度/完成通知。
- **严重度**：🔴 必须修
- **修复建议**：
  - Prompt 中增加显式防御："如果 exec 调用失败或返回非零退出码，**必须**输出以下固定消息并 NO_REPLY：'⚠️ 巡检脚本执行失败，请检查日志'。**禁止**自行构造 JSON 或推断执行结果。"
  - 增加正向示例（few-shot）：给出 exec 失败时的正确处理样例。

### 5.2 LLM 可能"优化"消息格式

- **问题**：Prompt 说"输出 message 字段的文本"，但 LLM 可能认为消息格式不够好，自行修改/美化/翻译，导致输出与脚本生成的不一致。
- **严重度**：🟡 建议修
- **修复建议**：
  - Prompt 中强调："输出 message 字段时，**逐字复制，不做任何修改**。不翻译、不美化、不补充、不删减。"
  - 如果可能，用结构化输出（JSON mode）强制 LLM 只输出 message 字段的原始值。

### 5.3 LLM 可能忽略 should_remove_cron

- **问题**：LLM 可能解析 JSON 后只关注 action 和 message，忽略 should_remove_cron 字段，导致 cron 未被清理。
- **严重度**：🟡 建议修
- **修复建议**：
  - Prompt 中将 should_remove_cron 检查放在 action 处理之前（先清理，再输出）。
  - 增加 few-shot 示例覆盖 should_remove_cron=true 的场景。

### 5.4 10 行 prompt 是否足够

- **问题**：10 行 prompt 覆盖了正常路径，但对异常路径（exec 失败、JSON 解析失败、字段缺失）缺乏指导。LLM 在异常情况下有"自由发挥"空间。
- **严重度**：🟡 建议修
- **修复建议**：
  - 将 prompt 扩展到 ~20 行，增加异常处理指令：
    ```
    5. 如果 exec 失败 → 输出 "⚠️ 巡检脚本执行失败" → NO_REPLY
    6. 如果 stdout 不是合法 JSON → 输出 "⚠️ 巡检输出异常" → NO_REPLY
    7. 如果 JSON 缺少 action 字段 → NO_REPLY
    ```
  - 20 行仍然远少于当前的 120 行，token 开销可忽略。

---

## 6. 其他可靠性问题

### 6.1 脚本依赖 Python 3.9+ 但无版本检查

- **问题**：设计指定 Python 3.9+（系统自带），但如果用户系统 Python 版本过低（如 macOS 自带的 3.8），`datetime.fromisoformat()` 行为不同，`|` 联合类型语法不可用，脚本可能静默产出错误结果。
- **严重度**：🟡 建议修
- **修复建议**：脚本开头加版本检查：
  ```python
  import sys
  if sys.version_info < (3, 9):
      print("Error: Python 3.9+ required", file=sys.stderr)
      sys.exit(1)
  ```

### 6.2 配置文件不存在时的行为

- **问题**：`--config` 指向的 JSON 文件被删除或路径错误，`load_config()` 抛 `FileNotFoundError`，脚本崩溃，stdout 无 JSON 输出。
- **严重度**：🟡 建议修
- **修复建议**：配置文件缺失 → stderr 报错 + exit code 2（区分于脚本错误的 exit code 1）。Wrapper prompt 对 exit code != 0 统一处理为"巡检脚本执行失败"。

### 6.3 base_path 不存在时的行为

- **问题**：管线目录被清理（用户手动删除或磁盘满），`scan_dirs` 中的路径不存在，`glob()` 可能返回空或抛异常。
- **严重度**：🟢 可接受
- **修复建议**：路径不存在 → 视为无新阶段 → 走 circuit breaker 逻辑。在 stderr 输出警告。不应崩溃。

---

## 总体判断

### CONDITIONAL — 有必须修的问题，修后可以开发

**必须修（🔴）共 6 项**：

| # | 问题 | 修复复杂度 |
|---|------|-----------|
| 1.1 | 并发写状态文件无锁 | 中（加文件锁 + 原子写入） |
| 1.2 | JSON 解析异常未处理 | 低（加 try/except） |
| 1.3 | stdout 被非 JSON 内容污染 | 低（stderr 分离 + warning 抑制） |
| 2.1 | should_remove_cron 信号丢失 | 中（调整 prompt 执行顺序 + max_runs 兜底） |
| 2.3 | cron_job_id 回填机制缺失 | 中（需设计文件协议或两步创建） |
| 4.2 | ISO 格式不兼容 | 低（dateutil 或手动 strip） |
| 4.3 | completed_at 字段缺失 | 低（fallback 到 mtime） |
| 5.1 | LLM 跳过 exec 编造结果 | 低（prompt 加异常指令） |

**建议修（🟡）共 8 项**：可在开发过程中逐步修复，不阻塞。

**修复建议优先级**：
1. 先修 1.1 + 1.2 + 1.3（脚本防御性，开发阶段就能解决）
2. 再修 2.1 + 2.3（cron 生命周期，需要设计决策）
3. 最后修 4.2 + 4.3 + 5.1（边界情况 + prompt 完善）

修复上述 🔴 项后，设计可以进入开发阶段。
