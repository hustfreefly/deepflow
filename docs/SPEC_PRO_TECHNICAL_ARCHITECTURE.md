# Spec Pro 技术架构设计（v2.0 — OpenClaw 多Agent协作版）

> **版本**: v2.0
> **日期**: 2026-05-23
> **作者**: 小满 🦞
> **状态**: ✅ 技术架构设计（基于 OpenClaw 约束重构）
> **变更**: v1.0 → v2.0 核心变更：从纯 Python 库 → OpenClaw 多Agent协作系统

---

## 1. 核心约束

### 1.1 OpenClaw 平台约束

| 约束 | 含义 | 影响 |
|:---|:---|:---|
| `sessions_spawn` | 创建子Agent的唯一方式 | 所有 LLM 推理必须通过 spawn Worker |
| `sessions_yield` | 等待子Agent完成 | 主Agent需要 yield 等待 Worker |
| 子Agent无用户交互 | 子Agent不能直接跟用户对话 | 主Agent是唯一用户界面 |
| Blackboard | 文件共享是跨Agent状态传递方式 | Worker 通过文件读写传递数据 |
| Prompt 驱动 | Worker 行为由 Prompt 决定 | 核心逻辑在 Prompt，不在 Python |
| exec 无 openclaw | Python 进程不能 import openclaw | Orchestrator 不能直接调 spawn |

### 1.2 与 Solution Pro 架构对齐

```
Solution Pro 模式（参考）:
  主Agent
    └── spawn → Orchestrator (depth-1, LLM Agent)
         ├── spawn → DataManager Worker (depth-2)
         ├── spawn → Planner Worker (depth-2)
         ├── spawn → Reviewers ×3 (depth-2, parallel)
         ├── spawn → Researchers ×N (depth-2, parallel)
         └── ...

Spec Pro 模式（对齐）:
  主Agent（用户界面）
    └── spawn → SpecProOrchestrator (depth-1, LLM Agent)
         ├── spawn → ParseWorker (depth-2)
         ├── spawn → QuestionWorker (depth-2)
         ├── spawn → ResponseWorker (depth-2)
         ├── spawn → AssessWorker (depth-2)
         └── spawn → StructureWorker (depth-2)
```

### 1.3 交互式 vs 批处理的差异

| 维度 | Solution Pro（批处理） | Spec Pro（交互式） |
|:---|:---|:---|
| 执行方式 | 一次启动，端到端自动完成 | 分轮次执行，每轮暂停等用户 |
| Orchestrator | 一个 sub-agent 跑完全程 | 每轮 spawn 新的 Worker |
| 用户交互 | 无（只有最终输出） | 多轮对话 |
| 主Agent角色 | 启动 + 等待 + 交付结果 | 启动 + 中继对话 + 交付结果 |

---

## 2. 整体架构

### 2.1 三层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: 主Agent（小满）— 用户界面层                               │
│                                                                     │
│  职责:                                                              │
│  - 接收用户输入                                                     │
│  - spawn SpecProOrchestrator（每轮一次或首次）                       │
│  - 中继问题给用户                                                   │
│  - 中继用户回答给下一轮                                             │
│  - 展示摘要 + 确认                                                  │
│  - 将最终 Living Spec 喂给 Solution Pro                             │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ sessions_spawn
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2: SpecProOrchestrator Worker（depth-1）                     │
│                                                                     │
│  职责:                                                              │
│  - 读取 Blackboard 上的当前 Spec 状态                               │
│  - 根据当前阶段 spawn 对应 Worker                                   │
│  - 等待 Worker 完成                                                 │
│  - 汇总 Worker 输出                                                 │
│  - 决定是否需要继续收集                                             │
│  - 将结果写入 Blackboard                                            │
│                                                                     │
│  执行模式:                                                          │
│  - 每轮被主Agent spawn 一次                                         │
│  - 输入: Blackboard 当前状态 + 用户本轮回答                         │
│  - 输出: 问题列表（需要继续）或 最终 Spec（完成）                    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ sessions_spawn
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: Worker Agents（depth-2）                                  │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐         │
│  │  ParseWorker  │  │ Question     │  │  ResponseWorker  │         │
│  │  (解析+推断)  │  │ Worker       │  │  (解析回答)      │         │
│  │              │  │ (苏格拉底    │  │                  │         │
│  │ 首轮专用     │  │  问题生成)   │  │  每轮(非首轮)    │         │
│  └──────────────┘  └──────────────┘  └──────────────────┘         │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐                                │
│  │  AssessWorker │  │  Structure   │                                │
│  │  (质量评估)   │  │  Worker      │                                │
│  │              │  │  (最终结构化)│                                │
│  │  每轮执行    │  │  末轮专用    │                                │
│  └──────────────┘  └──────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Blackboard 数据流

