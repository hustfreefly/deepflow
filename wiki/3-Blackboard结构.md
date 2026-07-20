# Blackboard 文件结构

> 黑板系统的完整文件组织规范  
> 最后更新: 2026-07-08

---

## 目录结构

```
blackboard/
├── spec_spec_XXX/                    # Spec Pro 会话
│   ├── input.md                      # 用户原始输入
│   ├── user_response_round_N.md      # 第 N 轮用户回复
│   ├── spec/
│   │   ├── living_spec.json          # 需求规格 (核心产物)
│   │   ├── harness_report.json       # Harness 评估报告
│   │   ├── conversation_log.json     # 完整对话日志
│   │   └── quality_trajectory.json   # 质量轨迹
│   ├── stages/
│   │   ├── round_N_questions.json    # 第 N 轮问题
│   │   └── round_N_response.json     # 第 N 轮响应
│   └── coord_state.json              # Coordinator 状态
│
├── solution_XXX/                     # Solution Pro 会话
│   ├── input.json                    # LivingSpec 输入
│   ├── control_contract.json         # 控制契约
│   ├── master_state.json             # MasterOrchestrator 状态
│   ├── planning/
│   │   ├── module_state.json         # Planning 模块状态
│   │   ├── meta_plan.json            # 元规划结果
│   │   ├── expert_results.json       # 多专家方案
│   │   └── convergence.json          # 收敛结果
│   ├── research/
│   │   ├── module_state.json         # Research 模块状态
│   │   ├── research_plan.json        # 研究计划
│   │   └── research_results.json     # 研究结果
│   ├── summary/
│   │   ├── module_state.json         # Summary 模块状态
│   │   ├── analysis_results.json     # 多维分析
│   │   ├── synthesis.json            # 综合结果
│   │   └── final_result.json         # 最终方案 (核心产物)
│   └── .completed                    # 完成标记
│
├── ship_{hash}/                       # Ship Pro 会话
│   ├── input.json                     # 技术方案输入
│   ├── pipeline_plan.json             # PipelineDesigner 输出
│   ├── stages/                        # Worker 输出
│   │   ├── worker_N.json              # 第 N 个 Worker 输出
│   │   └── ...
│   ├── ship_package.json              # 工程包 (核心产物)
│   ├── summary.md                     # 人类可读摘要
│   └── .completed                     # 完成标记
│
└── research_pro_XXX/                 # Research Pro 会话
    ├── input.json                    # 研究输入
    ├── search_results.json           # 搜索结果
    ├── fetched_pages.json            # 抓取页面
    ├── analysis.json                 # 分析结果
    └── report/
        └── final.md                  # 最终报告 (核心产物)
```

---

## 核心文件格式

### 1. living_spec.json (Spec Pro)

```json
{
  "meta": {
    "version": "2.2.0",
    "spec_version": 3,
    "created_at": "2026-07-08T10:00:00Z",
    "updated_at": "2026-07-08T10:30:00Z",
    "conversation_rounds": 3,
    "quality_score": 85,
    "quality_level": "A",
    "domain_id": "software"
  },
  "confirmed": {
    "objective": "为电商团队构建订单自动通知系统",
    "pain_points": ["手动发邮件经常漏发"],
    "success_metrics": [
      {"metric": "邮件送达率", "target": "99.9%"}
    ],
    "users": [
      {"role": "运营人员", "key_needs": "批量处理订单通知"}
    ],
    "capabilities": {
      "always_do": ["自动发送订单确认邮件"],
      "should_do": ["发送状态看板"],
      "never_do": ["微服务架构"]
    },
    "quality_attributes": [
      {"category": "可靠性", "spec": "邮件送达率99.9%", "priority": "P0"}
    ],
    "constraints": {
      "platform": "阿里云",
      "tech_stack": ["Vue", "Node.js"]
    }
  },
  "inferred": [
    {"hypothesis": "多渠道通知", "confidence": 0.6, "status": "pending"}
  ],
  "conversation_digest": {
    "summary": "...",
    "key_excerpts": [],
    "covered_dimensions": [],
    "total_excerpts": 0
  }
}
```

### 2. final_result.json (Solution Pro)

```json
{
  "solution_version": "2.1.1",
  "generated_at": "2026-07-08T11:30:00Z",
  "domain_profile": {
    "domain_id": "software",
    "domain_label": "软件工程",
    "description": "..."
  },
  "covered_req_ids": ["REQ-001", "REQ-002"],
  "architecture": {
    "layers": [],
    "components": [],
    "data_flow": ""
  },
  "implementation_plan": {
    "phases": [],
    "timeline": "",
    "risks": []
  },
  "quality_attributes": {}
}
```

### 3. ship_package.json (Ship Pro)

```json
{
  "package_version": "2.0.0",
  "generated_at": "2026-07-08T12:30:00Z",
  "work_packages": [
    {
      "wp_id": "WP-001",
      "name": "数据库Schema设计",
      "priority": "P0",
      "dependencies": [],
      "estimated_hours": 8,
      "deliverables": ["orders.sql"],
      "acceptance_criteria": ["支持订单CRUD"]
    }
  ],
  "execution_order": ["WP-001", "WP-002"],
  "total_estimated_hours": 80
}
```

---

## 文件生成时机

| 文件 | 生成时机 | 生成者 |
|:---|:---|:---|
| `input.md` | Spec Pro init_session | SpecProCoordinator |
| `living_spec.json` | 每轮对话后 | merge_spec.py |
| `harness_report.json` | Harness 评估后 | contracts/gate.py |
| `master_state.json` | 每个模块完成后 | MasterOrchestrator |
| `module_state.json` | 模块内部阶段完成后 | ModuleOrchestratorBase |
| `final_result.json` | Summary 5+1 Phase 完成后 | SummaryOrchestrator |
| `pipeline_plan.json` | 设计完成后 | PipelineDesigner |
| `ship_package.json` | Consolidator 完成后 | Consolidator |
| `.completed` | 整个流程完成 | Orchestrator |

---

## I/O 规范

所有 Blackboard 文件 I/O 通过 `BlackboardManager` API，不直接拼接路径:

```python
from core.blackboard.blackboard_manager import BlackboardManager

# 正确
bm = BlackboardManager(session_dir)
bm.write_json("spec/living_spec.json", data)
data = bm.read_json("spec/living_spec.json")

# 错误 ❌
path = session_dir / "spec" / "living_spec.json"
path.write_text(json.dumps(data))
```

---

## 恢复指南

如果 Blackboard 数据丢失，参见 [6-恢复手册](6-恢复手册.md)。
