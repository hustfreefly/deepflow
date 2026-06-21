# 评审：边界场景视角

> **评审对象**: `cron_fix_plan.md` + `cron_watcher.md`
> **评审视角**: 边界场景与失败模式
> **评审时间**: 2026-06-20

---

## 评分：CONDITIONAL

方案对核心问题（channel 误判 + open_id 硬编码）的修复方向正确，Fix 1-4 覆盖了已知 P1-P4。但 5 个边界场景中有 3 个未覆盖或覆盖不足，需要补充后才能达到 PASS。

---

## 逐场景分析

### 场景 1：多 channel 配置（feishu + imessage）

**状态：⚠️ 部分覆盖，存在隐患**

**分析**：
- Fix 1 的分支逻辑：`channel=webchat → 分支A`，`channel=feishu → 分支B`，`其他 → 分支A`
- SKILL.md 选择规则表也写了"其他/不确定 → A"
- **问题**：imessage 会话中启动 Solution Pro 时，`delivery: {"mode": "announce"}` 会走默认 announce。这**可能**能工作（announce 自动路由到当前会话），但方案没有验证这个假设。
- **更深层问题**：如果 imessage 的 announce 路由机制与 webchat 不同（例如需要指定 accountId 或 recipient），默认分支 A 就会静默失败——cron 以为发送成功，但用户收不到。

**建议**：
- 在 pre-flight check 中增加对 imessage channel 的显式测试（创建一个测试 cron 立即触发，验证 imessage announce 是否可达）
- 或者在 SKILL.md 的选择规则表中增加 `imessage → 分支A（已验证）` 或 `imessage → 分支C（特殊配置）`
- **最低要求**：至少记录"imessage 使用默认 announce，未经验证"作为已知风险

---

### 场景 2：Cron 发送失败的恢复（连续失败 N 次）

**状态：❌ 未覆盖**

**分析**：
- Fix 3 只覆盖了"orchestrator 死亡"场景（.stage_progress.json 15 分钟未更新）
- cron_watcher.md 的 Step 1 有 max_runs=20 的超时保护（约 60 分钟）
- **但没有覆盖**：cron 自身的 delivery 连续失败的情况。例如：
  - open_id 错误（本次事故的直接原因）
  - 飞书 API 临时不可用
  - 网络问题
- 当前行为：cron 每 3 分钟跑一次，每次 delivery 失败，但 count 继续累加。直到 20 次（60 分钟）才超时退出。**用户在这 60 分钟内收不到任何通知，也不知道 cron 在持续失败。**

**建议**：
- 在 cron_watcher.md 中增加 `.cron_failure_count` 计数器
- 每次 delivery 失败（exec 返回非 0 或 announce 报错）时递增
- 连续失败 ≥ 3 次 → 发送告警消息（"通知发送连续失败，可能 channel 配置有误"）→ cron 自删
- 这样用户在 9 分钟内（3 次 × 3 分钟）就能发现问题，而不是等 60 分钟

---

### 场景 3：并发运行（两个不同 topic 的管线）

**状态：✅ 基本安全，但有注意事项**

**分析**：
- 每个管线有独立的 `base_path`（如 `.deepflow/runs/solution/{topic_hash}/`）
- `.cron_run_count`、`.notified_stages.json`、`.completed`、`.cron_job_id` 都在各自 base_path 下
- cron job ID 是全局唯一的
- **因此**：两个管线的 cron watcher 不会互相干扰文件系统状态
- **潜在风险**：如果两个管线同时在同一个会话中启动，announce 消息会混在同一个会话流中。用户可能混淆哪个进度属于哪个 topic。但这不是 cron 层面的问题，而是 UX 问题。

**建议**：
- 进度消息中增加 topic 标识（如 `📊 [Topic: K8s迁移] 方案设计进度 (3/10)`）
- 这不是本修复方案的必要范围，但值得记录为后续改进项

---

### 场景 4：Gateway 重启

**状态：❌ 未覆盖**

**分析**：
- Gateway 重启时，运行中的 subagent（orchestrator）会被终止
- **关键问题**：cron job 是否跨 Gateway 重启持久化？
  - 如果 cron 是内存态的（Gateway 重启后丢失）→ 管线静默终止，用户无感知
  - 如果 cron 是持久化的（写入磁盘/数据库）→ cron 继续运行，但 orchestrator 已死 → Fix 3 的 Step 2.5 能在 15 分钟后检测到
