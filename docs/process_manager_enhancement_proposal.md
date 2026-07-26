# ProcessManager 增强方案（评审稿）

> 目标：极端稳健性，确保 Agent 任务能够执行、有过程监控、正常结束、有 complete

---

## 1. 问题回顾（真实故障案例）

### 1.1 V39 故障（2026-07-26）

**现象**：
- Planning ✅ 完成
- Research ✅ 完成（research_digest.json 160KB）
- Orchestrator 卡死，Summary 未开始

**根因**：
1. Research Module Agent 完成了工作，但**没有调用 mark_completed()**
2. Orchestrator 的 wait_for_module 等待 status=="completed"，但 run record 永远是 "running"
3. Orchestrator prompt **没有 stall/timeout 处理分支**

### 1.2 V40 故障（2026-07-26）

**现象**：
- Planning Module Agent spawn 后立即失败
- 报错：`planning_module_prompt.md not found`

**根因**：
1. spawn task 中使用了相对路径 `stages/planning_module_prompt.md`
2. Module Agent 不知道 blackboard 的绝对路径
3. **路径问题反复出现**（V39 也是同样问题）

### 1.3 共性问题

| 问题 | 根因 | 当前状态 |
|------|------|----------|
| mark_completed 没调用 | Phase 2 只有"任务完成"措辞，没有强制调用 | ✅ 已修复（prompt 层面）|
| stall/timeout 无处理 | Orchestrator prompt 缺少分支 | ✅ 已修复（prompt 层面）|
| 路径问题 | spawn task 缺少绝对路径 | ✅ 已修复（PathManager）|
| 输出格式不对 | Planner 输出 Markdown 而非 JSON | ✅ 已修复（prompt 层面）|

**关键洞察**：这些问题都是**prompt 层面修复**，但 prompt 修复不可靠（LLM 可能不遵守）。需要**代码层面强制**。

---

## 2. 当前 ProcessManager 分析

### 2.1 现有能力

| 组件 | 能力 | 局限 |
|------|------|------|
| `ProcessManager` | wait_for（阻塞等待文件）| 只检查文件存在，不验证内容 |
| `ModuleLifecycleManager` | try_acquire_run / heartbeat / mark_completed / wait_for_module | 依赖 Agent 主动调用 |

### 2.2 关键缺陷

**缺陷 1：mark_completed 是"建议性"的，不是"强制性"的**
- 当前：Module Agent 在 prompt 中被要求调用 mark_completed
- 问题：LLM 可能不调用（V39 故障）
- 修复方向：**代码层面强制**，不依赖 prompt

**缺陷 2：完成判定依赖单一信号**
- 当前：wait_for_module 检查 run record status == "completed"
- 问题：如果 Agent 没调用 mark_completed，永远等不到
- 修复方向：**多信号验证**（run record + 完成标记文件 + 输出文件）

**缺陷 3：stall 检测只有心跳超时**
- 当前：心跳 > 30 分钟 = stall
- 问题：Agent 可能还在工作但没发心跳（网络问题、Agent 卡住）
- 修复方向：**多信号 stall 检测**（心跳 + 文件 mtime + 子 Agent 状态）

**缺陷 4：输出验证只检查文件存在**
- 当前：expected_files 存在 = 完成
- 问题：文件可能存在但内容无效（空文件、格式错误）
- 修复方向：**输出内容验证**（大小、格式、schema）

---

## 3. 增强方案

### 3.1 核心原则

1. **代码强制 > Prompt 约定**：关键行为用代码强制，不依赖 LLM 遵守
2. **多信号验证 > 单一信号**：不依赖单一信号判断完成/stall
3. **确定性 > 灵活性**：过程管理用确定性代码，LLM 只做语义判断
4. **零删除 > 可恢复**：不删除任何文件，只新增，支持恢复

### 3.2 增强点 1：CompletionVerifier（完成验证器）

**问题**：mark_completed 是建议性的，Agent 可能不调用

**方案**：代码层面自动检测完成，不依赖 Agent 调用

