# 专家评审报告：Contract-First 设计与 API 治理视角

**评审专家**: Contract-First 设计与 API 治理专家  
**评审日期**: 2026-06-23  
**评审对象**: DeepFlow Contract Layer 提案  

---

## 一、核心判断（TL;DR）

**诊断基本准确，但方案可能过度工程化。**

"缺少合同层"确实是根因之一，但 Contract Layer 提案试图解决的是"5份独立文档同步"问题，而实际更紧迫的是"执行路径分裂"和"状态管理混乱"问题。

**我的建议**: 先解决执行路径统一和状态机集中化，再考虑是否需要完整的 Contract Layer。对于当前规模的系统，OpenAPI-style spec + 轻量级代码生成可能已足够。

---

## 二、逐项分析

### 2.1 Contract-First 是否适用于 DeepFlow？

#### 传统 Contract-First 的适用边界

传统 Contract-First（OpenAPI/gRPC）适用于：
- **网络边界清晰的系统**: Client/Server 通过 HTTP/gRPC 通信
- **多语言/多团队环境**: 需要生成不同语言的 stub
- **长期演进的公共 API**: 需要版本管理和向后兼容

#### DeepFlow 的特殊性

DeepFlow 是**进程内多 Agent 协作系统**：
- 组件间通过文件系统（blackboard）通信，非网络调用
- 所有 Agent 都是 Python + LLM，无多语言需求
- "API" 实际上是 Prompt 的输出格式约定，非真正的网络 API

#### contract.yaml 的设计评估

提案中的 `contract.yaml` 示例：

```yaml
output:
  required_fields:
    project_type: { type: string, enum: [...] }
    requirements:
      items:
        mapped_components: { type: array, required: true }
```

**问题**：
1. **这不是标准格式**: 既非 OpenAPI，也非 JSON Schema，也非 protobuf。需要维护自定义解析器。
2. **表达能力不足**: 无法表达复杂的嵌套验证规则（如"如果 type=X，则必须包含 Y"）
3. **与 LLM 的天然矛盾**: LLM 输出是概率性的，contract 是确定性的。128 个 schema 错误恰恰证明了这一点。

**建议**: 如果一定要做 Contract Layer，直接使用 **JSON Schema**（已经是 Schema 组件的格式）或 **Pydantic v2**（Python 原生），而非发明新格式。

---

### 2.2 单向生成 vs 双向同步

#### 这是 Contract-First 的经典陷阱

提案说"从 contract 自动生成 Prompt/Gate/Schema"，但实践中：

```
开发者修改 Prompt 测试 → 发现需要新字段 → 修改 contract → 重新生成 → 又破坏其他东西
```

**双向同步的三种策略**:

| 策略 | 优点 | 缺点 | 适用场景 |
|:---|:---|:---|:---|
| **单向生成** (提案方案) | 简单，单一数据源 | 灵活性差，开发者体验差 | 大型团队，严格治理 |
| **双向同步** | 灵活 | 复杂，容易冲突 | 成熟团队，有自动化工具 |
| **契约即代码** (Code-as-Contract) | 开发者友好 | 需要强类型语言 | Python + Pydantic |

#### 对 DeepFlow 的建议

**采用"契约即代码"模式**：

```python
# agents/architect/contract.py
from pydantic import BaseModel, Field
from typing import Literal, List

class ArchitectOutput(BaseModel):
    project_type: Literal["web_app", "data_pipeline", "api_service"]
    modules: List[Module] = Field(min_length=1)
    requirements: List[Requirement]
    
class Requirement(BaseModel):
    mapped_components: List[str]  # required by Gate
    
    # 自动生成 Gate 检查代码
    @classmethod
    def gate_checks(cls) -> List[Callable]:
        return [
            lambda x: len(x.mapped_components) > 0,
            # ...
        ]
```

**好处**:
- 使用标准 Pydantic，无自定义格式
- 类型定义即契约，Gate 检查可直接从类型推导
- Prompt schema 段落可从 model_json_schema() 生成

