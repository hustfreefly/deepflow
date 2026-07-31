# Deliver Pro 系统性修复方案

> 整合：INVESTIGATION-001（消息队列阻塞）+ 四专家复盘报告
> 日期：2026-07-31
> 状态：待审批

---

## 一、问题全景图

### 1.1 问题关联网络

```
                    ┌─────────────────────────────────┐
                    │  根因 A：Pulse 没有独立调度       │
                    │  （最高杠杆修复点）                │
                    └─────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ↓                       ↓                       ↓
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│ INVESTIGATION-001 │   │ 复盘 P0-2         │   │ 复盘 P0-3         │
│ 消息队列阻塞      │   │ 告警静默失效      │   │ 调度空窗          │
│ 用户无法发消息    │   │ 4个WP卡6h无告警   │   │ 吞吐衰减          │
└───────────────────┘   └───────────────────┘   └───────────────────┘

                    ┌─────────────────────────────────┐
                    │  根因 B：状态文件假设恒好         │
                    └─────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ↓                       ↓                       ↓
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│ 复盘 H1-H3        │   │ 复盘 M2-M8        │   │ 状态双写漂移      │
│ LLM输出无校验     │   │ 裸json.loads      │   │ 27/28不一致       │
│ 静默吞异常        │   │ 契约未强制        │   │ 终态枚举混乱      │
└───────────────────┘   └───────────────────┘   └───────────────────┘

                    ┌─────────────────────────────────┐
                    │  根因 C：生成端问题（对抗审查发现）│
                    └─────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ↓                               ↓
        ┌───────────────────┐           ┌───────────────────┐
        │ LLM 输出损坏      │           │ 损坏率未度量      │
        │ max_tokens截断    │           │ 无基线数据        │
        │ 无结构化输出      │           │ 无法验证修复效果  │
        └───────────────────┘           └───────────────────┘
```

### 1.2 问题清单（按根因分组）

| 根因 | 问题 | 来源 | 严重度 |
|------|------|------|:------:|
| **A: Pulse 无独立调度** | 消息队列阻塞 | INVESTIGATION-001 | 🔴 |
| | 告警静默失效 | 复盘 P0-2 | 🔴 |
| | 调度空窗 | 复盘 P0-3 | 🔴 |
| | STALLED 判定错误 | 复盘 P0-2 | 🔴 |
| **B: 状态文件假设恒好** | MANIFEST 损坏静默跳过 | 复盘 H1 | 🔴 |
| | batch_progress 全损 | 复盘 H2 | 🔴 |
| | 无限回退循环 | 复盘 H3 | 🔴 |
| | 裸 json.loads | 复盘 M2-M8 | 🟡 |
| | 状态双写漂移 | 复盘 | 🟡 |
| | 异常分类过粗 | 复盘 M7, L2 | 🟡 |
| **C: 生成端问题** | LLM 输出损坏 | 对抗审查 | 🔴 |
| | 损坏率未度量 | 对抗审查 | 🟡 |
| | 交付物未验证 | 对抗审查 | 🔴 |

---

## 二、修复策略

### 2.1 核心原则

1. **先修根因，后修症状**：根因 A 的修复同时解决 3 个 P0 问题
2. **先度量，后修复**：先统计损坏率，再决定防御 vs 消除
3. **先止血，后根治**：Phase 1 立即阻止主 agent 同步调用 pulse

### 2.2 修复顺序

```
Phase 0: 度量与验证（30min）
    ↓
Phase 1: 止血 — Pulse 独立调度（3h）  ← 解决根因 A
    ↓
Phase 2: 防御 — SafeJsonLoader 落地（4h）  ← 解决根因 B
    ↓
Phase 3: 根治 — 生成端优化（2h）  ← 解决根因 C
    ↓
Phase 4: 加固 — CI 护栏 + 测试（3h）
```

---

## 三、Phase 详细计划

### Phase 0: 度量与验证（30min）

**目标**：回答对抗审查的核心问题 —— 损坏率是多少？

#### 任务 0.1: 统计损坏率