```python
class CompletionVerifier:
    """
    多信号完成验证器
    
    完成判定（满足任一即可）：
    1. run record status == "completed"（Agent 调用了 mark_completed）
    2. .{module}_completed.json 存在（Agent 写了完成标记）
    3. 所有 output_files 存在且有效（文件层面完成）
    """
    
    def verify_completion(
        self,
        module: str,
        expected_files: list[str],
        min_file_sizes: dict[str, int] | None = None,
        validate_schema: dict[str, str] | None = None,
    ) -> CompletionResult:
        """
        验证模块是否完成
        
        Returns:
            CompletionResult:
                - completed: bool
                - signals: dict（各信号状态）
                - confidence: float（0-1，综合置信度）
        """
        signals = {}
        
        # 信号 1: run record status
        record = self._read_run(module)
        signals["run_record"] = record and record.get("status") == "completed"
        
        # 信号 2: 完成标记文件
        marker = self.session_dir / "stages" / f".{module}_completed.json"
        signals["completion_marker"] = marker.exists()
        
        # 信号 3: 输出文件存在且有效
        signals["output_files"] = self._verify_output_files(
            expected_files, min_file_sizes, validate_schema
        )
        
        # 综合判断
        completed = any(signals.values())
        confidence = sum(signals.values()) / len(signals)
        
        return CompletionResult(
            completed=completed,
            signals=signals,
            confidence=confidence,
        )
```

**关键设计**：
- 不依赖单一信号
- 多信号交叉验证
- 输出置信度供 LLM 判断

### 3.3 增强点 2：MultiSignalStallDetector（多信号 stall 检测）

**问题**：心跳超时是唯一 stall 信号，不够稳健

**方案**：多信号 stall 检测

```python
class MultiSignalStallDetector:
    """
    多信号 stall 检测器
    
    stall 判定（满足任一即可）：
    1. 心跳超时（> 30 分钟无心跳）
    2. 输出文件长时间无更新（> 15 分钟无 mtime 变化）
    3. 子 Agent 已退出但完成标记未写
    """
    
    def detect_stall(
        self,
        module: str,
        expected_files: list[str],
        heartbeat_threshold: int = 1800,
        file_mtime_threshold: int = 900,
    ) -> StallResult:
        """
        检测是否 stall
        
        Returns:
            StallResult:
                - stalled: bool
                - reasons: list[str]（stall 原因）
                - evidence: dict（证据）
        """
        reasons = []
        evidence = {}
        
        # 信号 1: 心跳超时
        record = self._read_run(module)
        if record and record.get("status") == "running":
            last_hb = record.get("last_heartbeat", 0)
            age = time.time() - last_hb
            evidence["heartbeat_age"] = age
            if age > heartbeat_threshold:
                reasons.append(f"heartbeat_timeout: {age:.0f}s")
        
        # 信号 2: 输出文件无更新
        for fname in expected_files:
            fpath = self.session_dir / fname
            if fpath.exists():
                mtime = fpath.stat().st_mtime
                age = time.time() - mtime
                evidence[f"{fname}_mtime_age"] = age
                if age > file_mtime_threshold:
                    reasons.append(f"file_stale: {fname} age={age:.0f}s")
        
        # 信号 3: 子 Agent 已退出
        # （需要查询 sessions_list，这里简化）
        
        stalled = len(reasons) > 0
        
        return StallResult(
            stalled=stalled,
            reasons=reasons,
            evidence=evidence,
        )
```

### 3.4 增强点 3：OutputValidator（输出验证器）

**问题**：只检查文件存在，不验证内容

**方案**：声明式输出验证

