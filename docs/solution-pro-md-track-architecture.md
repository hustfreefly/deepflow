# Solution Pro MD + Track 架构设计

> **版本**: V1.0 | **日期**: 2026-07-29  
> **目标**: 清理 JSON 技术债 → 纯 MD 流转 → 加 Track 追踪层

---

## 1. 现状分析

### 1.1 已有的基础设施

| 组件 | 位置 | 功能 |
|------|------|------|
| `track_generator.py` | `core/` | 从 MD 生成 track.json |
| `md_track_extractor.py` | `core/` | mistune AST 解析，提取结构化数据 |
| `solution_living_md.py` | `domains/solution_pro/` | final_solution MD ↔ Dict 双向转换 |
| `frozen_living_md.py` | `domains/solution_pro/` | frozen_spec MD ↔ Dict 双向转换 |
| `generate_solution_track()` | `domains/solution_pro/__init__.py` | 从 final_solution.md 生成 track |

### 1.2 当前问题

| 问题 | 类型 | 影响 |
|------|------|------|
| `frozen_spec.json` fallback 路径 | 技术债 | 绕过 MD-first |
| `final_solution.json` fallback 路径 | 技术债 | 绕过 MD-first |
| `master_state.json` 双源共存 | 技术债 | 状态不一致风险 |
| Track 是"附加功能" | 架构问题 | 不是核心架构的一部分 |
| MD 和 Track 关系不清晰 | 设计问题 | 谁是 source of truth？ |

### 1.3 Solution Pro 数据流

```
Spec Pro → frozen_spec.md → Solution Pro → final_solution.md → Ship Pro
                                       → solution_document.md
                                       → solution_track.json (衍生)
```

---