```
blackboard/{session_id}/
├── spec/
│   ├── input.md                    # 用户初始输入（主Agent写入）
│   ├── living_spec.json            # Living Spec（Worker读写）
│   ├── conversation_log.json       # 对话历史（Worker追加）
│   ├── quality_report.json         # 质量评估（AssessWorker写入）
│   └── route_recommendation.json   # 路由建议（StructureWorker写入）
├── stages/
│   ├── round_01_parse.json         # ParseWorker 输出
│   ├── round_01_questions.json     # QuestionWorker 输出
│   ├── round_02_response.json      # ResponseWorker 输出
│   ├── round_02_assess.json        # AssessWorker 输出
│   ├── round_02_questions.json     # QuestionWorker 输出
│   ├── ...
│   └── final_structure.json        # StructureWorker 输出
└── execution_log.json              # 执行日志
```

---

## 3. 执行流程（详细）

### 3.1 Round 1（首轮）

```
主Agent:
  1. 用户说: "设计一个AI算力调度平台"
  2. 写入 Blackboard: spec/input.md
  3. spawn SpecProOrchestrator Worker:
     task: "你是 Spec Pro Orchestrator。
            Session: {session_id}
            Blackboard: {blackboard_path}
            当前阶段: round_1_init
            执行首轮解析和推断。"
     timeout: 300

SpecProOrchestrator Worker (depth-1):
  1. 读取 spec/input.md
  2. spawn ParseWorker (depth-2):
     task: "你是 Spec Pro ParseWorker。
            读取: {blackboard}/spec/input.md
            任务: 解析用户输入 + 行业推断
            写入: {blackboard}/stages/round_01_parse.json
                  {blackboard}/spec/living_spec.json
            Prompt: {spec_pro/parse.md 内容}"
  3. 等待 ParseWorker 完成
  4. spawn AssessWorker (depth-2):
     task: "你是 Spec Pro AssessWorker。
            读取: {blackboard}/spec/living_spec.json
            任务: 7维度质量评估
            写入: {blackboard}/spec/quality_report.json
                  {blackboard}/stages/round_01_assess.json"
  5. 等待 AssessWorker 完成
  6. spawn QuestionWorker (depth-2):
     task: "你是 Spec Pro QuestionWorker。
            读取: {blackboard}/spec/living_spec.json
                  {blackboard}/spec/quality_report.json
            任务: 苏格拉底式引导问题生成 (2-3个)
            写入: {blackboard}/stages/round_01_questions.json"
  7. 等待 QuestionWorker 完成
  8. 汇总输出 → 写入 {blackboard}/spec/current_questions.json
  9. Worker 完成，返回主Agent

主Agent:
  4. 读取 current_questions.json
  5. 展示问题给用户（带推断确认）
  6. 等待用户回答
```

### 3.2 Round N（后续轮次）

```
主Agent:
  1. 用户回答了上一轮问题
  2. 写入 Blackboard: spec/user_response_round_{N}.md
  3. spawn SpecProOrchestrator Worker:
     task: "你是 Spec Pro Orchestrator。
            Session: {session_id}
            Blackboard: {blackboard_path}
            当前阶段: round_{N}_collecting
            用户回答已写入 spec/user_response_round_{N}.md
            执行本轮解析 + 评估 + 问题生成。"
     timeout: 300

SpecProOrchestrator Worker (depth-1):
  1. spawn ResponseWorker (depth-2):
     task: "读取当前问题 + 用户回答 + 当前 Spec
            任务: 解析回答，更新 living_spec.json
            写入: stages/round_{N}_response.json"
  2. 等待完成
  3. spawn AssessWorker (depth-2):
     task: "读取更新后的 living_spec.json
            任务: 重新评估质量"
  4. 等待完成
  5. 读取 quality_report.json
  6. 判断: 质量是否达标？
     - 达标 → spawn StructureWorker → 返回最终结果
     - 未达标 → spawn QuestionWorker → 返回下一轮问题
  7. Worker 完成，返回主Agent

主Agent:
  4. 读取结果
     - 如果是问题 → 展示给用户，等待回答 → 进入 Round N+1
     - 如果是最终 Spec → 展示摘要给用户确认
```

### 3.3 确认阶段

```
主Agent:
  1. 展示 Spec 摘要
  2. 用户确认 or 修正
  3. 如果修正:
     - 写入 spec/user_revision.md
     - spawn SpecProOrchestrator（修正模式）
     - Orchestrator spawn ResponseWorker 解析修正
     - 重新评估 → 可能继续提问或重新确认
  4. 如果确认:
     - spawn StructureWorker（最终结构化）
     - 输出 final living_spec.json
     - 写入 Blackboard
```

---

## 4. Python 辅助层设计

### 4.1 SpecProCoordinator（主Agent侧辅助类）

> **不是 Orchestrator**，是主Agent侧的辅助工具类。
> 不负责 LLM 推理，只负责状态管理和流程控制。

