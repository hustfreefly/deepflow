# Deep Dive V3.0 架构设计文档 - 最终完整版

**文档版本**: v3.0-final  
**设计日期**: 2026-04-11  
**状态**: 最终版 — 可直接进入实施  
**设计来源**: Kimi基础方案 + Gemini/千问/Kimi专家评审意见融合  
**决策者**: 小满 (AI Agent) 基于全量输入材料最优决策

---

## 执行摘要

### 核心设计哲学

> **"配置驱动，声明编排，智能控制反转，渐进交付，可观测优先，四层容错"**

V3.0架构以 **OpenClaw平台约束为硬边界**，以 **Claude Code/Hermes/OpenProse为设计灵感**，以 **V2.4资产为复用基础**，融合三位专家评审意见，打造一套**配置驱动、具备人机回环(HITL)、四层故障隔离、可观测优先**的通用多Agent协作系统。

### 关键决策矩阵（最优决策）

| 决策项 | 最优选择 | 决策理由 | 来源 |
|:---|:---|:---|:---|
| **编排范式** | YAML声明式 + 轻量Python引擎 | P0验证：行数-15%，字符数-49% | Kimi P0验证 |
| **控制哲学** | Intelligent Inversion of Control | 声明式编排本质，智能服务连接 | Gemini专家 |
| **数据传递** | 文件Blackboard + shared_state Schema | 0%冲突率，标准化持久化 | Kimi+千问融合 |
| **拓扑结构** | 星型（main协调） | OpenClaw硬约束：只有main能spawn | 平台约束 |
| **管线模型** | 3种模板（iterative/audit/gated） | 覆盖6大场景，80%纯YAML配置 | 三专家共识 |
| **状态机** | FSM平铺结构 | 简单可维护，Checkpoint友好 | Kimi专家+最优决策 |
| **人机回环** | HITL门控节点（仅gated管线） | 关键决策点人工确认，避免过度设计 | Gemini专家+最优决策 |
| **故障处理** | L1-L4四层故障隔离矩阵 | 生产级必需，千问方案最完整 | 千问专家 |
| **可观测性** | 日志+指标+追踪（Phase 1纳入） | 三专家共识，生产级必需 | 三专家共识 |
| **交付模式** | 渐进式（2/8/30分钟三层） | 用户确认，解决耐心上限问题 | Kimi基础方案 |
| **向后兼容** | 自动化迁移 + 双版本并行 | 4领域100%不损坏 | Kimi基础方案 |

### 架构公式（一句话概括）

```
V3.0 = Intelligent IoC声明式编排 + FSM平铺状态机 + V2.4领域资产 
       + L1-L4四层故障隔离 + HITL人机回环（关键节点） + 可观测优先
```

### 质量四维验收标准

| 维度 | 验收标准 | V3.0设计满足度 |
|:---|:---|:---:|
| **准确度** | 输出可溯源、有依据 | ✅ Blackboard完整证据链 |
| **可用性** | 产出可执行、方案可落地 | ✅ YAML配置即代码 |
| **先进性** | 支持动态委托、自适应编排 | ✅ HITL+IoC+三层架构 |
| **优雅性** | 配置驱动、易于维护 | ✅ 80%纯YAML，一人维护 |

---

## 第一章：设计哲学与原则

### 1.1 五大设计原则（融合千问专家）

#### 原则1：配置驱动（Configuration-Driven）

> **80%场景纯YAML配置，20%复杂场景可扩展**

核心理念：将多变的业务逻辑从代码中抽离，通过声明式配置表达。配置即代码，版本化、可审计、易回滚。

**实现方式**:
```yaml
# 添加一个新领域 = 添加一份YAML配置
domain: new_domain
intent:
  keywords: ["关键词1", "关键词2"]
pipeline: iterative
agents:
  - role: researcher
  - role: critic
    instances:
      - name: angle_1
        angle: "从角度1分析"
```

**验收标准**: 新领域开发时间从2天降至2小时。

#### 原则2：向后兼容（Backward Compatible）

> **现有4领域100%不损坏，自动化迁移零成本**

- V2.4配置自动转换为V3.0 YAML（提供迁移工具）
- 并行运行期：V2.4和V3.0共存，对比验证
- 回滚策略：保留V2.4代码路径作为紧急备选

**验收标准**: 现有4领域（investment/architecture/code/general）迁移后100%成功率。

