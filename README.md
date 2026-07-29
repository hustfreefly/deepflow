# DeepFlow

> **多 Agent 管线框架**，运行在 OpenClaw 之上。
> 多 Agent 管线框架：**Spec → Solution → Ship → Deliver** 四域管线协作，另有独立研究引擎 Research Pro。

---

## 定位

DeepFlow 不是一个 Agent，而是 **Agent 的编排框架**。它在 OpenClaw 的 `sessions_spawn` 原语之上构建了：

- **域（Domain）**：独立的能力单元，每个域有自己的入口、prompts、测试
- **管线（Pipeline）**：域间协作，上游输出自动成为下游输入
- **统一 Blackboard**：基于文件系统的跨域状态共享（`.deepflow/blackboard/{project}/`）
- **全链路追踪**：跨域 `trace_id`，从需求到最终交付可追溯
- **MD-First 架构**：Markdown 做 source of truth，JSON 做 ~1KB 衍生品

---

## 五域架构

| 域 | 版本 | 职责 | 入口 |
|:---|:---:|:---|:---|
| **Spec Pro** | V2.3.0 | 需求梳理引擎 — 苏格拉底式对话，输出 Living Spec (MD) | `SpecProCoordinator` |
| **Solution Pro** | V4.1.0 | 方案设计引擎 — 纯 Agent Orchestrator + 对抗审查 | `run_solution_pro()` |
| **Ship Pro** | V2.1.0 | 交付包生成引擎 — PipelineDesigner + Workers + Consolidator | `run_ship_pro()` |
| **Deliver Pro** | V3.1.0 | 执行引擎 — Code-First Assembly，确定性拼接零 LLM | `run_deliver_pro()` |
| **Research Pro** | V2.0.0 | 多专家并行研究 — DDGS 搜索 + 来源分级 + 引用验证 | `run_research_pro()` |

> Loop Engine 为内部调度引擎，非独立域。

---

## 域间协作流

```
用户输入
  │
  ▼
┌─────────────────────────────────────┐
│  Spec Pro (V2.3.0)                  │
│  苏格拉底式对话 → Living Spec (MD)  │
│  Semantic REQ-ID + Anchors          │
└──────────────┬──────────────────────┘
               │ living_spec.md + requirement_index
               ▼
┌─────────────────────────────────────┐
│  Solution Pro (V4.1.0)              │
│  纯 Agent Orchestrator              │
│  Planning / Research / Summary      │
│  + 对抗质量审查 + 一致性检查        │
└──────────────┬──────────────────────┘
               │ final_solution.md + solution_track.json
               ▼
┌─────────────────────────────────────┐
│  Ship Pro (V2.1.0)                  │
│  PipelineDesigner → Orchestrator    │
│  → Workers(并行) → Consolidator     │
│  → ShipPackage (MD)                 │
└──────────────┬──────────────────────┘
               │ ship_package.md + ship_track.json
               ▼
┌─────────────────────────────────────┐
│  Deliver Pro (V3.1.0)               │
│  Analyze → Generate → **Assemble**  │
│  Code-First Assembly (零 LLM)       │
│  → Validate → Package               │
│  → deliver_final.md                 │
└─────────────────────────────────────┘
```

---

## 核心设计

### MD-First 架构 (ADR-009)

- **MD 是 source of truth**：下游 LLM 直接读上游 MD（完整语义）
- **JSON 是衍生品**：`{域}_track.json` ~1KB（Gate 数值 + 追溯摘要）
- **数据流**：MD → JSON（单向），不存在同步问题
- 每域 2 文件 + 1 目录：`{域}_{内容}.md` + `{域}_track.json` + `stages/`

### 三层门控

所有关键决策点采用三层门控，而非单一 LLM 判断：

| 层 | 职责 | 实现 |
|:---:|:---|:---|
| **L1** | 代码粗筛 | 确定性校验：Pydantic Schema、字段存在、无环依赖 |
| **L2** | LLM 语义 | 独立视角评估：对抗审查、一致性检查、质量打分 |
| **L3** | 合并决策 | L1 + L2 合并 → PASS / CONDITIONAL / FAIL |