```bash
# 扫描所有 MANIFEST.json，统计损坏比例
cd /Users/allen/.openclaw/workspace/.deepflow/blackboard/2.5D封装设计团队_MD_V2/deliver_pro

for wp in */; do
    for manifest in $wp/stages/worker_outputs/*/MANIFEST.json; do
        if [ -f "$manifest" ]; then
            python3 -c "import json; json.load(open('$manifest'))" 2>/dev/null
            if [ $? -ne 0 ]; then
                echo "CORRUPTED: $manifest"
            fi
        fi
    done
done
```

**输出**：
- 总 MANIFEST 数量
- 损坏数量
- 损坏率（%）
- 损坏样本（保存为 `.corrupted` 备份）

#### 任务 0.2: 验证交付物完整性

**问题**：28 个交付物是否真正完整？

**方法**：
1. 检查每个 WP 的 `final_deliverable` 是否存在
2. 检查 `delivery_manifest.json` 是否与实际文件匹配
3. 抽样验证 3-5 个 WP 的内容质量

**输出**：
- 完整交付物列表
- 可疑交付物列表
- 是否需要重新生成

#### 任务 0.3: 决策点

根据损坏率决定后续策略：

| 损坏率 | 策略 | 理由 |
|:------:|------|------|
| < 5% | 防御为主 | 损坏是边缘场景，SafeJsonLoader 足够 |
| 5-20% | 防御 + 消除 | 损坏较频繁，需要优化生成端 |
| > 20% | 消除为主 | 损坏是常态，防御只是掩盖问题 |

---

### Phase 1: 止血 — Pulse 独立调度（3h）

**目标**：解决根因 A，同时修复 INVESTIGATION-001 + 复盘 P0-2 + P0-3

#### 任务 1.1: 代码护栏（1h）

**修改文件**：`domains/deliver_pro/pulse_cli.py`

```python
def cmd_pulse(args) -> int:
    # 检测是否在主 agent 中运行
    session_id = os.environ.get("OPENCLAW_SESSION_ID", "")
    if "main" in session_id.lower():
        print("ERROR: pulse 不应在主 agent 中同步执行", file=sys.stderr)
        print("请使用 cron + isolated session 模式", file=sys.stderr)
        print("或添加 --async 参数使用异步模式", file=sys.stderr)
        return 10  # 特殊退出码
    
    # 写心跳
    heartbeat_path = BLACKBOARD_ROOT / args.project / "_pulse_heartbeat.json"
    atomic_write_json(heartbeat_path, {
        "timestamp": time.time(),
        "pid": os.getpid(),
        "session_id": session_id
    })
    
    # 原有逻辑
    orch = _load_orchestrator(args.project)
    report = orch.pulse()
    ...
```

**更新文档**：
- `AGENTS.md`：明确禁止主 agent 同步调用 pulse
- `SKILL.md`：说明正确的调用方式

#### 任务 1.2: launchd 配置（1h）

**创建文件**：`~/Library/LaunchAgents/ai.openclaw.deliver-pro-pulse.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.openclaw.deliver-pro-pulse</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>-m</string>
        <string>domains.deliver_pro.pulse_cli</string>
        <string>pulse</string>
        <string>--project</string>
        <string>2.5D封装设计团队_MD_V2</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/allen/.openclaw/workspace/.deepflow</string>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>StandardOutPath</key>
    <string>/tmp/deliver-pro-pulse.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/deliver-pro-pulse.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OPENCLAW_SESSION_ID</key>
        <string>cron-pulse</string>
    </dict>
</dict>
</plist>
```

**加载并验证**：
```bash
launchctl load ~/Library/LaunchAgents/ai.openclaw.deliver-pro-pulse.plist
launchctl list | grep deliver-pro-pulse
tail -f /tmp/deliver-pro-pulse.log
```

#### 任务 1.3: STALLED 判定修正（0.5h）

**修改文件**：`domains/deliver_pro/orchestrator.py`

