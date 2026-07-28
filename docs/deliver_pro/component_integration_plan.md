# Deliver Pro 公共组件整合方案

> 目标：识别 Solution Pro 与 Deliver Pro 的重复基础设施，设计整合路径，让两个 Pro 共享同一套 core 层。
> 
> 日期：2026-07-28 | 作者：公共组件提取与整合专家

---

## 1. 现有公共组件清单

| 组件 | 位置 | 使用者 | 整合建议 |
|------|------|--------|---------|
| BlackboardManager | `core/blackboard/blackboard_manager.py` (531L) | Solution Pro（直接继承） | ✅ 已是 core 层，Deliver Pro 应迁移到此 |
| DomainRegistry | `core/blackboard/registry_base.py` | Solution Pro（SolutionRegistry 继承） | ✅ 已是 core 层，Deliver Pro 可选用 |
| context_injector | `core/blackboard/context_injector.py` | 两个 Pro 共用 | ✅ 已整合，无需变更 |
| session_id | `core/blackboard/session_id.py` | 全局 | ✅ 已整合 |
| blackboard_bridge | `core/blackboard/blackboard_bridge.py` | 前端状态桥接 | ✅ 已整合 |
| prompt_registry | `deliver_pro/prompt_registry.py` (149L) | 仅 Deliver Pro | ⚠️ 保持在域内，但接口可标准化 |
| state_manager | `deliver_pro/state_manager.py` (224L) | 已 DEPRECATED | 🔴 应删除，无生产调用方 |
| Pulse 调度 | `solution_pro/pulse.py` (590L) / `deliver_pro/pulse_cli.py` (100L) | 各自域 | ⚠️ 架构相似但域特定，提取公共基类到 core |
| 原子写 JSON | 散落在 7+ 文件中 | 两个 Pro | 🔴 应提取到 core 工具函数 |

---

## 2. 重复代码识别

### 2.1 Blackboard 实现（最大重复）

| 代码片段 | Solution Pro | Deliver Pro | 重复度 | 整合方式 |
|---------|-------------|-------------|--------|---------|
| 原子写 JSON（tempfile+fsync+rename） | `blackboard.py:195-210` (write 方法) | `blackboard.py:105-120` (save_json), `blackboard.py:162-175` (save_file) | **95%** — 逻辑完全相同 | 提取到 `core/utils/atomic_io.py` |
| JSON 读写 + 目录管理 | 继承 core BlackboardManager | `DeliverProBlackboard` 独立实现 242 行 | **70%** — 功能重叠但 API 不同 | Deliver Pro 迁移到 core BlackboardManager + 适配层 |
| 目录初始化 | core BlackboardManager `init_session()` | `DeliverProBlackboard._init_directories()` | **60%** — 结构相似 | core 提供 `ensure_dirs()` 可配置方法 |

**关键差异分析**：
- `DeliverProBlackboard` 使用 `project_name/deliver_pro/wp_subdir` 路径结构
- `core.BlackboardManager` 使用 `session_id/stages/` 路径结构
- Deliver Pro 的 `save_json(stage, data, filename)` 是 `stage/filename` 二维寻址
- Core 的 `write_stage(name, data)` 是 `stages/{name}.json` 一维寻址

**结论**：DeliverProBlackboard 不是 core 的简单子类，需要适配层。

### 2.2 Pulse 契约（结构相似，字段不同）

| 代码片段 | Solution Pro | Deliver Pro | 重复度 | 整合方式 |
|---------|-------------|-------------|--------|---------|
| PulseAction | `SolutionPulseAction` (module/action/task/label/mode) | `PulseAction` (wp_id/action/task/label/model/mode/thinking) | **65%** — 骨架相同，字段不同 | 提取 `BasePulseAction` 到 core |
| PulseAlert | `SolutionPulseAlert` (severity/code/message) | `PulseAlert` (severity/code/message) | **95%** — 完全相同 | 统一到 core |
| PulseSummary | `SolutionPulseSummary` | `PulseSummary` | **50%** — 字段不同 | 保持域特定 |
| PulseReport | `SolutionPulseReport` | `PulseReport` | **70%** — 骨架相同 | 提取 `BasePulseReport` 到 core |
| SpawnConfirmation | `SpawnConfirmation` (module/label/ok/error) | `SpawnConfirmation` (wp_id/label/ok/error) | **90%** — 仅第一个字段名不同 | 统一到 core，用泛型字段名 |
| 原子写 JSON | `pulse.py:_atomic_write_json` | `orchestrator.py:_atomic_write_json`, `wp_runner.py:atomic_write_json` | **100%** — 完全相同 | 提取到 core |

