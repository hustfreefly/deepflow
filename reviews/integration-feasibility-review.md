# 集成可行性评审报告

> 评审对象：V3 当前代码库的依赖注入与接口适配可行性
> 评审日期：2026-04-14
> 评审人：集成可行性评审专家

---

## 总评

- **集成可行性评分: 6.5/10**
- **主要优点:**
  1. `PipelineEngine.__init__` 已经支持 `Optional[T]` 参数注入，骨架到位
  2. 各组件（QualityGate、ResilienceManager、BlackboardManager）内部接口清晰、职责单一
  3. `ConfigLoader` 和 `BlackboardManager` 支持可选注入 + 默认实例回退
  4. 所有组件都无外部硬依赖，可独立实例化和测试

- **主要缺陷:**
  1. **`v3_protocols.py` 不存在** — 没有 Protocol 定义，当前使用的是具体类类型注解
  2. **方法签名不一致** — 调用方与实现方存在多处参数不匹配（P0 级）
  3. **Observability 是静态方法集合** — 无法通过依赖注入替换
  4. **`Task` dataclass 定义与调用不匹配** — pipeline_engine 构造 Task 但缺少必需字段
  5. **两个 QualityConfig 并存** — `config_loader.DomainQualityConfig` 和 `quality_gate.QualityConfig` 不兼容

---

## 依赖注入可行性

| 注入点 | 当前类型 | Protocol 可行? | 风险 | 建议 |
|--------|---------|---------------|------|------|
| `PipelineEngine.quality_gate` | `Optional[QualityGate]` | ✅ 可行 | 调用方传参缺少 `context`；`QualityReport.converged` 属性不存在 | 定义 `IQualityGate` Protocol，修正 evaluate 调用 |
| `PipelineEngine.resilience_manager` | `Optional[ResilienceManager]` | ✅ 可行 | `execute_with_resilience` 调用只传了 `task`，缺 `executor` 参数 | 定义 `IResilienceManager` Protocol，修正调用 |
| `PipelineEngine.blackboard` | `Optional[BlackboardManager]` | ✅ 可行 | 方法多、接口大；`list_files` 返回 `list` 但 `_build_result` 期望 `.name` 属性 | 定义 `IBlackboard` Protocol，拆分大接口 |
| `PipelineEngine.config_loader` | `Optional[ConfigLoader]` | ✅ 可行 | 内部调用 `load_domain` 和 `load_pipeline`，接口小且稳定 | 定义 `IConfigLoader` Protocol（低优先级） |
| `PipelineEngine.agent_callback` | `Optional[Callable]` | ✅ 可行 | 已经是函数式注入，最灵活的注入点 | 可定义 `IAgentExecutor` Protocol 规范化 |
| `PipelineEngine` 内部 `Observability` | 模块级静态方法 | ❌ **不可行** | 全静态方法，无法构造实例也无法注入 | 改为 `IObservability` Protocol + 默认实现类 |

---

## 使用场景验证

### 场景1: 构造函数注入

```python
engine = PipelineEngine(
    domain="investment",
    session_id="sess_001",
    quality_gate=my_quality_gate,
    resilience_manager=my_rm,
)
```

| 维度 | 评估 | 说明 |
|------|------|------|
| 语法可行性 | ✅ 可行 | 当前 `__init__` 接受 `Optional[T]` 参数 |
| Protocol 替换 | ✅ 可行 | Python `typing.Protocol` 支持 structural subtyping |
| 实际运行风险 | ⚠️ 中风险 | `QualityGate.evaluate()` 调用缺少第2参数 `context`（见下方 P0-1） |

### 场景2: 运行时 isinstance 检查

```python
assert isinstance(engine._quality_gate, IQualityGate)
```

| 维度 | 评估 | 说明 |
|------|------|------|
| 语法可行性 | ✅ 可行 | `typing.runtime_checkable` + `@runtime_checkable` 支持 |
| 限制 | ⚠️ 仅检查方法名 | `isinstance` 只检查方法签名存在，不检查返回值类型 |
| 建议 | 使用 `typing_extensions.Protocol` + `@runtime_checkable` | 确保 Protocol 可运行时检查 |