```python
class SpecProCoordinator:
    """
    Spec Pro 主Agent侧协调器
    
    职责（纯流程控制，无 LLM 推理）:
    1. 初始化 session + Blackboard 目录
    2. 构建每轮 Orchestrator Worker 的 task prompt
    3. 跟踪对话轮次和状态
    4. 读取 Worker 输出，判断下一步动作
    
    注意:
    - 这个类运行在主Agent进程中
    - 不调用 sessions_spawn（由主Agent调用）
    - 不调用 LLM（所有推理由 Worker Agent 完成）
    """
    
    def __init__(self, scenario: str = "genesis", mode: str = "standard",
                 session_prefix: str = None):
        self.scenario = scenario
        self.mode = mode
        self.session_prefix = session_prefix
        self.session_id = None
        self.base_path = None
        self.current_round = 0
        
        # 模式配置
        self.mode_config = {
            "quick":    {"max_rounds": 3, "threshold": 60},
            "standard": {"max_rounds": 6, "threshold": 75},
            "deep":     {"max_rounds": 10, "threshold": 85}
        }
    
    def init_session(self, user_input: str) -> dict:
        """
        初始化 session 和 Blackboard
        
        写入:
        - spec/input.md（用户原始输入）
        - execution_log.json
        
        返回:
        {
            "session_id": str,
            "base_path": str,
            "orchestrator_task": str  # 首轮 Orchestrator Worker task
        }
        """
        # 生成 session_id
        self.session_id = self._generate_session_id()
        self.base_path = f"{DEEPFLOW_BASE}/blackboard/{self.session_id}"
        
        # 创建目录
        os.makedirs(f"{self.base_path}/spec", exist_ok=True)
        os.makedirs(f"{self.base_path}/stages", exist_ok=True)
        
        # 写入用户输入
        with open(f"{self.base_path}/spec/input.md", 'w') as f:
            f.write(user_input)
        
        # 写入初始 execution_log
        self._write_execution_log("init", {"user_input_length": len(user_input)})
        
        # 构建首轮 Orchestrator task
        task = self._build_orchestrator_task(round_num=1, phase="init")
        
        return {
            "session_id": self.session_id,
            "base_path": self.base_path,
            "orchestrator_task": task
        }
    
    def build_next_round_task(self, user_response: str) -> dict:
        """
        构建下一轮的 Orchestrator Worker task
        
        主Agent调用此方法前，已将用户回答写入 Blackboard。
        
        返回:
        {
            "orchestrator_task": str,
            "round_num": int,
            "is_final": bool  # 是否可能是最终轮
        }
        """
        self.current_round += 1
        
        # 写入用户回答
        response_path = f"{self.base_path}/spec/user_response_round_{self.current_round}.md"
        with open(response_path, 'w') as f:
            f.write(user_response)
        
        # 判断是否可能最终轮
        is_final = self.current_round >= self.mode_config[self.mode]["max_rounds"]
        
        task = self._build_orchestrator_task(
            round_num=self.current_round + 1,
            phase="collecting"
        )
        
        return {
            "orchestrator_task": task,
            "round_num": self.current_round + 1,
            "is_final": is_final
        }
    
    def read_round_output(self) -> dict:
        """
        读取本轮 Orchestrator Worker 的输出
        
        返回:
        {
            "action": "questions" | "summary" | "done",
            "questions": [...],          # action=questions 时
            "quality": {...},            # 当前质量评分
            "summary_text": str,         # action=summary 时
            "living_spec": {...},        # action=done 时
            "route_recommendation": {...} # action=done 时
        }
        """
        # 读取 Orchestrator 写入的结果文件
        result_path = f"{self.base_path}/spec/round_result.json"
        if os.path.exists(result_path):
            with open(result_path) as f:
                return json.load(f)
        
        return {"action": "error", "message": "Orchestrator 未产出结果"}
    
    def build_confirmation_task(self, user_confirmation: dict) -> str:
        """构建确认阶段的 Orchestrator task"""
        # 写入用户确认/修正
        confirm_path = f"{self.base_path}/spec/user_confirmation.md"
        with open(confirm_path, 'w') as f:
            json.dump(user_confirmation, f, ensure_ascii=False)
        
        return self._build_orchestrator_task(
            round_num=self.current_round + 1,
            phase="confirmation"
        )
    
    def _build_orchestrator_task(self, round_num: int, phase: str) -> str:
        """
        构建 SpecProOrchestrator Worker 的 task prompt
        
        这是核心方法：将 Prompt 模板 + 上下文 + 指令组装成完整 task
        """
        config = self.mode_config[self.mode]
        
        # 读取 Orchestrator Prompt 模板
        orchestrator_prompt = read_prompt("spec_pro/orchestrator")
        
        task = f"""{orchestrator_prompt}

## 当前任务上下文

- Session: {self.session_id}
- Blackboard: {self.base_path}
- 场景: {self.scenario}
- 模式: {self.mode}
- 当前轮次: {round_num}
- 阶段: {phase}
- 质量阈值: {config['threshold']}
- 最大轮数: {config['max_rounds']}

## 本轮执行指令
"""
        if phase == "init":
            task += """
### Round 1: 初始解析

1. spawn ParseWorker:
   - 读取: {blackboard}/spec/input.md
   - 任务: 解析用户输入 + 行业推断
   - Prompt: 使用 spec_pro/parse.md
   - 写入: {blackboard}/stages/round_01_parse.json + {blackboard}/spec/living_spec.json

2. spawn AssessWorker:
   - 读取: {blackboard}/spec/living_spec.json
   - 任务: 7维度质量评估
   - Prompt: 使用 spec_pro/assess.md
   - 写入: {blackboard}/spec/quality_report.json

3. spawn QuestionWorker:
   - 读取: living_spec.json + quality_report.json
   - 任务: 苏格拉底式引导问题 (2-3个) + 推断验证问题
   - Prompt: 使用 spec_pro/guide.md
   - 写入: {blackboard}/stages/round_01_questions.json

4. 汇总: 将问题写入 {blackboard}/spec/round_result.json
   格式: {"action": "questions", "questions": [...], "quality": {...}}
"""
        elif phase == "collecting":
            task += f"""
### Round {round_num}: 收集轮次

1. spawn ResponseWorker:
   - 读取: spec/living_spec.json + spec/user_response_round_{round_num-1}.md
           + stages/round_{round_num-1:02d}_questions.json
   - 任务: 解析用户回答，更新 living_spec.json
   - Prompt: 使用 spec_pro/parse_response.md
   - 写入: stages/round_{round_num:02d}_response.json

2. spawn AssessWorker:
   - 读取: spec/living_spec.json
   - 任务: 重新评估质量
   - 写入: spec/quality_report.json

3. 读取 quality_report.json，判断:
   - 总分 ≥ {config['threshold']} → 进入步骤 4a
   - 总分 < {config['threshold']} → 进入步骤 4b

4a. spawn StructureWorker:
    - 读取: spec/living_spec.json + spec/quality_report.json
    - 任务: 生成摘要 + 路由建议 + solution_pro_hints
    - 写入: spec/round_result.json
      格式: {{"action": "summary", "summary_text": "...", "quality": {{...}}}}

4b. spawn QuestionWorker:
    - 读取: living_spec.json + quality_report.json
    - 任务: 生成下一轮问题
    - 写入: spec/round_result.json
      格式: {{"action": "questions", "questions": [...], "quality": {{...}}}}
"""
        elif phase == "confirmation":
            task += """
### 确认阶段

1. 读取: spec/user_confirmation.md
2. 如果用户确认:
   - spawn StructureWorker (最终结构化)
   - 写入: spec/round_result.json
     格式: {"action": "done", "living_spec": {...}, "quality_report": {...}}
3. 如果用户修正:
   - spawn ResponseWorker (解析修正)
   - spawn AssessWorker (重新评估)
   - spawn QuestionWorker (如有新缺失)
   - 写入: spec/round_result.json
"""
        return task
    
    def _generate_session_id(self) -> str:
        """生成 session_id"""
        import hashlib
        prefix = self.session_prefix or "spec"
        hash8 = hashlib.md5(
            f"{prefix}_{time.time()}".encode()
        ).hexdigest()[:8]
        return f"{prefix}_spec_{hash8}"
    
    def _write_execution_log(self, event: str, data: dict):
        """写入执行日志"""
        log_path = f"{self.base_path}/execution_log.json"
        log = {"events": []}
        if os.path.exists(log_path):
            with open(log_path) as f:
                log = json.load(f)
        log["events"].append({
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data
        })
        with open(log_path, 'w') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
```