**当前逻辑**（错误）：
```python
if n_spawn_actions == 0 and signature == last_sig:
    state["zero_progress_count"] += 1
elif n_spawn_actions > 0:
    state["zero_progress_count"] = 0  # 有 spawn 就归零
```

**修正逻辑**：
```python
# 检查是否有新完成（completed + terminal_failed 变化）
completed_now = status["completed"] + status["terminal_failed"]
completed_before = state.get("last_completed_count", 0)

# 检查是否有新产出文件（MANIFEST mtime 更新）
new_evidence = self._check_new_evidence_files()

if completed_now == completed_before and not new_evidence:
    # 真正无进展
    state["zero_progress_count"] += 1
else:
    # 有进展（完成或新产出）
    state["zero_progress_count"] = 0

state["last_completed_count"] = completed_now
```

#### 任务 1.4: per-WP dwell-time 监控（0.5h）

**修改文件**：`domains/deliver_pro/orchestrator.py`

**新增方法**：
```python
def _check_wp_dwell_time(self) -> list[dict]:
    """检查每个 WP 在当前 phase 的停留时间"""
    alerts = []
    now = time.time()
    
    for wp_id in self._all_wp_ids():
        phase = self._get_wp_phase(wp_id)
        entered_at = self._get_wp_phase_entered_at(wp_id)
        
        if entered_at is None:
            continue
        
        dwell_seconds = now - entered_at
        dwell_hours = dwell_seconds / 3600
        
        if phase == "PACKAGING" and dwell_hours > 6:
            alerts.append({
                "severity": "CRITICAL",
                "code": "WP_DWELL_CRITICAL",
                "wp_id": wp_id,
                "phase": phase,
                "dwell_hours": round(dwell_hours, 1),
                "message": f"{wp_id} 卡在 {phase} {dwell_hours:.1f} 小时"
            })
        elif phase == "PACKAGING" and dwell_hours > 2:
            alerts.append({
                "severity": "WARN",
                "code": "WP_DWELL_WARN",
                "wp_id": wp_id,
                "phase": phase,
                "dwell_hours": round(dwell_hours, 1),
                "message": f"{wp_id} 卡在 {phase} {dwell_hours:.1f} 小时"
            })
    
    return alerts
```

**集成到 pulse()**：
```python
def pulse(self) -> dict:
    ...
    # 检查 dwell time
    dwell_alerts = self._check_wp_dwell_time()
    alerts.extend(dwell_alerts)
    ...
```

#### 任务 1.5: 告警推送通道（0.5h）

**修改文件**：`domains/deliver_pro/pulse_cli.py`

```python
def cmd_pulse(args) -> int:
    ...
    report = orch.pulse()
    
    # 检查是否有告警
    alerts = report.get("alerts", [])
    if alerts:
        # 发送飞书消息
        critical_alerts = [a for a in alerts if a.get("severity") == "CRITICAL"]
        if critical_alerts:
            self._send_feishu_alert(critical_alerts)
    
    ...

def _send_feishu_alert(self, alerts: list[dict]):
    """发送飞书告警"""
    message = "🚨 Deliver Pro 告警\n\n"
    for alert in alerts:
        message += f"- [{alert['code']}] {alert['message']}\n"
    
    # 调用飞书 API
    # ... (复用现有的飞书消息发送逻辑)
```

#### Phase 1 验收标准

| 验收项 | 标准 | 验证方法 |
|--------|------|----------|
| 主 agent 不被阻塞 | 用户消息 <5 秒响应 | 手动测试 |
| Pulse 独立运行 | cron 每 5 分钟触发 | 查看日志 |
| 心跳正常 | `_pulse_heartbeat.json` 每 5 分钟更新 | 检查文件 |
| STALLED 判定正确 | 重派不重置计数 | 单元测试 |
| dwell-time 告警 | PACKAGING >2h 触发 WARN | 模拟测试 |
| 告警推送 | CRITICAL 告警发飞书 | 模拟测试 |

---

### Phase 2: 防御 — SafeJsonLoader 落地（4h）

**目标**：解决根因 B，修复 H1-H3 + M2-M8

