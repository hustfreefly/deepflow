# Ship Package 改进方案 2.0.0（基于 3 位 AI Native 专家评审修订）

> **日期**: 2026-06-26  
> **版本**: 2.0.0（评审后修订版）  
> **状态**: 待执行

---

## 评审修订摘要

| 评审意见 | 采纳 | 修订内容 |
|:---|:---:|:---|
| LLM 生成缺乏上下文锚定 | ✅ | api_conventions / integration_tests 强制注入 WP 接口作为锚定 |
| error_handling 放错位置 | ✅ | 从 Specifier 提升到 Packager，改为 `error_handling_principles`（项目级原则） |
| 无规范演化/override 机制 | ✅ | 增加 `convention_overrides` 字段，Hermes 可标记 override |
| environment 不该让 LLM 决定 | ✅ | environment 完全确定性生成（代码检测 import + 固定模板） |
| 缺乏渐进信任路径 | ✅ | 新增 confidence 字段 + Phase 1-3 演进路径 |

---

## 改进项（4 个 → 3 个 + 1 确定性）

### 1. api_conventions（LLM 生成 + 强锚定 + override 机制）

**生成者**: Packager（LLM）  
**锚定输入**: work_packages 列表 + 每个 WP 的 outputs 字段  
**契约笼子**:
```python
class ApiConvention(BaseModel):
    naming_style: Literal["snake_case", "camelCase", "PascalCase"]
    method_prefixes: dict[str, list[str]]  # {"write": ["write_", "set_"], "read": ["read_", "get_"]}
    parameter_style: Literal["dict", "kwargs", "positional", "dataclass"]
    rules: list[str]  # 5-8 条规则，必须引用实际 WP 中出现的模块名
    examples: list[dict]  # 正反例，correct/incorrect 必填
    confidence: Literal["high", "medium", "low"]  # LLM 自评估
    convention_overrides: list[dict] = []  # Hermes 执行时可标记 override
```

**防幻觉护栏**:
- rules 中引用的模块名必须存在于 work_packages 的 module_id 列表
- confidence=low → 自动降级为 null，记录到 risk_register
- gate 检查：rules 数量 5-8，examples 数量 3-5，naming_style 是合法枚举

**override 机制**:
- Hermes 执行时可添加 `convention_overrides`：`[{rule_index, reason, alternative}]`
- 下次 Ship Pro 生成时读取历史 overrides，调整规范

### 2. integration_tests（LLM 生成 + 组件锚定）

**生成者**: Packager（LLM）  
**锚定输入**: dependency_graph + work_packages 列表  
**契约笼子**:
```python
class IntegrationTest(BaseModel):
    name: str
    description: str
    components: list[str]  # 必须引用 work_packages 中存在的 module_id
    scenario: str
    expected_result: str  # 必须包含可量化指标（禁止"正常""符合预期"）
    confidence: Literal["high", "medium", "low"]
```

**防幻觉护栏**:
- components 中每个元素必须存在于 work_packages 列表
- expected_result 禁止模糊表述（gate 检查：不包含"正常""符合预期""工作良好"）
- confidence=low → 自动降级

### 3. error_handling_principles（LLM 生成 + 项目级原则）

**生成者**: Packager（LLM）— 从 Specifier 提升到 Packager  
**锚定输入**: work_packages 的 constraints + acceptance_criteria  
**契约笼子**:
```python
class ErrorHandlingPrinciples(BaseModel):
    principles: list[str]  # 3-5 条项目级原则（如"所有外部 API 调用必须有重试"）
    exception_categories: list[str]  # 异常分类（不超过 WP 数量的 50%）
    max_retry_limit: int = 5  # 全局重试上限
    confidence: Literal["high", "medium", "low"]
```

**防幻觉护栏**:
- exception_categories 数量 ≤ work_packages 数量 × 0.5
- max_retry_limit 必须有值且 ≤ 10
- 具体异常类型和重试策略由 Codex 根据原则自行决定（给自由度）

### 4. environment（确定性生成，0 LLM）

**生成者**: 确定性代码（不是 LLM）  
**契约笼子**:
```python
class EnvironmentSpec(BaseModel):
    python: str  # 从代码检测或固定 ">=3.10"
    dependencies: list[str]  # 从 import 语句扫描
    test_dependencies: list[str]  # 固定 ["pytest>=7.0"]
    test_runner: str = "pytest"
    test_command: str = "pytest -v"
```

**生成逻辑**:
1. 扫描 work_packages 的 context_files 中的 import 语句
2. 过滤标准库（用 `sys.stdlib_module_names`）
3. 剩余 → dependencies 列表
4. python 版本固定 `">=3.10"`
5. **0 LLM 调用**

---

## 实施计划（契约笼子执行）

| Phase | 内容 | 文件 |
|:---|:---|:---|
| **S1** | 4 个 Pydantic Contract | `contracts/ship_package_extras.py` |
| **S2** | Packager prompt 更新 | `prompts/packager.md`（注入锚定上下文） |
| **S3** | environment 确定性生成 | `scripts/generate_environment.py` |
| **S4** | gate_packager 扩展 | `eval/gates.py`（格式检查 + 引用验证） |
| **S5** | Judge prompt 更新 | `prompts/ship_judge.md`（语义评估新字段） |
| **S6** | 端到端验证 | 用现有数据验证 |

总计: ~60 分钟
