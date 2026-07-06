# Research Pro 架构与集成审计报告

**审计日期**: 2026-06-05  
**审计员**: DeepFlow Research Pro 架构与集成审计员  
**审计标准**: 独立可运行、架构合理

---

## 总体评级: 🟡 YELLOW

**评级理由**: Research Pro 具备完整的核心功能实现，架构设计遵循了 DeepFlow 的契约笼子模式，但存在与 Core 框架集成不完整、缺少统一入口注册、以及部分隐式依赖的问题。建议修复 P0/P1 级别问题后升级为 GREEN。

---

## 架构图（从代码推断）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           OpenClaw 主 Agent                              │
│                              (调用方)                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ spawn_fn 注入
┌─────────────────────────────────────────────────────────────────────────┐
│                    ResearchProOrchestrator                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   Planning  │─▶│  Confirming │─▶│  Executing  │─▶│    Reporting    │ │
│  │  (生成计划)  │  │ (用户确认)  │  │  (搜索研究)  │  │  (生成报告)     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │
│         │                               │                    │        │
│         ▼                               ▼                    ▼        │
│  ┌─────────────┐              ┌─────────────────┐      ┌───────────┐  │
│  │ KeywordGen  │              │   Mode A/B/C    │      │ Citation  │  │
│  │  (关键词)   │              │  (Agent 模式)   │      │  Verifier │  │
│  └─────────────┘              └─────────────────┘      └───────────┘  │
│                                          │                            │
│                                          ▼                            │
│                              ┌─────────────────┐                      │
│                              │  SourceRegistry │                      │
│                              │  (来源注册中心)  │                      │
│                              └─────────────────┘                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Blackboard (文件系统)                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐          │
│  │ state.json │ │source_reg..│ │ research/  │ │ report/    │          │
│  │ (状态管理)  │ │ (来源注册)  │ │ (研究数据) │ │ (最终报告)  │          │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 与 Core 集成评估

### EntryHarness: ⚠️ 未集成

**现状**: Research Pro 完全独立运行，未使用 `core.quality.entry_harness.EntryHarness`。

**问题**:
- Research Pro 自行实现状态管理和配置加载，未复用 EntryHarness 的统一入口逻辑
- 缺少 EntryHarness 提供的 spawn_fn 验证、session 初始化、execution_plan 生成等标准流程
- 没有调用 `EntryHarness.validate_and_start()` 方法

**影响**: 中等 - Research Pro 有自己的状态机实现，但缺少统一入口的标准化保障。

**建议**: 
- [P1] 可选：考虑添加 EntryHarness 包装层，使 Research Pro 可以通过统一入口启动
- 或在 Cage 契约中明确说明 Research Pro 是独立架构，不依赖 EntryHarness

### PipelineOrchestrator: ⚠️ 未集成

**现状**: Research Pro 使用自研的四阶段状态机，未使用 `core.orchestrator.pipeline_orchestrator.PipelineOrchestrator`。

**问题**:
- Research Pro 的 `ResearchProOrchestrator` 自行管理阶段流转 (planning → confirming → executing → reporting)
- 未使用 PipelineOrchestrator 的 phase/worker 并行执行模型
- 没有 execution_plan.json 和 tasks.json 的标准生成流程

**影响**: 中等 - Research Pro 的阶段模型与 Solution Pro 不同，但自身实现完整。

**对比**:
| 特性 | Solution Pro | Research Pro |
|------|-------------|-------------|
| 阶段模型 | 10阶段管线 (PipelineOrchestrator) | 4阶段状态机 (自研) |
| Worker 管理 | PipelineOrchestrator 统一 spawn | Orchestrator 内部 Mode A/B/C 切换 |
| 并行执行 | PipelineOrchestrator 控制 | ThreadPoolExecutor + spawn_fn |
| Execution Plan | 标准 JSON 文件 | 内部 dict 传递 |

### Blackboard: ✅ 部分使用

**现状**: Research Pro 使用文件系统作为 Blackboard，但未使用 `core.blackboard.blackboard_manager.BlackboardManager`。

**评估**:
- ✅ Research Pro 使用 `PathConfig` 获取 Blackboard 路径，符合 Core 标准
- ✅ 文件写入使用原子操作 (`.tmp` + `os.replace`)
- ⚠️ 未使用 `BlackboardManager` 类，而是直接文件操作
- ⚠️ 未使用 `BlackboardBridge` 进行前端状态同步

