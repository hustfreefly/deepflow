---
id: contracts/coding_standards
version: "2.0.0"
updated: "2026-06-01"
---

# DeepFlow 编码规范

> **版本**: 2.0.0
> **生效日期**: 2026-05-30
> **适用范围**: `.deepflow/` 目录下所有 Python 代码

---

## 一、P0 规则（MUST — 零容忍）

### 1.1 禁止裸 except

```python
# ❌ NEVER
except:
    pass

# ❌ NEVER
except Exception:
    pass

# ✅ MUST — 捕获具体异常类型
except OSError:
    pass

except (ValueError, KeyError) as e:
    logger.warning("parse_error", error=str(e))
```

### 1.2 日志格式

```python
# ❌ NEVER — f-string 破坏结构化日志解析
logger.info(f"Using cached result: {request_id}")

# ✅ MUST — 使用 kwargs 传递变量
logger.info("Using cached result", request_id=request_id)
```

### 1.3 检查 IO 返回值

```python
# ❌ NEVER — 忽略写入结果
os.write(fd, data)

# ✅ MUST — 检查返回值
written = os.write(fd, data)
if written != len(data):
    raise IOError(f"Partial write: {written}/{len(data)} bytes")
```

### 1.4 禁止未使用的 import

```python
# ❌ NEVER
import logging  # 未使用
from typing import Optional  # 未使用

# ✅ MUST — 只导入实际使用的模块
```

### 1.5 Score 尺度统一

所有模块内部统一使用 **0-100** 尺度。如果外部输入是 0-1 尺度，必须在入口处转换：

```python
# ✅ MUST — 入口处转换
threshold_100 = threshold_0_1 * 100
```

---

## 二、P1 规则（SHOULD — 质量门禁）

### 2.1 类型注解

所有公开方法必须有参数类型注解和返回类型注解：

```python
# ✅ SHOULD
async def execute_stage(
    self,
    stage: PipelineStage,
    agent_config: AgentConfig,
    input_context: str
) -> StageResult:
    ...

# ❌ 不应出现
async def execute_stage(self, stage, agent_config, input_context):
    ...
```

### 2.2 Docstring

所有公开方法必须有 docstring（Google style）：

```python
# ✅ SHOULD
def calculate_score(self, dimensions: List[Dict]) -> float:
    """计算加权质量分数。

    Args:
        dimensions: 维度列表，每个维度包含 name、weight、score。

    Returns:
        加权总分（0-100）。
    """
```

### 2.3 文件长度

单文件 ≤ 500 行。超过则拆分。

### 2.4 日志命名

使用 snake_case 模块名作为 logger 名称：

```python
# ✅ SHOULD
logger = Observability.get_logger("pipeline_engine")

# ❌ 不应出现
logger = Observability.get_logger("v3.obs")
```

### 2.5 None 值保护

可能返回 None 的地方必须显式处理：

```python
# ✅ SHOULD
result = get_data()
if result is None:
    return default_value

# ❌ 不应出现
result = get_data()
value = result["key"]  # result 可能是 None
```

---

## 三、P2 规则（建议 — 代码质量）

### 3.1 Import 顺序（三段式）

```python
# 1. stdlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 2. third-party
import yaml

# 3. local
from core.quality.observability import Observability
```

段间空一行。

### 3.2 命名规范

| 类型 | 规范 | 示例 |
|:---|:---|:---|
| 模块名 | snake_case | `pipeline_engine.py` |
| 类名 | PascalCase | `PipelineEngine` |
| 方法/函数 | snake_case | `execute_stage` |
| 常量 | UPPER_SNAKE_CASE | `DEFAULT_TIMEOUT = 120` |
| logger 名 | snake_case 模块名 | `"pipeline_engine"` |

### 3.3 DRY 原则

重复代码必须提取为公共函数或方法。

### 3.4 魔法数字

提取为模块级常量：

```python
# ✅ SHOULD
MAX_RETRIES = 3
TIMEOUT_SECONDS = 120

# ❌ 不应出现
if retries > 3:
    ...
```

---

## 四、验证方式

### 4.1 编码规范检查

```bash
# 检查单个文件
python scripts/check_standards.py [module].py

# 检查所有模块
python scripts/check_standards.py --all
```

### 4.2 LLM 检查

LLM 在代码审查时应逐项检查：

| 检查项 | 方法 |
|--------|------|
| 裸 except | 搜索 `except:` 和 `except Exception:` |
| f-string 日志 | 搜索 `logger.*f"` |
| IO 返回值 | 检查 `os.write` / `os.read` 调用 |
| 类型注解 | 检查所有 `def` 的参数和返回值 |
| 未使用 import | 对比 import 列表和实际使用 |

---

## 五、关键成功指标

| 指标 | 目标 |
|:---|:---:|
| P0 违规 | 0 |
| P1 违规 | ≤ 5 |
| 日志格式一致性 | 100% |
| 类型注解覆盖率 | ≥ 90% |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-04-24 | 初始版本（基于三次审计） |
| 2.0.0 | 2026-05-30 | 重写：删除历史审计数据，保留纯规范定义 |