### 2.3 Pipeline State（语义不同，模式相似）

| 代码片段 | Solution Pro | Deliver Pro | 重复度 | 整合方式 |
|---------|-------------|-------------|--------|---------|
| 状态模型 | `SolutionProPipelineState` (模块树: modules→stages) | `PipelineState` (线性相位: phase enum) | **30%** — 语义根本不同 | ❌ 保持域特定 |
| 阶段进度 | `StageProgress` (status/timestamps) | `PipelinePhase` (enum + transitions) | **20%** — 设计模式不同 | ❌ 保持域特定 |
| 收敛状态 | `ConvergenceState` (gate_a/gate_b/verdict) | 无对应 | **0%** | ❌ Solution Pro 特有 |
| 任务追踪 | 无直接对应 | `completed_tasks/failed_tasks/pending_tasks` | **0%** | ❌ Deliver Pro 特有 |

**结论**：Pipeline State 是"假公共组件"——看似都是状态管理，但 Solution Pro 是模块树模型，Deliver Pro 是线性相位模型，语义根本不同。

### 2.4 原子写 JSON（最广泛的重复）

| 出现位置 | 行数 | 实现 |
|---------|------|------|
| `core/blackboard/blackboard_manager.py` | 3 处 | tempfile + fsync + rename |
| `deliver_pro/blackboard.py` | 2 处 | tempfile + fsync + rename |
| `deliver_pro/state_manager.py` | 2 处 | tempfile + fsync + rename |
| `deliver_pro/orchestrator.py` | 5+ 处 | tempfile + os.replace |
| `deliver_pro/wp_runner.py` | 2 处 | tempfile + fsync + os.replace |
| `solution_pro/pulse.py` | 5+ 处 | tempfile + os.replace |
| `solution_pro/blackboard.py` | 1 处 | tempfile + fsync + rename |

**总计**：20+ 处几乎完全相同的原子写实现。

---

## 3. 整合方案

### 3.1 提到 core/ 层的组件

#### P0：`core/utils/atomic_io.py`（新建）

提取原子写 I/O 工具函数，消除 20+ 处重复。

```python
# core/utils/atomic_io.py
"""原子 I/O 工具 — 消除散落在各域的重复实现。"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    """原子写 JSON（temp + fsync + replace）。
    
    替代 20+ 处重复实现：
    - core/blackboard/blackboard_manager.py (3x)
    - deliver_pro/blackboard.py (2x)
    - deliver_pro/orchestrator.py (5x)
    - deliver_pro/wp_runner.py (2x)
    - solution_pro/pulse.py (5x)
    - ...
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        content = json.dumps(data, ensure_ascii=False, indent=indent).encode("utf-8")
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        Path(tmp).rename(path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """原子写文本。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        os.write(fd, text.encode(encoding))
        os.fsync(fd)
        os.close(fd)
        Path(tmp).rename(path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(tmp).unlink(missing_ok=True)
        raise


def safe_read_json(path: Path, default=None):
    """安全读取 JSON（不存在返回 default）。"""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default
```

**收益**：消除 20+ 处重复，约 200 行代码。

#### P1：`core/blackboard/pulse_contracts.py`（新建）

提取 Pulse 公共契约基类。

```python
# core/blackboard/pulse_contracts.py
"""Pulse 调度公共契约 — 两个 Pro 共享的基础模型。"""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class BasePulseAction(BaseModel):
    """Pulse 动作基类。域特定子类扩展 action 字段。"""
    model_config = ConfigDict(extra="forbid")
    
    task: str = Field(min_length=1, description="sessions_spawn 的 task 内容")
    label: str = Field(min_length=1, description="sessions_spawn 的 label")
    mode: str = "run"


class BasePulseAlert(BaseModel):
    """Pulse 告警（两个 Pro 完全相同）。"""
    model_config = ConfigDict(extra="forbid")
    
    severity: Literal["INFO", "WARN", "CRITICAL"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class BaseSpawnConfirmation(BaseModel):
    """Spawn 回执基类。域特定子类扩展标识字段。"""
    model_config = ConfigDict(extra="forbid")
    
    label: str = Field(min_length=1, description="spawn 时使用的 label")
    ok: bool
    error: str | None = None
```

**收益**：
- 消除 `SolutionPulseAlert` / `PulseAlert` 重复（95% 相同）
- 统一 `SpawnConfirmation` 接口（90% 相同）
- 为未来新 Pro 域提供标准 Pulse 接口

#### P2：`core/utils/prompt_loader.py`（新建）

从 `deliver_pro/prompt_registry.py` 提取通用 prompt 加载逻辑。