#### 任务 2.1: SafeJsonLoader 完善（1h）

**文件**：`domains/deliver_pro/utils/safe_json_loader.py`

**当前状态**：已实现，但需要验证

**验证清单**：
- [ ] 纯函数（不写合成文件）
- [ ] mtime 宽限（<60s 跳过）
- [ ] 异常三分类（OSError / JSONDecodeError / ValidationError）
- [ ] 备份损坏文件

#### 任务 2.2: 统一替换 json.loads（2h）

**文件列表**：
- `orchestrator.py`: 14 处
- `driver.py`: 5 处
- `wp_runner.py`: 11 处
- `phase_deriver.py`: 1 处

**替换模式**：
```python
# 旧代码
data = json.loads(path.read_text())

# 新代码
result = SafeJsonLoader.load(path, SchemaClass)
if result.state == "ok":
    data = result.data
elif result.state == "invalid_json":
    # 显式降级策略
    logger.error(f"{path} 损坏: {result.error}")
    # 备份 + 告警 + 合成 fallback（如需要）
elif result.state == "schema_validation_failed":
    # 字段缺失/类型错误
    logger.error(f"{path} schema 校验失败: {result.error}")
    # 显式降级策略
```

#### 任务 2.3: 显式降级策略声明（1h）

**每个读取点必须声明**：
```python
# 示例：_filter_spawnable_tasks 中读取 MANIFEST
result = SafeJsonLoader.load(manifest_path, WorkerOutputMeta)

if result.state == "ok":
    # 正常路径
    mdata = result.data
elif result.state in ("invalid_json", "schema_validation_failed"):
    # 显式降级：写合成 FAILED MANIFEST + 告警
    synthetic_manifest = {
        "task_id": task_id,
        "status": "FAILED",
        "failure_class": "output_corrupted",
        "failure_reason": f"MANIFEST corrupted: {result.state}",
        "synthetic": True
    }
    atomic_write_json(manifest_path, synthetic_manifest)
    logger.error(f"{task_id} MANIFEST 损坏，已写合成 FAILED")
    # 不递增 retry counter（这不是 LLM 的错）
```

#### Phase 2 验收标准

| 验收项 | 标准 | 验证方法 |
|--------|------|----------|
| 无裸 json.loads | 所有 LLM 输出读取过 SafeJsonLoader | grep 检查 |
| 降级策略显式 | 每个读取点有明确降级逻辑 | 代码审查 |
| 测试通过 | 现有 361 测试全绿 | pytest |
| 故障注入测试 | 损坏场景测试覆盖 | 新增测试 |

---

### Phase 3: 根治 — 生成端优化（2h）

**目标**：解决根因 C，减少 LLM 输出损坏

#### 任务 3.1: 强制结构化输出（1h）

**问题**：当前只是 prompt 里写"输出 JSON"，没有强制约束

**方案**：使用 OpenAI function calling / JSON mode

```python
# wp_runner.py
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    response_format={"type": "json_object"},  # 强制 JSON 输出
    # 或使用 function calling
    functions=[{
        "name": "output_manifest",
        "parameters": WorkerOutputMeta.schema()
    }],
    function_call={"name": "output_manifest"}
)
```

#### 任务 3.2: validate-and-retry 生成循环（0.5h）

```python
def generate_with_validation(prompt, schema, max_retries=3):
    for attempt in range(max_retries):
        response = client.chat.completions.create(...)
        
        # 尝试解析
        result = SafeJsonLoader.load_from_string(response, schema)
        
        if result.state == "ok":
            return result.data
        
        # 解析失败，重试
        logger.warning(f"Attempt {attempt+1} failed: {result.state}")
        prompt += f"\n\n上次输出格式错误：{result.error}。请重新生成。"
    
    # 所有重试失败
    raise ValueError(f"Failed to generate valid output after {max_retries} attempts")
```

#### 任务 3.3: max_tokens 检查（0.5h）

**问题**：输出被截断是 JSON 损坏的最常见原因

