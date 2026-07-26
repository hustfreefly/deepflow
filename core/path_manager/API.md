# PathManager API 手册

> DeepFlow 统一路径管理器 - 核心组件

## 概述

PathManager 负责 DeepFlow 所有路径的统一管理，提供：
- 安全验证（路径遍历防护、文件名验证）
- 并发安全（文件锁 + 重试机制）
- 跨平台支持（Unicode 规范化、路径长度验证）
- 域抽象（Solution/Ship/Deliver）

---

## 核心 API

### 1. 初始化

```python
from core.path_manager import PathManager

pm = PathManager(
    session_id: str,              # 会话 ID（自动 sanitize）
    deepflow_root: Path = None,   # DeepFlow 根目录（默认自动检测）
    domain: str = "solution"      # 域：solution/ship/deliver/research
)
```

**示例**：
```python
# Solution Pro
pm = PathManager("2.5D封装_V40", domain="solution")

# Ship Pro
pm = PathManager("ship_session_001", domain="ship")
```

---

### 2. 路径属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `pm.session_id` | str | 已 sanitize 的 session ID |
| `pm.root` | Path | DeepFlow 根目录 |
| `pm.blackboard` | Path | blackboard/{session_id} |
| `pm.stages` | Path | stages 目录 |
| `pm.data` | Path | data 目录 |
| `pm.runs` | Path | .runs 目录 |
| `pm.artifacts` | Path | artifacts 目录（Ship 域）|
| `pm.packages` | Path | packages 目录（Ship 域）|
| `pm.deliveries` | Path | deliveries 目录（Deliver 域）|

**示例**：
```python
pm = PathManager("test_session", domain="solution")
print(pm.stages)
# /path/to/.deepflow/blackboard/test_session/stages
```

---

### 3. 路径获取方法

#### `get_prompt_path(module, prompt_type="prompt")`
获取 prompt 文件路径

```python
# 获取 planning 模块的 prompt
prompt_path = pm.get_prompt_path("planning")
# /path/to/blackboard/test_session/stages/planning_prompt.md

# 获取 worker prompt
worker_prompt = pm.get_prompt_path("planning_planner", "worker")
# /path/to/blackboard/test_session/stages/planning_planner_worker.md
```

#### `get_output_path(filename)`
获取输出文件路径

```python
output_path = pm.get_output_path("planning_convergence.json")
# /path/to/blackboard/test_session/stages/planning_convergence.json
```

#### `get_data_path(filename)`
获取 data 目录下的文件路径

```python
data_path = pm.get_data_path("living_spec.json")
# /path/to/blackboard/test_session/data/living_spec.json
```

#### `get_run_record_path(module)`
获取模块运行记录路径

```python
run_record = pm.get_run_record_path("planning")
# /path/to/blackboard/test_session/.runs/planning.run.json
```

#### `get_blackboard_path(relative_path)`
获取 blackboard 下的任意路径

```python
custom_path = pm.get_blackboard_path("stages/custom/file.txt")
# /path/to/blackboard/test_session/stages/custom/file.txt
```

---

### 4. 目录管理

#### `ensure_directories()`
确保所有必要目录存在

```python
pm.ensure_directories()
# 创建：blackboard/stages/data/.runs
```

#### `ensure_parent(file_path)`
确保文件的父目录存在

```python
output_path = pm.get_output_path("result.json")
pm.ensure_parent(output_path)
# 确保 stages/ 目录存在
```

---

### 5. 路径验证

#### `validate_path(path, must_exist=False, must_be_writable=False, expected_type=None)`
验证路径

```python
# 验证路径存在
pm.validate_path(output_path, must_exist=True)

# 验证路径可写
pm.validate_path(output_path, must_be_writable=True)

# 验证是文件
pm.validate_path(output_path, expected_type="file")

# 验证是目录
pm.validate_path(pm.stages, expected_type="dir")
```

#### `path_exists(filename)`
检查文件是否存在

