# Solution Pro 通用模块完全集成 + P0 修复方案

> 版本：V1.0
> 日期：2026-07-27
> 目标：稳健性、正确性、闭环当前问题
> 状态：待专家评审

---

## 一、问题全景

基于三份审计报告（integration_audit / orchestrator_review / module_agents_review），问题分为三层：

### 层 1：P0 稳健性问题（必须修复）

| # | 问题 | 根因 | 影响 |
|---|------|------|------|
| P0-1 | `.runs/*.run.json` 状态与实际不一致 | `wait_for_module()` 只检查文件不更新状态；依赖 LLM 主动调用 `mark_completed()` | 状态不可信，stall detection 误判 |
| P0-2 | Planning Module 不调用 `mark_completed()` | `planning_module.md` Step 4.4 用 `bm.write_stage('.planning_completed')` 替代 | `.runs/planning.run.json` 永远 running |
| P0-3 | Gateway 重启后 session 丢失，无恢复机制 | Orchestrator session reset 后无法续跑 | 收尾步骤丢失 |

### 层 2：P1 集成不完整（需要补齐）

| # | 问题 | 根因 | 影响 |
|---|------|------|------|
| P1-1 | PromptUtils 在 Agent 层被绕过 | prompt 模板用 `{var}` 单花括号，PromptUtils 用 `{{var}}` 双花括号 | 失去注入检测、大小检查、变量 fail-fast |
| P1-2 | PathManager 类零引用 | 只用了 PathConfig（简单单例），PathManager（完整管理器）未使用 | 路径安全依赖隐式保证 |
| P1-3 | 路径硬编码在 prompt 中 | 字符串插值 `'{deepflow_root}/blackboard/{session_id}'` | 路径变更需改所有 prompt |

### 层 3：P2 架构改进（可选）

| # | 问题 | 根因 | 影响 |
|---|------|------|------|
| P2-1 | 架构版本不一致 | orchestrator V3.2 / master_state v3.1 / module_summary_state v3.3 | 维护混乱 |
| P2-2 | PathConfig vs PathManager 职责重叠 | 两个模块做类似的事 | 死代码 |

---

## 二、修复方案

### 2.1 P0-1：`wait_for_module()` 成功后自动更新 `.runs/` 状态

**设计原则**：代码做确定性行为，不依赖 LLM 主动性。

**修改文件**：`core/process_manager/lifecycle.py`

**修改内容**：在 `wait_for_module()` 返回 `found=True` 之前，自动调用 `mark_completed()`。

```python
# lifecycle.py — wait_for_module() 增强
# 完成判定：输出文件有效 + (run record completed OR 完成标记存在 OR 文件存在)
if files_valid:
    # 🔴 P0 修复：如果文件有效但 run record 未更新，自动更新
    if status != "completed":
        self.mark_completed(module, run_id, output_files=self._get_file_details(expected_files or []))
        completion_source = "auto_update"
    else:
        completion_source = "run_record"
    
    return ModuleWaitResult(found=True, ...)
```

**关键决策**：
- 文件有效 = 模块完成的充分条件（文件是产出物，状态是信号）
- 信号可以丢失/延迟，但产出物不会骗人
- 自动更新状态 = 让代码保证一致性，不依赖 LLM

**风险评估**：
- ✅ 低风险：mark_completed 是幂等的（重复调用不会出错）
- ✅ 向后兼容：如果 Module Agent 已经调用了 mark_completed，auto_update 是 no-op
- ⚠️ 需要注意：`mark_completed` 内部检查 `run_id` 匹配，如果 run_id 不匹配会返回 False

### 2.2 P0-2：修复 Planning Module 的 mark_completed 调用

**修改文件**：`domains/solution_pro/prompts/planning_module.md`

**修改内容**：Step 4.4 从 `bm.write_stage('.planning_completed')` 改为 `lifecycle.mark_completed()`。

```python
# 当前（错误）：
bm.write_stage('.planning_completed', {
    'module': 'planning',
    'status': 'completed',
    ...
})

# 修复后（正确）：
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')
lifecycle.mark_completed('planning', run_id, output_files={
    'stages/planning_convergence.json': {
        'size': os.path.getstat('{deepflow_root}/blackboard/{session_id}/stages/planning_convergence.json').st_size,
        'mtime': os.path.getmtime('{deepflow_root}/blackboard/{session_id}/stages/planning_convergence.json'),
    },
})
# 同时保留 .planning_completed 作为辅助信号（向后兼容）
bm.write_stage('.planning_completed', {...})
```