#### 原则3：渐进交付（Progressive Delivery）

> **洋葱式分层，用户可控，耐心上限管理**

```
T+30s  → 快速预览（意图+计划+预估）
T+2min → 初稿交付（核心框架+关键发现）
T+8min → 完整报告（详细分析+建议）
T+30min→ 深度研究（全面覆盖+证据链）
```

**关键机制**:
- 8分钟时通过`sessions_yield`返回初稿
- 用户确认后继续后台执行
- 完成后通过`message` API飞书推送

#### 原则4：故障隔离（Fault Isolation）

> **单Agent失败不影响全局，L1-L4四层防护**

| 层级 | 范围 | 防护机制 | 恢复策略 | 责任组件 |
|:---|:---|:---|:---|:---|
| L1 Agent级 | 单个Agent | 超时+重试+熔断 | 降级模型重试 | ResilienceManager |
| L2 Stage级 | 单个Stage | 检查点+重入 | 从检查点恢复 | CheckpointManager |
| L3 Pipeline级 | 整个管线 | 事务回滚+状态重置 | 回滚到安全状态 | PipelineEngine |
| L4 System级 | 系统整体 | 优雅降级+资源保护 | 核心功能保活 | Coordinator |

#### 原则5：可观测优先（Observability First）

> **Phase 1就纳入日志/指标/追踪，非事后补充**

- **日志**：结构化JSON，全链路追踪ID（trace_id）
- **指标**：成功率、延迟、质量分、收敛轮数、成本
- **追踪**：Pipeline→Stage→Agent层级跨度可视化

**验收标准**: 任何故障可在30秒内定位到具体Agent和具体代码行。

### 1.2 Intelligent Inversion of Control（融合Gemini专家）

#### 核心理念

传统命令式控制流：
```
代码 → 调用Agent → 等待结果 → 处理结果 → 调用下一个Agent
```

V3.0声明式控制流：
```
YAML声明期望状态 → PipelineEngine协调 → Agent自报告状态 → 自动状态转换
```

**关键转变**:
- 从"命令式调用"到"声明式期望"
- 从"硬编码流程"到"配置驱动编排"
- 从"中心化控制"到"分布式状态机"

#### 容器语义化服务连接

借鉴OpenProse的Forme Container理念，Agent通过Blackboard自注册、自发现、自协调，Engine只负责状态流转。

```yaml
# 声明式连接，而非命令式绑定
pipeline:
  stages:
    - id: plan
      output: plan.md           # 声明产出
      next: execute             # 声明流向
      
    - id: execute
      input: [plan.md]          # 声明依赖
      output: execution.md      # 声明产出
```

---

## 第二章：系统架构

### 2.1 三层架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    配置层（Configuration Layer）                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │   domains/  │ │  pipelines/ │ │   prompts/  │               │
│  │   *.yaml    │ │   *.yaml    │ │   *.md      │               │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
└────────────────────────────┬────────────────────────────────────┘
                             │声明式加载
┌────────────────────────────▼────────────────────────────────────┐
│                    运行时层（Runtime Layer）                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              PipelineEngine（Python ~300行）              │ │
│  │   Stage调度 │ Convergence │ Quality │ Checkpoint          │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │   iterative │ │    audit    │ │    gated    │              │
│  │    管线     │ │    管线     │ │    管线     │              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
└────────────────────────────┬────────────────────────────────────┘
                             │sessions_spawn
┌────────────────────────────▼────────────────────────────────────┐
│                    平台层（Platform Layer）                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ planner ││researcher││ auditor ││ fixer   ││summarizer│   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           Blackboard（文件共享 + shared_state）         │   │
│  │   ~/.openclaw/workspace/.v3/blackboard/{session_id}/   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流设计