```python
class OutputValidator:
    """
    输出验证器
    
    验证层级：
    L0: 文件存在
    L1: 文件大小合理
    L2: JSON 可解析
    L3: Schema 验证（Pydantic）
    L4: 业务规则验证（LLM 语义判断）
    """
    
    def validate(
        self,
        path: str,
        checks: list[OutputCheck],
    ) -> ValidationResult:
        """
        验证输出文件
        
        Args:
            path: 文件路径（相对 session_dir）
            checks: 验证规则列表
        
        Returns:
            ValidationResult:
                - valid: bool
                - failed_checks: list[str]
        """
        fpath = self.session_dir / path
        
        # L0: 文件存在
        if not fpath.exists():
            return ValidationResult(valid=False, failed_checks=["file_not_found"])
        
        size = fpath.stat().st_size
        
        for check in checks:
            if check.type == "min_size":
                if size < check.value:
                    return ValidationResult(
                        valid=False,
                        failed_checks=[f"size_too_small: {size} < {check.value}"]
                    )
            
            elif check.type == "json_parseable":
                try:
                    json.loads(fpath.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return ValidationResult(
                        valid=False,
                        failed_checks=["json_parse_error"]
                    )
            
            elif check.type == "schema":
                # Pydantic schema 验证
                # ...
                pass
        
        return ValidationResult(valid=True, failed_checks=[])
```

### 3.5 增强点 4：PathManager 集成

**问题**：路径问题反复出现

**方案**：所有路径操作通过 PathManager

```python
# 当前（容易出错）
prompt_path = f"{deepflow_root}/blackboard/{session_id}/stages/planning_prompt.md"

# 增强后（PathManager 统一处理）
pm = PathManager(session_id, domain="solution")
prompt_path = pm.get_prompt_path("planning")
```

**集成点**：
- ProcessManager 内部使用 PathManager
- wait_for_module 使用 PathManager 获取路径
- OutputValidator 使用 PathManager 验证路径

### 3.6 增强点 5：ErrorRecoveryManager（错误恢复管理器）

**问题**：stall/timeout 后没有自动恢复

**方案**：声明式恢复策略

```python
class ErrorRecoveryManager:
    """
    错误恢复管理器
    
    恢复策略（声明式）：
    - stall → respawn（最多 2 次）
    - timeout → fail（不重试）
    - output_invalid → respawn（最多 1 次）
    """
    
    def handle_failure(
        self,
        module: str,
        failure_type: str,  # "stall" | "timeout" | "output_invalid"
        attempt: int,
    ) -> RecoveryAction:
        """
        处理失败
        
        Returns:
            RecoveryAction:
                - action: "respawn" | "fail" | "escalate"
                - reason: str
        """
        max_retries = {
            "stall": 2,
            "output_invalid": 1,
            "timeout": 0,
        }
        
        if attempt < max_retries.get(failure_type, 0):
            return RecoveryAction(
                action="respawn",
                reason=f"{failure_type} attempt={attempt}, will retry",
            )
        else:
            return RecoveryAction(
                action="fail",
                reason=f"{failure_type} max_retries_exceeded",
            )
```

---

## 4. 模块结构（增强后）

```
core/process_manager/
├── __init__.py              # 公开 API
├── manager.py               # ProcessManager 主类（~150 行）
├── lifecycle.py             # ModuleLifecycleManager（~200 行）
├── completion_verifier.py   # 新增：CompletionVerifier（~100 行）
├── stall_detector.py        # 新增：MultiSignalStallDetector（~80 行）
├── output_validator.py      # 新增：OutputValidator（~120 行）
├── error_recovery.py        # 新增：ErrorRecoveryManager（~60 行）
└── contracts.py             # 新增：Pydantic 契约定义（~80 行）

总计：~790 行（仍保持轻量）
```

---

## 5. API 设计（增强后）

### 5.1 Orchestrator 使用方式

```python
from core.process_manager import ProcessManager, CompletionVerifier, StallDetector

pm = ProcessManager(session_dir)
verifier = CompletionVerifier(session_dir)
detector = StallDetector(session_dir)

# spawn 前
run = pm.try_acquire_run("planning")

# spawn Module Agent
sessions_spawn(task=f"...RUN_ID={run.run_id}...")

# 等待完成（增强版）
result = pm.wait_for_module(
    module="planning",
    expected_files=["stages/planning_convergence.json"],
    min_file_sizes={"stages/planning_convergence.json": 10000},
    validate_json=True,
    # 新增参数
    multi_signal_completion=True,  # 多信号完成验证
    stall_detection=True,          # 多信号 stall 检测
    auto_recovery=True,            # 自动恢复
)

if result.found:
    # 完成
    pass
elif result.reason == "stall":
    # stall，自动 respawn
    recovery = pm.handle_failure("planning", "stall", result.attempt)
    if recovery.action == "respawn":
        # 重新 spawn
        pass
elif result.reason == "timeout":
    # 超时，失败
    pass
```