- **方案没有讨论 cron 的持久化特性**，也没有 Gateway 重启后的恢复策略

**建议**：
- 在方案中明确声明 cron job 的持久化特性（持久化 or 非持久化）
- 如果是持久化的：Fix 3 的 Step 2.5 已经能兜底（15 分钟后检测 orchestrator 死亡）
- 如果是非持久化的：需要在 SKILL.md 中增加"Gateway 重启后管线需要重新启动"的说明，或者在 Gateway 启动时检查是否有未完成的管线
- **最低要求**：在方案文档中记录这个已知行为，无论是否在本次修复中解决

---

### 场景 5：用户中途切换 channel

**状态：❌ 未覆盖**

**分析**：
- cron 的 delivery 配置在**创建时确定**，之后不可更改
- 用户在 webchat 启动管线 → cron delivery = `{"mode": "announce"}`（路由到 webchat）
- 用户切到飞书继续聊 → cron 通知仍然发到 webchat
- **用户感知**：在飞书上等不到进度更新，以为管线挂了

**根因**：delivery 是 cron job 的静态配置，绑定的是创建时的 channel context，不是运行时的。

**建议**：
- **方案 A（简单）**：在 SKILL.md 中明确告知用户"管线启动后不要切换 channel，否则通知可能送不到"
- **方案 B（健壮）**：cron_watcher 每次运行时检查当前活跃会话的 channel，如果发现与创建时不同，输出告警消息提醒用户回到原 channel 查看通知
- **方案 C（最优但复杂）**：不使用 cron 的静态 delivery，而是让 cron_watcher 在输出中指定动态 delivery（如果 OpenClaw cron 支持）
- **推荐**：先做方案 A（文档说明），后续迭代方案 B

---

## 遗漏的边界场景

### 遗漏 1：base_path 包含特殊字符

如果 topic 名称包含空格、中文、引号等特殊字符，cron_watcher 中的 `exec` 命令（如 `test -f {base_path}/.completed`）可能失败。方案未提及 base_path 的转义/校验。

### 遗漏 2：磁盘满 / 文件写入失败

cron_watcher 需要 write `.cron_run_count` 和 `.notified_stages.json`。如果磁盘满，写入失败，cron 会报错但不会优雅处理。

### 遗漏 3：.cron_preflight.json 被误删或损坏

Fix 2 引入了 `.cron_preflight.json` 作为 pre-flight check 的产物。如果这个文件被外部因素删除或损坏，后续流程没有处理。

### 遗漏 4：时区问题

cron_watcher 中的 `run_start_at` 是 ISO 格式时间。如果 Gateway 系统时区与飞书用户时区不同，超时计算可能不准确。当前方案假设所有时间戳使用同一时区，但未显式声明。

---

## 改进建议

| 优先级 | 建议 | 对应场景 |
|:---|:---|:---|
| 🔴 P0 | 增加 cron delivery 连续失败计数器（≥3次自删+告警） | 场景 2 |
| 🔴 P0 | 明确声明 cron 持久化特性及 Gateway 重启行为 | 场景 4 |
| 🟡 P1 | imessage channel 显式验证或标记为已知风险 | 场景 1 |
| 🟡 P1 | 进度消息增加 topic 标识 | 场景 3 |
| 🟡 P1 | 文档说明"启动后不要切换 channel" | 场景 5 |
| 🟢 P2 | base_path 特殊字符校验 | 遗漏 1 |
| 🟢 P2 | 时区声明（统一 UTC 或 Asia/Shanghai） | 遗漏 4 |

---

## 最核心的一个建议

**增加 cron delivery 连续失败保护（circuit breaker）。**

理由：本次事故的根因就是 delivery 失败（错误的 open_id），但 cron 没有自我检测失败的能力，继续空跑了 2 次才被用户发现。Fix 3 解决了"orchestrator 死了 cron 还跑"的问题，但没有解决"cron 自己发不出去还继续跑"的问题。这是同一类失败模式的另一个面。

具体实现：cron_watcher.md 增加 `.cron_consecutive_failures` 计数器，每次消息输出失败时 +1，成功时归零。达到 3 次连续失败 → 输出最终告警（"通知发送连续失败，请检查 channel 配置"）→ cron 自删。这样用户在 9 分钟内就能发现问题，而不是等 60 分钟的 max_runs 超时。

---

*评审完成。评分 CONDITIONAL：核心修复方向正确，但场景 2（连续失败恢复）和场景 4（Gateway 重启）需要补充覆盖后方可执行。*
