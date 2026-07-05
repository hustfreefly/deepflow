# Depth-3 Worker 缺失诊断报告

**日期**: 2026-06-29  
**问题**: 2.0.0 Planning Module (depth-2) 没有 spawn depth-3 Workers，直接自己生成了 22KB 输出  
**影响**: 多 Worker 架构失效，退化为单 Agent 模式

---

## 1. 2.0.0 vs 2.0.0 Prompt 对比表

| 维度 | 2.0.0 Pipeline Orchestrator | 2.0.0 Planning Module | 影响 |
|------|-------------------------|-------------------|------|
| **执行循环强调** | ✅ "遍历 phases（🔴 循环，不是单次执行）"<br>✅ "你必须在一个 turn 内循环执行所有 10 个 phase"<br>✅ "每次 yield 返回后，立即验证输出文件，然后继续下一个 phase" | ⚠️ "你必须按顺序执行 3 个 Layer"<br>❌ 没有强调"循环"概念<br>❌ 没有说"在一个 turn 内完成所有 3 个 Layer" | 🔴 **高**：2.0.0 可能让 LLM 认为每个 Layer 是独立的 turn，而不是连续执行 |
| **Preamble 和 Python 环境** | ✅ "🔴 Python 执行环境修复（必须）"<br>✅ 给出具体的 preamble 内容<br>✅ 强调"每个 worker 的 task 前面必须加上 preamble" | ❌ 没有提到 preamble<br>❌ 没有强调 Python 环境修复 | 🔴 **高**：2.0.0 的 Worker 可能因 Python 环境问题失败，Module Agent 放弃 spawn |
| **Yield 返回后的强制检查** | ✅ "🔴 自检清单（每次 yield 返回后执行）"<br>✅ 4 个具体的检查项<br>✅ "只有写完 `.completed` 后你才能结束 turn" | ⚠️ 有"🔴 完成条件"<br>❌ 但没有"自检清单"<br>❌ 没有强调"每次 yield 返回后"要做什么 | 🟡 **中**：2.0.0 缺少 yield 返回后的强制检查步骤 |
| **Task 内容的具体性** | ✅ Task 内容从 Blackboard 读取（`tasks[task_key]`）<br>✅ 动态生成，不是硬编码 | ⚠️ Task 内容在 prompt 中硬编码<br>⚠️ 包含占位符（如 `[这里放 frozen_spec 的 JSON 内容]`） | 🟡 **中**：2.0.0 的硬编码 task 内容可能让 LLM 认为这只是示例 |
| **角色声明** | ✅ "你不是一个'启动器'，你是一个'执行器'" | ⚠️ "你是 Planning 模块的**调度 Agent**" | 🟡 **中**：2.0.0 的"调度 Agent"声明可能让 LLM 认为它只需要"调度"，不需要确保执行完成 |
| **错误处理和降级** | ✅ 明确的错误分类（retry, skip, abort）<br>✅ "失败不隐身：失败要记录到 `.completed.failed_stages`"<br>✅ "非 abort 级错误可继续后续阶段" | ⚠️ 有降级策略（"如果 MISSING，用 exec 写入默认配置作为降级"）<br>❌ 但没有明确的错误分类 | 🟡 **中**：2.0.0 的降级策略可能导致 LLM 直接自己生成输出，而不是重试 spawn |
| **Prompt 长度** | ~4000 字 | ~3000 字 | 🟢 **低**：2.0.0 更短，应该更容易遵循 |
| **平台配置** | N/A | ✅ `maxSpawnDepth: 4`（足够支持 depth-3） | ✅ **无问题** |

---

## 2. 根因分析（按重要性排序）

### 🔴 根因 1：缺少"循环执行"的强调（置信度：90%）

**问题**：2.0.0 prompt 没有强调"在一个 turn 内完成所有 3 个 Layer"，导致 LLM 可能认为：
- 每个 Layer 是一个独立的 turn
- spawn 一个 Worker 后就可以结束 turn
- 不需要等待 Worker 完成并继续下一个 Layer

**证据**：
- 2.0.0 明确说"遍历 phases（🔴 循环，不是单次执行）"
- 2.0.0 说"你必须在一个 turn 内循环执行所有 10 个 phase"
- 2.0.0 只说"你必须按顺序执行 3 个 Layer"，没有强调"循环"和"在一个 turn 内"

**影响**：LLM 在 spawn 第一个 Worker（Meta-Planner）后，可能认为自己的任务完成了，等待下一次调度。

---

### 🔴 根因 2：缺少 Preamble 和 Python 环境修复（置信度：85%）

**问题**：2.0.0 prompt 没有提到 preamble，导致 Worker 可能因 Python 环境问题失败。

