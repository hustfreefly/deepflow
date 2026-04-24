# DeepFlow V2.0 笼子契约开发方案

> 契约驱动开发（Contract-Driven Development）
> 版本: 2026-04-20-v1

---

## 1. 契约体系架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      笼子契约体系                                 │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   接口契约       │   行为契约       │      数据契约               │
│  (Interface)     │  (Behavior)     │     (Data)                  │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ • 输入/输出格式  │ • 状态转换规则   │ • Blackboard 结构           │
│ • 异常契约       │ • 收敛检测规则   │ • 阶段输出 Schema           │
│ • Fallback 契约 │ • 并发控制规则   │ • 最终结果 Schema           │
│ • Timeout 契约   │ • 重试策略      │ • 配置 Schema               │
└─────────────────┴─────────────────┴─────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        笼子文件 (Cage Files)                     │
│  cage/                                                          │
│   ├── domain_investment.yaml      # 领域契约                     │
│   ├── stage_data_collection.yaml  # 阶段契约                     │
│   ├── stage_worker_dispatch.yaml  # 阶段契约                     │
│   ├── worker_researcher.yaml      # Worker 契约                  │
│   ├── worker_auditor.yaml         # Worker 契约                  │
│   └── convergence_rules.yaml      # 收敛契约                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 笼子契约定义

### 2.1 领域契约 (`cage/domain_investment.yaml`)

```yaml
# DeepFlow Domain Contract - Investment
cage_version: "2.0"
domain: investment

# 接口契约
interface:
  input:
    schema:
      type: object
      required: [code, name]
      properties:
        code:
          type: string
          pattern: "^\\d{6}\\.(SH|SZ|BJ)$"
          example: "300604.SZ"
        name:
          type: string
          minLength: 2
          maxLength: 20
        price:
          type: number
          minimum: 0
          optional: true
    validation: "domains.investment.validator.validate_input"
  
  output:
    schema:
      type: object
      required: [status, pipeline_state, session_id, final_score]
      properties:
        status:
          type: string
          enum: [completed, failed]
        pipeline_state:
          type: string
          enum: [CONVERGED, MAX_ITERATIONS, FAILED, TIMEOUT]
        session_id:
          type: string
          pattern: "^[a-zA-Z0-9_]+_\\d{6}_[a-z]+_[a-f0-9]{8}$"
        final_score:
          type: number
          minimum: 0
          maximum: 1
        convergence_reason:
          type: string
        iterations:
          type: integer
          minimum: 1
    validation: "domains.investment.validator.validate_output"

# 行为契约
behavior:
  stages:
    count: 9
    required_order: [data_collection, search, planning, research, financial_analysis, audit, fix, verify, summarize]
    allow_skip: false
  
  workers:
    researcher:
      count: 6
      parallel: true
      max_concurrency: 3
      timeout: 300
    auditor:
      count: 3
      parallel: true
      max_concurrency: 3
      timeout: 180
    fixer:
      count: 1
      parallel: false
      timeout: 240
  
  convergence:
    min_iterations: 2
    max_iterations: 10
    target_score: 0.92
    stall_threshold: 0.02
    must_converge: true  # 未收敛视为失败

# 异常契约
exceptions:
  circuit_breaker:
    trigger: "all_models_exhausted"
    action: "fail_pipeline"
    notify: true
  
  timeout:
    worker: 300
    stage: 600
    action: "retry_once_then_fail"
  
  validation_failure:
    input: "fail_fast"
    output: "retry_stage"

# 数据契约
data:
  blackboard:
    path: "blackboard/{session_id}/"
    required_files:
      - "data/INDEX.json"
      - "data/01_financials/key_metrics.json"
      - "stages/{stage_name}/output.json"
    schema_validation: true
  
  checkpoints:
    enabled: true
    interval: "per_stage"
    retention: "7d"
```

---

### 2.2 阶段契约 (`cage/stage_data_collection.yaml`)