**方案**：
```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    max_tokens=4096,  # 显式设置
)

# 检查是否被截断
if response.choices[0].finish_reason == "length":
    logger.error("Output truncated! Increase max_tokens or reduce output size")
    # 重试或报错
```

#### Phase 3 验收标准

| 验收项 | 标准 | 验证方法 |
|--------|------|----------|
| 结构化输出 | 所有 LLM 输出强制 JSON | 代码审查 |
| validate-and-retry | 解析失败自动重试 | 模拟测试 |
| max_tokens 检查 | 截断时立即报错 | 模拟测试 |
| 损坏率下降 | 损坏率 < 5% | 统计对比 |

---

### Phase 4: 加固 — CI 护栏 + 测试（3h）

**目标**：防止同类问题复发

#### 任务 4.1: CI 静态护栏（1h）

**新增检查**：
```bash
#!/bin/bash
# ci-checks.sh

# 1. 禁止裸 except
if grep -r "except:" --include="*.py" domains/deliver_pro/; then
    echo "ERROR: 发现裸 except，请使用具体异常类型"
    exit 1
fi

# 2. 禁止 except 内 pass/continue
if grep -rA 1 "except.*:" --include="*.py" domains/deliver_pro/ | grep -E "pass|continue"; then
    echo "ERROR: except 块不能为空，请添加日志或降级逻辑"
    exit 1
fi

# 3. 禁止裸 json.loads（LLM 输出读取）
if grep -r "json.loads" --include="*.py" domains/deliver_pro/ | grep -v "safe_json_loader"; then
    echo "WARNING: 发现裸 json.loads，请确认是否为 LLM 输出读取"
fi

# 4. 重复定义检测
python3 -c "
import ast
import sys

for file in sys.argv[1:]:
    with open(file) as f:
        tree = ast.parse(f.read())
    
    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name in funcs:
                print(f'ERROR: 重复定义函数 {node.name} in {file}')
                sys.exit(1)
            funcs[node.name] = node
" domains/deliver_pro/*.py
```

#### 任务 4.2: 故障注入测试（1.5h）

**新增测试文件**：`tests/test_fault_injection.py`

```python
class TestFaultInjection:
    """故障注入测试：验证降级行为"""
    
    def test_manifest_corrupted_json(self, tmp_path):
        """MANIFEST 是无效 JSON → 合成 FAILED + 告警"""
        manifest_path = tmp_path / "MANIFEST.json"
        manifest_path.write_text("{invalid json")
        
        result = SafeJsonLoader.load(manifest_path, WorkerOutputMeta)
        assert result.state == "invalid_json"
        
        # 验证降级行为
        # ...
    
    def test_manifest_schema_mismatch(self, tmp_path):
        """MANIFEST 字段缺失 → 显式降级"""
        manifest_path = tmp_path / "MANIFEST.json"
        manifest_path.write_text('{"task_id": "T-001"}')  # 缺 status
        
        result = SafeJsonLoader.load(manifest_path, WorkerOutputMeta)
        assert result.state == "schema_validation_failed"
        
        # 验证降级行为
        # ...
    
    def test_batch_progress_corrupted(self, tmp_path):
        """batch_progress 损坏 → 从文件证据重建"""
        progress_path = tmp_path / "batch_progress.json"
        progress_path.write_text("{corrupted")
        
        orch = DeliverOrchestrator("test_project")
        # 验证重建逻辑
        # ...
    
    def test_pulse_state_corrupted(self, tmp_path):
        """_pulse_state 损坏 → 保守重建"""
        state_path = tmp_path / "_pulse_state.json"
        state_path.write_text("{corrupted")
        
        # 验证 zero_progress_count 设为阈值-1
        # ...
```

#### 任务 4.3: 不变量测试（0.5h）