**证据**：
- 2.0.0 明确说"🔴 Python 执行环境修复（必须）"
- 2.0.0 给出具体的 preamble 内容：
  ```
  你执行的所有 Python 命令必须以 `cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=.` 开头。
  否则 `from core.blackboard.blackboard_manager import BlackboardManager` 会报 ModuleNotFoundError。
  ```
- 2.0.0 强调"每个 worker 的 task 前面必须加上 preamble"
- 2.0.0 完全没有提到 preamble

**影响**：
1. Worker 在执行 `from core.blackboard.blackboard_manager import BlackboardManager` 时报错
2. Worker 无法写入 Blackboard
3. Module Agent 验证时发现输出缺失
4. Module Agent 可能选择"降级"（自己生成输出），而不是重试 spawn

**验证方法**：检查 2.0.0 执行日志，看是否有 `ModuleNotFoundError` 错误。

---

### 🟡 根因 3：缺少 yield 返回后的强制检查（置信度：70%）

**问题**：2.0.0 没有"自检清单"，导致 LLM 可能跳过验证直接结束。

**证据**：
- 2.0.0 有"🔴 自检清单（每次 yield 返回后执行）"
- 2.0.0 的自检清单包含 4 个具体的检查项
- 2.0.0 只有"🔴 完成条件"，但没有"自检清单"
- 2.0.0 没有强调"每次 yield 返回后"要做什么

**影响**：LLM 在 yield 返回后，可能没有验证 Worker 输出，直接认为任务完成。

---

### 🟡 根因 4：Task 内容的硬编码（置信度：60%）

**问题**：2.0.0 的 task 内容包含占位符，可能让 LLM 认为这只是示例。

**证据**：
- 2.0.0 的 task 内容包含 `[这里放 frozen_spec 的 JSON 内容]` 等占位符
- 2.0.0 的 task 内容从 Blackboard 动态读取，不是硬编码

**影响**：LLM 可能认为这些 task 内容只是"示例"，不是真正要执行的。当需要实际执行时，LLM 可能选择自己生成输出，而不是构造真实的 task 内容。

---

### 🟡 根因 5："调度 Agent"的角色声明（置信度：50%）

**问题**：2.0.0 声明"你是 Planning 模块的**调度 Agent**"，可能让 LLM 认为它只需要"调度"（spawn），不需要确保执行完成。

**证据**：
- 2.0.0 声明"你不是一个'启动器'，你是一个'执行器'"
- 2.0.0 声明"你是 Planning 模块的**调度 Agent**"

**影响**：LLM 可能认为"调度 Agent"的职责只是"启动" Worker，不需要等待 Worker 完成并验证输出。

---

### 🟡 根因 6：缺少错误分类（置信度：40%）

**问题**：2.0.0 没有明确的错误分类，导致 LLM 可能直接降级而不是重试。

**证据**：
- 2.0.0 有明确的错误分类（retry, skip, abort）
- 2.0.0 说"失败不隐身：失败要记录到 `.completed.failed_stages`"
- 2.0.0 只有降级策略（"如果 MISSING，用 exec 写入默认配置作为降级"）

**影响**：当 Worker 输出缺失时，LLM 可能直接选择"降级"（自己生成输出），而不是重试 spawn。

---

### ✅ 排除：平台配置问题

**结论**：`maxSpawnDepth: 4` 配置正确，足够支持 depth-3 Workers。

**证据**：
```json
"subagents": {
  "maxConcurrent": 20,
  "maxSpawnDepth": 4,
  "archiveAfterMinutes": 60
}
```

**深度计算**：
- depth-0: Main Agent（用户交互层）
- depth-1: 2.0.0 Orchestrator（spawned by Main Agent）
- depth-2: Planning Module（spawned by 2.0.0 Orchestrator）
- depth-3: Workers（spawned by Planning Module）

`maxSpawnDepth: 4` 允许 depth-0 → depth-1 → depth-2 → depth-3 → depth-4，完全足够。

---

## 3. 具体修复建议

### 修复 1：添加"循环执行"的强调（优先级：P0）

**修改位置**：`v2_planning_module.md` 的"⚡ 关键规则"部分

**修改内容**：

```markdown
## ⚡ 关键规则

1. **sessions_spawn 是 tool call，不是 Python 函数**。你必须直接调用 `sessions_spawn` tool，不能在 `exec` 里调用。
2. **sessions_yield 是 tool call**。spawn 后立即调用 `sessions_yield` 等待 Worker 完成。
3. **Blackboard 操作用 exec**。读写 Blackboard 通过 `exec` 执行 Python 代码。
4. **你不能跳过任何 Layer**。必须按 Layer 0 → Layer 1 → Layer 2 顺序完成。
5. **只有写完 `planning_convergence` 后你才能结束**。
6. 🔴 **你必须在一个 turn 内循环执行所有 3 个 Layer**。不能 spawn 一个 Worker 后就结束 turn。每次 yield 返回后，立即验证输出，然后继续下一个 Layer。
7. 🔴 **你不是一个"启动器"，你是一个"执行器"**。你的职责是确保所有 3 个 Layer 都完成，而不是只启动第一个 Worker。
```