```
用户: /deep 分析贵州茅台
  │
  ▼
┌────────────────────────────────────────┐
│ IntentParser → DomainMatcher           │  解析意图，匹配领域配置
│ 输出: DomainConfig (investment.yaml)   │
└──────────────┬─────────────────────────┘
               │
               ▼
┌────────────────────────────────────────┐
│ PipelineSelector                       │  选择管线模板
│ 输出: PipelineTemplate (iterative.yaml)│
└──────────────┬─────────────────────────┘
               │
               ▼
┌────────────────────────────────────────┐
│ PipelineEngine.execute()               │  执行管线
│ ├── Blackboard.init()                  │  初始化Blackboard
│ ├── Stage.execute()                    │  按序执行各阶段
│ ├── ConvergenceChecker.check()         │  检测收敛
│ ├── QualityAssessor.assess()           │  质量评估
│ ├── CheckpointManager.save()           │  保存检查点
│ └── DeliveryManager.deliver()          │  渐进交付
└──────────────┬─────────────────────────┘
               │
               ▼
┌────────────────────────────────────────┐
│ Blackboard.shared_state.json           │  持久化状态
│ 迭代历史 + 质量分数 + 收敛状态         │
└────────────────────────────────────────┘
```

### 2.3 状态机定义（FSM平铺结构 - 最优决策）

**决策依据**: 采用Kimi的FSM平铺结构（而非Gemini的AST嵌套），原因：
1. Checkpoint读写简单（只需记录当前stage ID）
2. 符合"一人维护"约束
3. 三专家共识：Kimi方案最可实施

```
                    ┌─────────────┐
         ┌─────────│   FAILED    │◄──── 任何状态异常/超时
         │         └──────┬──────┘      或L1-L4故障无法恢复
         │                │
         │                │ 恢复（从Checkpoint）
         ▼                ▼
┌──────────┐    ┌─────────────┐    ┌─────────────┐
│   INIT   │───►│  PLANNING   │───►│  EXECUTING  │
└──────────┘    └─────────────┘    └──────┬──────┘
                                          │
                                          ▼
┌──────────┐    ┌─────────────┐    ┌─────────────┐
│   DONE   │◄───│  DELIVERING │◄───│  CHECKING   │
└──────────┘    └──────┬──────┘    └──────┬──────┘
                       │        未收敛    │ 已收敛
                       │            ┌────┘
                       │            ▼
                       │    ┌─────────────┐
                       └────│   FIXING    │
                            └─────────────┘
                                          │
                                          ▼
                            ┌─────────────┐
                            │   HITL      │◄──── gated管线特有
                            │ 人工干预     │      人工确认/拒绝
                            └─────────────┘
```

**状态说明**:

| 状态 | 说明 | 超时 | 可恢复 | 所属层级 |
|:---|:---|:---:|:---:|:---:|
| INIT | 初始化，创建Blackboard | 10s | - | System |
| PLANNING | 意图解析+管线选择 | 30s | ✅ | Pipeline |
| EXECUTING | Agent执行 | 120s/Agent | ✅ L1 | Stage |
| CHECKING | 收敛+质量检测 | 10s | - | Stage |
| FIXING | 修复阶段 | 120s | ✅ L1 | Stage |
| HITL | 人工干预（仅gated） | 无限 | ✅ | Pipeline |
| DELIVERING | 渐进式交付 | 按需 | - | Pipeline |
| DONE | 完成 | - | - | - |
| FAILED | 失败 | - | ✅ L2-L4 | System |

---

## 第三章：核心组件设计

### 3.1 Coordinator（协调器）

**职责**: 主Agent入口，意图解析，管线调度，全局状态管理

**接口定义**:
```python
class Coordinator:
    def execute(self, user_input: str, domain_hint: Optional[str] = None) -> ExecutionResult:
        """主入口，执行用户请求"""
        pass
    
    def pause(self, session_id: str) -> bool:
        """暂停执行中的管线"""
        pass
    
    def resume(self, session_id: str) -> ExecutionResult:
        """从Checkpoint恢复执行"""
        pass
    
    def get_status(self, session_id: str) -> PipelineStatus:
        """获取当前执行状态"""
        pass
```

**HITL集成**（融合Gemini专家）:
- 仅在`gated`管线中触发HITL节点
- 进入HITL状态时，将Blackboard状态推送到Feishu
- 等待用户`/approve`或`/reject`
- `/approve`：继续执行下一阶段
- `/reject`：返回FIXING阶段或终止

### 3.2 BlackboardManager（黑板管理器）

**职责**: 文件读写，上下文组装，路径管理，shared_state持久化

**shared_state Schema**（融合千问专家）:
```json
{
  "session_id": "uuid",
  "domain": "investment",
  "pipeline": "iterative",
  "current_stage": "executing",
  "stage_history": [
    {"stage": "plan", "status": "completed", "output": "plan.md"}
  ],
  "quality_scores": [
    {"stage": "plan", "score": 85, "passed": true}
  ],
  "convergence": {
    "converged": false,
    "round": 2,
    "max_rounds": 5
  },
  "checkpoints": [
    {"stage": "plan", "timestamp": "2026-04-11T10:00:00Z"}
  ],
  "trace_id": "uuid-for-observability"
}
```

