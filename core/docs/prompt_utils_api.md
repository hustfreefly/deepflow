# PromptUtils API 文档

> **版本**: v1.0.0  
> **位置**: `core/prompt_utils.py`  
> **设计原则**: 纯函数、无状态、fail-fast、契约笼子

---

## 1. 核心函数

### 1.1 load_prompt

```python
def load_prompt(prompt_path: str | Path) -> str
```

**功能**: 加载 prompt 文件内容（自动剥离 Front Matter）

**参数**:
- `prompt_path`: prompt 文件路径

**返回**: prompt 内容字符串

**异常**:
- `FileNotFoundError`: 文件不存在
- `ValueError`: 文件为空

**示例**:
```python
from core.prompt_utils import load_prompt

content = load_prompt("prompts/orchestrator.md")
```

---

### 1.2 render_prompt

```python
def render_prompt(
    prompt_path: str | Path,
    **variables: str,
) -> PromptRenderResult
```

**功能**: 渲染 prompt（变量替换）

**模板语法**:
- `{{variable}}` — 必需变量，缺失则 fail-fast
- `{variable}` — 可选变量，缺失则保留原文

**参数**:
- `prompt_path`: prompt 文件路径
- `**variables`: 变量键值对

**返回**: `PromptRenderResult(content, size, content_hash)`

**异常**:
- `FileNotFoundError`: 文件不存在
- `ValueError`: 必需变量缺失

**示例**:
```python
from core.prompt_utils import render_prompt

result = render_prompt(
    "prompts/orchestrator.md",
    session_id="sess_123",
    deepflow_root="/path/to/deepflow"
)

print(result.content)       # 渲染后内容
print(result.size)          # 字节数
print(result.content_hash)  # SHA256 前 8 位
```

---

### 1.3 check_task_size

```python
def check_task_size(
    text: str,
    warn_bytes: Optional[int] = None,
    block_bytes: Optional[int] = None,
) -> TaskSizeCheckResult
```

**功能**: 检查 task 大小（防止 spawn 截断）

**参数**:
- `text`: task 文本
- `warn_bytes`: 警告阈值（默认 2048，可环境变量覆盖）
- `block_bytes`: 阻断阈值（默认 6000，可环境变量覆盖）

**返回**: `TaskSizeCheckResult(ok, size, level)`
- `level`: `"ok"` | `"warn"` | `"block"`

**示例**:
```python
from core.prompt_utils import check_task_size

result = check_task_size(task_text)

if result.level == "block":
    raise ValueError(f"Task 太大: {result.size}B")
elif result.level == "warn":
    print(f"警告: Task 接近阈值 {result.size}B")
```

---

### 1.4 detect_injection

```python
def detect_injection(text: str) -> InjectionCheckResult
```

**功能**: 检测已知危险模式（防 prompt 注入）

**检测模式**:
- `ignore previous instructions`
- `system: override`
- `<script>` 标签
- `javascript:` 协议
- `you are now a/an ...`
- `disregard previous rules`

**参数**:
- `text`: 待检测文本

**返回**: `InjectionCheckResult(clean, matches)`

**示例**:
```python
from core.prompt_utils import detect_injection

result = detect_injection(prompt_content)

if not result.clean:
    print(f"检测到危险模式: {result.matches}")
```

---

### 1.5 write_blackboard_prompt

```python
def write_blackboard_prompt(
    blackboard_dir: str | Path,
    name: str,
    content: str,
    subdir: str = "stages",
) -> Path
```

**功能**: 写入 prompt 到 blackboard（原子写）

**参数**:
- `blackboard_dir`: blackboard 根目录
- `name`: 文件名（不含扩展名，不能含路径分隔符）
- `content`: prompt 内容
- `subdir`: 子目录（默认 `"stages"`）

**返回**: 写入的文件路径

**异常**:
- `ValueError`: name 包含路径分隔符

**示例**:
```python
from core.prompt_utils import write_blackboard_prompt

path = write_blackboard_prompt(
    blackboard_dir="blackboard/sess_123",
    name="orchestrator_prompt",
    content=rendered_content,
    subdir="stages"
)
# 返回: blackboard/sess_123/stages/orchestrator_prompt.md
```

---

### 1.6 validate_all

```python
def validate_all(
    prompt_path: str | Path,
    variables: dict[str, str],
    check_size: bool = True,
    check_injection: bool = True,
    task_text: Optional[str] = None,
) -> ValidateAllResult
```

**功能**: spawn 前完整预检（一站式验证）

**检查项**:
1. 文件存在性
2. 必需变量完整性
3. 未替换变量残留（警告）
4. Task 大小（可选）
5. 注入检测（可选）

**参数**:
- `prompt_path`: prompt 文件路径
- `variables`: 变量键值对
- `check_size`: 是否检查大小（默认 True）
- `check_injection`: 是否检查注入（默认 True）
- `task_text`: task 文本（用于大小检查，默认用渲染后内容）