```python
class TestInvariants:
    """不变量测试：验证系统状态一致性"""
    
    def test_state_consistency(self):
        """batch_progress 与 delivery_state 一致"""
        orch = DeliverOrchestrator("test_project")
        
        for wp_id in orch._all_wp_ids():
            progress_phase = orch.progress[wp_id]["phase"]
            delivery_state = orch._read_delivery_state(wp_id)
            
            assert progress_phase == delivery_state["phase"], \
                f"{wp_id} 状态不一致: progress={progress_phase}, delivery={delivery_state['phase']}"
    
    def test_pulse_tick_invariant(self):
        """pulse tick 后所有状态文件仍可解析"""
        orch = DeliverOrchestrator("test_project")
        orch.pulse()
        
        # 验证所有状态文件可解析
        for path in orch._all_state_files():
            result = SafeJsonLoader.load(path, ...)
            assert result.state == "ok", f"{path} 不可解析: {result.state}"
```

#### Phase 4 验收标准

| 验收项 | 标准 | 验证方法 |
|--------|------|----------|
| CI 护栏 | 禁止裸 except / 重复定义 | CI 运行 |
| 故障注入测试 | 损坏场景全覆盖 | pytest |
| 不变量测试 | 状态一致性验证 | pytest |
| 测试覆盖率 | > 80% | coverage.py |

---

## 四、实施时间表

| Phase | 任务 | 工作量 | 依赖 | 风险 |
|-------|------|:------:|------|:----:|
| **Phase 0** | 度量与验证 | 0.5h | 无 | 🟢 低 |
| **Phase 1** | Pulse 独立调度 | 3h | Phase 0 | 🟡 中 |
| **Phase 2** | SafeJsonLoader 落地 | 4h | Phase 1 | 🟡 中 |
| **Phase 3** | 生成端优化 | 2h | Phase 2 | 🟢 低 |
| **Phase 4** | CI 护栏 + 测试 | 3h | Phase 2 | 🟢 低 |
| **总计** | | **12.5h** | | |

### 关键里程碑

| 时间点 | 里程碑 | 验收标准 |
|--------|--------|----------|
| T+0.5h | Phase 0 完成 | 损坏率已知，交付物验证完成 |
| T+3.5h | Phase 1 完成 | 消息队列不再阻塞，告警正常 |
| T+7.5h | Phase 2 完成 | SafeJsonLoader 全覆盖，测试通过 |
| T+9.5h | Phase 3 完成 | 生成端优化，损坏率下降 |
| T+12.5h | Phase 4 完成 | CI 护栏 + 测试覆盖 |

---

## 五、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|----------|
| Phase 1 引入新问题 | 中 | 高 | 先在测试环境验证，灰度发布 |
| SafeJsonLoader 替换遗漏 | 中 | 中 | grep 检查 + 代码审查 |
| 生成端优化效果不佳 | 低 | 中 | 保留防御层作为兜底 |
| 测试覆盖不足 | 中 | 中 | 故障注入测试 + 不变量测试 |

---

## 六、总结

### 核心洞察

1. **INVESTIGATION-001（消息队列阻塞）与复盘 P0-2/P0-3 共享同一根因**：Pulse 没有独立调度
2. **修复根因 A 同时解决 3 个 P0 问题**：这是最高杠杆的修复点
3. **对抗审查的核心问题**：28 个交付物是否真正完整？需要先验证再修复
4. **生成端是根因**：防御是症状管理，消除损坏源才是根治

### 修复策略

1. **先度量**：统计损坏率，决定防御 vs 消除
2. **先止血**：Pulse 独立调度，解决消息队列阻塞
3. **后防御**：SafeJsonLoader 落地，显式降级策略
4. **再根治**：生成端优化，减少损坏
5. **最后加固**：CI 护栏 + 测试覆盖

### 预期效果

| 指标 | 当前 | 目标 |
|------|------|------|
| 消息响应延迟 | 30-60 秒 | <5 秒 |
| 告警覆盖率 | 0%（Pulse 不跑） | 100% |
| 损坏率 | 未知 | < 5% |
| 状态一致性 | 27/28 不一致 | 100% 一致 |
| 测试覆盖率 | ~60% | > 80% |

---

> 方案完成时间：2026-07-31 19:45
> 方案作者：四专家复盘 + INVESTIGATION-001 整合
> 下一步：等待用户审批，开始实施 Phase 0