**文件命名规范**:
```
{session_id}/
├── shared_state.json      # 共享状态
├── plan.md                # Plan阶段产出
├── execution.md           # Execute阶段产出
├── review_critique_1.md   # Critic多实例产出
├── review_critique_2.md
├── review_critique_3.md
├── fixed.md               # Fix阶段产出
└── final_report.md        # Summarizer产出
```

### 3.3 PipelineEngine（管线引擎）

**职责**: 解析YAML管线，调度Stage，状态流转，FSM驱动

**核心实现**:
```python
class PipelineEngine:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.current_stage = None
        self.state = PipelineState.INIT
    
    def execute(self, blackboard: Blackboard) -> ExecutionResult:
        """执行管线，驱动FSM状态流转"""
        while self.state not in [PipelineState.DONE, PipelineState.FAILED]:
            # 获取当前stage配置
            stage_config = self.get_current_stage()
            
            # 执行stage
            result = self.execute_stage(stage_config, blackboard)
            
            # 状态流转（FSM）
            self.state = self.transition(self.state, result)
            
            # 保存checkpoint
            CheckpointManager.save(blackboard)
        
        return ExecutionResult(state=self.state)
    
    def transition(self, current: PipelineState, result: StageResult) -> PipelineState:
        """FSM状态转换逻辑"""
        # FSM平铺结构实现
        pass
```

### 3.4 QualityGate（质量门控）

**职责**: 收敛检测，质量评估，门控判断，HITL触发

**质量维度**（可配置）:
```yaml
quality_dimensions:
  - name: accuracy      # 准确度
    weight: 0.4
    threshold: 80
  - name: completeness  # 完整度
    weight: 0.3
    threshold: 75
  - name: depth         # 深度
    weight: 0.2
    threshold: 70
  - name: elegance      # 优雅度
    weight: 0.1
    threshold: 65
```

**门控逻辑**:
- 自动通过：所有维度≥阈值
- 人工确认：总分≥阈值但有维度不及格（触发HITL）
- 拒绝重做：总分<阈值（返回FIXING）

### 3.5 CheckpointManager（检查点管理器）

**职责**: 异步保存，故障恢复，自动清理

**保存策略**:
- Stage完成时自动保存
- 最小保存间隔60秒（防止I/O阻塞）
- 仅保存shared_state.json（轻量）

**恢复机制**:
```python
def restore(session_id: str) -> Optional[Blackboard]:
    """从checkpoint恢复Blackboard"""
    checkpoint = load_checkpoint(session_id)
    if checkpoint:
        return Blackboard.from_checkpoint(checkpoint)
    return None
```

### 3.6 ResilienceManager（韧性管理器）

**职责**: L1-L4四层故障处理（融合千问专家）

**L1 Agent级**:
```python
def execute_with_resilience(agent_task: Task) -> Result:
    """L1：超时+重试+熔断+降级"""
    for attempt in range(max_retries):
        try:
            return execute_with_timeout(agent_task, timeout=120)
        except TimeoutError:
            if attempt < max_retries - 1:
                sleep(backoff(attempt))  # 指数退避
            else:
                return fallback_to_cheaper_model(agent_task)  # 降级
        except CircuitBreakerOpen:
            return Error("Circuit breaker open")
```

**L2 Stage级**:
- 检查点+重入：失败时从检查点重试当前Stage

**L3 Pipeline级**:
- 事务回滚+状态重置：失败时回滚到安全状态

**L4 System级**:
- 优雅降级+资源保护：核心功能保活

### 3.7 Observability（可观测性）

**职责**: 日志+指标+追踪（Phase 1纳入，三专家共识）

**日志**:
```python
import structlog

logger = structlog.get_logger()

# 全链路追踪ID
logger.info(
    "stage_started",
    trace_id=trace_id,
    session_id=session_id,
    stage=stage_name,
    agent=agent_role,
)
```

**指标**:
- 成功率：`successful_tasks / total_tasks`
- 延迟：`task_completion_time`
- 质量分：`quality_scores.average`
- 收敛轮数：`convergence.round`
- 成本：`token_usage * price_per_token`