**代码位置**:
```python
# Research Pro 使用 PathConfig
from core.config.path_config import PathConfig
_path_config = PathConfig.resolve()
_BASE_DIR = _path_config.base_dir
```

### Cage: ✅ 正确使用

**现状**: Research Pro 有完整的 Cage 契约文件。

**评估**:
- ✅ `cage/active/research_pro_v1.0.yaml` 存在且内容完整
- ✅ 契约包含 interface、behavior、data、harness、quality_gates 等完整章节
- ✅ 7条红线 (RED-DC-001 到 RED-DC-007) 定义清晰
- ✅ Python 模块契约 (orchestrator.py 等) 定义明确
- ⚠️ 未使用 `core.cage.cage_loader.CageLoader` 和 `CageValidator` 进行契约加载和验证

**Cage 契约亮点**:
- 完整的四级 Harness (input_guard/process_guard/output_guard/safety_valve)
- 明确的 Blackboard 布局定义
- 三级 Agent 模式 (A/B/C) 的详细契约
- 完成标准 (completion_criteria) 定义

### spawn_fn 注入模式: ✅ 正确使用

**评估**:
- ✅ `ResearchProOrchestrator.__init__` 接收 `spawn_fn` 参数
- ✅ 契约笼子注释明确："Python 代码禁止直接 import openclaw SDK"
- ✅ Mode C 使用注入的 spawn_fn 创建子 Agent
- ✅ spawn_fn 不可用时降级为 Mode B 串行执行

**代码示例**:
```python
def __init__(
    self,
    mode: str = 'standard',
    base_path: str = '',
    spawn_fn: Optional[Callable] = None,  # ✅ 正确注入
) -> None:
    # P2-Mode C: 注入 spawn 回调
    self._spawn_fn = spawn_fn
```

---

## 与 Solution Pro 对标

