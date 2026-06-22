# Blackboard 文件结构

> 黑板系统的完整文件组织规范  
> 最后更新：2026-06-22

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
│   ├── execution_plan.json           # 执行计划
│   ├── stage_1_planner.json          # Stage 1 输出
│   ├── stage_2_reviewer.json         # Stage 2 输出
│   ├── stage_3_fixer.json            # Stage 3 输出
│   ├── stage_4_researcher.json       # Stage 4 输出
│   ├── stage_5_consolidator.json     # Stage 5 输出
│   ├── stage_6_auditor.json          # Stage 6 输出
│   ├── stage_7_fixer.json            # Stage 7 输出
│   ├── stage_8_harness.json          # Stage 8 输出
│   ├── stage_9_fixer.json            # Stage 9 输出 (条件)
│   ├── final_result.json             # 最终方案 (核心产物)
│   └── .completed                    # 完成标记
│
├── ship_{hash}/                       # Ship Pro 会话
│   ├── input.json                     # 技术方案输入
│   ├── stages/                        # Agent 间数据传递
│   │   ├── architect.json             # Architect 输出
│   │   ├── decomposer.json            # Decomposer 输出
│   │   ├── specifier.json             # Specifier 输出
│   │   ├── reviewer.json              # Reviewer 输出
│   │   └── packager.json              # Packager 输出
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
    "version": "2.1.0",
    "spec_version": 3,
    "created_at": "2026-06-22T10:00:00Z",
    "updated_at": "2026-06-22T10:30:00Z",
    "conversation_rounds": 3,
    "quality_score": 85,
    "quality_level": "A"
  },
  "confirmed": {
    "objective": "为电商团队构建订单自动通知系统",
    "pain_points": [
      "手动发邮件经常漏发",
      "客户投诉3次"
    ],
    "success_metrics": [
      {"metric": "邮件送达率", "target": "99.9%"},
      {"metric": "漏发率", "target": "0%"}
    ],
    "users": [
      {"role": "运营人员", "key_needs": "批量处理订单通知"}
    ],
    "key_scenarios": [
      "订单提交后自动发邮件",
      "邮件发送失败自动重试"
    ],
    "capabilities": {
      "always_do": ["自动发送订单确认邮件", "支持批量处理"],
      "should_do": ["发送状态看板"],
      "never_do": ["微服务架构"]
    },
    "quality_attributes": [
      {"category": "可靠性", "spec": "邮件送达率99.9%", "priority": "P0"}
    ],
    "constraints": {
      "platform": "阿里云",
      "tech_stack": ["Vue", "Node.js"],
      "data_source": ["订单数据库"]
    },
    "integration": {
      "existing_systems": [
        {"name": "邮件SMTP", "type": "email"}
      ],
      "requirements": ["SMTP邮件发送接口"]
    },
    "risks_and_assumptions": {
      "risks": ["SMTP服务商限流"],
      "assumptions": ["团队有基础Node.js开发能力"],
      "dependencies": ["SMTP服务商可用"]
    },
    "user_directives": [
      {"directive": "GDPR合规", "dimension": "compliance", "content": "用户数据必须加密存储"}
    ]
  },
  "inferred": [
    {"hypothesis": "用户可能需要多渠道通知", "confidence": 0.6, "status": "pending"}
  ],
  "guardrails": {
    "always_do": ["所有邮件发送记录审计日志"],
    "ask_first": ["更改数据保留策略"],
    "never_do": ["不引入微服务架构"]
  },
  "conversation_digest": {
    "summary": "某电商团队目前用Excel手动处理每天50+订单的邮件通知...",
    "key_excerpts": [
      {
        "excerpt": "每天50多个订单要手动发邮件通知，经常漏发",
        "dimension": "pain_points",
        "importance": "critical",
        "source_round": 1
      },
      {
        "excerpt": "宁可慢一点也要稳定，性能可以后面优化",
        "dimension": "tradeoff",
        "importance": "important",
        "source_round": 3
      }
    ],
    "covered_dimensions": ["pain_points", "constraints", "tradeoff"],
    "total_excerpts": 6,
    "full_conversation_path": "spec/conversation_log.json"
  }
}
```

---

### 2. final_result.json (Solution Pro)

```json
{
  "solution_version": "1.0.0",
  "generated_at": "2026-06-22T11:30:00Z",
  "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003"],
  "architecture": {
    "layers": [
      {
        "name": "接入层",
        "components": ["API Gateway", "Load Balancer"],
        "technology": ["Nginx", "Kong"]
      },
      {
        "name": "业务层",
        "components": ["订单服务", "通知服务"],
        "technology": ["Node.js", "Express"]
      },
      {
        "name": "数据层",
        "components": ["订单数据库", "日志数据库"],
        "technology": ["PostgreSQL", "Elasticsearch"]
      }
    ],
    "components": [
      {
        "name": "订单服务",
        "responsibility": "处理订单创建、更新、查询",
        "interfaces": ["POST /orders", "GET /orders/:id"]
      },
      {
        "name": "通知服务",
        "responsibility": "发送邮件通知",
        "interfaces": ["POST /notifications"]
      }
    ],
    "data_flow": "订单服务 → 消息队列 → 通知服务 → SMTP"
  },
  "implementation_plan": {
    "phases": [
      {
        "phase": 1,
        "name": "核心功能",
        "duration": "4周",
        "deliverables": ["订单服务", "通知服务", "数据库"]
      },
      {
        "phase": 2,
        "name": "监控告警",
        "duration": "2周",
        "deliverables": ["日志系统", "告警规则"]
      }
    ],
    "timeline": "6周",
    "risks": [
      {"risk": "SMTP服务商限流", "mitigation": "使用多个服务商轮换"}
    ]
  },
  "quality_attributes": {
    "performance": "P99延迟<100ms",
    "scalability": "支持1000订单/秒",
    "security": "GDPR合规，数据加密"
  }
}
```

---

### 3. ship_package.json (Ship Pro)

```json
{
  "package_version": "1.0.0",
  "generated_at": "2026-06-22T12:30:00Z",
  "work_packages": [
    {
      "wp_id": "WP-001",
      "name": "数据库Schema设计",
      "priority": "P0",
      "dependencies": [],
      "estimated_hours": 8,
      "deliverables": [
        "orders.sql",
        "notifications.sql"
      ],
      "acceptance_criteria": [
        "支持订单CRUD",
        "索引覆盖常用查询"
      ]
    },
    {
      "wp_id": "WP-002",
      "name": "订单服务API",
      "priority": "P0",
      "dependencies": ["WP-001"],
      "estimated_hours": 16,
      "deliverables": [
        "order_controller.ts",
        "order_service.ts",
        "order_model.ts"
      ],
      "acceptance_criteria": [
        "POST /orders 返回201",
        "GET /orders/:id 返回订单详情"
      ]
    }
  ],
  "execution_order": ["WP-001", "WP-002", "WP-003"],
  "total_estimated_hours": 80
}
```

---

## 文件生成时机

| 文件 | 生成时机 | 生成者 |
|:---|:---|:---|
| `input.md` | Spec Pro init_session | Coordinator |
| `living_spec.json` | 每轮对话后 | merge_spec.py |
| `harness_report.json` | Harness 评估后 | harness.py |
| `stage_N_*.json` | 每个阶段完成后 | 对应 Worker |
| `final_result.json` | Stage 10 完成后 | Summarizer |
| `ship_package.json` | Stage 5 完成后 | Reviewer |
| `.completed` | 整个流程完成 | Orchestrator |

---

## 恢复指南

如果 Blackboard 数据丢失，参见 `6-恢复手册.md`。