### 4.2 什么 NOT 用 Python

| 功能 | ❌ 不用 Python 实现 | ✅ 用 Worker Agent 实现 |
|:---|:---|:---|
| 解析用户输入 | ResponseParser 类 | ParseWorker（spawn + Prompt） |
| 行业推断 | InferenceEngine 类 | ParseWorker Prompt 中内嵌推断指令 |
| 问题生成 | QuestionGenerator 类 | QuestionWorker（苏格拉底 Prompt） |
| 质量评估 | QualityAssessor 类 | AssessWorker（评估 Prompt） |
| 回答解析 | ResponseParser 类 | ResponseWorker（解析 Prompt） |
| 最终结构化 | SpecBuilder 类 | StructureWorker（结构化 Prompt） |
| 路由建议 | RouteRecommender 类 | StructureWorker Prompt 中内嵌路由指令 |

**Python 只做**:
- session/Blackboard 初始化
- task prompt 构建（拼接 Prompt 模板 + 上下文）
- 文件读写（读 Worker 输出、写用户输入）
- 状态跟踪（轮次计数、模式配置）

---

## 5. Worker Agent Prompt 设计

### 5.1 Prompt 文件清单

```
prompts/spec_pro/
├── orchestrator.md       # SpecProOrchestrator 系统 Prompt
├── parse.md              # ParseWorker Prompt（解析+推断）
├── guide.md              # QuestionWorker Prompt（苏格拉底问题）
├── parse_response.md     # ResponseWorker Prompt（解析回答）
├── assess.md             # AssessWorker Prompt（质量评估）
└── structure.md          # StructureWorker Prompt（最终结构化+路由）
```

