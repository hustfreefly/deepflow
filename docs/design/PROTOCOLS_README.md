# protocols.py — DeepFlow 接口协议层说明书

> **角色**：接口说明书（非运行时依赖）  
> **版本**：0.1.0 (V4.0) — 历史文档  
> **日期**：2026-04-14  
> **位置**：`/Users/allen/.openclaw/workspace/protocols.py`

---

## 一、这个文件是什么

`protocols.py` 是 DeepFlow 多 Agent 系统的**接口协议层**，定义了 6 个核心模块的：

1. **接口协议**（Protocol）— 每个模块的方法签名契约
2. **数据契约**（dataclass/Enum）— 各模块间传递的数据结构
3. **尺度转换**（工具函数）— 解决 0-1 vs 0-100 评分尺度不一致问题
4. **模块接口地图**（MODULE_INTERFACES）— 模块间的依赖关系

### 它不是什么

- ❌ **不是运行时依赖** — 没有任何实际模块 import 它
- ❌ **不是适配器** — 它不改变任何模块的行为
- ❌ **不是新代码** — 所有定义都基于现有代码，不发明新方法

### 类比

| 类比 | 说明 |
|------|------|
| 📖 字典 | 告诉你单词怎么拼，但不参与你说话 |
| 📐 蓝图 | 描述建筑应该什么样，但不是建筑本身 |
| 📋 合同 | 规定双方义务，但不替你履约 |

---

## 二、核心内容

### 2.1 尺度声明

```python
DeepFlow_SCORE_SCALE = "0-100"  # 全局统一尺度声明
```

**问题背景**：DeepFlow 系统存在两套评分尺度：
- `QualityGate` 使用 0-100 尺度
- `ConfigLoader.DomainQualityConfig` 使用 0-1 尺度

**解决**：统一声明 0-100 为标准尺度，提供转换函数。

### 2.2 尺度转换函数

| 函数 | 用途 | 示例 |
|------|------|------|
| `scale_01_to_100(value)` | 0-1 → 0-100 | `scale_01_to_100(0.85) = 85.0` |
| `scale_100_to_01(value)` | 0-100 → 0-1 | `scale_100_to_01(85.0) = 0.85` |
| `convert_domain_quality_to_gate_quality(config)` | 完整配置转换 | ConfigLoader → QualityGate |

### 2.3 7 个 Protocol 接口

| Protocol | 方法数 | 对应模块 | 说明 |
|----------|--------|---------|------|
| `IPipelineEngine` | 14 | pipeline_engine.py | FSM 执行引擎 |
| `IQualityGate` | 9 | quality_gate.py | 质量门控 |
| `IResilienceManager` | 18 | resilience_manager.py | 四层故障隔离 |
| `ICircuitBreaker` | 5 | resilience_manager.py 内部类 | 熔断器 |
| `IObservability` | 14 | observability.py | 可观测性（纯静态方法） |
| `IBlackboardManager` | 14 + 6 常量 | blackboard_manager.py | 数据总线 |
| `IConfigLoader` | 5 | config_loader.py | 配置加载 |

### 2.4 数据契约

所有 dataclass 和 Enum 都**严格基于实际代码**定义：

- `PipelineState` — 7 个 FSM 状态
- `StageResult` / `PipelineResult` — 执行结果
- `QualityConfig` / `QualityReport` / `DimensionScore` — 质量评估
- `Task` / `Result` / `Checkpoint` — 韧性管理
- `DomainConfig` / `PipelineTemplate` — 配置层
- `BlackboardConfig` — 数据层

### 2.5 模块接口地图

```
Layer 0: PipelineEngine (唯一 hub，入口模块)
         ↓    ↓    ↓    ↓    ↓
Layer 1: CL   BB   QG   RM   Obs (互相零依赖)
```

| 模块 | 依赖谁 | 被谁依赖 |
|------|--------|---------|
| PipelineEngine | CL, BB, QG, RM, Obs | 无（入口） |
| QualityGate | 无 | PipelineEngine |
| ResilienceManager | 无 | PipelineEngine |
| Observability | 无 | PE, QG, RM（横切） |
| BlackboardManager | 无 | PipelineEngine |
| ConfigLoader | 无 | PipelineEngine |

### 2.6 验证工具

```python
# 单个协议验证
@validate_protocol(IQualityGate)
class MyQualityGate: ...

# 批量验证
missing = validate_all_protocols(MyEngine, IPipelineEngine, IObservability)
```

---

## 三、如何使用

### 场景 1：查看接口签名（主要用途）

```python
import v3_protocols as p
import inspect

# 查看 PipelineEngine 的完整签名
sig = inspect.signature(p.IPipelineEngine.__init__)
print(sig)

# 查看 QualityGate 的所有方法
for name in dir(p.IQualityGate):
    if not name.startswith('_'):
        print(name)
```