### 场景3: Mock 替换

```python
class MockQualityGate(IQualityGate):
    def evaluate(self, output: str, context: Optional[Dict] = None) -> QualityReport:
        return QualityReport(overall_score=90, dimensions={}, decision=GateDecision.PASS, reasoning="mock")
```

| 维度 | 评估 | 说明 |
|------|------|------|
| 可行性 | ✅ 可行 | structural subtyping 允许任何实现相同方法的类 |
| 注意 | `QualityReport` 和 `GateDecision` 等数据类需保持兼容 | Mock 需要返回正确的数据结构 |

### 场景4: 尺度转换集成

| 问题 | 评估 | 说明 |
|------|------|------|
| `convert_domain_quality_to_gate_quality()` 在哪调用？ | ⚠️ 需新增 | 当前代码无此函数；存在两套 QualityConfig |
| ConfigLoader 加载后是否自动转换？ | ❌ 未实现 | `DomainQualityConfig`（0-1 范围）与 `QualityConfig`（0-100 范围）不互通 |
| PipelineEngine 初始化时是否自动转换？ | ❌ 未实现 | `PipelineEngine` 根本不创建 `QualityGate` 实例 |

---

## 关键发现：方法签名不一致（P0 级）

### P0-1: `QualityGate.evaluate()` 调用缺少参数

**`pipeline_engine.py` 第 275 行:**
```python
quality_report = self._quality_gate.evaluate(full_content)
# 但 QualityGate.evaluate 签名是:
# def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> QualityReport
```
✅ 实际上 `context` 有默认值 `None`，**运行时不会报错**，但 Protocol 设计应明确标注可选性。

### P0-2: `QualityReport.converged` 属性不存在

**`pipeline_engine.py` 第 277 行:**
```python
converged = quality_report.converged  # ← 此属性不存在！
```

`QualityReport` dataclass 只有:
- `overall_score: float`
- `dimensions: Dict[str, DimensionScore]`
- `decision: GateDecision`
- `reasoning: str`
- `timestamp: float`

**没有 `converged` 属性**。运行时此处会抛 `AttributeError`。

**修复方案:** 应在 `QualityReport` 中添加 `converged: bool = False`，或改用 `quality_gate.check_convergence()` 方法。

### P0-3: `ResilienceManager.execute_with_resilience()` 调用参数不匹配

**`pipeline_engine.py` 第 228 行:**
```python
task = Task(
    id=f"{stage.id}_{instance_name}",    # ← Task 没有 id 字段！
    coro=agent_executor(),               # ← Task 没有 coro 字段！
    stage=stage.id,                      # ← Task 没有 stage 字段！
)
result = await self._resilience_manager.execute_with_resilience(task)
# 但方法签名是:
# async def execute_with_resilience(self, agent_task: Task, executor: Callable) -> Result
```

**问题清单:**
1. `Task` dataclass 的字段是 `agent_id, task_prompt, model, fallback_model, timeout, metadata`，**没有 `id`、`coro`、`stage` 字段**
2. `execute_with_resilience` 需要 **两个参数**（`agent_task` + `executor`），但调用只传了一个
3. `agent_executor()` 立即执行了协程（括号调用），应传 `agent_executor`（无括号）

**这是运行时必崩的 Bug。**

### P0-4: `Task` dataclass 字段与调用方不匹配