| 维度 | Solution Pro | Research Pro | 差距评估 |
|------|-------------|-------------|---------|
| **统一入口** | `UnifiedEntry.run()` 标准入口 | 无统一入口，直接实例化 Orchestrator | 🔴 缺少 |
| **EntryHarness** | 完整使用 | 未使用 | 🔴 缺少 |
| **PipelineOrchestrator** | 10阶段管线 | 4阶段状态机 | 🟡 架构差异 |
| **BlackboardManager** | 完整使用 | 直接文件操作 | 🟡 未复用 |
| **Cage 契约** | domain_solution.yaml | ✅ research_pro_v1.0.yaml | ✅ 完整 |
| **spawn_fn 注入** | ✅ 正确注入 | ✅ 正确注入 | ✅ 一致 |
| **QualityGate** | 使用 core.quality.quality_gate | 自研完成标准检查 | 🟡 功能等价 |
| **session_id 生成** | `_SolutionDispatcher._generate_session_id()` | `base_path.name` 或外部传入 | 🟡 简化 |
| **进度跟踪** | `ProgressTracker` + `BlackboardBridge` | 内部 state.json | 🟡 简化 |
| **安全验证** | `SecurityValidator` | `_SafeFetcher` + `_validate_safe_url` | ✅ 等价 |
| **配置管理** | `config/solution.yaml` + 动态加载 | `config/time_budgets.json` + `completion_criteria.json` | ✅ 完整 |
| **子 Agent 模式** | PipelineOrchestrator 统一调度 | Mode A/B/C 内部切换 | 🟡 差异设计 |
| **恢复机制** | 通过 Blackboard 文件 | `resume_from_state()` 方法 | ✅ 完整 |
| **Harness 体系** | 4层 Harness + Final Gate | 4层 Harness (契约定义) | ✅ 完整 |
| **Prompt 管理** | `task_builder.py` 动态生成 | 静态 prompt 文件 (prompts/*.md) | 🟡 风格差异 |

**关键差距分析**:

1. **统一入口缺失** (P1): Solution Pro 可以通过 `UnifiedEntry.run(domain="solution")` 启动，Research Pro 没有注册到 UnifiedEntry。

2. **BlackboardManager 未复用** (P2): Research Pro 直接操作文件，而 Solution Pro 使用 `BlackboardManager` 封装。

3. **进度同步机制** (P2): Solution Pro 有 `BlackboardBridge` 同步前端状态，Research Pro 只有内部 state.json。

---

## 独立可运行性评估

### 需要的外部依赖

| 依赖 | 用途 | 是否必须 | 降级策略 |
|------|------|---------|---------|
| `ddgs` / `duckduckgo_search` | 搜索功能 | 否 | 关键词降级数据 |
| `core.config.path_config` | 路径管理 | ✅ 是 | 无 |
| `core.cage.cage_loader` | 契约加载 | 否 | 未使用 |
| `core.cage.cage_validator` | 契约验证 | 否 | 未使用 |
| `core.blackboard.blackboard_manager` | Blackboard | 否 | 直接文件操作 |
| `core.quality.quality_gate` | 质量门控 | 否 | 自研完成检查 |
| `subprocess` (Python 标准库) | 调用 DDGS | 否 | 降级数据 |

### 隐式假设

| 假设 | 风险 | 建议 |
|------|------|------|
| OpenClaw 环境提供 spawn_fn | 高 - 无法在纯 Python 环境运行 Mode C | 文档化说明 Mode C 需要 spawn_fn |
| `~/.openclaw/workspace/.deepflow/` 存在 | 中 - 路径硬编码 | 使用 PathConfig 动态解析 |
| DDGS 命令行工具可用 | 低 - 有降级策略 | 已处理 |
| 文件系统可写 | 中 - 需要 Blackboard 目录 | 启动时检查并创建目录 |

### 入口点清晰度

**当前入口**:
```python
from domains.research_pro.orchestrator import ResearchProOrchestrator

orch = ResearchProOrchestrator(mode='standard', base_path='/path/to/blackboard', spawn_fn=spawn_fn)
result = orch.init_session(query="研究主题")
# ... 用户确认 ...
result = orch.execute_research()
result = orch.generate_report()
```

**评估**: 
- ✅ 入口清晰，API 简洁
- ⚠️ 缺少统一入口封装（如 `run_research_pro()` 便捷函数）
- ⚠️ 需要调用方管理状态机流转

### 配置加载自包含性

**配置文件**:
- `config/time_budgets.json` - 时间预算配置
- `config/completion_criteria.json` - 完成标准配置
- `config/tier_domains.json` - 域名分级配置

**评估**: ✅ 配置加载完整，有合理的默认值回退

```python
def _load_time_budgets() -> Dict[str, Any]:
    return _load_json_file(_TIME_BUDGETS_PATH, {
        "quick_mode": {"total_timeout": 600},
        "standard_mode": {"total_timeout": 2700},
        # ... 默认值
    })
```

---

## 模块边界评估

### 职责清晰度

| 模块 | 职责 | 评估 |
|------|------|------|
| `orchestrator.py` | 四阶段状态机、Agent 模式切换、搜索编排 | ✅ 清晰 |
| `source_registry.py` | 来源注册、验证、去重 | ✅ 清晰 |
| `tier_classifier.py` | 域名质量分级 | ✅ 清晰 |
| `citation_verifier.py` | 引用验证 | ✅ 清晰 |
| `keyword_generator.py` | 关键词生成 | ✅ 清晰 |
| `safe_fetcher.py` | 安全 HTTP 请求 | ✅ 清晰 |

### 循环依赖检查

**检查结果**: ✅ 无循环依赖

```
orchestrator.py
    ├── source_registry.py
    ├── tier_classifier.py
    ├── citation_verifier.py
    ├── keyword_generator.py
    └── safe_fetcher.py

(无反向依赖)
```

### 接口定义

**ResearchProOrchestrator 公共接口**:
```python
class ResearchProOrchestrator:
    def __init__(self, mode: str = 'standard', base_path: str = '', spawn_fn: Optional[Callable] = None)
    def init_session(self, query: str) -> Dict[str, Any]
    def confirm_plan(self, user_confirmation: Dict[str, Any]) -> Dict[str, Any]
    def execute_research(self) -> Dict[str, Any]
    def generate_report(self) -> Dict[str, Any]
    def get_status(self) -> Dict[str, Any]
    def resume_from_state(self, state_path: str = None) -> Dict[str, Any]
```

**评估**: ✅ 接口清晰，职责单一

---

## 可扩展性评估

### 添加新数据源

**当前设计**:
- `tier_classifier.py` 定义 Tier 1/2/3 域名列表
- `source_registry.py` 统一管理来源
- 搜索通过 DDGS，抓取通过 `_SafeFetcher`

**扩展难度**: 🟢 容易
- 在 `tier_domains.json` 添加新域名即可
- 或修改 `TierClassifier._bundled_config()` 添加内置域名

### 添加新研究领域

**当前设计**:
- `keyword_generator.py` 内置基础词典 `_SYNONYMS`
- `orchestrator.py` 的 `_generate_analysis_plan()` 定义研究维度

**扩展难度**: 🟡 中等
- 需要修改 `KeywordGenerator._SYNONYMS` 添加领域术语
- 或使关键词生成可配置化

### Prompt 自定义

**当前设计**:
- Prompts 存储在 `prompts/*.md` 文件
- 契约中定义了 prompt 路径

**扩展难度**: 🟢 容易
- 直接修改 `prompts/planning.md` 等文件
- 或通过配置覆盖路径

### 配置灵活性

**当前设计**:
- JSON 配置文件支持完整
- 有合理的默认值回退
- 时间预算、完成标准、Tier 域名均可配置

**扩展难度**: 🟢 容易

---

## 必须修复清单

### [P0] 关键问题

1. **缺少统一入口注册** (P1)
   - 问题: Research Pro 未注册到 `core.unified_entry.UnifiedEntry`
   - 修复: 在 `UnifiedEntry._register_domains()` 中添加 research_pro 领域
   - 代码位置: `core/unified_entry.py`

```python
def _register_domains(self) -> Dict[str, DomainRegistry]:
    return {
        "solution": DomainRegistry(...),
        "research_pro": DomainRegistry(
            module="domains.research_pro.orchestrator",
            class_name="ResearchProOrchestrator",
            required_context=["query"]
        ),
        # ...
    }
```

2. **Cage 契约未通过 Loader/Validator 验证** (P2)
   - 问题: 未使用 `CageLoader` 和 `CageValidator` 验证契约
   - 修复: 添加契约加载和验证的单元测试
   - 代码位置: 新增 `tests/test_cage_integration.py`

### [P1] 重要问题

3. **添加便捷入口函数** (P1)
   - 问题: 缺少类似 `run_solution_pro()` 的便捷函数
   - 修复: 在 `__init__.py` 添加 `run_research_pro()` 函数
   - 代码位置: `domains/research_pro/__init__.py`

```python
def run_research_pro(query: str, mode: str = 'standard', spawn_fn=None) -> Dict[str, Any]:
    """便捷函数：运行 Research Pro"""
    orch = ResearchProOrchestrator(mode=mode, spawn_fn=spawn_fn)
    result = orch.init_session(query)
    # ... 完整流程或返回 orchestrator 实例
    return result
```

4. **文档化 Mode C 依赖** (P2)
   - 问题: Mode C 需要 spawn_fn，但未在文档中明确说明
   - 修复: 在 `_overview.md` 和 Cage 契约中添加说明

5. **考虑使用 BlackboardManager** (P2)
   - 问题: 直接文件操作，未复用 `BlackboardManager`
   - 修复: 可选 - 评估是否迁移到 `BlackboardManager`

### [P2] 建议改进

6. **添加前端状态同步** (P2)
   - 建议: 参考 Solution Pro 的 `BlackboardBridge` 添加进度同步

7. **关键词生成可配置化** (P2)
   - 建议: 将 `KeywordGenerator._SYNONYMS` 移到配置文件

8. **添加更多单元测试** (P2)
   - 建议: 补充 Mode A/B/C 切换、降级策略、超时处理的测试

---

## 审计结论

### 优势

1. **完整的 Cage 契约**: Research Pro 拥有 DeepFlow 中最详细的 Cage 契约文件，包含 7 条红线、完整的 Harness 体系、清晰的 Blackboard 布局定义。

2. **自包含的架构**: 四阶段状态机设计清晰，Mode A/B/C 切换逻辑完整，可以独立运行。

3. **安全设计**: SSRF 防护、URL 验证、内容哈希、来源分级等安全机制完善。

4. **降级策略**: 搜索失败、抓取失败、超时等场景都有合理的降级处理。

### 劣势

1. **与 Core 框架集成不完整**: 未使用 EntryHarness、PipelineOrchestrator、BlackboardManager 等核心组件。

2. **缺少统一入口**: 无法通过 `UnifiedEntry.run(domain="research_pro")` 启动。

3. **前端集成缺失**: 没有 BlackboardBridge 进度同步机制。

### 最终建议

Research Pro 是一个功能完整、架构清晰的领域实现，但需要从"独立 Skill"向"DeepFlow 核心领域"演进。建议按以下优先级修复：

1. **立即** (P0): 注册到 UnifiedEntry，使其可以通过统一入口启动
2. **短期** (P1): 添加便捷入口函数，完善文档
3. **中期** (P2): 评估是否复用 BlackboardManager 和 BlackboardBridge

修复 P0/P1 问题后，评级可提升至 🟢 GREEN。

---

*审计完成*