### 5.2 orchestrator.md

```markdown
# Spec Pro Orchestrator

你是 Spec Pro 的管线调度器，负责编排需求收集的 Worker Agents。

## 你的职责
1. 根据当前阶段，按顺序 spawn Worker Agents
2. 每个 Worker 完成后，读取其输出
3. 根据输出决定下一步动作
4. 将最终结果写入 {blackboard}/spec/round_result.json

## 你的约束
- 你通过 sessions_spawn 创建 Worker
- Worker 之间通过 Blackboard 文件传递数据
- 你不能自己执行 LLM 推理（解析/推断/评估/问题生成），必须 spawn Worker
- 每个 Worker 完成后会写入文件，你读取文件判断下一步

## Worker 配置
所有 Worker 使用 cleanup="delete"（完成后清理）。
超时: 每个 Worker 300秒。

## 苏格拉底对话哲学
Spec Pro 的对话风格基于苏格拉底方法:
- **不告诉用户答案**，而是通过提问帮用户自己想清楚
- **六类问题**: 澄清 / 挑战假设 / 追问证据 / 换视角 / 推演后果 / 反思
- **推断-验证**: 基于行业知识推断，让用户确认
- **渐进收敛**: 先宽后窄，先大局后细节

## 执行指令
[由 SpecProCoordinator._build_orchestrator_task() 动态注入]
```

### 5.3 parse.md（ParseWorker）

```markdown
# Spec Pro ParseWorker

你是 Spec Pro 的解析与推断专家。

## 你的任务
1. 解析用户输入，提取结构化信息
2. 基于行业知识推断用户可能遗漏的需求
3. 生成初始 Living Spec

## 输入
读取: {blackboard}/spec/input.md（用户原始输入）

## 输出格式

写入两个文件:

### 文件 1: {blackboard}/stages/round_01_parse.json
```json
{
  "status": "completed",
  "parsed": {
    "objective": "一句话核心目标",
    "pain_points": ["痛点1", "痛点2"],
    "industry": "行业/领域",
    "solution_type_guess": "architecture|business|technical",
    "users_mentioned": [{"role": "角色", "detail": "细节"}],
    "capabilities_mentioned": [{"name": "功能", "detail": "细节"}],
    "constraints_mentioned": {"budget": "", "timeline": "", "tech_stack": []},
    "quality_hints": ["性能/安全/可用性线索"],
    "integration_hints": ["已有系统/集成需求"]
  },
  "inferred": [
    {
      "id": "INF-001",
      "dimension": "目标维度",
      "content": "推断内容",
      "confidence": 0.0-1.0,
      "basis": "推断依据（行业经验/常见模式）"
    }
  ],
  "confidence_note": "整体置信度说明"
}
```

### 文件 2: {blackboard}/spec/living_spec.json
[Living Spec 标准格式，包含 confirmed / inferred / guardrails 三层]

## 推断规则
1. 只推断**高概率**的行业通用需求（置信度 ≥ 0.5）
2. 每个推断必须标注 confidence 和 basis
3. 不推断用户明确否定的方向
4. 推断数量: 5-10 项（不要太多也不要太少）
5. 推断维度优先: 质量属性 > 集成环境 > 风险 > 用户场景

## 推断知识库（内置）
- AI平台类: GPU调度、多租户、任务队列、监控告警、成本分析...
- 电商类: 支付、库存、物流、推荐、风控...
- 数据平台类: ETL、数据质量、血缘分析、权限管控...
- 通用类: 安全合规、灾备、日志审计、API网关...
```

### 5.4 guide.md（QuestionWorker）

```markdown
# Spec Pro QuestionWorker

你是 Spec Pro 的苏格拉底式对话引导专家。

## 你的任务
基于当前 Living Spec 和质量评估报告，生成 2-3 个高质量引导问题。

## 输入
- 读取: {blackboard}/spec/living_spec.json
- 读取: {blackboard}/spec/quality_report.json

## 苏格拉底六类问题

| 类型 | 目的 | 示例 |
|:---|:---|:---|
| 澄清 | 追问模糊概念 | "你说的'高性能'具体指什么指标？" |
| 挑战假设 | 暴露隐含假设 | "你假设用户都熟悉K8s，如果不呢？" |
| 追问证据 | 验证合理性 | "99.99%的可用性目标，依据是什么？" |
| 换视角 | 引入其他视角 | "运维团队会怎么看这个设计？" |
| 推演后果 | 测试取舍 | "如果预算砍半，哪些功能先不做？" |
| 反思 | 检验问题定义 | "我们是不是在解决正确的问题？" |

## 问题生成策略

### 按轮次调整
- **第1-2轮**: 侧重 澄清 + 追问证据（理解基础）
- **第3-4轮**: 侧重 挑战假设 + 换视角（深挖）
- **第5+轮**: 侧重 推演后果 + 反思（验证完整性）

### 按维度优先级
评分最低的维度优先提问:
1. 目标与痛点 (weight 20%)
2. 用户与场景 (weight 15%)
3. 能力要求 (weight 15%)
4. 质量属性 (weight 15%)
5. 约束边界 (weight 15%)
6. 环境与集成 (weight 10%)
7. 风险与假设 (weight 10%)

### 推断验证
如果有高置信度推断（confidence ≥ 0.6）且状态为 pending:
- 生成 1 个验证问题: "我推断你可能需要 X，这符合你的情况吗？"
- 每轮最多验证 2 个推断

## 输出格式
写入: {blackboard}/stages/round_{NN}_questions.json
```json
{
  "questions": [
    {
      "type": "clarification|probe_assumption|probe_evidence|alternative_view|implication|meta",
      "dimension": "针对的需求维度",
      "text": "问题文本（自然、口语化、有温度）",
      "importance": "high|medium|low",
      "is_inference_validation": false,
      "inference_id": null
    }
  ],
  "strategy_note": "本轮提问策略说明（1-2句）"
}
```

## 约束
- 每轮 2-3 个问题，不超过 3 个
- 问题要具体，不要泛泛而谈
- 问题之间不重叠
- 混合至少 2 种问题类型
- 语气自然，像资深顾问在聊天，不像在审问
```