**`resilience_manager.py` 定义:**
```python
@dataclass
class Task:
    agent_id: str
    task_prompt: str
    model: str = "default"
    fallback_model: str = "lightweight"
    timeout: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**`pipeline_engine.py` 构造:**
```python
Task(id=..., coro=..., stage=...)  # 三个字段全部不存在
```

### 已验证非 Bug
- `BlackboardManager.list_files("*.md")` 返回 `List[Path]`，coordinator 中 `f.name` 可正常访问 ✅
- `QualityGate.evaluate(full_content)` 缺 `context` 参数但有默认值 `None`，不崩溃 ✅

---

## 适配层设计建议

| 需要适配的模块 | 适配方式 | 复杂度 |
|---------------|---------|--------|
| `QualityGate` → `IQualityGate` | **直接定义 Protocol**，方法签名与现有类一致 | 低 |
| `ResilienceManager` → `IResilienceManager` | **修复 `Task` 字段 + 调用参数**，然后定义 Protocol | 中 |
| `BlackboardManager` → `IBlackboard` | 提取核心方法子集（read/write/list_files/init_session） | 低 |
| `ConfigLoader` → `IConfigLoader` | 提取 `load_domain` + `load_pipeline` | 低 |
| `Observability` → `IObservability` | **从静态方法改为实例方法** + Protocol | 高（需改所有调用方） |
| `DomainQualityConfig` ↔ `QualityConfig` | 添加 `to_gate_config()` 转换方法 | 中 |
| `Task` dataclass | **修正字段名**或添加 PipelineEngine 适配函数 | 低 |

### 适配层代码示例

```python
# v3_protocols.py（建议新增）
from typing import Protocol, runtime_checkable, Optional, Dict, Any, Callable, Coroutine
from pathlib import Path


@runtime_checkable
class IQualityGate(Protocol):
    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Any: ...
    def check_convergence(self, scores: list, iteration: int, 
                         max_iterations: int = 10, target_score: float = 80.0) -> tuple[bool, str]: ...


@runtime_checkable
class IResilienceManager(Protocol):
    async def execute_with_resilience(self, agent_task: Any, 
                                       executor: Callable[[Any], Coroutine[Any, Any, Any]]) -> Any: ...
    def save_checkpoint(self, stage: str, data: Dict[str, Any]) -> None: ...
    def load_checkpoint(self, stage: str) -> Optional[Dict[str, Any]]: ...
    def rollback_to_safe_state(self) -> Optional[Dict[str, Any]]: ...


@runtime_checkable
class IBlackboard(Protocol):
    def init_session(self) -> None: ...
    def write(self, filename: str, content: str) -> None: ...
    def read(self, filename: str) -> Optional[str]: ...
    def list_files(self, pattern: str = "*.md") -> list: ...
    def get_shared_state(self) -> Dict[str, Any]: ...
    def add_quality_score(self, score: float, decision: str) -> None: ...
    def update_convergence(self, converged: bool, round_num: int, 
                          reason: Optional[str] = None) -> None: ...
    def save_checkpoint(self, checkpoint_name: str) -> None: ...


@runtime_checkable
class IConfigLoader(Protocol):
    def load_domain(self, domain: str) -> Any: ...
    def load_pipeline(self, pipeline_type: str) -> Any: ...
```

---

## 尺度转换集成方案

### 问题
`DomainQualityConfig`（0-1 范围）和 `QualityConfig`（0-100 范围）是两套独立配置。

### 推荐方案：在 ConfigLoader 中添加转换方法

```python
# config_loader.py 中添加
@dataclass
class DomainConfig:
    # ... 现有字段 ...
    
    def to_quality_gate_config(self) -> "QualityConfig":
        """将 DomainQualityConfig 转换为 quality_gate.QualityConfig"""
        from quality_gate import QualityConfig, DimensionConfig
        
        dimensions = [
            DimensionConfig(
                name=d.name,
                weight=d.weight,
                threshold=d.threshold * 100,  # 0-1 → 0-100
            )
            for d in self.quality.dimensions
        ]
        
        return QualityConfig(
            dimensions=dimensions,
            auto_pass_threshold=self.quality.auto_pass_threshold * 100,
            hitl_threshold=self.quality.human_gate_threshold * 100,
        )