**同时修复**：在每个 Phase 验证通过后添加 `lifecycle.heartbeat('planning', run_id)`。

### 2.3 P0-3：Gateway 重启后的 zombie 状态恢复

**修改文件**：`core/process_manager/lifecycle.py`

**新增方法**：`recover_zombie_runs()`

```python
def recover_zombie_runs(self, max_age: int = 7200) -> list[str]:
    """
    检测并修复 zombie running 状态。
    
    Zombie 定义：status="running" 但 heartbeat 超过 max_age 秒。
    修复方式：检查输出文件是否存在，存在则 mark_completed，不存在则 mark_failed。
    
    Returns:
        修复的模块名列表
    """
    recovered = []
    for module in ["planning", "research", "summary"]:
        record = self._read_run(module)
        if not record or record.get("status") != "running":
            continue
        
        last_hb = record.get("last_heartbeat", 0)
        age = time.time() - last_hb
        if age < max_age:
            continue
        
        # Zombie 检测：检查输出文件
        expected = self._get_expected_files(module)
        if self._verify_output_files(expected):
            self.mark_completed(module, record["run_id"])
            recovered.append(f"{module}: auto-completed")
        else:
            record["status"] = "failed"
            record["failure_reason"] = "zombie_detected_no_output"
            self._write_run(module, record)
            recovered.append(f"{module}: marked failed")
    
    return recovered
```

**调用时机**：Orchestrator Step 0 初始化时调用。

### 2.4 P1-1：PromptUtils 完全集成

**设计原则**：统一变量语法，所有 prompt 加载通过 `render_prompt()`。

**修改范围**：

| 文件 | 修改点 | 数量 |
|------|--------|------|
| `orchestrator.md` | 6 处 `.read_text()` + `.replace()` → `render_prompt()` | 6 |
| `planning_module.md` | 4 处 → `render_prompt()` | 4 |
| `research_module.md` | 2 处 → `render_prompt()` | 2 |
| `summary_module.md` | 9 处 → `render_prompt()` | 9 |

**变量语法兼容方案**：

PromptUtils `render_prompt()` 已支持双语法：
- `{{variable}}` = 必需变量，缺失 fail-fast
- `{variable}` = 可选变量，缺失保留原文

当前 prompt 模板全部使用 `{variable}` 单花括号 → PromptUtils 会替换提供的变量，未提供的保留原文。

**结论**：不需要修改 prompt 模板语法！只需将 `.read_text()` + `.replace()` 替换为 `render_prompt()` 调用。

**修改示例**（orchestrator.md Step 1a）：

```python
# 当前（手动加载）：
prompt_path = pathlib.Path('domains/solution_pro/prompts/planning_module.md')
prompt = prompt_path.read_text(encoding='utf-8')
prompt = prompt.replace('{session_id}', '{session_id}')
prompt = prompt.replace('{deepflow_root}', '{deepflow_root}')

# 修复后（PromptUtils）：
from core.prompt_utils import render_prompt
result = render_prompt(
    'domains/solution_pro/prompts/planning_module.md',
    session_id='{session_id}',
    deepflow_root='{deepflow_root}',
)
if result.missing_required:
    raise ValueError(f"Missing required variables: {result.missing_required}")
prompt = result.content
```

### 2.5 P1-2：PathManager 集成

**设计原则**：prompt 中的路径构造通过 PathManager，不通过字符串插值。

**方案选择**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：prompt 中用 PathManager | 每个 exec 块先创建 PathManager 实例 | 路径安全、统一 | prompt 改动大 |
| B：BlackboardManager 封装路径方法 | `bb.get_path('stages/xxx.json')` 内部用 PathManager | 改动小，Agent 无需改 | 需要修改 BlackboardManager |
| C：保持现状 | PathConfig 已满足需求 | 零改动 | PathManager 是死代码 |