### 5.5 assess.md（AssessWorker）

```markdown
# Spec Pro AssessWorker

你是 Spec Pro 的需求质量评估专家。

## 你的任务
对 Living Spec 进行 7 维度加权评分，输出 S/A/B/C 等级。

## 输入
读取: {blackboard}/spec/living_spec.json

## 评估维度

| 维度 | 权重 | 评估要点 |
|:---|:---|:---|
| 目标与痛点 (Why) | 20% | 问题清晰、目标可衡量、有成功指标 |
| 用户与场景 (Who) | 15% | 角色明确、场景具体、有用户旅程 |
| 能力要求 (What) | 15% | Always/Should/Never三层清晰 |
| 质量属性 (How Well) | 15% | 有具体指标和优先级 |
| 约束边界 (Bounds) | 15% | 预算/时间/技术约束明确 |
| 环境与集成 (Where) | 10% | 已有系统、集成接口清晰 |
| 风险与假设 (What If) | 10% | 已识别关键风险和假设 |

## 评分标准

每个维度 0-100 分:
- 0: 完全缺失
- 30: 有信息但严重不足
- 50: 部分覆盖
- 70: 基本满足
- 85: 充分
- 100: 卓越

## 质量等级
- S (90-100): 卓越 — 7维全覆盖，三层边界清晰
- A (75-89):  良好 — 核心维度覆盖，部分推断
- B (60-74):  可用 — 目标+能力+约束覆盖
- C (<60):    不足 — 建议继续收集

## 输出格式
写入: {blackboard}/spec/quality_report.json
```json
{
  "overall_score": 72.5,
  "level": "B",
  "dimensions": [
    {
      "dimension": "objective",
      "name": "目标与痛点",
      "weight": 0.20,
      "score": 85,
      "reasoning": "核心目标清晰，痛点有具体数据",
      "missing_items": []
    },
    ...
  ],
  "top_missing": ["缺少集成环境的详细信息", "风险识别不充分"],
  "recommendation": "建议继续收集集成环境和风险维度"
}
```
```

### 5.6 parse_response.md（ResponseWorker）

```markdown
# Spec Pro ResponseWorker

你是 Spec Pro 的回答解析专家。

## 你的任务
解析用户对引导问题的回答，提取结构化信息更新 Living Spec。

## 输入
- 读取: {blackboard}/spec/living_spec.json（当前 Spec）
- 读取: {blackboard}/stages/round_{NN}_questions.json（上轮问题）
- 读取: {blackboard}/spec/user_response_round_{NN}.md（用户回答）

## 解析规则

### 信息提取
1. 从用户自然语言中提取结构化信息
2. 映射到 Living Spec confirmed 层的对应维度
3. 只提取**新增**信息，不重复已有内容

### 推断处理
- 用户确认推断 → 移入 confirmed 层
- 用户拒绝推断 → 标记为 rejected
- 用户修正推断 → 更新内容并移入 confirmed

### 元信号检测
- "够了/可以了" → user_said_enough = true
- "方向不对" → user_wants_pivot = true
- "不太确定" → 标记为 needs_followup

## 输出格式
写入: {blackboard}/stages/round_{NN}_response.json
[解析结果 + 更新后的 living_spec.json]

## 重要: 更新 living_spec.json
你必须直接更新 {blackboard}/spec/living_spec.json:
- 新确认信息 → 加入 confirmed 层
- 推断确认 → 从 inferred 移到 confirmed
- 推断拒绝 → 标记 status=rejected
- 新推断（基于新信息的推断）→ 加入 inferred 层
```

### 5.7 structure.md（StructureWorker）