---

### 2.3 Schema Evolution

#### 当前问题分析

128 个 schema 错误的本质是：
- `ship_package.json` 的 `_meta` 在顶层（schema 不允许）
- `meta.input_format` 用 `"A"` 而非 `"A_final_solution"`
- `model_tier` 用 `"standard"` 而非枚举值

**这不是 schema evolution 问题，这是基本类型不匹配问题。**

#### Schema Evolution 的正确姿势

如果 DeepFlow 真的需要处理 schema 变更，应该考虑：

```python
# 版本化 schema 注册表
@schema_registry.register(version="3.0")
class ShipPackageV3(BaseModel):
    meta: PackageMeta
    work_packages: List[WorkPackage]
    
@schema_registry.register(version="2.0", deprecated=True)
class ShipPackageV2(BaseModel):
    # 旧版本，支持迁移
    ...

# 自动迁移
def migrate_v2_to_v3(v2_data: dict) -> ShipPackageV3:
    # 显式迁移逻辑
    ...
```

**但对当前 DeepFlow**：
- 128 个错误说明连基本类型都没对齐，谈 evolution 为时过早
- 建议先解决"Prompt 和 Schema 用同一套类型定义"，再考虑版本管理

---

### 2.4 治理模型

#### 关键问题：谁有权修改 contract？

提案没有回答这个问题。在单人维护项目中，可能的模式：

| 模式 | 描述 | 适用 |
|:---|:---|:---|
| **自由修改** | 任何人可改，CI 验证 | 小型团队，快速迭代 |
| **PR 审查** | 修改需审查，Gate 测试通过 | 中型团队 |
| **版本冻结** | Contract 版本化，修改需升级版本 | 大型系统，多团队协作 |

#### 对 DeepFlow 的判断

**当前规模下，严格治理是过度工程化。**

建议的轻量级治理：
1. **Pydantic 模型即契约**（代码层面）
2. **CI 运行 schema 验证**（自动化检查）
3. **修改前运行端到端测试**（质量保证）

无需单独的 contract approval 流程。

---

### 2.5 最小可行方案（MVP）

如果 Contract Layer 太重，更轻量的方案：

#### 方案 A：Pydantic 统一类型（推荐）

```
agents/
  architect/
    __init__.py
    types.py          # Pydantic 模型 = 契约
    prompt.md         # 引用 types.py 生成 schema 段落
    gate.py           # 从 types.py 自动生成检查
```

**实施步骤**:
1. 将 `ship_package_v3.schema.json` 转为 `ship_package/types.py`
2. Prompt 模板从 `types.py` 动态生成 schema 描述
3. Gate 从 `types.py` 自动生成字段检查
4. 删除独立的 JSON Schema 文件

**工作量**: 2-3 天  
**收益**: 消除 128 个 schema 错误的主要来源

#### 方案 B：OpenAPI 子集

如果坚持外部契约文件：

```yaml
# ship_package.openapi.yaml
openapi: 3.0.0
components:
  schemas:
    ShipPackage:
      type: object
      properties:
        meta:
          $ref: '#/components/schemas/PackageMeta'
```

**工具链**:
- `datamodel-codegen` 生成 Pydantic 模型
- `openapi-generator` 生成文档

**缺点**: 仍然需要维护同步，且 OpenAPI 表达能力不如 Pydantic 直接。

---

### 2.6 128 个 Schema 错误的深层含义

#### 错误分类

| 错误类型 | 数量估计 | 根因 | 修复策略 |
|:---|:---:|:---|:---|
| 类型不匹配 | ~60 | Prompt 输出与 Schema 定义不同 | 统一类型定义 |
| 必填字段缺失 | ~40 | Prompt 未要求，Schema 要求了 | 调整必填/可选 |
| 枚举值错误 | ~20 | 字符串硬编码 vs 枚举定义 | 统一枚举定义 |
| 结构错误 | ~8 | `_meta` 位置等 | 修正结构定义 |

