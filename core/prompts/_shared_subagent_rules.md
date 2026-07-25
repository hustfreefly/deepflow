## 🔴 执行铁律（契约笼子 — 所有子 Agent 必须遵守）

1. **声称 ≠ 完成，证据 = 完成** — 写完 stage 后必须等待父 Agent exec 验证，不能自行声明"完成"
2. **只写指定 stage** — 不修改任何其他 stage，不写完成信号（`*_completed`）
3. **MUST 约束不可妥协** — planning_convergence 中标记为 MUST 的约束是硬约束，任何情况下不能违反或弱化
4. **语义判断用 LLM，确定性穷举用 Python** — 不混用。分类/匹配/评估 → LLM；字段检查/格式验证/计数 → Python
5. **不修改上游输出** — 只能读取和写入自己的 stage，不能修改 Planning/Research 模块的产出
6. **完成后只写指定 stage** — 不生成额外文件，不写 summary/README/完成报告到 Blackboard 以外的位置
7. **不能 web_search** — 基于已有知识工作，不搜索新信息（除非 prompt 明确要求）
8. **绝不输出 NO_REPLY**——即使无事可做，也输出一行状态文本（如"无待处理动作"）。
   NO_REPLY 会导致 run-mode session 关闭 = 死亡。重复完成事件是平台行为，不是你的错误。

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

### BlackboardManager API 快速参考

```
bb = BlackboardManager('{session_id}')

# Stage 读写（JSON dict）
bb.write_stage('name', {'key': 'val'})    # 写 dict → stages/name.json
bb.read_stage('name', default=None)        # 读 dict ← stages/name.json
bb.append_stage('name', {'key': 'val'})    # 增量合并
bb.stage_exists('name')                    # → bool
bb.list_stages()                           # → list[str]
bb.read_stage_raw('name')                  # 读原始文本（.md/.txt/.json）

# 文件读写（文本/任意内容）
bb.write('file.md', text, subdir='stages/sub')   # 写文本
bb.read('file.md', subdir='stages/sub')          # 读文本
bb.read_json('file.json', default=None)           # 读 JSON

# 属性
bb.session_dir   # → Path
bb.session_id    # → str
```

⚠️ 常见错误（禁止）：
- ❌ `bb._load()` → 不存在！用 `bb.read_stage()` 或 `bb.read()`
- ❌ `bb.write_stage('name', markdown_string)` → write_stage 接收 dict，不接收 str！写文本用 `bb.write()`
- ❌ `bb.read_stage('name')` 读文本 → read_stage 返回 dict！读文本用 `bb.read()` 或 `bb.read_stage_raw()`

### Python 代码规范
- **注释和 docstring 必须用英文** — 中文全角字符（，/（/）/—）会导致 SyntaxError
- **使用绝对路径**: `{deepflow_root}/...`
- **禁止相对路径**: `data/`, `prompts/`, `stages/`（subagent cwd 可能不是 .deepflow/）

## 文件操作安全规则

### edit 工具使用约束
1. **edit 前必须先 read**: 在调用 edit 工具之前，**必须**先 read 目标文件的当前内容
2. 原因: 文件可能已被其他 Agent 修改，你记忆中的内容可能已过时
3. ❌ 禁止: 凭记忆中的文件内容构造 oldText
4. ✅ 正确: read 当前内容 → 确认 oldText 精确匹配 → 再 edit

### 中文路径处理
1. shell 命令中的中文路径**必须**用引号包裹
2. ❌ 禁止: `cat blackboard/国产半导体封装材料VC投资框架/data.json`
3. ✅ 正确: `cat "blackboard/国产半导体封装材料VC投资框架/data.json"`
4. 更优: 在 Python 内用 `Path()` 操作路径，避免 shell 编码问题

### 禁止操作（subagent 环境限制）
- ❌ `cron(action="add", sessionTarget="main")` → 用 `sessionTarget="isolated"`
- ❌ `sessions_list()` / `sessions_history()` → visibility=tree 限制
- ❌ `exec` 中设置 `PYTHONPATH` 环境变量
- ❌ `cron(action="list")` → restricted to current job
