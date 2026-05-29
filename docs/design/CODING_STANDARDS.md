# DeepFlow 0.1.0 编码标准

> **版本**: 0.1.0 (V4.0)  
> **日期**: 2026-04-24

> 基于三个独立审计的综合发现制定
> - Style Auditor 1: 代码风格审计（P0×3, P1×5, P2×5, P3×3）
> - Style Auditor 2: API接口设计审计（P0×3, P1×6, P2×5）
> - Style Auditor 3: 防御性编程审计（P0×5, P1×4, P2×5, P3×5）

---

## 🚨 P0 严重问题总览（必须修复）

### 1. 日志格式不统一（P0-2, P0-5）

**问题**: `coordinator.py` 和 `pipeline_engine.py` 使用 f-string 嵌入变量到日志消息，破坏结构化日志解析

**错误模式**:
```python
# ❌ 错误
coordinator.py:517
logger.info(f"Using cached result: {request_id}", score=existing_result.score)

# ✅ 正确（与 resilience_manager.py 一致）
logger.info("Using cached result", request_id=request_id, score=existing_result.score)
```

**修复优先级**: 🔴 最高 — 影响生产环境日志可观测性

---

### 2. Score 尺度混用（P0-2, P0-3, P1-5）

**问题**: `config_loader.py` 使用 0-1 尺度，`quality_gate.py` 要求 0-100 尺度，导致质量门失效

**影响链**:
```
config_loader.py::QualityDimension.threshold (0-1)
    ↓
coordinator.py 构造 DimensionConfig (未转换)
    ↓
quality_gate.py 期望 0-100，得到 0.70
    ↓
所有输出都自动 PASS（最低分也有 40-55 基线）
```

**修复方案**:
```python
# coordinator.py 中统一转换
dims.append(DimensionConfig(
    name=dim.name,
    weight=dim.weight,
    threshold=dim.threshold * 100,  # 0-1 → 0-100
))
```

或使用 `coding_standards.py` 提供的转换器:
```python
from coding_standards import ScoreScaleConverter

threshold_100 = ScoreScaleConverter.to_0_100(threshold_0_1)
```

---

### 3. 导入不存在的类（P0-1）

**问题**: `coordinator.py:180-181` 尝试从 `resilience_manager` 导入 `RetryConfig` 和 `CircuitBreakerConfig`，但这两个类**不存在**

**修复方案**:
```python
# ❌ 删除这行
from resilience_manager import ResilienceManager, RetryConfig, CircuitBreakerConfig

# ✅ 改为传递 Dict
resilience_manager = ResilienceManager({
    "max_retries": getattr(resilience_config, "max_retries", 2),
    "agent_timeout": getattr(resilience_config, "agent_timeout", 120),
    "circuit_failure_threshold": getattr(resilience_config, "circuit_breaker_threshold", 5),
})
```

---

### 4. 裸 except 捕获（P0-4）

**位置**: `blackboard_manager.py:175`

**错误模式**:
```python
# ❌ 危险
except:
    pass
```

**修复**:
```python
# ✅ 安全
except OSError:
    pass
```

---

### 5. os.write() 不检查返回值（P0-5）

**位置**: `blackboard_manager.py`

**修复**:
```python
written = os.write(fd, data)
if written != len(data):
    raise IOError(f"Partial write: {written}/{len(data)} bytes")
```

---

## 📋 规范清单

### 日志规范

| 规则 | 级别 | 说明 |
|:---|:---:|:---|
| 禁止 f-string 日志 | P0 | `logger.info(f"msg: {var}")` → `logger.info("msg", var=var)` |
| 使用 Observability logger | P1 | 统一 `Observability.get_logger("module_name")` |
| 命名 snake_case | P1 | `"pipeline_engine"` 而非 `"v3.obs"` |
| 删除死 import logging | P0 | 6个模块都有冗余 import |

### Score 尺度规范

| 模块 | 尺度 | 说明 |
|:---|:---:|:---|
| `ConfigLoader` | 0-1 | `QualityDimension.threshold` |
| `QualityGate` | 0-100 | `DimensionConfig.threshold` |
| `Observability` | 0-1 | `record_quality_score` 要求 |
| `PipelineEngine` | 0-100 | 内部质量分存储 |

**转换规则**:
```python
from coding_standards import ScoreScaleConverter

# 自动检测并转换
converted = ScoreScaleConverter.auto_convert(
    score=0.85, 
    from_scale="0-1", 
    to_scale="0-100"
)  # → 85.0
```

### 类型注解规范

| 规则 | 级别 | 说明 |
|:---|:---:|:---|
| 参数类型注解 | P1 | 所有参数必须有类型 |
| 返回类型注解 | P1 | 所有方法必须有返回类型 |
| 覆盖率 ≥90% | P1 | 使用 mypy 检查 |

**模板**:
```python
from config_loader import PipelineStage, AgentConfig

async def _execute_agent_single(
    self, 
    stage: PipelineStage, 
    agent_config: AgentConfig, 
    instance: Dict[str, str], 
    input_context: str
) -> StageResult:
```

### Import 规范

**三段式顺序**（段间空一行）:
```python
# 1. stdlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 2. third-party
import yaml

# 3. local
from observability import Observability
```

### 命名规范