**理由**：
- 添加第 6 条规则，明确强调"循环执行"和"在一个 turn 内"
- 添加第 7 条规则，明确角色是"执行器"而不是"启动器"
- 使用 🔴 标记，与 2.0.0 保持一致

---

### 修复 2：添加 Preamble 和 Python 环境修复（优先级：P0）

**修改位置**：`v2_planning_module.md` 的每个 Layer 的 spawn 部分

**修改内容**：

在 Layer 0、Layer 1、Layer 2 的 spawn 部分，添加以下内容：

```markdown
### Layer 0: Meta-Planner

**你的行动**：

1. 用 `exec` 读取 frozen_spec：
```
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('OpenClaw AI Native Loop Engineering Framework')
import json
spec = bb.read_stage('data/frozen_spec', default={})
print(json.dumps(spec, ensure_ascii=False, indent=2))
"
```

2. 用 `sessions_spawn` tool call 启动 Meta-Planner Worker。

🔴 **Python 执行环境修复（必须）**：
每个 worker 的 task 前面必须加上 `preamble`，内容为：
```
你执行的所有 Python 命令必须以 `cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=.` 开头。
否则 `from core.blackboard.blackboard_manager import BlackboardManager` 会报 ModuleNotFoundError。

正确示例：exec(command="cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c \"...\"")
```

同时，sessions_spawn 必须传 `cwd="/Users/allen/.openclaw/workspace/.deepflow"`。

task 内容如下（把 frozen_spec 的内容嵌入）：

```
你是 Meta-Planner。分析以下需求，输出专家配置和 Gate 配置。

## 需求
[这里放 frozen_spec 的 JSON 内容]

## 输出格式（JSON）
{
  "task_profile": {"domain": "...", "complexity": "standard|rigorous"},
  "experts": [
    {"expert_name": "security_expert", "domain": "security", "focus_areas": [...]},
    {"expert_name": "performance_expert", "domain": "performance", "focus_areas": [...]}
  ],
  "gate_a": {
    "layer1_weights": {"schema": 0.3, "completeness": 0.4, "traceability": 0.3},
    "layer2_enabled": true
  },
  "gate_b": {
    "critical_checks": ["P0_REQ_COVERAGE", "ARCHITECTURE_SOUNDNESS"]
  }
}

## 输出要求
用 exec 写入 Blackboard:
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json
bb = BlackboardManager('OpenClaw AI Native Loop Engineering Framework')
result = { ... 你的输出 ... }
bb.write_stage('stages/meta_planning', result)
print('Written')
"
```

spawn 参数：
- runtime: "subagent"
- mode: "run"
- label: "planning_meta_planner"
- cwd: "/Users/allen/.openclaw/workspace/.deepflow"
```

**理由**：
- 添加"🔴 Python 执行环境修复（必须）"部分，与 2.0.0 保持一致
- 明确给出 preamble 内容
- 强调"每个 worker 的 task 前面必须加上 preamble"
- 强调"sessions_spawn 必须传 cwd"

---

### 修复 3：添加 Yield 返回后的强制检查（优先级：P1）

**修改位置**：`v2_planning_module.md` 的末尾

**修改内容**：

```markdown
## 🔴 自检清单（每次 yield 返回后执行）

1. ☐ 输出是否存在？（`bb.read_stage(expected_output_path)` 不为 None）
2. ☐ 是否还有未执行的 Layer？→ 有 → **立即继续下一个 Layer，不能结束 turn**
3. ☐ 全部 3 个 Layer 是否完成？→ 是 → 写 `planning_convergence` → 然后才能结束

**只有写完 `planning_convergence` 后你才能结束 turn。**
```

**理由**：
- 添加"自检清单"，与 2.0.0 保持一致
- 明确"每次 yield 返回后"要做什么
- 强调"不能结束 turn"

---

### 修复 4：改进 Task 内容的具体性（优先级：P1）

**修改位置**：`v2_planning_module.md` 的每个 Layer 的 task 内容

**修改内容**：

将占位符 `[这里放 frozen_spec 的 JSON 内容]` 替换为具体的指令：

```markdown
task 内容如下：

```
你是 Meta-Planner。分析以下需求，输出专家配置和 Gate 配置。

## 需求
{frozen_spec_json}

## 输出格式（JSON）
...
```

**注意**：`{frozen_spec_json}` 是你从 Blackboard 读取的 frozen_spec 的 JSON 内容，你必须用实际的内容替换这个占位符。
```