**追踪**:
- Pipeline→Stage→Agent层级跨度
- 可视化调用链

---

## 第四章：配置Schema（YAML）

### 4.1 完整Schema定义

```yaml
# domain.yaml 结构
version: "3.0"
domain:
  name: str              # 领域标识
  description: str       # 领域描述
  
intent:
  keywords: [str]        # 触发关键词
  examples: [str]        # 示例输入
  
pipeline:
  type: enum             # iterative | audit | gated
  max_rounds: int        # 最大迭代轮数
  
agents:
  - role: enum           # planner | researcher | auditor | fixer | summarizer
    instances: int       # 实例数（默认1）
    model: str           # 模型选择（可选）
    prompt_template: str # Prompt模板路径
    
quality:
  dimensions:
    - name: str
      weight: float
      threshold: int
  auto_pass_threshold: int    # 自动通过阈值
  human_gate_threshold: int   # 人工门控阈值
  
delivery:
  quick_preview: bool    # 2分钟预览
  draft_delivery: bool   # 8分钟初稿
  async_deep: bool       # 30分钟后台深度
```

### 4.2 修正后的6大场景配置示例

**场景1：代码审查（code_review）- iterative管线**（⚠️已修正，原audit错误）

```yaml
domain: code_review
version: "3.0"

description: 审查代码质量、安全性、性能

intent:
  keywords: ["审查代码", "code review", "检查代码", "review"]
  examples:
    - "帮我review这段Python代码"
    - "审查这个函数的安全性"

pipeline:
  type: iterative        # ⚠️已修正：原audit错误，应为iterative
  max_rounds: 3

agents:
  - role: planner
    prompt_template: prompts/code_review/planner.md
    
  - role: researcher
    instances: 2
    prompt_template: prompts/code_review/security_expert.md
    
  - role: auditor
    instances: 3
    prompt_template: prompts/code_review/critic.md
    
  - role: fixer          # ⚠️已补充：iterative必须有fixer
    prompt_template: prompts/code_review/fixer.md
    
  - role: summarizer
    prompt_template: prompts/code_review/summarizer.md

quality:
  dimensions:
    - name: security
      weight: 0.4
      threshold: 85
    - name: performance
      weight: 0.3
      threshold: 75
    - name: readability
      weight: 0.2
      threshold: 70
    - name: best_practices
      weight: 0.1
      threshold: 65
  auto_pass_threshold: 80
  human_gate_threshold: 70

delivery:
  quick_preview: true
  draft_delivery: true
  async_deep: false
```

**场景2：架构设计（architecture）- iterative管线**

```yaml
domain: architecture
version: "3.0"

description: 从零设计系统架构

intent:
  keywords: ["架构设计", "设计系统", "技术方案", "architecture"]

pipeline:
  type: iterative
  max_rounds: 5

agents:
  - role: planner
  - role: researcher
    instances: 2
  - role: auditor
    instances: 3
  - role: fixer
  - role: summarizer

quality:
  dimensions:
    - name: scalability
      weight: 0.3
    - name: reliability
      weight: 0.3
    - name: performance
      weight: 0.2
    - name: maintainability
      weight: 0.2
```

**场景3：投资分析（investment）- iterative管线**

```yaml
domain: investment
version: "3.0"

intent:
  keywords: ["分析", "投资", "研报", "股票"]

pipeline:
  type: iterative
  max_rounds: 5

agents:
  - role: planner
  - role: researcher
    instances: 3  # 财务/行业/管理层三角度
  - role: auditor
    instances: 3
  - role: fixer
  - role: summarizer
```

**场景4：通用分析（general）- iterative管线**

```yaml
domain: general
version: "3.0"

intent:
  keywords: ["分析", "研究", "调研", "报告"]

pipeline:
  type: iterative
  max_rounds: 3

agents:
  - role: planner
  - role: researcher
  - role: auditor
    instances: 2
  - role: fixer
  - role: summarizer
```

**场景5：系统构建（system_build）- gated管线**（两阶段门控）