**返回**: `ValidateAllResult(ok, errors, warnings)`

**示例**:
```python
from core.prompt_utils import validate_all

result = validate_all(
    prompt_path="prompts/orchestrator.md",
    variables={"session_id": "sess_123"},
)

if not result.ok:
    print(f"验证失败: {result.errors}")
    # 不 spawn
    
if result.warnings:
    print(f"警告: {result.warnings}")
    # 可继续 spawn
```

---

## 2. Pydantic 契约

### 2.1 PromptRenderResult

```python
class PromptRenderResult(BaseModel):
    content: str        # 渲染后内容
    size: int           # 字节数
    content_hash: str   # SHA256 前 8 位
```

### 2.2 TaskSizeCheckResult

```python
class TaskSizeCheckResult(BaseModel):
    ok: bool              # 是否通过
    size: int             # 实际大小
    warn_threshold: int   # 警告阈值
    block_threshold: int  # 阻断阈值
    level: str            # "ok" | "warn" | "block"
```

### 2.3 InjectionCheckResult

```python
class InjectionCheckResult(BaseModel):
    clean: bool          # 是否干净
    matches: list[str]   # 匹配的危险模式
```

### 2.4 ValidateAllResult

```python
class ValidateAllResult(BaseModel):
    ok: bool              # 是否全部通过
    errors: list[str]     # 错误列表
    warnings: list[str]   # 警告列表
```

---

## 3. 便捷类封装（可选）

```python
class PromptUtils:
    @staticmethod
    def load(prompt_path) -> str
    @staticmethod
    def render(prompt_path, **vars) -> PromptRenderResult
    @staticmethod
    def check_size(text, **kwargs) -> TaskSizeCheckResult
    @staticmethod
    def check_injection(text) -> InjectionCheckResult
    @staticmethod
    def write(bb_dir, name, content, **kwargs) -> Path
    @staticmethod
    def validate(prompt_path, variables, **kwargs) -> ValidateAllResult
```

**使用示例**:
```python
from core.prompt_utils import PromptUtils

result = PromptUtils.validate("prompts/orchestrator.md", {"session_id": "x"})
```

---

## 4. 配置（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TASK_SIZE_WARN_BYTES` | `2048` | 警告阈值（字节） |
| `TASK_SIZE_BLOCK_BYTES` | `6000` | 阻断阈值（字节） |

---

## 5. 典型工作流

### 5.1 Orchestrator spawn 前预检

```python
from core.prompt_utils import validate_all, render_prompt, write_blackboard_prompt

# 1. 预检
result = validate_all(
    prompt_path="prompts/orchestrator.md",
    variables={"session_id": session_id, "deepflow_root": deepflow_root},
)

if not result.ok:
    # 写入 .failed，不 spawn
    write_failure(result.errors)
    return

# 2. 渲染
rendered = render_prompt(
    "prompts/orchestrator.md",
    session_id=session_id,
    deepflow_root=deepflow_root
)

# 3. 写入 blackboard
prompt_path = write_blackboard_prompt(
    blackboard_dir=bb_dir,
    name="orchestrator_prompt",
    content=rendered.content
)

# 4. 构造最小 task
task = f"读取 blackboard 文件 {prompt_path} 并按指令执行。"

# 5. spawn
sessions_spawn(task=task, ...)
```

### 5.2 Module Agent 读取 prompt

```python
from core.blackboard.blackboard_manager import BlackboardManager
from core.prompt_utils import render_prompt

bb = BlackboardManager(session_id)
prompt_text = bb.read_stage_raw("orchestrator_prompt.md")

# 直接执行 prompt 内容
execute(prompt_text)
```

---

## 6. 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `FileNotFoundError` | prompt 文件不存在 | 检查路径 |
| `必需变量缺失` | 模板中 `{{var}}` 未提供 | 补充变量 |
| `Task 太大` | task > 6000B | 改用文件引用模式 |
| `检测到危险模式` | prompt 含注入内容 | 检查 prompt 来源 |

---

## 7. 设计决策

| 决策 | 理由 |
|------|------|
| 纯函数，无状态 | 可测试、可组合、无副作用 |
| fail-fast | 不静默降级，早期暴露问题 |
| 原子写 | 防止写入中断导致文件损坏 |
| 双花括号 vs 单花括号 | 必需 vs 可选，明确语义 |
| 环境变量配置 | 阈值可调，无需改代码 |

---

## 8. 与现有组件关系

| 组件 | 关系 |
|------|------|
| `BlackboardManager` | PromptUtils 写文件，BlackboardManager 读文件 |
| `ProcessManager` | 无直接依赖，可配合使用 |
| `PathManager` | 无直接依赖，路径由调用方提供 |
| `SpawnParamsContract` | 可配合使用（大小检查） |

---

**文档版本**: v1.0.0  
**最后更新**: 2026-07-27