```python
# core/utils/prompt_loader.py
"""通用 Prompt 加载器 — 从 .md 文件加载模板并替换变量。"""

from pathlib import Path
from typing import Any
import re


class PromptLoader:
    """域无关的 prompt 模板加载器。
    
    功能：
    - 从指定目录加载 .md 模板
    - 支持 {variable} 和 {{required_variable}} 替换
    - 自动剥离 YAML Front Matter
    - 模板缓存
    """
    
    def __init__(self, prompts_dir: Path, deepflow_root: Path | None = None):
        self.prompts_dir = Path(prompts_dir)
        self.deepflow_root = deepflow_root or Path.cwd()
        self._cache: dict[str, str] = {}
    
    def load(self, name: str, **kwargs: Any) -> str:
        """加载并渲染 prompt 模板。"""
        template = self._load_template(name)
        return self._render(template, **kwargs)
    
    # ... (从 deliver_pro/prompt_registry.py 提取 _load_template, _render_template, _strip_front_matter)
```

**收益**：Solution Pro 未来也可复用；消除 prompt 加载逻辑的域特定重复。

### 3.2 保持域特定的组件

| 组件 | 原因 | 备注 |
|------|------|------|
| `SolutionProPipelineState` | 模块树模型（planning→research→summary），与 Deliver Pro 线性相位根本不兼容 | 假公共组件 |
| `PipelineState` (Deliver Pro) | 线性相位模型（INIT→ANALYZING→...），域特定语义 | 假公共组件 |
| `SolutionPulse` (pulse.py) | 包含 Solution Pro 特有的相位推进逻辑、模块完成判定、审查 Agent 管理 | 域特定调度 |
| `DeliverOrchestrator.pulse()` | 包含 Deliver Pro 特有的 WP 调度、Worker 管理逻辑 | 域特定调度 |
| `DeliverProBlackboard` | 二维寻址（stage/filename）与 core 一维寻址不兼容；但应迁移到使用 core 的原子写工具 | 需适配但不应强行统一 |
| `StageContract` (Solution Pro) | Solution Pro 特有的 checkpoint 验证逻辑 | 域特定 |
| `WorkPackage`, `ExecutionPlan` 等 | Deliver Pro 业务模型 | 域特定 |
| `state_manager.py` (Deliver Pro) | 已 DEPRECATED，无生产调用方 | 应删除 |

### 3.3 接口设计

#### 3.3.1 atomic_io 接口（P0）

```python
# 使用方式（替代 20+ 处重复实现）
from core.utils.atomic_io import atomic_write_json, atomic_write_text, safe_read_json

# 替代 deliver_pro/wp_runner.py:atomic_write_json
atomic_write_json(state_path, state.model_dump())

# 替代 deliver_pro/blackboard.py:save_json
atomic_write_json(target_dir / filename, data)

# 替代 solution_pro/pulse.py:_atomic_write_json
atomic_write_json(self.state_path, state.model_dump(mode="json"))
```

#### 3.3.2 Pulse 契约接口（P1）

```python
# Solution Pro 继承
from core.blackboard.pulse_contracts import BasePulseAlert, BaseSpawnConfirmation

class SolutionPulseAction(BasePulseAction):
    module: str = Field(min_length=1)
    action: Literal["spawn_module", "spawn_reviewer"]

class SolutionPulseAlert(BasePulseAlert):
    pass  # 无额外字段

class SolutionSpawnConfirmation(BaseSpawnConfirmation):
    module: str = Field(min_length=1)


# Deliver Pro 继承
class PulseAction(BasePulseAction):
    wp_id: str = Field(min_length=1)
    action: Literal["analyze", "spawn_workers", "validate", "package", "package_failed"]
    model: str | None = None
    thinking: str = "medium"

class PulseAlert(BasePulseAlert):
    pass  # 无额外字段

class PulseSpawnConfirmation(BaseSpawnConfirmation):
    wp_id: str = Field(min_length=1)
```

#### 3.3.3 DeliverProBlackboard 迁移路径

```python
# 阶段 1：使用 core 的原子写工具（不改 API）
from core.utils.atomic_io import atomic_write_json, atomic_write_text

class DeliverProBlackboard:
    def save_json(self, stage: str, data: dict, filename: str) -> Path:
        target_dir = self.get_stage_path(stage)
        target = target_dir / filename
        atomic_write_json(target, data)  # 替代手写 tempfile+fsync+rename
        return target
    
    def save_file(self, stage: str, content: str, filename: str) -> Path:
        target_dir = self.get_stage_path(stage)
        target = target_dir / filename
        atomic_write_text(target, content)
        return target

# 阶段 2（可选）：考虑继承 core.BlackboardManager
# 需要解决二维寻址问题，风险较高，建议仅在阶段 1 稳定后评估
```