```yaml
# Stage Contract - Data Collection
stage: data_collection
domain: investment
cage_version: "2.0"

# 接口契约
interface:
  input:
    context:
      required: [code, name]
    config: "data_sources/investment.yaml"
  
  output:
    schema:
      type: object
      required: [datasets, count, verification]
      properties:
        datasets:
          type: array
          items:
            type: string
        count:
          type: integer
          minimum: 0
        verification:
          type: object
          required: [index, financials, market]
          properties:
            index: {type: boolean}
            financials: {type: boolean}
            market: {type: boolean}
    
    assertions:
      - "output.count >= 3"  # 至少3个数据集
      - "output.verification.index == true"  # INDEX.json 必须存在

# 行为契约
behavior:
  timeout: 120
  retry:
    max_attempts: 2
    backoff: "exponential"
  
  failure_mode: "warn_and_continue"  # 采集失败不终止流程
  
  collectors:
    - tushare
    - akshare
    - sina_finance
    - web_search

# 数据契约
data:
  output_path: "blackboard/{session_id}/data/"
  files:
    INDEX: "INDEX.json"
    financials: "01_financials/key_metrics.json"
    market: "02_market_quote/key_metrics.json"
  
  validation:
    - "file_exists(INDEX)"
    - "json_valid(INDEX)"
    - "file_not_empty(financials)"
```

---

### 2.3 Worker 契约 (`cage/worker_researcher.yaml`)

```yaml
# Worker Contract - Researcher
worker: researcher
domain: investment
cage_version: "2.0"

# 角色定义
roles:
  - researcher_finance
  - researcher_tech
  - researcher_market
  - researcher_macro
  - researcher_management
  - researcher_sentiment

# 接口契约
interface:
  input:
    prompt: "prompts/investment/workers/{role}.md"
    context:
      required: [stock_code, stock_name, stage_outputs]
      injection: "blackboard_data"
  
  output:
    format: "markdown_with_json_block"
    schema:
      type: object
      required: [analysis, conclusions, data_sources]
      properties:
        analysis:
          type: string
          minLength: 100
        conclusions:
          type: array
          items: {type: string}
        data_sources:
          type: array
          items: {type: string}
        confidence:
          type: number
          minimum: 0
          maximum: 1

# 行为契约
behavior:
  count: 6
  parallel: true
  max_concurrency: 3
  
  timeout: 300
  retry: 1
  
  fallback:
    model_chain: [bailian/qwen3.5-plus, bailian/kimi-k2.5, kimi/kimi-code]
    on_failure: "continue_with_partial"  # 部分失败继续
  
  label_format: "{role}_{iteration}"

# 契约检查
checks:
  pre_spawn:
    - "validate_context_schema"
    - "check_blackboard_data_exists"
  
  post_complete:
    - "validate_output_schema"
    - "check_no_mock_result"
    - "write_to_blackboard"

# 数据契约
data:
  blackboard:
    write:
      path: "blackboard/{session_id}/stages/research/{role}_output.json"
      format: "json"
    
    read:
      - "blackboard/{session_id}/data/INDEX.json"
      - "blackboard/{session_id}/data/01_financials/*.json"
```

---

### 2.4 收敛契约 (`cage/convergence_rules.yaml`)

```yaml
# Convergence Contract
domain: investment
cage_version: "2.0"

# 收敛规则定义
rules:
  # 规则1: 最少迭代次数
  min_iterations:
    value: 2
    hard: true  # 不可覆盖
    message: "至少2轮才能收敛"
  
  # 规则2: 最大迭代次数
  max_iterations:
    value: 10
    action: "force_converge"
    message: "达到最大迭代次数，强制收敛"
  
  # 规则3: 高分快速收敛
  high_score:
    threshold: 0.95
    immediate: true
    message: "分数≥0.95，立即收敛"
  
  # 规则4: 目标分 + 停滞
  target_score:
    value: 0.92