```

### 集成点建议

| 模块 | 调用时机 | 说明 |
|------|---------|------|
| `PipelineEngine.__init__` | 初始化时 | 若 `quality_gate=None`，用 `domain_config.to_quality_gate_config()` 创建默认实例 |
| `Coordinator.execute` | 创建引擎前 | 可预先创建并注入 |

---

## 改进建议

### P0 必须修复（不修则运行时崩溃）

1. **P0-2: 修复 `quality_report.converged` 不存在**
   - 方案 A: 在 `QualityReport` 添加 `converged: bool = False` 字段
   - 方案 B: `pipeline_engine.py` 中改用 `self._quality_gate.check_convergence(scores, ...)`
   - 推荐方案 B，收敛检测本就是 QualityGate 的职责

2. **P0-3: 修复 `ResilienceManager.execute_with_resilience` 调用**
   - 修正 `Task` 构造：使用正确的字段 `agent_id`, `task_prompt`
   - 修正调用：传两个参数 `execute_with_resilience(task, agent_executor)`（注意无括号）
   - 或：将 `execute_with_resilience` 重构为只需 task，executor 由 Task 携带

3. **P0-4: 修复 `Task` dataclass 字段不匹配**
   - 选择：要么修改 `Task` 增加 PipelineEngine 需要的字段，要么在 PipelineEngine 中正确构造
   - 推荐：保持 `Task` 不变（ResilienceManager 已定义清晰），PipelineEngine 适配

4. **P0-5: `PipelineEngine._build_result` 中 `output_files` 类型问题**
   ```python
   # pipeline_engine.py 第 330 行
   output_files=self._blackboard.list_files("*.md"),
   # 而 coordinator.py 第 242 行:
   for f in result.output_files[-5:]:
       lines.append(f"- {f.name}")  # ← 期望 Path 对象
   # 但 BlackboardManager.list_files 返回的是 list[str]，没有 .name 属性
   ```

### P1 建议修复（不修则 Protocol 设计困难）

5. **创建 `v3_protocols.py`** — 定义 `IQualityGate`、`IResilienceManager`、`IBlackboard`、`IConfigLoader`、`IObservability`

6. **`PipelineEngine` 类型注解改用 Protocol**
   ```python
   # 从:
   quality_gate: Optional[QualityGate] = None
   # 改为:
   quality_gate: Optional[IQualityGate] = None
   ```

7. **统一两套 QualityConfig** — 在 `DomainConfig` 中添加 `to_quality_gate_config()` 转换方法

8. **`Observability` 改为实例化注入** — 当前全静态方法无法替换，改为 `IObservability` Protocol + 默认实现

9. **修复 `_execute_gate_stage` 返回值** — gate 阶段不应在 `_execute_stage` 内部特殊处理 next_stage，应由 `_determine_next_stage` 统一处理

### P2 可选优化

10. **`BlackboardManager.list_files` 返回 `List[Path]` 而非 `list`** — 类型安全性

11. **`PipelineEngine._execute_agent_single` 中 `from resilience_manager import Task` 延迟导入** — 应改为文件顶部导入

12. **`_build_result` 中 `self.state in (PipelineState.DONE, PipelineState.CONVERGED)`** — `CONVERGED` 状态从未被设置（只有 `DONE`），应确认是否遗漏

13. **`PipelineState` 枚举中 `WAIT_HITL` 拼写为 `WAITING_HITL`** — 但 `_determine_next_stage` 返回 `"wait_hitl"` 字符串，两者不一致

---

## 总结

**当前代码可以跑通 Protocol 依赖注入的骨架**（`__init__` 接受 Optional 参数），但存在多个 **P0 级运行时 Bug** 必须在定义 Protocol 之前修复。

**建议执行顺序:**
1. 先修 P0（4 个 Bug）→ 确保代码能运行
2. 创建 `v3_protocols.py` → 定义 5 个 Protocol
3. 修改 `pipeline_engine.py` 类型注解 → 从具体类改为 Protocol
4. 添加 `to_quality_gate_config()` 转换 → 统一两套配置
5. （可选）Observability 实例化改造

**整体可行性判断: 可行，但需要先修 Bug。**