### 场景 2：尺度转换

```python
from v3_protocols import scale_01_to_100, convert_domain_quality_to_gate_quality

# 单个值转换
threshold_100 = scale_01_to_100(0.85)  # = 85.0

# 完整配置转换
gate_config = convert_domain_quality_to_gate_quality(domain_config.quality)
```

### 场景 3：依赖注入（Phase 3 启用后）

```python
from v3_protocols import IQualityGate

class PipelineEngine:
    def __init__(self, ..., quality_gate: IQualityGate = None):
        assert quality_gate is None or isinstance(quality_gate, IQualityGate)
        self._quality_gate = quality_gate
```

### 场景 4：Mock 替换（测试时）

```python
from v3_protocols import IQualityGate

class MockQualityGate(IQualityGate):
    def evaluate(self, output, context=None):
        return QualityReport(overall_score=90.0, ...)

engine = PipelineEngine(..., quality_gate=MockQualityGate(...))
```

---

## 四、当前状态

| 维度 | 状态 | 说明 |
|------|------|------|
| Protocol 对齐度 | ✅ 8.5/10 | 严格基于实际代码 |
| 数据契约 | ✅ 9/10 | 字段完全匹配 |
| 尺度转换 | ✅ 8/10 | 含防御性校验 |
| 运行时集成 | ❌ 0/10 | 无模块引用它 |
| 自动同步 | ❌ 0/10 | 代码改了协议不会自动更新 |

---

## 五、已知限制

1. **手动维护** — 代码改了，协议层需人工同步
2. **无运行时强制** — Protocol 只是约定，编译器不检查
3. **私有方法覆盖不全** — 验证装饰器只检查公开方法
4. **文件位置** — 在根目录而非 `.v3/`，容易遗漏

---

## 六、未来方向

| 方向 | 说明 | 优先级 |
|------|------|--------|
| 运行时注入检查 | PipelineEngine 构造函数加 isinstance 验证 | P1 |
| 自动化测试 | 用 Protocol 生成 Mock 类做集成测试 | P2 |
| 类型检查集成 | mypy 检查 Protocol 实现 | P2 |
| 自动同步工具 | 代码改了自动更新协议层 | P3 |

---

## 七、修订历史

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-04-21 | 添加附录 C：Orchestrator-Worker 调用标准模式 | 小满 |
| 2026-04-14 | 基于实际代码重建（Phase 2.6） | 协议重写专家 |
| 2026-04-14 | 修复 3 个小问题（config 属性、类型注解、空维度校验） | 小满 |
| 2026-04-14 | 本说明书创建 | 小满 |

---

## 附录 C：Orchestrator-Worker 调用标准模式（2026-04-21 新增）

### C.1 标准调用流程

```
Orchestrator (depth-1)
  │
  ├── sessions_spawn(runtime="subagent", mode="run") 
  │     → 返回 {childSessionKey, ...}（仅元数据，非结果）
  │
  ├── 等待 Worker 完成（两种模式）
  │     ├── 模式 A：Blackboard 轮询（推荐）
  │     │     Worker 按契约写入 blackboard/{session_id}/stages/{role}_output.json
  │     │     Orchestrator 轮询检测文件存在且内容有效
  │     │
  │     └── 模式 B：sessions_history 查询（Fallback）
  │           查询子 Agent 历史消息提取实际分析结果
  │
  └── 读取结果并继续
```

### C.2 反模式（绝对禁止）

| 反模式 | 错误表现 | 后果 |
|--------|---------|------|
| ❌ **反模式 1** | 把 spawn 返回的元数据当作 Worker 结果 | Blackboard 中只有 {"status": "accepted"}，无实际分析 |
| ❌ **反模式 2** | spawn 后不等待直接继续 | 获取空结果或旧数据 |
| ❌ **反模式 3** | 绕过 Orchestrator，主Agent直接 spawn Workers | 违背架构设计，失去质量门控和迭代收敛 |

### C.3 结果验证标准

有效的 Worker 输出必须包含：
- `analysis` 或 `executive_summary`（分析内容）
- `conclusions` 或 `key_findings`（结论）

无效的特征（spawn 元数据）：
- `status: "accepted"`
- `childSessionKey` 字段

### C.4 记忆锚点

> "spawn 返回的是车票，不是目的地；必须等待 Worker 到站"
> "Orchestrator 是将军，Workers 是士兵；将军必须能指挥士兵"
> "架构设计是宪法，bug 是违宪，修复是修宪，绕过是政变"

---

*附录 C 添加于 2026-04-21，修复 Orchestrator-Worker 调用 bug*