```markdown
# Spec Pro StructureWorker

你是 Spec Pro 的最终结构化专家。

## 你的任务
1. 生成 Living Spec 的用户可读摘要
2. 生成路由建议（推荐执行引擎）
3. 生成 solution_pro_hints（下游引擎提示）

## 输入
- 读取: {blackboard}/spec/living_spec.json
- 读取: {blackboard}/spec/quality_report.json

## 输出

### 摘要文本（展示给用户确认）
简洁、结构化、一目了然:
- 🎯 目标: ...
- 👥 用户: ...
- 💰 约束: ...
- 🔧 基础: ...
- 📦 核心能力: ...
- ⚡ 质量要求: ...

### 路由建议
```json
{
  "suggested_engine": "solution_pro|lightweight|direct",
  "suggested_mode": "quick|standard|rigorous",
  "reasoning": "推荐理由",
  "confidence": 0.0-1.0,
  "complexity_score": 0-100,
  "complexity_factors": ["因素1", "因素2"]
}
```

### Solution Pro 提示
```json
{
  "focus_areas": [
    {"area": "领域", "weight": 0.30, "reason": "理由"}
  ],
  "layer2_hints": {
    "researcher": ["研究重点1"],
    "auditor": ["审计重点1"]
  },
  "anti_patterns": ["不要做什么"]
}
```

写入: {blackboard}/spec/round_result.json
格式: {"action": "summary"|"done", ...}
```

---

## 6. 主Agent调用模式

### 6.1 完整对话流程（主Agent视角）

```python
# === 主Agent 代码 ===

from core.spec_pro.coordinator import SpecProCoordinator

# 1. 用户说: "设计一个AI算力调度平台"
coordinator = SpecProCoordinator(scenario="genesis", mode="standard")
init_result = coordinator.init_session("设计一个AI算力调度平台")

# 2. Spawn 首轮 Orchestrator
sessions_spawn(
    runtime="subagent",
    mode="run",
    task=init_result["orchestrator_task"],
    runTimeoutSeconds=300
)
sessions_yield()  # 等待 Orchestrator 完成

# 3. 读取首轮输出
round_output = coordinator.read_round_output()

# 4. 展示问题给用户
if round_output["action"] == "questions":
    # 展示推断确认 + 引导问题
    display_questions(round_output)

# 5. 用户回答
user_response = get_user_input()

# 6. 构建下一轮 task
next_task = coordinator.build_next_round_task(user_response)

# 7. Spawn 下一轮 Orchestrator
sessions_spawn(
    runtime="subagent",
    mode="run",
    task=next_task["orchestrator_task"],
    runTimeoutSeconds=300
)
sessions_yield()

# 8. 循环 3-7 直到完成
round_output = coordinator.read_round_output()
if round_output["action"] == "summary":
    display_summary(round_output)
    # 用户确认/修正...
elif round_output["action"] == "questions":
    # 继续对话...
```

### 6.2 与 Solution Pro 衔接

```python
# Spec Pro 完成
spec_result = coordinator.read_round_output()
living_spec = spec_result["living_spec"]

# 衔接 Solution Pro
from domains.solution import SolutionOrchestratorV21

orch = SolutionOrchestratorV21(
    topic=living_spec["confirmed"]["objective"],
    living_spec=living_spec  # ← Spec Pro 产出直接喂入
)
session_id = orch.init()

# 启动 Solution Pro 管线
sessions_spawn(
    runtime="subagent",
    mode="run",
    task=build_solution_pro_task(orch, living_spec),
    runTimeoutSeconds=3600
)
sessions_yield()
```

---

## 7. 文件清单（修正版）

### 7.1 新增文件

```
.deepflow/
├── core/
│   └── spec_pro/
│       ├── __init__.py                    # 模块导出
│       ├── coordinator.py                 # SpecProCoordinator (~250行)
│       └── models.py                      # 数据结构定义 (~150行)
├── prompts/
│   └── spec_pro/
│       ├── orchestrator.md                # Orchestrator 系统 Prompt
│       ├── parse.md                       # ParseWorker Prompt
│       ├── guide.md                       # QuestionWorker Prompt
│       ├── parse_response.md              # ResponseWorker Prompt
│       ├── assess.md                      # AssessWorker Prompt
│       └── structure.md                   # StructureWorker Prompt
├── cage/
│   └── spec_pro.yaml                      # 契约笼子文件
└── docs/
    └── SPEC_PRO_TECHNICAL_ARCHITECTURE.md # 本文档
```

### 7.2 修改文件

| 文件 | 改动 |
|:---|:---|
| `domains/solution_pro/orchestrator_agent.py` | 新增 `living_spec` 参数 |
| `domains/solution_pro/task_builder.py` | 各 build_xxx_task 支持 living_spec |

### 7.3 对比 v1.0（修正了什么）

