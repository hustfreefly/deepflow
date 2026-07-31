# Deliver Pro 共享子 Agent 规则

> **所有 Deliver Pro 子 Agent 必须遵守以下规则。**
> 引用方式：在每个 prompt 开头添加 `请先阅读 _shared_subagent_rules.md`

---

## 🔴 执行铁律（8 条）

1. **声称 ≠ 完成，证据 = 完成** — 写完产出后必须等待验证，不能自行声明"完成"
2. **不修改他人产出** — 只写自己负责的文件，不修改上游/下游的产出
3. **不 spawn 子 Agent** — 你是执行者，不是调度者。禁止 sessions_spawn
4. **MUST 约束不可妥协** — 上游标记为 MUST 的约束是硬约束，不能违反或弱化
5. **语义判断用 LLM，确定性穷举用 Python** — 分类/匹配/评估 → LLM；字段检查/格式验证/计数 → Python
6. **数据走文件** — 不通过 prompt 传递数据，所有中间结果写入 blackboard
7. **生成者 ≠ 验证者** — 你生成的产出必须由独立验证者检查
8. **诚实优于完美** — 有问题写入 ISSUES.md，不要隐藏或跳过

---

## 🔧 防御性编码规则（exec Python 代码时必须遵守）

### Blackboard 文件读取
Blackboard 文件可能有 3 种格式（dict / str / 双重编码），读取时必须防御：
```python
import json
with open(path) as f:
    raw = f.read()
try:
    data = json.loads(raw)
    if isinstance(data, str):
        try:
            data = json.loads(data)  # double-encoded
        except (json.JSONDecodeError, TypeError):
            pass  # plain string, use as-is
except json.JSONDecodeError:
    data = raw  # not JSON, use raw text

# 安全预览（适用于任何类型）
preview = str(data)[:2000] if not isinstance(data, str) else data[:2000]
print(preview)
```

### Python 代码规范
- **注释和 docstring 必须用英文** — 中文全角字符（，/（/）/—）会导致 SyntaxError
- **使用绝对路径**: `{deepflow_root}/...`
- **禁止相对路径**: `data/`, `prompts/`, `stages/`（subagent cwd 可能不是 .deepflow/）

---

## ⏱️ 执行安全规则（exec 运行任何命令时必须遵守）

> 来源：2026-07-31 git_init.sh 事故 — 生成的脚本参数解析缺 `shift` 死循环，无超时执行，烧了 15.75 小时 CPU 直到人工发现。

1. **任何脚本/命令执行必须带超时** — 用 exec 工具的 `timeout` 参数（≤ 300 秒），或 `gtimeout 300 <cmd>` 包裹命令
2. **禁止无超时运行生成物脚本** — 你生成的脚本可能有 bug（死循环/阻塞输入），无超时执行 = 烧 CPU 到人工发现
3. **调试模式同样要超时** — `bash -x script.sh | tail` 这类调试命令也必须带 timeout
4. **长耗时操作必须声明** — 预期 > 5 分钟的操作，在 EVIDENCE.md 中写明预期耗时和理由

---

## 📁 文件操作安全规则

### edit 工具使用约束
1. **edit 前必须 read**: 在调用 edit 工具之前，**必须**先 read 目标文件的当前内容
2. 原因: 文件可能已被其他 Agent 修改，你记忆中的内容可能已过时
3. ❌ 禁止: 凭记忆中的文件内容构造 oldText
4. ✅ 正确: read 当前内容 → 确认 oldText 精确匹配 → 再 edit

### 中文路径处理
1. shell 命令中的中文路径**必须**用引号包裹
2. ❌ 禁止: `cat blackboard/国产半导体/data.json`
3. ✅ 正确: `cat "blackboard/国产半导体/data.json"`
4. 更优: 在 Python 内用 `Path()` 操作路径，避免 shell 编码问题

---

## 🚫 禁止操作（subagent 环境限制）

- ❌ `cron(action="add", sessionTarget="main")` → 用 `sessionTarget="isolated"`
- ❌ `sessions_list()` / `sessions_history()` → visibility=tree 限制
- ❌ `exec` 中设置 `PYTHONPATH` 环境变量
- ❌ `cron(action="list")` → restricted to current job
- ❌ `web_search` — 基于已有知识工作，不搜索新信息（除非 prompt 明确要求）

---

## ✅ 第一行动硬约束

**你的第一个 action 必须是 exec 创建输出目录。**

- ❌ 不要先 read 上游文件
- ❌ 不要 ls/find/glob 探索目录
- ❌ 不要输出纯文本分析而不产出文件

你的任务数据全在 prompt 里。执行 `mkdir -p` 后，立即开始执行任务。

---

## 📏 路径铁律（P0）

所有输出文件必须写入 prompt 中指定的**绝对路径**目录。

- ❌ 不要使用相对路径 `stages/worker_outputs/` 或 `worker_outputs/`
- ✅ 必须使用 `{deepflow_root}/blackboard/{project_name}/deliver_pro/...`
- 如果目录不存在，先用 `exec mkdir -p` 创建

---

*本文件是 Deliver Pro 子 Agent 的共享规则。各 prompt 引用此文件后，不再重复写这些铁律。*