---

## 4. 迁移路径

| 阶段 | 整合内容 | 风险 | 验证方式 | 预计收益 |
|------|---------|------|---------|---------|
| **Phase 0** | 创建 `core/utils/atomic_io.py` | 🟢 极低 — 纯新增，不改现有代码 | 单元测试覆盖 3 个函数 | 为后续迁移奠基 |
| **Phase 1** | 替换 20+ 处原子写实现为 `atomic_io` 调用 | 🟡 中低 — 逐文件替换，每个替换独立可测 | 每替换一个文件跑一次 `pytest` | 消除 ~200 行重复代码 |
| **Phase 2** | 创建 `core/blackboard/pulse_contracts.py` | 🟢 低 — 纯新增基类 | 两个 Pro 的现有测试不受影响 | 统一 Pulse 接口 |
| **Phase 3** | 两个 Pro 的 PulseAlert/SpawnConfirmation 继承 core 基类 | 🟡 中 — 需要调整 import 路径 | 两个 Pro 的 pulse 测试全通过 | 消除 ~80 行重复 |
| **Phase 4** | 提取 `core/utils/prompt_loader.py` | 🟢 低 — 从 deliver_pro 提取，不改行为 | Deliver Pro prompt 测试通过 | 未来新 Pro 可复用 |
| **Phase 5** | 删除 `deliver_pro/state_manager.py` | 🟡 中 — 需确认无引用 | `grep -r "state_manager" deliver_pro/` 无结果 | 消除 224 行死代码 |
| **Phase 6** | 评估 DeliverProBlackboard → core.BlackboardManager 迁移可行性 | 🔴 高 — 需解决二维寻址差异 | 完整 E2E 测试 | 长期统一 Blackboard API |

### Phase 1 详细替换清单

| 文件 | 替换数 | 替换内容 |
|------|--------|---------|
| `deliver_pro/blackboard.py` | 2 | `save_json`, `save_file` 的原子写 |
| `deliver_pro/state_manager.py` | 2 | `save`, `write_progress_file` 的原子写 |
| `deliver_pro/orchestrator.py` | 5+ | `_atomic_write_json` 方法调用 |
| `deliver_pro/wp_runner.py` | 2 | `atomic_write_json` 函数 |
| `solution_pro/pulse.py` | 5+ | `_atomic_write_json` 方法调用 |
| `solution_pro/blackboard.py` | 1 | `write` 方法的原子写 |
| `core/blackboard/blackboard_manager.py` | 3 | `write`, `write_stage`, `copy_stage` 的原子写 |

---

## 5. 收益评估

### 5.1 代码行数减少

| 整合项 | 消除重复行数 | 新增代码行数 | 净减少 |
|--------|------------|------------|--------|
| `atomic_io.py` | ~200 行（20+ 处 × ~10 行） | ~60 行 | **-140 行** |
| `pulse_contracts.py` | ~80 行（2 个域 × ~40 行） | ~50 行 | **-30 行** |
| `prompt_loader.py` | ~50 行（未来复用） | ~80 行 | **+30 行**（短期） |
| 删除 `state_manager.py` | 224 行死代码 | 0 | **-224 行** |
| **合计** | | | **-364 行** |

### 5.2 维护成本降低

| 维度 | 当前 | 整合后 | 改善 |
|------|------|--------|------|
| 原子写 bug 修复 | 需改 7+ 文件 | 改 1 处 `atomic_io.py` | **7x → 1x** |
| 新增 Pro 域 | 需复制 pulse contracts | 继承 core 基类 | **减少 50% 模板代码** |
| Pulse 契约变更 | 需同步 2 个域 | 改 core 基类，域自动继承 | **2x → 1x** |
| 新人理解成本 | 需读 2 套 blackboard 实现 | 理解 core 1 套 + 域适配层 | **降低认知负担** |

### 5.3 稳健性提升

| 维度 | 当前风险 | 整合后 |
|------|---------|--------|
| 原子写一致性 | 20+ 处实现可能有微妙差异（有的用 `os.replace`，有的用 `Path.rename`） | 统一实现，行为一致 |
| Pulse 契约漂移 | 两个域的 Alert/Confirmation 可能逐渐分化 | 基类约束，强制一致 |
| 死代码维护 | `state_manager.py` 已 DEPRECATED 但仍存在 | 删除，消除混淆 |
| 测试覆盖 | 原子写逻辑分散，难以集中测试 | 集中测试 `atomic_io.py` |

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Phase 1 替换引入行为差异 | 低 | 中 | 逐个替换 + 每个文件跑测试；`atomic_io` 实现取各版本并集 |
| Pulse 基类设计不当限制未来扩展 | 中 | 低 | 基类只提取完全相同的字段（Alert），域特定字段用子类扩展 |
| DeliverProBlackboard 迁移到 core 破坏 API | 高 | 高 | Phase 6 才做，且需完整 E2E 测试；短期只迁移原子写工具 |
| 删除 state_manager.py 影响旧测试 | 中 | 低 | 先 `grep` 确认所有引用，连同测试一起删除 |