| v1.0（❌） | v2.0（✅） | 原因 |
|:---|:---|:---|
| 12个 Python 模块 | 2个 Python 模块 + 6个 Prompt | LLM推理必须在 Worker Agent 中 |
| QuestionGenerator 类 | QuestionWorker Agent | 苏格拉底问题生成需要 LLM |
| InferenceEngine 类 | ParseWorker Prompt 内嵌 | 推断需要 LLM 的行业知识 |
| QualityAssessor 类 | AssessWorker Agent | 评估需要 LLM 的理解力 |
| ResponseParser 类 | ResponseWorker Agent | 解析自然语言需要 LLM |
| RouteRecommender 类 | StructureWorker Prompt 内嵌 | 路由建议需要 LLM 的判断 |
| engine.py（编排逻辑） | orchestrator.md（Prompt编排） | 编排逻辑由 Orchestrator Agent 执行 |
| 函数调用传参 | Blackboard 文件 | Agent 间通过文件共享状态 |

---

## 8. 契约笼子（修正版）

```yaml
module: spec_pro
version: "2.0"
complexity: medium  # Python层从 complex 降为 medium（重活交给 Worker）

interface:
  classes:
    - name: SpecProCoordinator
      methods:
        - name: init_session
          params: [user_input]
          returns: dict
          description: "初始化session，写入Blackboard，返回首轮task"
        - name: build_next_round_task
          params: [user_response]
          returns: dict
          description: "写入用户回答，构建下轮Orchestrator task"
        - name: read_round_output
          params: []
          returns: dict
          description: "读取Orchestrator Worker的输出"
        - name: build_confirmation_task
          params: [user_confirmation]
          returns: str
          description: "构建确认阶段的task"
  
  workers:  # Worker Agents（通过 Prompt 定义行为）
    - name: SpecProOrchestrator
      prompt: prompts/spec_pro/orchestrator.md
      spawns: [ParseWorker, QuestionWorker, ResponseWorker, AssessWorker, StructureWorker]
    - name: ParseWorker
      prompt: prompts/spec_pro/parse.md
    - name: QuestionWorker
      prompt: prompts/spec_pro/guide.md
    - name: ResponseWorker
      prompt: prompts/spec_pro/parse_response.md
    - name: AssessWorker
      prompt: prompts/spec_pro/assess.md
    - name: StructureWorker
      prompt: prompts/spec_pro/structure.md

behavior:
  success:
    - "Coordinator 正确生成 Orchestrator task（含完整上下文）"
    - "Orchestrator 正确 spawn Workers 并读取输出"
    - "Workers 正确读写 Blackboard 文件"
    - "3-6轮对话产出 Living Spec（Standard模式）"
    - "Living Spec 质量评分 ≥ 75（Standard模式阈值）"
    - "Solution Pro 可消费 Living Spec（向后兼容）"
  
  failure:
    - "Worker 超时 → Orchestrator 用简化输出继续"
    - "Blackboard 文件损坏 → 保留已收集的部分 Spec"
    - "用户输入无意义 → ParseWorker 标注低置信度"

boundaries:
  dependencies:
    - core/prompt_registry.py (读取 Prompt)
    - core/config/path_config.py (路径管理)
  
  forbidden:
    - "Coordinator 不得包含 LLM 推理逻辑"
    - "Coordinator 不得直接调用 sessions_spawn（由主Agent调用）"
    - "不得修改 Solution Pro 现有行为（只扩展）"
    - "Worker 不得直接调用 openclaw SDK"
```

---

## 9. 实施计划（修正版）

### Phase 1: 骨架 + Prompt（3天）

```
□ core/spec_pro/models.py（数据结构）
□ core/spec_pro/coordinator.py（状态管理 + task构建）
□ prompts/spec_pro/orchestrator.md
□ prompts/spec_pro/parse.md
□ prompts/spec_pro/guide.md
□ prompts/spec_pro/parse_response.md
□ prompts/spec_pro/assess.md
□ prompts/spec_pro/structure.md
□ cage/spec_pro.yaml
```

### Phase 2: Solution Pro 集成（1天）

```
□ SolutionOrchestratorV21 新增 living_spec 参数
□ task_builder.py 改造（注入 Living Spec 上下文）
□ 集成测试
```

### Phase 3: 端到端验证（1天）

```
□ POC: 真实需求跑完整流程
□ 验证: Worker Agent 正确读写 Blackboard
□ 验证: Living Spec 质量 ≥ A级
□ 验证: Solution Pro 消费 Living Spec 后输出质量提升
```

**总计: ~5天**（比 v1.0 的 8天更短，因为 Python 代码量大幅减少）

---

## 10. 关键洞察

> **v1.0 的根本错误**: 把 Spec Pro 设计成了"用 Python 写逻辑，用 Prompt 做包装"。
> 
> **v2.0 的核心修正**: Spec Pro 是"用 Prompt 写逻辑，用 Python 做脚手架"。
> 
> Python（Coordinator）只是脚手架——搭目录、拼 task、读文件。
> 真正的智能在 Worker Agent 的 Prompt 里——解析、推断、提问、评估、结构化。
> 
> 这跟 Solution Pro 的模式完全一致：**Prompt 是灵魂，Python 是骨架。**

---

*技术架构 v2.0 完成。忠礼确认后开始 Phase 1 实施。*
