# DeepFlow 教训记录 - 2026-06-25

## 事件：Spec Pro + Solution Pro 启动链路上的 3 个系统性问题

### 问题 1：Spec Pro 入口跑偏（主 Agent 行为问题）
**现象**：用户输入一大段调研材料后，主 Agent 没有走 Spec Pro 流程，而是直接开始写代码（contracts/__init__.py）。

**根因**：SKILL.md 的 Step 1 触发条件不够明确，缺少"入口守卫"。

**修复**：
- 在 `domains/spec_pro/SKILL.md` 增加 **Step 0: 入口守卫（防偏检查）**
- 明确列出"绝对禁止"的行为（禁止自己出方案/写代码/设计架构）
- 强制要求：无论用户输入什么，只要识别到要做 Spec Pro，必须走 `spec_pro_api.py init` → 多轮对话

### 问题 2：Harness 调用路径不匹配
**现象**：`exec python3 domains/spec_pro/eval/harness.py {session_id}` 报 `FileNotFoundError`。

**根因**：harness.py 内部用 `os.path.join(blackboard_path, "spec/living_spec.json")` 拼接路径，但 CLI 传入的是 session_id，拼接后路径错误。

**修复**：
- harness.py 改用 BlackboardManager API
- `load_and_evaluate()` 支持 `session_id` 参数（推荐）和 `blackboard_path` 参数（兼容）
- CLI 用法：`python harness.py <session_id>`

### 问题 3：Solution Pro 启动时 constraints 格式不兼容
**现象**：`start_solution_pro.py` 报 `AttributeError: 'list' object has no attribute 'get'`。

**根因**：
- Spec Pro 生成的 LivingSpec 中 `confirmed.constraints` 是 **list 格式**：`["一步到位", "全LLM控制"]`
- Solution Pro 的 `task_builder.py` 假设是 **dict 格式**：`{"budget": "...", "timeline": "..."}`
- 4 处调用 `confirmed.get("constraints", {}).get("budget", ...)` 在 list 上崩溃

**修复**：
- `task_builder.py` 添加 `_extract_constraints()` 兼容函数
- `frozen_spec.py` 2 处兼容 list 格式
- `requirement_structuring.py` 2 处兼容 list 格式
- `harness.py` 2 处兼容 list 格式
- 共修复 **9 处**，覆盖 Spec Pro + Solution Pro 全链路

### 问题 4（举一反三）：子 Agent PYTHONPATH 缺失
**现象**：子 Agent 执行 `from core.blackboard.blackboard_manager import BlackboardManager` 报 `ModuleNotFoundError: No module named 'core'`。

**根因**：
- Orchestrator spawn 子 Agent 时没有传 `cwd` 参数
- 子 Agent 在默认目录执行 `python3 -c "..."`，找不到 `core` 模块
- 每个子 Agent 自行探索路径，浪费 1-2 次工具调用（11 个子 Agent × 1-2 次 = ~20 次浪费）

**修复**：
- `pipeline_orchestrator.md` 的 `sessions_spawn` 调用加上 `cwd="/Users/allen/.openclaw/workspace/.deepflow"`
- 在 `task_builder.py` 添加 `PYTHON_EXECUTION_PREAMBLE` 常量
- prompt 模板中要求 worker 加 `PYTHONPATH=.` 前缀

### 问题 5（举一反三）：task_builder.py 中 `get_blackboard_path()` 方法不存在
**现象**：子 Agent 照着 prompt 模板写 `bb.get_blackboard_path()` 崩溃。

**根因**：
- `BlackboardManager` 只有 `get_stage_path()`（已 deprecated），没有 `get_blackboard_path()`
- `task_builder.py` 5 处 prompt 模板里错误地写了这个方法

**修复**：
- 5 处全部替换为正确的 API 使用说明：`bb.read_stage()` / `bb.write_stage()`

---

## 教训总结

### 教训 1：数据契约必须双向兼容
**场景**：上游（Spec Pro）生成 list 格式，下游（Solution Pro）假设 dict 格式。

**规则**：
- 任何读取其他模块输出的代码，必须用 `isinstance()` 检查类型
- 提供兼容函数（如 `_extract_constraints()`），统一返回标准化格式
- 在 SKILL.md 中明确标注输入/输出的 schema，包括可变格式

### 教训 2：子 Agent 执行环境必须显式配置
**场景**：`sessions_spawn` 不传 `cwd`，子 Agent 在错误目录执行。

**规则**：
- 所有 `sessions_spawn` 调用必须传 `cwd` 参数
- 子 Agent prompt 中必须包含 `PYTHONPATH=.` 的强制要求
- 子 Agent 执行 `python3` 命令时必须用完整路径：`cd /path/to/deepflow && PYTHONPATH=. python3 -c "..."`

### 教训 3：prompt 模板中的 API 调用必须真实存在
**场景**：`task_builder.py` 中写了 `bb.get_blackboard_path()`，但这个方法不存在。

**规则**：
- prompt 模板中的所有代码示例，必须来自真实的 API 文档或源码
- 禁止在 prompt 中"想象" API 方法名
- 修改 prompt 模板前，先用 `grep` 确认方法在源码中存在

### 教训 4：入口守卫防止主 Agent 跑偏
**场景**：用户输入调研材料，主 Agent 直接开始写代码而不是走 Spec Pro 流程。

**规则**：
- 每个 SKILL.md 必须有 **Step 0: 入口守卫**
- 明确列出"触发条件"和"绝对禁止"的行为
- 主 Agent 看到用户输入后，先判断"这是要启动 Spec Pro 还是直接给方案"

---

## 修复文件清单

| 文件 | 修复内容 | 影响范围 |
|------|----------|----------|
| `domains/spec_pro/SKILL.md` | 增加 Step 0 入口守卫 | Spec Pro 启动流程 |
| `domains/spec_pro/eval/harness.py` | 改用 BlackboardManager API + constraints 兼容 | Harness 评估 |
| `domains/solution_pro/task_builder.py` | `_extract_constraints()` + `PYTHON_EXECUTION_PREAMBLE` + 修复 5 处 `get_blackboard_path` | Solution Pro worker prompt 生成 |
| `domains/solution_pro/frozen_spec.py` | constraints 兼容（2 处） | Frozen Spec 生成 |
| `domains/solution_pro/requirement_structuring.py` | constraints 兼容（2 处） | REQ-ID 结构化 |
| `domains/solution_pro/prompts/pipeline_orchestrator.md` | sessions_spawn 加 `cwd` 参数 | Orchestrator 行为 |

---

## 验证状态

- ✅ constraints 兼容函数测试通过（dict/list/空格式）
- ✅ 所有修复文件代码检查通过
- ✅ 当前 Solution Pro 管线仍在运行（Phase 1-3 完成，Phase 4 进行中）
- ⚠️ 旧管线使用已生成的 prompt（包含错误），但子 Agent 自行恢复了
- ✅ 新管线将使用修复后的 prompt，不会再出现这些错误

---

## 记忆锚点

> "上游 list 下游 dict = 崩溃；用 isinstance 兼容"  
> "sessions_spawn 必须传 cwd，子 Agent 必须加 PYTHONPATH"  
> "prompt 里的 API 必须真实存在，禁止想象方法名"  
> "SKILL.md 必须有入口守卫，防止主 Agent 跑偏"