### Code-First Assembly (Deliver Pro)

- **问题**：LLM 做"合并"会摘要压缩（264KB → 42KB，84% 丢失）
- **解决**：Python 确定性拼接（读文件→标题归一→物理拼接→TOC→写文件）
- **效果**：保留率 ≥95%，零 LLM 调用
- **不变量**：`len(final) >= sum(len(worker.content))`

### Semantic Anchors

- 不可变实体（只增不改不删），跨域全链路透传
- 三层防线：注入(预防) + 位置优化(增强) + Judge(检测修复)
- 契约笼子：Pydantic `raise ValueError`，不静默降级

### 能力正交

- **代码做格式兼容**（确定性）：Pydantic alias、类型转换、字段映射
- **LLM 做语义设计**（非确定性）：判断、决策、生成、评估

---

## Quick Start

### 安装

```bash
# 克隆仓库
git clone https://github.com/hustfreefly/deepflow.git
cd deepflow

# 安装依赖
pip install -r requirements.txt
```

### 前置条件

DeepFlow 运行在 [OpenClaw](https://github.com/openclaw/openclaw) 之上，需要：
- OpenClaw 已安装并运行
- Python 3.11+
- LLM API 配置（支持 Qwen / DeepSeek / Kimi / GPT 等）

### 运行测试

```bash
python3 -m pytest tests/ -v
```

### 使用示例

```python
# 1. 需求梳理（Spec Pro）
from domains.spec_pro import SpecProCoordinator
coordinator = SpecProCoordinator(user_input="我要做一个高并发消息系统")
result = coordinator.run()
# → living_spec.md + requirement_index

# 2. 方案设计（Solution Pro）
from domains.solution_pro import run_solution_pro
result = run_solution_pro(project_name="my_project")
# → solution_design.md

# 3. 交付包生成（Ship Pro）
from domains.ship_pro import run_ship_pro
result = run_ship_pro(project_name="my_project")
# → ship_package.md (WPs + 依赖图)

# 4. 执行交付（Deliver Pro）
from domains.deliver_pro import run_deliver_pro
result = run_deliver_pro(project_name="my_project")
# → deliver_final.md
```

---

## 项目结构

```
deepflow/
├── README.md                    # 本文件
├── SKILL.md                     # OpenClaw Skill 定义
├── CHANGELOG.md                 # 变更日志
├── LICENSE                      # MIT License
├── requirements.txt             # Python 依赖
├── conftest.py                  # pytest 配置
├── pytest.ini                   # 测试配置
│
├── core/                        # 框架核心
│   ├── agents/                  # Agent 基类
│   ├── blackboard/              # Blackboard 引擎
│   ├── cage/                    # 契约笼子
│   ├── config/                  # 全局配置
│   ├── orchestrator/            # 编排基类
│   ├── quality/                 # 质量评判
│   ├── prompt_registry.py       # Prompt 注册表
│   ├── trace.py                 # 全链路追踪
│   ├── md_track_extractor.py    # MD → track.json 提取
│   └── unified_entry.py         # 统一入口
│
├── domains/                     # 五域
│   ├── spec_pro/                # Spec Pro V2.3.0
│   ├── solution_pro/            # Solution Pro V4.1.0
│   ├── ship_pro/                # Ship Pro V2.1.0
│   ├── deliver_pro/             # Deliver Pro V3.1.0
│   ├── research_pro/            # Research Pro V2.0.0
│   └── loop_engine/             # 内部调度引擎
│
├── contracts/                   # 全局契约
├── prompts/                     # 全局 prompts
├── config/                      # 全局配置
├── scripts/                     # 工具脚本
├── tests/                       # 全局测试
├── docs/                        # 文档 + 架构图
├── eval/                        # 评估框架
├── wiki/                        # 知识库
└── decisions/                   # ADR 决策记录
```

---

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。

---

*DeepFlow — 让 Agent 管线像流水线一样可靠。*