```python
if pm.path_exists("planning_convergence.json"):
    print("文件存在")
```

#### `get_file_size(filename)`
获取文件大小

```python
size = pm.get_file_size("planning_convergence.json")
if size:
    print(f"文件大小: {size} bytes")
```

---

### 6. 跨平台支持

#### `get_max_path_length()`
获取系统最大路径长度

```python
max_len = pm.get_max_path_length()
# Windows: 260, macOS/Linux: 4096
```

#### `validate_path_length(path)`
验证路径长度

```python
pm.validate_path_length(output_path)
# 如果超过系统限制，抛出 PathValidationError
```

---

## 异常类型

| 异常 | 说明 |
|------|------|
| `PathManagerError` | 基础异常类 |
| `PathValidationError` | 路径验证失败 |
| `PathNotFoundError` | 路径不存在 |
| `PathNotWritableError` | 路径不可写 |
| `PathTraversalError` | 路径遍历攻击检测 |

**示例**：
```python
from core.path_manager import PathValidationError, PathNotFoundError

try:
    pm.validate_path(path, must_exist=True)
except PathNotFoundError:
    print("路径不存在")
except PathValidationError as e:
    print(f"验证失败: {e}")
```

---

## 使用示例

### 场景 1：Orchestrator spawn Module Agent

```python
from core.path_manager import PathManager

pm = PathManager(session_id, domain="solution")
pm.ensure_directories()

# 获取 prompt 路径（用于 spawn task）
prompt_path = pm.get_prompt_path("planning")
task = f"读取文件 `{prompt_path}` 并执行"

# spawn Module Agent
sessions_spawn(
    task=task,
    cwd=pm.root,
    lightContext=True
)
```

### 场景 2：Module Agent 读取 prompt

```python
from core.path_manager import PathManager

pm = PathManager(session_id, domain="solution")

# 获取 prompt 路径
prompt_path = pm.get_prompt_path("planning")
pm.validate_path(prompt_path, must_exist=True)

# 读取 prompt
content = prompt_path.read_text()
```

### 场景 3：验证模块输出

```python
from core.path_manager import PathManager

pm = PathManager(session_id, domain="solution")

# 检查输出文件
output_path = pm.get_output_path("planning_convergence.json")
if pm.path_exists("planning_convergence.json"):
    size = pm.get_file_size("planning_convergence.json")
    print(f"输出文件: {size} bytes")
else:
    print("输出文件不存在")
```

---

## 安全特性

### 1. 路径遍历防护
```python
# 自动检测并阻止路径遍历
pm.get_output_path("../../../etc/passwd")
# 抛出 PathValidationError
```

### 2. session_id 清理
```python
# 自动清理危险字符
pm = PathManager("test/session\\with:bad")
print(pm.session_id)
# "test_session_with_bad"
```

### 3. 并发安全
```python
# 自动使用文件锁防止并发冲突
pm.ensure_directories()
# 内部使用 fcntl.flock() 保证原子性
```

---

## 最佳实践

1. **始终使用 PathManager**：不要手动拼接路径
2. **先 ensure_directories()**：在写入前确保目录存在
3. **验证路径**：使用 `validate_path()` 检查路径有效性
4. **捕获异常**：处理 `PathValidationError` 等异常
5. **使用域配置**：根据域选择正确的 PathManager 配置

---

## 迁移指南

### 旧代码
```python
# ❌ 手动拼接路径
prompt_path = Path(f"{deepflow_root}/blackboard/{session_id}/stages/planning_prompt.md")
```

### 新代码
```python
# ✅ 使用 PathManager
pm = PathManager(session_id, domain="solution")
prompt_path = pm.get_prompt_path("planning")
```

---

## 测试

```bash
# 运行 PathManager 测试
python3 -m pytest core/path_manager/test_path_manager.py -v
```

---

## 版本历史

- **v1.0** (2026-07-26): 初始版本，契约论实施，专家评审修复