| 类型 | 规范 | 示例 |
|:---|:---|:---|
| 模块名 | snake_case | `pipeline_engine.py` |
| 类名 | PascalCase | `PipelineEngine` |
| 方法/函数 | snake_case | `execute_stage` |
| 常量 | UPPER_SNAKE_CASE | `DEFAULT_TIMEOUT = 120` |
| logger名 | snake_case模块名 | `Observability.get_logger("pipeline_engine")` |

### 防御性编程规范

| 规则 | 级别 | 说明 |
|:---|:---:|:---|
| 禁止裸 except | P0 | 必须捕获具体异常类型 |
| 检查 IO 返回值 | P0 | `os.write()`, `os.read()` 必须检查 |
| 验证输入参数 | P1 | 关键参数类型/范围检查 |
| None 值保护 | P1 | 可能返回 None 的地方显式处理 |
| 字典键存在性 | P1 | 使用 `.get()` 或 `in` 检查 |

---

## 🛠️ 使用编码风格检查器

### 命令行检查

```bash
# 检查单个文件
python coding_standards.py coordinator.py

# 检查整个目录
python coding_standards.py .deepflow/ --strict

# JSON 输出
python coding_standards.py .deepflow/ --json > audit_report.json
```

### 程序化使用

```python
from coding_standards import CodingStandardsChecker, ScoreScaleConverter
from pathlib import Path

# 检查单个文件
checker = CodingStandardsChecker(strict_mode=True)
report = checker.check_file(Path("coordinator.py"))

print(f"P0: {report.p0_count}, P1: {report.p1_count}")
for v in report.violations:
    print(f"  {v.file}:{v.line} — {v.description}")

# 尺度转换
score_100 = ScoreScaleConverter.to_0_100(0.85)  # → 85.0
score_0_1 = ScoreScaleConverter.to_0_1(85.0)   # → 0.85
```

### 生成规范代码模板

```python
from coding_standards import CodeTemplateGenerator

# 生成模块头部
template = CodeTemplateGenerator.module_header(
    "new_module",
    "新模块描述"
)
print(template)

# 生成方法模板
method = CodeTemplateGenerator.method_template(
    "execute_task",
    [("task_id", "str", ""), ("timeout", "int", "120")]
)
print(method)
```

---

## 📊 审计发现汇总

### 按级别统计

| 级别 | 数量 | 主要类别 |
|:---:|:---:|:---|
| **P0** | 11 | 日志格式、尺度混用、导入错误、裸except、IO检查 |
| **P1** | 15 | 类型注解、命名、import顺序、API不对称、私有属性访问 |
| **P2** | 15 | 文档、注释、代码结构 |

### 按模块统计

| 模块 | P0 | P1 | P2 | 最严重问题 |
|:---|:---:|:---:|:---:|:---|
| `coordinator.py` | 3 | 4 | 3 | 导入不存在类、score尺度 |
| `pipeline_engine.py` | 2 | 3 | 3 | 日志f-string、返回值不一致 |
| `config_loader.py` | 2 | 3 | 2 | 尺度定义、方法过长 |
| `quality_gate.py` | 1 | 2 | 2 | 尺度要求 |
| `resilience_manager.py` | 1 | 2 | 2 | None返回值、配置key不一致 |
| `blackboard_manager.py` | 2 | 1 | 1 | 裸except、os.write检查 |
| `observability.py` | 0 | 1 | 2 | logger命名、record_quality_score尺度 |

---

## ✅ 修复检查清单

### 立即修复（P0）

- [ ] `coordinator.py:180-181` — 删除 `RetryConfig`, `CircuitBreakerConfig` 导入
- [ ] `coordinator.py` — 添加 score 尺度转换 `* 100`
- [ ] `coordinator.py`, `pipeline_engine.py` — 替换所有 f-string 日志调用
- [ ] `blackboard_manager.py:175` — 裸 except 改为具体异常
- [ ] `blackboard_manager.py` — os.write() 检查返回值
- [ ] 6个模块 — 删除 `import logging`

### 短期修复（P1）

- [ ] 所有模块 — 统一 logger 命名为 snake_case 模块名
- [ ] `pipeline_engine.py` — 添加 `PipelineStage` 参数类型注解
- [ ] 所有模块 — 按 isort 三段式整理 import
- [ ] 所有模块 — docstring 统一为 Google style
- [ ] `coordinator.py` — 停止访问 `PipelineEngine` 私有属性
- [ ] `resilience_manager.py` — 统一配置 key 命名

### 中期改进（P2）

- [ ] 清理 23 处 `# V2.6-FIX:` 注释
- [ ] 提取魔法数字为模块级常量
- [ ] 添加 `pyproject.toml` 或 `ruff.toml` 配置
- [ ] 为 `Observability` 添加缺失的 `log()` 方法

---

## 🎯 关键成功指标

修复完成后，应达到：

| 指标 | 目标 |
|:---|:---:|
| P0 违规 | 0 |
| P1 违规 | ≤5 |
| 日志格式一致性 | 100% |
| Score 尺度一致性 | 100% |
| 类型注解覆盖率 | ≥90% |
| mypy 检查通过 | ✅ |

---

*规范版本: 1.0*
*最后更新: 2026-04-15*