**理由**：
- 使用 `{frozen_spec_json}` 占位符，而不是 `[这里放 frozen_spec 的 JSON 内容]`
- 添加"注意"部分，明确说明必须用实际内容替换占位符

---

### 修复 5：明确错误分类和重试策略（优先级：P2）

**修改位置**：`v2_planning_module.md` 的"⚡ 关键规则"部分之后

**修改内容**：

```markdown
## 错误分类

- `retry`: worker 超时、输出文件暂未出现、JSON 暂时不可读 → 重试一次（重新 spawn）
- `skip`: 非关键 worker 缺输出，例如某个 expert 失败 → 用空 dict 降级，继续后续 Layer
- `abort`: frozen_spec 无法读取、所有 Worker 都失败 → 记录错误，结束 turn

**失败不隐身**：失败要记录到最终输出，但不能跳过 Layer。
```

**理由**：
- 添加明确的错误分类，与 2.0.0 保持一致
- 明确"重试一次"的策略
- 强调"失败不隐身"

---

## 4. 置信度评估

| 根因 | 置信度 | 证据强度 | 修复优先级 |
|------|--------|----------|-----------|
| 缺少"循环执行"的强调 | 90% | 2.0.0 有明确强调，2.0.0 没有 | P0 |
| 缺少 Preamble 和 Python 环境修复 | 85% | 2.0.0 有明确要求，2.0.0 没有 | P0 |
| 缺少 yield 返回后的强制检查 | 70% | 2.0.0 有自检清单，2.0.0 没有 | P1 |
| Task 内容的硬编码 | 60% | 2.0.0 动态生成，2.0.0 硬编码 | P1 |
| "调度 Agent"的角色声明 | 50% | 2.0.0 明确是"执行器"，2.0.0 是"调度 Agent" | P2 |
| 缺少错误分类 | 40% | 2.0.0 有明确分类，2.0.0 没有 | P2 |

**总体置信度**：85%（前两个根因的置信度都很高，且修复方向明确）

---

## 5. 验证计划

### 5.1 短期验证（修复后立即执行）

1. **应用修复 1 和修复 2**（P0 修复）
2. **重新运行 2.0.0 Planning Module**
3. **检查**：
   - 是否成功 spawn 了 3 个 Workers（Meta-Planner, Expert Planners, Convergence Planner）？
   - Workers 是否成功写入 Blackboard？
   - 是否有 `ModuleNotFoundError` 错误？
   - Module Agent 是否在一个 turn 内完成了所有 3 个 Layer？

### 5.2 长期验证（修复所有问题后）

1. **应用所有修复**（P0 + P1 + P2）
2. **运行完整的 2.0.0 管线**（Planning → Research → ReviewQC）
3. **检查**：
   - 每个 Module 是否都成功 spawn 了 Workers？
   - 整个管线是否在一个 turn 内完成？
   - 输出质量是否与 2.0.0 一致或更好？

---

## 6. 结论

**核心问题**：2.0.0 Planning Module 的 prompt 缺少 2.0.0 的关键元素，导致 LLM 跳过了 spawn Workers 的步骤。

**核心修复**：
1. 添加"循环执行"的强调（P0）
2. 添加 Preamble 和 Python 环境修复（P0）
3. 添加 Yield 返回后的强制检查（P1）

**预期效果**：修复后，2.0.0 Planning Module 应该能够成功 spawn depth-3 Workers，并在一个 turn 内完成所有 3 个 Layer。

---

**附录：2.0.0 vs 2.0.0 架构对比**

```
2.0.0 架构（已验证可用）：
depth-0: Main Agent
  ↓ spawn
depth-1: Pipeline Orchestrator（执行器）
  ↓ spawn（循环 10 个 phases）
depth-2: Workers（Planner, Researchers, Designers, etc.）

2.0.0 架构（当前问题）：
depth-0: Main Agent
  ↓ spawn
depth-1: 2.0.0 Orchestrator（调度器）
  ↓ spawn（3 个 modules）
depth-2: Module Agents（Planning, Research, ReviewQC）
  ↓ spawn（应该 spawn，但实际没有）
depth-3: Workers（Meta-Planner, Expert Planners, Convergence Planner）

2.0.0 架构（修复后）：
depth-0: Main Agent
  ↓ spawn
depth-1: 2.0.0 Orchestrator（调度器）
  ↓ spawn（3 个 modules）
depth-2: Module Agents（执行器，不是调度器）
  ↓ spawn（循环执行所有 Layers/Stages）
depth-3: Workers（Meta-Planner, Expert Planners, Convergence Planner）
```

**关键洞察**：2.0.0 的 Module Agents 应该被定位为"执行器"，而不是"调度器"。它们的职责是确保所有 Layers/Stages 都完成，而不是只启动第一个 Worker。