```yaml
domain: system_build
version: "3.0"

description: 从架构设计到代码实现的递进构建

intent:
  keywords: ["构建系统", "实现", "开发", "build"]

pipeline:
  type: gated
  stages:
    - name: architecture_gate    # 第一阶段门控
      agents:
        - role: planner
        - role: researcher
          instances: 2
        - role: auditor
          instances: 2
      gate: true                 # 架构评审后人工确认
      
    - name: implementation_gate  # 第二阶段门控
      agents:
        - role: researcher       # 代码实现
        - role: auditor          # 代码审查
        - role: fixer            # 代码修复
      gate: true                 # 代码评审后人工确认

quality:
  dimensions:
    - name: architecture_quality
      weight: 0.5
    - name: code_quality
      weight: 0.5

delivery:
  quick_preview: true
  draft_delivery: true
  async_deep: true
```

**场景6：系统审查（system_audit）- audit管线**（纯审查无修复）

```yaml
domain: system_audit
version: "3.0"

description: 审查现有系统的一致性、合规性

intent:
  keywords: ["审查系统", "审计", "合规检查", "audit"]

pipeline:
  type: audit           # 纯审查，无fixer
  
agents:
  - role: planner
  - role: researcher
    instances: 2
  - role: auditor
    instances: 3        # 多视角并行审查
  # ⚠️注意：audit管线无fixer角色
  - role: summarizer

quality:
  dimensions:
    - name: compliance
      weight: 0.4
    - name: consistency
      weight: 0.3
    - name: security
      weight: 0.3
```

### 4.3 三种管线模板定义

**Template 1：iterative（迭代生成管线）**

```yaml
template:
  name: iterative
  description: Generate → Critique → Refinement循环
  
flow:
  - stage: plan
    agent: planner
    next: execute
    
  - stage: execute
    agent: researcher
    parallel: true        # 可配置并行
    next: critique
    
  - stage: critique
    agent: auditor
    parallel: true        # 多Critic并行
    next: check
    
  - stage: check
    type: convergence
    on_converged: summarize
    on_not_converged: fix
    
  - stage: fix
    agent: fixer          # iterative特有
    next: critique        # 循环
    
  - stage: summarize
    agent: summarizer
    next: done
```

**Template 2：audit（纯审查管线）**

```yaml
template:
  name: audit
  description: Plan → Collect → Critique，无Fix
  
flow:
  - stage: plan
    agent: planner
    next: collect
    
  - stage: collect
    agent: researcher    # 收集信息
    parallel: true
    next: critique
    
  - stage: critique
    agent: auditor       # 多视角并行审查
    parallel: true
    next: summarize
    
  - stage: summarize
    agent: summarizer    # 汇总审查结果
    next: done
    
# ⚠️注意：无fix阶段，纯审查
```

**Template 3：gated（递进门控管线）**

```yaml
template:
  name: gated
  description: Stage1 → Gate → Stage2 → Gate
  
flow:
  - stage: stage1
    name: architecture   # 第一阶段
    agents: [planner, researcher, auditor]
    next: gate1
    
  - stage: gate1
    type: hitl           # 人工门控
    on_approve: stage2
    on_reject: fix1
    
  - stage: fix1
    agent: fixer
    next: gate1          # 重新评审
    
  - stage: stage2
    name: implementation # 第二阶段
    agents: [researcher, auditor, fixer]
    next: gate2
    
  - stage: gate2
    type: hitl           # 人工门控
    on_approve: summarize
    on_reject: fix2
    
  - stage: fix2
    agent: fixer
    next: gate2
    
  - stage: summarize
    agent: summarizer
    next: done
```

---

## 第五章：渐进交付实现

### 5.1 2/8/30分钟分层逻辑

```python
class DeliveryManager:
    def deliver(self, blackboard: Blackboard, elapsed_time: int) -> DeliveryResult:
        """根据时间分层渐进交付"""
        
        if elapsed_time <= 30:  # T+30s
            return self.quick_preview(blackboard)
            
        elif elapsed_time <= 120:  # T+2min
            return self.draft_delivery(blackboard, "core_framework")
            
        elif elapsed_time <= 480:  # T+8min
            return self.draft_delivery(blackboard, "full_report")
            
        else:  # T+30min
            return self.deep_research(blackboard)
    
    def quick_preview(self, blackboard: Blackboard) -> DeliveryResult:
        """快速预览：意图+计划+预估"""
        preview = {
            "intent": blackboard.get("intent"),
            "plan_summary": blackboard.get("plan.md").summary(),
            "estimated_time": "8-10 minutes",
            "preview_only": True
        }
        return DeliveryResult(content=preview, type="preview")
    
    def draft_delivery(self, blackboard: Blackboard, level: str) -> DeliveryResult:
        """初稿交付"""
        if level == "core_framework":
            content = blackboard.get("core_findings.md")
        else:
            content = blackboard.get("full_report.md")
        
        # 通过sessions_yield返回
        return DeliveryResult(content=content, type="draft")
    
    def deep_research(self, blackboard: Blackboard) -> DeliveryResult:
        """深度研究：异步后台完成后推送"""
        # 转入后台执行
        # 完成后通过message API飞书推送
        content = blackboard.get("deep_research_report.md")
        return DeliveryResult(content=content, type="final")
```