#### 核心洞察

**128 个错误不是"spec 太严格"，而是"实现太随意" + "契约未共享"。**

在传统 API 治理中，这相当于：
- 后端实现返回 `"status": "ok"`
- 但 OpenAPI spec 定义的是 `"status": {"enum": ["success", "error"]}`

**这不是治理过度，是治理缺失。**

---

## 三、盲点与遗漏

### 3.1 LLM 输出的概率性本质

Contract Layer 假设 LLM 输出可以被确定性 schema 约束。但：
- LLM 可能"幻觉"出额外字段
- LLM 可能用近似值而非精确枚举（如用 `"standard"` 而非 `"claude-opus"`）
- LLM 可能忽略"必填"要求

**建议**: Contract Layer 应该包含**输出后处理层**：
```python
# 在 Gate 之前添加
normalized_output = llm_output.post_process(
    coerce_types=True,      # 自动类型转换
    fill_defaults=True,     # 填充默认值
    remove_extra=True       # 删除额外字段
)
```

### 3.2 执行路径分裂是更紧迫的问题

评审材料提到：
- SKILL.md 描述 V2 流程
- run_pipeline.py 实现 V3 流程
- orchestrator.py 是第三条路

**这比"缺少 Contract Layer"更致命。**

建议优先级：
1. **P0**: 统一执行路径（删除 SKILL.md 流程描述，只保留 run_pipeline.py）
2. **P1**: 集中状态管理（消除 `.completed.json` vs `.stage_progress.json` 分裂）
3. **P2**: 统一类型定义（Pydantic 方案）
4. **P3**: 完整的 Contract Layer

### 3.3 Prompt 工程 vs 契约约束

Contract Layer 无法解决 Prompt 工程问题：
- Prompt 可能描述不清导致 LLM 误解
- Few-shot 示例可能与 schema 不一致

**建议**: Contract Layer 应该包含 **Prompt 验证**：
```python
# 验证 Prompt 中的 schema 描述与契约一致
assert "project_type" in prompt.template
assert prompt.schema_description == contract.field_description("project_type")
```

---

## 四、建议与优先级

### 4.1 立即执行（本周）

1. **统一执行路径**
   - 删除 SKILL.md 中的流程描述
   - 所有 Agent 通过 `run_pipeline.py` CLI 调用
   - 删除 `orchestrator.py` 中的重复逻辑

2. **修复 128 个 schema 错误**
   - 选择 10 个高频错误，对齐 Prompt 和 Schema
   - 添加 Gate 后处理层处理类型不匹配

### 4.2 短期优化（本月）

3. **Pydantic 统一类型**
   - 将核心数据结构转为 Pydantic 模型
   - Prompt schema 段落从模型自动生成
   - Gate 检查从模型自动推导

4. **集中状态管理**
   - 单一状态机（`pipeline_status.json`）
   - 删除 `.completed.json` 等冗余状态文件

### 4.3 长期考虑（视情况而定）

5. **评估是否需要完整 Contract Layer**
   - 如果 Pydantic 方案解决 90% 问题，无需额外 Contract Layer
   - 如果多 Agent/多版本问题出现，再考虑版本化契约

---

## 五、总结

| 维度 | 评估 |
|:---|:---|
| 诊断准确性 | ⭐⭐⭐⭐☆ "缺少合同层"是症状，不是唯一根因 |
| 方案可行性 | ⭐⭐⭐☆☆ Contract Layer 可行但可能过度设计 |
| 实施优先级 | 执行路径统一 > 状态管理 > 类型统一 > Contract Layer |
| 推荐方案 | Pydantic 统一类型（轻量级）而非自定义 contract.yaml |

**最终建议**:

> 不要为了解决"5份文档同步"问题而引入第6份文档（contract.yaml）。
> 
> 先用 Pydantic 把类型定义变成代码，让代码成为唯一真相源。
> 当代码层面的统一被证明不够时，再考虑更重的 Contract Layer。

---

*报告完成*
