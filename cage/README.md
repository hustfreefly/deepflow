# 契约笼子（Contract Cage）

> DeepFlow V1.0 单个模块开发质量保障系统  
> **核心理念**：AI 在契约约束下写代码，写完必须通过所有检查才能算完成

---

## 一、契约笼子的四层约束

```
┌─────────────────────────────────────┐
│         契约笼子（Cage）              │
│                                     │
│  L1: 接口契约  ← 方法签名 + 类型     │
│  L2: 行为契约  ← 输入/输出/边界      │
│  L3: 验证脚本  ← 契约测试 + 规范检查  │
│  L4: 编码规范  ← P0/P1 自动化检查    │
│                                     │
└─────────────────────────────────────┘
```

## 二、契约文件规范

### 2.1 位置

```
cage/[module].yaml     ← 每个模块一个契约文件
```

### 2.2 大小限制（分级）

| 复杂度 | 方法数 | 大小限制 |
|:---|:---|:---|
| **simple** | ≤10 | 2KB |
| **medium** | 10-30 | 5KB |
| **complex** | >30 | 10KB |

在契约文件中声明 `complexity` 字段自动应用对应限制。

### 2.3 必需字段

```yaml
module: "模块名"              # 必填
version: "1.0"               # 必填

interface:                   # 必填：接口签名
  method_name(param: type) -> ReturnType

behavior:                    # 必填：行为契约
  method_name:
    input:
      param: "类型 + 约束"
    output:
      type: "返回类型"
      constraints: ["约束条件"]
    success: "成功时行为"
    failure: "失败时行为"

boundaries:                  # 必填：边界条件
  - "边界条件 1"
  - "边界条件 2"
```

### 2.4 可选字段

```yaml
dependencies:                # 依赖的其他模块
  - module.method

examples:                    # 使用示例
  method_name: |
    # 代码示例
```

---

## 三、契约笼子执行流程

```
Step 1: 写契约 YAML（cage/[module].yaml）
  └── 定义：接口 + 行为 + 边界（≤ 2KB）

Step 2: 写验证脚本（tests/contract/test_[module].py）
  └── 定义：契约测试 + 边界测试

Step 3: 实现代码（[module].py）
  └── 在笼子约束下写代码

Step 4: 自动验证（AI 自己跑）
  ├── Step 4.1: 契约验证
  │     python cage/validate.py [module]
  │     └── 通过 → 继续
  │     └── 失败 → 返工
  │
  ├── Step 4.2: 编码规范检查
  │     python cage/check_standards.py [module].py
  │     └── P0=0 → 继续
  │     └── P0>0 → 返工
  │
  └── Step 4.3: 导入验证
        python -c "from deepflow.[module] import *"
        └── 成功 → 完成
        └── 失败 → 返工

Step 5: 写入 PROGRESS → 进入下一模块
```

---

## 四、验证脚本

### 4.1 契约验证（cage/validate.py）

```bash
# 验证单个模块契约
python cage/validate.py config_loader

# 验证所有模块契约
python cage/validate.py --all
```

**检查内容**：
- 契约文件存在且格式正确
- 契约文件大小符合复杂度分级
- 契约包含所有必需字段
- 契约与代码实现对齐（方法签名一致）
- 依赖验证（dependencies 声明的依赖在代码中实际调用）
- 自动发现模块（从 cage/*.yaml 动态扫描，不硬编码）

### 4.2 编码规范检查（cage/check_standards.py）

```bash
# 检查单个模块
python cage/check_standards.py config_loader.py

# 检查所有模块
python cage/check_standards.py --all
```

**检查内容**：
| 检查项 | 级别 | 标准 |
|:---|:---|:---|
| bare except | P0 | 0（zero tolerance）|
| 未使用导入 | P0 | 0 |
| 未定义变量 | P0 | 0 |
| 类型注解缺失 | P1 | 所有公开方法必须有 |
| Docstring 缺失 | P1 | 所有公开方法必须有 |
| 单文件超 500 行 | P1 | 超过则拆分 |
| 重复代码 | P2 | 零容忍（DRY）|

---

## 五、质量门禁

每个模块开发完成后必须通过：

```
□ 契约文件存在（cage/[module].yaml，≤ 2KB）
□ 契约验证通过（python cage/validate.py [module]）
□ 编码规范 P0=0（python cage/check_standards.py [module].py）
□ 契约测试全通过（python -m pytest tests/contract/test_[module].py）
□ 导入验证通过（python -c "from deepflow.[module] import *"）
```

**任何一项不通过，不得进入下一模块。**

---

## 六、模块契约清单

| 模块 | 契约文件 | 状态 |
|:---|:---|:---|
| ConfigLoader | `cage/config_loader.yaml` | ⬜ 待创建 |
| BlackboardManager | `cage/blackboard_manager.yaml` | ⬜ 待创建 |
| Observability | `cage/observability.yaml` | ⬜ 待创建 |
| QualityGate | `cage/quality_gate.yaml` | ⬜ 待创建 |
| ResilienceManager | `cage/resilience_manager.yaml` | ⬜ 待创建 |
| PipelineEngine | `cage/pipeline_engine.yaml` | ⬜ 待创建 |
| Coordinator | `cage/coordinator.yaml` | ⬜ 待创建 |

---

*契约笼子版本: V1.0 | 2026-04-18*  
*核心理念: 在笼子里写代码，写完必须通过所有检查*