---

## 7. 决策记录

### 7.1 为什么不直接统一 Blackboard API？

`DeliverProBlackboard` 使用二维寻址 `(stage, filename)`，`core.BlackboardManager` 使用一维寻址 `(stage_name)`。强行统一需要：
- 修改 Deliver Pro 所有调用方（wp_runner.py, orchestrator.py, phase agents）
- 或修改 core BlackboardManager 支持二维寻址（增加复杂度）

**决策**：短期只提取原子写工具（Phase 1），不改变 Blackboard API。Phase 6 再评估。

### 7.2 为什么 PipelineState 不整合？

Solution Pro 是模块树模型（modules → stages → convergence），Deliver Pro 是线性相位模型（phase enum + transitions）。语义根本不同，强行统一会产生"最大公约数"设计，两边都不好用。

**决策**：标记为"假公共组件"，保持域特定。

### 7.3 为什么 prompt_loader 优先级最低？

当前只有 Deliver Pro 有 prompt_registry，Solution Pro 直接读文件。提取 prompt_loader 的收益是面向未来的（新 Pro 域），短期收益不明显。

**决策**：P2 优先级，在 Phase 4 执行。

---

## 附录 A：原子写实现差异清单

| 文件 | 方法 | 临时文件前缀 | fsync | replace 方式 |
|------|------|------------|-------|-------------|
| `core/blackboard_manager.py:write` | `write()` | 无 prefix | ✅ fsync | `Path.rename` |
| `core/blackboard_manager.py:write_stage` | `write_stage()` | 无 prefix（NamedTemporaryFile） | ✅ fsync | `os.replace` |
| `core/blackboard_manager.py:copy_stage` | `copy_stage()` | 无 prefix | ✅ fsync | `os.replace` |
| `deliver_pro/blackboard.py:save_json` | `save_json()` | `.{filename}_` prefix | ✅ fsync | `Path.rename` |
| `deliver_pro/blackboard.py:save_file` | `save_file()` | `.{filename}_` prefix | ✅ fsync | `Path.rename` |
| `deliver_pro/orchestrator.py:_atomic_write_json` | `_atomic_write_json()` | `{name}.` prefix | ❌ 无 fsync | `os.replace` |
| `deliver_pro/wp_runner.py:atomic_write_json` | `atomic_write_json()` | 无 prefix | ✅ fsync | `os.replace` |
| `solution_pro/pulse.py:_atomic_write_json` | `_atomic_write_json()` | 无 prefix（`.tmp.{pid}`） | ❌ 无 fsync | `os.replace` |

**统一方案**：`atomic_io.atomic_write_json()` 取最严格实现（有 fsync + `Path.rename`），确保数据安全。

---

## 附录 B：文件依赖图

```
core/
├── utils/
│   ├── atomic_io.py          ← Phase 0 新建
│   └── prompt_loader.py      ← Phase 4 新建
├── blackboard/
│   ├── blackboard_manager.py ← Phase 1 替换内部原子写
│   ├── pulse_contracts.py    ← Phase 2 新建
│   ├── registry_base.py      ← 不变
│   ├── context_injector.py   ← 不变（已共享）
│   └── session_id.py         ← 不变

domains/
├── solution_pro/
│   ├── blackboard.py         ← Phase 1 替换原子写；保持 SolutionRegistry 继承
│   ├── pulse.py              ← Phase 1 替换原子写；Phase 3 继承 pulse_contracts
│   └── contracts/
│       └── pulse_report.py   ← Phase 3 继承 BasePulseAction/Alert
│
├── deliver_pro/
│   ├── blackboard.py         ← Phase 1 替换原子写；保持独立 DeliverProBlackboard
│   ├── orchestrator.py       ← Phase 1 替换原子写
│   ├── wp_runner.py          ← Phase 1 替换原子写
│   ├── state_manager.py      ← Phase 5 删除
│   ├── prompt_registry.py    ← Phase 4 迁移到 core/utils/prompt_loader.py
│   └── contracts/
│       └── pulse_report.py   ← Phase 3 继承 BasePulseAction/Alert
```