### 5.2 异步后台执行机制

```python
class AsyncExecutionManager:
    def execute_async(self, pipeline: Pipeline, blackboard: Blackboard):
        """8分钟后转入后台异步执行"""
        
        # 1. 保存当前状态
        CheckpointManager.save(blackboard)
        
        # 2. 通过sessions_yield返回初稿
        yield DraftDeliveryResult(blackboard)
        
        # 3. 后台继续执行
        while not pipeline.is_complete():
            result = pipeline.continue_execution()
            CheckpointManager.save(blackboard)
        
        # 4. 完成后飞书推送
        final_report = blackboard.get_final_output()
        message(
            channel="feishu",
            content=final_report,
            notification=True
        )
```

### 5.3 Feishu推送集成

```python
def notify_user(session_id: str, content: str, level: str = "draft"):
    """向用户推送消息"""
    
    if level == "draft":
        # 8分钟初稿返回
        return {
            "type": "draft",
            "content": content,
            "next_actions": ["/continue", "/pause", "/approve"]
        }
    
    elif level == "hitl":
        # HITL门控等待确认
        return {
            "type": "approval_required",
            "content": content,
            "actions": ["/approve", "/reject", "/comment"]
        }
    
    elif level == "final":
        # 最终报告推送
        message(
            channel="feishu",
            target=USER_OPEN_ID,
            content=f"任务 {session_id} 已完成！\n\n{content}",
            notification=True
        )
```

---

## 第六章：实施路线图

### Phase 1 (MVP)：核心功能 + 可观测性（1-2周）

**目标**：可运行，4领域迁移完成

| 任务 | 优先级 | 工期 | 交付物 |
|:---|:---:|:---:|:---|
| T1.1 搭建项目结构 | P0 | 1天 | `skills/deep-dive-v3/`目录 |
| T1.2 实现BlackboardManager | P0 | 2天 | shared_state读写 |
| T1.3 实现PipelineEngine(FSM) | P0 | 3天 | 状态机驱动 |
| T1.4 实现Coordinator | P0 | 2天 | 主入口 |
| T1.5 实现三种管线模板 | P0 | 2天 | iterative/audit/gated |
| T1.6 实现QualityGate | P0 | 2天 | 质量评估 |
| T1.7 实现CheckpointManager | P0 | 2天 | 检查点保存 |
| T1.8 实现Observability | P0 | 2天 | 日志+指标+追踪 |
| T1.9 配置4个领域 | P0 | 2天 | investment/architecture/code/general |
| T1.10 迁移V2.4领域 | P0 | 2天 | 自动化迁移工具 |
| T1.11 集成测试 | P0 | 2天 | 100%成功率 |

**Phase 1验收标准**:
- 4个领域100%成功率
- 平均耗时4分钟以内
- 可观测性数据完整

### Phase 2：增强功能（2-3周）

**目标**：完善体验，增加场景

| 任务 | 优先级 | 工期 | 交付物 |
|:---|:---:|:---:|:---|
| T2.1 Project级记忆 | P1 | 3天 | workspace/.v3/projects/ |
| T2.2 扩展并行策略 | P1 | 2天 | all/first/any |
| T2.3 Critic动态分配 | P1 | 3天 | 领域感知Critic |
| T2.4 进度实时推送 | P1 | 2天 | 每2分钟更新 |
| T2.5 质量维度可配置 | P1 | 2天 | YAML配置维度 |
| T2.6 新增2个场景 | P1 | 3天 | system_build/system_audit |
| T2.7 性能优化 | P1 | 3天 | 冷启动优化 |

### Phase 3：高级功能（3-4周）

**目标**：智能化，生态化

