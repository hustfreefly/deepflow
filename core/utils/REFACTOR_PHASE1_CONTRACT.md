# Phase 1 替换契约

## 输入模式（旧代码）

### 模式 A: 静态方法定义
```python
@staticmethod
def _atomic_write_json(path: Path, data: dict) -> None:
    """原子写 JSON..."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(...)
    try:
        ...
    except:
        ...
```

### 模式 B: 模块级函数定义
```python
def atomic_write_json(path: Path, data: dict) -> None:
    """原子写 JSON..."""
    ...
```

### 模式 C: 方法调用
```python
self._atomic_write_json(path, data)
# 或
atomic_write_json(path, data)
```

## 输出模式（新代码）

### 替换后
```python
from core.utils.atomic_io import atomic_write_json

# 调用改为
atomic_write_json(path, data)
```

## 验证契约

1. 每个文件替换后立即运行 `pytest domains/{domain}/tests/`
2. 全量替换后运行 `pytest .deepflow/` 确保无回归
3. 检查无残留的 `tempfile.mkstemp` + `os.replace` 模式

## 替换顺序

1. `deliver_pro/wp_runner.py`（最简单，2 处调用）
2. `deliver_pro/orchestrator.py`（5 处调用）
3. `solution_pro/pulse.py`（5 处调用）
4. `spec_pro/merge_spec.py`（3 处调用）