### 5.2 Module Agent 使用方式

```python
from core.process_manager import ModuleLifecycleManager

lifecycle = ModuleLifecycleManager(session_dir)

# 执行工作
# ...

# 完成时（可选，CompletionVerifier 会自动检测）
lifecycle.mark_completed("planning", run_id, output_files={...})
```

---

## 6. 关键设计决策（请重点评审）

**决策 1：多信号完成验证**
- 不依赖单一信号（run record / 完成标记 / 输出文件）
- 任一信号满足即认为完成
- 风险：可能误判完成（文件存在但内容无效）
- 缓解：OutputValidator 验证内容

**决策 2：多信号 stall 检测**
- 心跳超时 + 文件 mtime + 子 Agent 状态
- 任一信号触发即认为 stall
- 风险：可能误判 stall（Agent 还在工作但没更新文件）
- 缓解：阈值可调，默认保守（30 分钟心跳 / 15 分钟文件）

**决策 3：自动恢复**
- stall → respawn（最多 2 次）
- timeout → fail（不重试）
- 风险：无限 respawn 循环
- 缓解：attempt 计数，超过阈值则 fail

**决策 4：PathManager 集成**
- 所有路径操作通过 PathManager
- 风险：增加依赖，PathManager 出错会影响 ProcessManager
- 缓解：PathManager 已有完善测试

---

## 7. 需要评审回答的问题

1. **多信号完成验证**：任一信号满足即认为完成，是否足够稳健？还是需要所有信号都满足？
2. **stall 检测阈值**：心跳 30 分钟 / 文件 15 分钟，是否合理？有没有更好的检测方式？
3. **自动恢复策略**：stall respawn 最多 2 次，是否足够？timeout 不重试是否合理？
4. **OutputValidator 层级**：L0-L4 验证层级是否够用？L4（LLM 语义验证）是否必要？
5. **PathManager 集成**：是否应该将 PathManager 作为 ProcessManager 的依赖？还是保持独立？
6. **代码量**：增强后 ~790 行，是否仍然"轻量"？有没有可以简化的地方？

---

## 8. 实施计划

**Phase 1（P0）**：CompletionVerifier + StallDetector
- 解决 mark_completed 不可靠问题
- 解决 stall 检测不全面问题

**Phase 2（P1）**：OutputValidator
- 解决输出验证不全面问题

**Phase 3（P2）**：ErrorRecoveryManager
- 解决自动恢复问题

**Phase 4（P3）**：PathManager 集成
- 解决路径问题反复出现问题

---

## 9. 测试计划

**单元测试**：
- CompletionVerifier：多信号验证逻辑
- StallDetector：多信号检测逻辑
- OutputValidator：各层级验证逻辑
- ErrorRecoveryManager：恢复策略逻辑

**集成测试**：
- 模拟 Module Agent 不调用 mark_completed，验证 CompletionVerifier 能检测到完成
- 模拟 Module Agent stall，验证 StallDetector 能检测到
- 模拟输出文件无效，验证 OutputValidator 能检测到
- 模拟 stall 后 respawn，验证 ErrorRecoveryManager 能正确处理

**端到端测试**：
- 重跑 V40，验证增强后的 ProcessManager 能正确处理各种故障

---

## 10. 总结

**核心目标**：极端稳健性

**关键增强**：
1. 多信号完成验证（不依赖单一信号）
2. 多信号 stall 检测（心跳 + 文件 + 子 Agent）
3. 输出内容验证（不只是文件存在）
4. 自动恢复（stall → respawn）
5. PathManager 集成（消除路径问题）

**预期效果**：
- V39/V40 类故障不再出现
- Agent 任务能够正常执行、监控、完成
- 过程管理极端稳健