| 任务 | 优先级 | 工期 | 交付物 |
|:---|:---:|:---:|:---|
| T3.1 User级记忆 | P2 | 5天 | 用户偏好学习 |
| T3.2 自动模型路由 | P2 | 5天 | 按复杂度选模型 |
| T3.3 HITL完善 | P2 | 3天 | 更灵活的人工干预 |
| T3.4 A2A协议预留 | P2 | 3天 | 兼容第三方Agent |
| T3.5 自动技能学习 | P2 | 5天 | Hermes借鉴 |

---

## 第七章：风险评估与缓解

### 7.1 风险矩阵（融合千问专家）

| 风险ID | 风险描述 | 概率 | 影响 | 等级 | 缓解措施 |
|:---:|:---|:---:|:---:|:---:|:---|
| R1 | 20并发极限性能不达标 | 中 | 高 | 🔴 | 单任务≤6并发，预留降级策略 |
| R2 | 长任务Checkpoint可靠性 | 中 | 中 | 🟡 | 阶段级保存+心跳检测 |
| R3 | 向后兼容破坏 | 低 | 高 | 🔴 | 自动化迁移+回归测试 |
| R4 | 配置复杂度失控 | 中 | 中 | 🟡 | 模板化+分层配置 |
| R5 | 维护认知负担 | 中 | 中 | 🟡 | 文档化+自解释配置 |
| R6 | HITL用户响应延迟 | 高 | 中 | 🟡 | 超时机制+默认自动通过 |
| R7 | 第三方模型不可用 | 低 | 高 | 🔴 | 降级链+Mock模式 |

### 7.2 关键风险详细缓解

**R1：20并发极限性能不达标**
- **根因**：OpenClaw maxConcurrent=20硬约束
- **缓解**:
  1. 单任务≤6并发（留14余量）
  2. 设计降级策略（减少Critic数量）
  3. 监控并发数，接近阈值时排队

**R3：向后兼容破坏**
- **根因**：V3.0改动可能影响V2.4领域
- **缓解**:
  1. 自动化迁移工具（V2.4→V3.0配置转换）
  2. 双版本并行运行期
  3. 完整回归测试套件
  4. 紧急回滚机制

**R6：HITL用户响应延迟**
- **根因**：用户可能长时间不响应`/approve`
- **缓解**:
  1. 设置HITL超时（默认24小时）
  2. 超时后默认自动通过（ configurable）
  3. 飞书推送+短信提醒（可选）

### 7.3 向后兼容策略

**迁移路径**:
```
V2.4领域 → [迁移工具] → V3.0 YAML配置
```

**并行运行期**（2周）:
- V2.4和V3.0同时运行
- 对比输出质量
- 逐步切流

**回滚策略**:
- 保留V2.4代码路径
- 配置开关切换
- 紧急情况下秒级回滚

---

## 附录

### A. 术语表

| 术语 | 定义 |
|:---|:---|
| Blackboard | 文件共享机制，Agent间通过文件传递数据 |
| FSM | 有限状态机，平铺结构，驱动管线状态流转 |
| HITL | Human-in-the-loop，人工回环，关键决策点人工确认 |
| IoC | Inversion of Control，控制反转，声明式编排 |
| Pipeline | 管线，定义Agent执行流程的模板 |
| Stage | 阶段，管线中的执行步骤 |
| Checkpoint | 检查点，保存执行状态以便恢复 |

### B. 参考文档

1. `v3-pre-design-spec.md` - Pre-Design规范
2. `v3-architecture-inputs-summary.md` - 架构输入汇总
3. `v3-architecture-design-kimi-k2.5-complete.md` - Kimi基础方案
4. `V3.0_ARCHITECTURE_DESIGN_GEMINI3.1.md` - Gemini方案
5. `v3.0-architecture-design-qwen3.6-plus-complete.md` - 千问方案
6. `V3.0_ARCHITECTURE_FINAL_REPORT.md` - 多Agent论证报告
7. `V3.0_ARCHITECTURE_REVIEW_REPORT_KIMI_K2.5_EXPERT.md` - Kimi专家评审
8. `v3-architecture-review-qwen3.6-plus.md` - 千问专家评审

---

**文档结束**

*本架构设计文档基于全量输入材料最优决策生成，融合了Kimi基础方案、Gemini先进理念、千问稳健设计，以及三位专家的评审意见。*