## 2. 目标架构：MD-Track 双层模型

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: MD（Source of Truth）                                  │
│  ─────────────────────────────                                  │
│  • frozen_spec.md        — 输入规格（来自 Spec Pro）              │
│  • final_solution.md     — 主交付物（结构化方案）                 │
│  • solution_document.md  — 人类可读文档                          │
│                                                                  │
│  特点：人类可读、语义丰富、版本可追踪                              │
│  写入：render_xxx_md() → write_stage(name, str)                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 自动提取（pipeline 完成时）
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: Track（Derived Metadata）                              │
│  ────────────────────────────                                   │
│  • solution_track.json   — 从 final_solution.md 自动提取         │
│                                                                  │
│  内容：                                                          │
│  • frontmatter: version, session, created                        │
│  • gate_summary: L1/L2/L3 verdicts                               │
│  • metrics: req_ids, req_count, section_count, content_length    │
│  • anchors: 章节行号（导航用）                                    │
│  • solution_specific: key_decisions, implementation_phases,      │
│                       risk_count, semantic_anchors,              │
│                       constraint_coverage                        │
│                                                                  │
│  消费方：                                                        │
│  • Ship Pro → 读取 REQ 覆盖、semantic_anchors                    │
│  • Deliver Pro → 读取质量指标、gate verdicts                     │
│  • 人类 → 快速查看状态（不用解析 MD）                             │
│                                                                  │
│  特点：只读、自动生成、不可手动修改                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: Internal JSON（Worker 通信，保留）                      │
│  ─────────────────────────────────────                          │
│  • planning_convergence.json                                    │
│  • expert_plans/*.json                                          │
│  • research_digest.json                                         │
│  • meta_planning.json                                           │
│  • ... (29 种内部中间产物)                                       │
│                                                                  │
│  特点：结构化数据、Worker 间传递、Schema 验证                    │
│  注意：不是"技术债"，是正确的工具选择                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: State（运行时状态，清理双源）                           │
│  ──────────────────────────────                                 │
│  • .runs/*.run.json          — 唯一状态源                        │
│  • ❌ master_state.json      — 删除（双源共存）                  │
│  • _solution_pulse_state.json — 保留（Pulse 专用）              │
│                                                                  │
│  特点：频繁读写、运行时状态、不参与跨域传递                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **MD 是唯一真相源** | Track 是从 MD 自动提取的"视图"，不是独立数据 |
| **Track 自动生成** | MD 写入后，Track 必须同步生成（失败 = 架构违反） |
| **Track 只读** | 任何系统不能直接写 Track，只能从 MD 提取 |
| **Internal JSON 保留** | Worker 间通信用 JSON 是正确的，不是债 |
| **State 单源** | 删除 master_state.json，统一用 .runs/*.run.json |

---

## 3. Solution Pro Track Schema

### 3.1 当前 Track Schema（基础版）

```json
{
  "schema_version": "3.0.0",
  "domain": "solution_pro",
  "source_file": "final_solution.md",
  "frontmatter": {
    "version": "2.0.0",
    "session": "sol_xxx",
    "created": "2026-07-29T20:00:00Z"
  },
  "gate_summary": {
    "L1_Schema": "PASS",
    "L2_Semantic": "PASS",
    "L3_Merge": "PASS"
  },
  "metrics": {
    "req_ids": ["REQ-001", "REQ-002"],
    "req_count": 2,
    "section_count": 8,
    "content_length": 12500
  },
  "anchors": {
    "meta_info": {"line": 5, "section": "meta_info"},
    "key_decisions": {"line": 45, "section": "key_decisions"}
  }
}
```

### 3.2 扩展 Track Schema（Solution Pro 专用）

```json
{
  "schema_version": "3.1.0",
  "domain": "solution_pro",
  "source_file": "final_solution.md",
  
  "frontmatter": {
    "version": "2.0.0",
    "session": "sol_xxx",
    "created": "2026-07-29T20:00:00Z",
    "topic": "全链路可观测性平台",
    "solution_type": "architecture"
  },
  
  "gate_summary": {
    "L1_Schema": "PASS",
    "L2_Semantic": "PASS",
    "L3_Merge": "PASS"
  },
  
  "metrics": {
    "req_ids": ["REQ-001", "REQ-002", "REQ-003"],
    "req_count": 3,
    "section_count": 12,
    "content_length": 15000
  },
  
  "solution_specific": {
    "key_decisions": [
      {
        "decision": "采用两层 Collector 拓扑",
        "rationale": "Agent-Gateway 分离，降低网络开销",
        "covered_req_ids": ["REQ-001", "REQ-004"]
      }
    ],
    "key_decisions_count": 5,
    
    "implementation_phases": [
      {
        "phase": "Phase 1: 采集层",
        "duration": "4 周",
        "milestones": ["OTLP Collector 部署", "Kafka 集群搭建"]
      }
    ],
    "implementation_phases_count": 4,
    
    "risk_count": 8,
    "risks": [
      {
        "risk": "Kafka 背压导致数据丢失",
        "impact": "high",
        "mitigation": "实现背压机制"
      }
    ],
    
    "semantic_anchors": [
      {
        "name": "OpenTelemetry Collector",
        "category": "technology",
        "constraint": "REQ-001"
      },
      {
        "name": "Apache Kafka",
        "category": "technology",
        "constraint": "REQ-004"
      }
    ],
    
    "constraint_coverage": {
      "total": 20,
      "covered": 18,
      "ratio": 0.9,
      "uncovered": ["REQ-015", "REQ-018"]
    }
  },
  
  "anchors": {
    "meta_info": {"line": 5, "section": "meta_info"},
    "overview": {"line": 15, "section": "overview"},
    "key_decisions": {"line": 45, "section": "key_decisions"},
    "implementation_phases": {"line": 120, "section": "implementation_phases"},
    "requirement_coverage": {"line": 200, "section": "requirement_coverage"},
    "risk_summary": {"line": 250, "section": "risk_summary"},
    "semantic_anchors": {"line": 300, "section": "semantic_anchors"}
  },
  
  "quality_indicators": {
    "harness_score": 0.85,
    "verification_status": "PASS",
    "fix_loops": 2
  }
}
```

### 3.3 Track 提取逻辑

```python
# core/md_track_extractor.py 扩展

def extract_solution_track(md_content: str) -> dict:
    """从 final_solution.md 提取 Solution Pro 专用 track.json"""
    
    # 1. 基础提取（已有）
    track = extract_track_json(md_content, "solution_pro")
    
    # 2. Solution Pro 专用提取
    tables = _extract_tables_mistune(md_content)
    
    # 2.1 提取 key_decisions
    key_decisions = _extract_key_decisions(md_content)
    
    # 2.2 提取 implementation_phases
    implementation_phases = _extract_implementation_phases(md_content)
    
    # 2.3 提取 risks
    risks = _extract_risks(md_content)
    
    # 2.4 提取 semantic_anchors
    semantic_anchors = _extract_semantic_anchors(md_content)
    
    # 2.5 计算 constraint_coverage
    constraint_coverage = _compute_constraint_coverage(md_content)
    
    # 3. 组装 solution_specific
    track["solution_specific"] = {
        "key_decisions": key_decisions,
        "key_decisions_count": len(key_decisions),
        "implementation_phases": implementation_phases,
        "implementation_phases_count": len(implementation_phases),
        "risk_count": len(risks),
        "risks": risks,
        "semantic_anchors": semantic_anchors,
        "constraint_coverage": constraint_coverage,
    }
    
    # 4. 提取质量指标
    track["quality_indicators"] = _extract_quality_indicators(md_content)
    
    return track
```

---

## 4. 实施计划

### Phase 1: 清理交付物 Fallback（P0）

**目标**: 删除所有 JSON fallback 路径，纯 MD 流转

| 任务 | 文件 | 动作 |
|------|------|------|
| 删除 frozen_spec.json fallback | `post_validator.py` | 改用 `read_stage` |
| 删除 final_solution.json fallback | `ship_pro/__init__.py` | 只读 `.md` |
| 删除 master_state.json | `__init__.py` | 统一用 `.runs/*.run.json` |

**验证**: `grep -rn "frozen_spec\.json\|final_solution\.json" domains/` 返回 0

### Phase 2: 扩展 Track Schema（P0）

**目标**: 添加 solution_specific 字段

| 任务 | 文件 | 动作 |
|------|------|------|
| 扩展 extract_track_json | `core/md_track_extractor.py` | 添加 solution_specific 提取 |
| 添加 key_decisions 提取 | `core/md_track_extractor.py` | 从 MD 表格提取 |
| 添加 implementation_phases 提取 | `core/md_track_extractor.py` | 从 MD 表格提取 |
| 添加 risks 提取 | `core/md_track_extractor.py` | 从 MD 表格提取 |
| 添加 semantic_anchors 提取 | `core/md_track_extractor.py` | 从 MD 列表提取 |
| 添加 constraint_coverage 计算 | `core/md_track_extractor.py` | 计算覆盖率 |

**验证**: 生成 solution_track.json 包含 solution_specific 字段

### Phase 3: Track 自动生成（P0）

**目标**: MD 写入后自动生成 Track

| 任务 | 文件 | 动作 |
|------|------|------|
| pipeline 完成后调用 generate_solution_track | `pulse.py` | 已有，确认调用 |
| Track 生成失败 = 架构违反 | `track_generator.py` | raise ValueError |
| 添加 Track 完整性检查 | `track_generator.py` | 验证 solution_specific 存在 |

**验证**: pipeline 完成后 solution_track.json 自动生成

### Phase 4: Ship Pro 改用 Track（P1）

**目标**: Ship Pro 读取 solution_track.json 而不是解析 final_solution.md

| 任务 | 文件 | 动作 |
|------|------|------|
| Ship Pro 读取 solution_track.json | `ship_pro/__init__.py` | 从 track 获取 REQ 覆盖 |
| Ship Pro 读取 semantic_anchors | `ship_pro/pipeline_designer.py` | 从 track 获取 |

**验证**: Ship Pro 能正确读取 Track 数据

### Phase 5: 清理 State 双源（P1）

**目标**: 删除 master_state.json，统一状态源

| 任务 | 文件 | 动作 |
|------|------|------|
| 删除 master_state.json 写入 | `__init__.py` | 移除写入逻辑 |
| 更新 orchestrator.md | `prompts/orchestrator.md` | 移除 master_state 引用 |

**验证**: `grep -rn "master_state" domains/solution_pro/` 返回 0

---

## 5. 关键决策点

### 5.1 Track 是否需要增量更新？

**当前设计**: 每次运行都是全新的 Track（全量生成）

**理由**:
- Solution Pro 是一次性运行，不是持续更新
- 全量生成更简单，不需要 diff 逻辑
- 如果需要历史，用 git 版本控制

### 5.2 Track 是否需要版本化？

**当前设计**: 只保留最新版本（覆盖写入）

**理由**:
- Track 是衍生数据，可以从 MD 重新生成
- 如果需要历史，用 git 版本控制 MD
- 减少存储开销

### 5.3 Track 的消费方有哪些？

| 消费方 | 读取字段 | 用途 |
|--------|---------|------|
| Ship Pro | req_ids, semantic_anchors | REQ 覆盖检查、锚点传递 |
| Deliver Pro | quality_indicators, gate_summary | 质量评估 |
| 人类 | metrics, solution_specific | 快速查看方案概要 |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Track 提取失败 | 下游无法获取元数据 | Track 生成失败 = 架构违反，raise ValueError |
| MD 结构变化 | Track 提取逻辑失效 | MD Schema 变更时同步更新 Track 提取逻辑 |
| Track Schema 扩展 | 向后兼容问题 | 使用 schema_version 字段标识版本 |

---

## 7. 记忆锚点

> "MD 是唯一真相源，Track 是衍生视图"
> "Track 自动生成，只读，不可手动修改"
> "Internal JSON 不是债，是正确的工具选择"
> "State 单源，删除 master_state.json"

---

*文档生成时间: 2026-07-29*  
*作者: Solution Pro Architecture Team*