**推荐方案 B**：
- BlackboardManager 已有 `read_json()` / `write_json()` / `write_stage()` 等方法
- 新增 `resolve_path(relative_path)` 方法，内部用 PathManager
- prompt 中通过 `bb.resolve_path('stages/xxx.json')` 获取绝对路径
- 减少 prompt 中的硬编码路径

**修改文件**：
1. `core/blackboard/blackboard_manager.py` — 新增 `resolve_path()` 方法
2. `orchestrator.md` — 路径构造改为 `bb.resolve_path(...)`
3. `planning_module.md` / `research_module.md` / `summary_module.md` — 同上

### 2.6 P1-3：状态信号统一

**当前问题**：两套状态信号（`module_*_state.json` + `.runs/*.run.json`）可能不一致。

**方案**：`.runs/*.run.json` 作为唯一真相源（Single Source of Truth），`module_*_state.json` 作为兼容层从 `.runs/` 派生。

**修改内容**：
1. `wait_for_module()` 成功后自动更新 `.runs/*.run.json`（已在 P0-1 中覆盖）
2. Module Agent 不再直接写 `module_*_state.json`，改由 Orchestrator 在 `wait_for_module()` 返回后写入
3. 或者：`module_*_state.json` 保留但标记为 deprecated，新代码只读 `.runs/`

---

## 三、实施计划

### Phase 1：P0 修复（稳健性）

| 步骤 | 修改文件 | 验证方式 |
|------|---------|---------|
| 1.1 修改 `wait_for_module()` 自动更新状态 | `core/process_manager/lifecycle.py` | 单元测试 + 手动验证 |
| 1.2 修复 Planning Module mark_completed | `domains/solution_pro/prompts/planning_module.md` | 代码审查 |
| 1.3 新增 `recover_zombie_runs()` | `core/process_manager/lifecycle.py` | 单元测试 |
| 1.4 Orchestrator Step 0 调用 recover | `domains/solution_pro/prompts/orchestrator.md` | 代码审查 |

### Phase 2：P1 集成（完全集成）

| 步骤 | 修改文件 | 验证方式 |
|------|---------|---------|
| 2.1 PromptUtils 集成 — orchestrator.md | `domains/solution_pro/prompts/orchestrator.md` | 代码审查 + 运行测试 |
| 2.2 PromptUtils 集成 — planning_module.md | `domains/solution_pro/prompts/planning_module.md` | 同上 |
| 2.3 PromptUtils 集成 — research_module.md | `domains/solution_pro/prompts/research_module.md` | 同上 |
| 2.4 PromptUtils 集成 — summary_module.md | `domains/solution_pro/prompts/summary_module.md` | 同上 |
| 2.5 PathManager 集成 — BlackboardManager | `core/blackboard/blackboard_manager.py` | 单元测试 |
| 2.6 PathManager 集成 — prompts | 4 个 prompt 文件 | 代码审查 |

### Phase 3：验证

| 步骤 | 验证方式 |
|------|---------|
| 3.1 单元测试 | pytest core/process_manager/ + core/prompt_utils/ |
| 3.2 集成测试 | 小案例跑通 Solution Pro |
| 3.3 状态一致性验证 | 检查 .runs/ 和 module_*_state.json 一致 |

---

## 四、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `wait_for_module()` 自动更新导致重复 mark_completed | 低 | 低 | mark_completed 是幂等的 |
| PromptUtils 集成后 prompt 模板变量缺失 | 中 | 中 | render_prompt 的 fail-fast 会提前暴露 |
| PathManager 集成改动过大 | 中 | 中 | 方案 B 最小化改动 |
| 修复引入新 bug | 低 | 高 | 每个 Phase 独立验证 |

---

## 五、验收标准

1. ✅ `.runs/*.run.json` 状态与实际一致（3/3 模块 completed）
2. ✅ Planning Module 正确调用 mark_completed
3. ✅ 所有 prompt 加载通过 PromptUtils（0 处 `.read_text()` + `.replace()`）
4. ✅ 所有路径构造通过 PathManager/BlackboardManager（0 处硬编码路径）
5. ✅ Gateway 重启后 zombie 状态自动恢复
6. ✅ pytest 全绿
7. ✅ 小案例 E2E 跑通

---

*等待专家评审后开始实施。*
