# DeepFlow Core 模块文档

> **通用核心模块**：跨域复用的基础组件

---

## 模块清单

| 模块 | 文件 | 功能 | 状态 |
|------|------|------|:----:|
| **PromptUtils** | `prompt_utils.py` | Prompt 加载/渲染/大小检查/注入检测 | ✅ 已完成 |
| **PathManager** | `path_manager/` | 路径拼接/校验/防遍历 | ✅ 已完成 |
| **ProcessManager** | `process_manager/` | spawn-yield 可靠性/stall 检测/完成确认 | ✅ 已完成 |
| **QualityUtils** | `quality_utils.py` | Schema 验证/覆盖率检查/锚点检查 | ✅ 已完成 |
| **ConservationUtils** | `conservation_utils.py` | 信息守恒验证（semantic_anchors） | ✅ 已完成 |

---

## 模块详情

### PromptUtils

**文件**: `prompt_utils.py`  
**API 文档**: [`docs/prompt_utils_api.md`](docs/prompt_utils_api.md)  
**测试**: `test_prompt_utils.py`

**核心函数**:
- `load_prompt(path)` — 加载 prompt（剥离 Front Matter）
- `render_prompt(path, **vars)` — 变量替换（双花括号必需/单花括号可选）
- `check_task_size(text)` — 大小检查（2KB warn / 6KB block）
- `detect_injection(text)` — 注入检测（7 种危险模式）
- `validate_all(path, vars)` — spawn 前完整预检

**解决的问题**:
- V39 截断（28KB prompt 塞进 sessions_spawn）
- V34-V37 灌入（外部内容注入 prompt）
- 重复代码（每个域都要手动实现）

---

### PathManager

**文件夹**: `path_manager/`  
**API 文档**: `path_manager/API.md`

**核心功能**:
- 路径拼接（blackboard/session/project）
- 路径校验（防遍历、防特殊字符）
- 跨域统一（Solution/Ship/Deliver 共用）

---

### ProcessManager

**文件夹**: `process_manager/`  
**API 文档**: `process_manager/API.md`

**核心功能**:
- spawn-yield 可靠性（stall 检测、超时处理）
- 完成确认（文件存在性 + 大小 + JSON 可解析）
- 错误恢复（自动重试、降级策略）

---

### QualityUtils

**文件**: `quality_utils.py`  
**测试**: `test_quality_utils.py`（39 个测试用例）

**核心函数**:
- `check_schema(data, required_fields, field_types)` — L1 Schema 验证
- `check_coverage(requirements, output, critical_threshold, warning_threshold)` — L2 需求覆盖率检查（双层阈值）
- `check_anchors(anchors, output, critical_threshold, warning_threshold)` — L1 锚点保留检查（双层阈值）
- `aggregate_gate_results(results)` — 聚合多个检查结果

**Pydantic 契约**:
- `CheckResult(check, passed, message, severity)`
- `CoverageResult(total_reqs, covered_reqs, coverage_rate, uncovered, passed, severity)`
- `GateResult(passed, results, summary)`

**解决的问题**:
- 三域 Gate 标准不统一
- V38 文件判别标准不对齐
- 双层阈值支持（0.5 critical / 0.8 warning）

---

### ConservationUtils

**文件**: `conservation_utils.py`  
**测试**: `test_conservation_utils.py`（27 个测试用例）

**核心函数**:
- `verify_anchors(upstream_data, downstream_data, threshold)` — 验证 semantic_anchors 保留率

**Pydantic 契约**:
- `ConservationResult(ok, preserved, lost, alignment_rate, verdict)`

**解决的问题**:
- 跨域信息流断裂（最频繁故障类型）
- P2 原则（信息守恒）无统一验证

---

## 使用约定

### 引用方式

```python
from core.prompt_utils import render_prompt, check_task_size
from core.quality_utils import check_schema
from core.conservation_utils import verify_anchors
```

### 契约锁定

所有 `core/` 模块遵循**契约锁定**原则：
- 函数签名不变
- 输入输出类型不变
- 行为语义不变

升级时：内部实现可优化，但不改签名、不改语义。

---

## 开发规范

1. **纯函数优先**：无状态、可测试、可组合
2. **fail-fast**：不静默降级，早期暴露问题
3. **Pydantic 契约**：输入输出通过 Pydantic 验证
4. **测试覆盖**：每个函数至少 5 个测试用例（正常/异常/边界）

---

**文档版本**: v1.0  
**最后更新**: 2026-07-27
