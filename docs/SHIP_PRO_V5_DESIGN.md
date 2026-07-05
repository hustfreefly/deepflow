# Ship Pro 2.0.0 架构设计方案（评审后最终版 2.0.0）

> **版本**: 2.0.0
> **日期**: 2026-06-27
> **状态**: ✅ 评审通过，待实施
> **评审**: 5 位专家综合评分 7.0/10，修正全部 P0 后预期 8.5/10
> **前序**: 2.0.0（单 Agent，认知过载）→ 2.0.0 draft（评审）→ 2.0.0 final

---

## 一、设计原则

1. **运动员 ≠ 裁判员**：生成 Agent 和审计 Agent 严格分离
2. **LLM 做理解，代码做确定性**：LLM 负责语义理解/决策/推理，代码负责算法/比对/校验
3. **推理链显式传递**：每个 Agent 输出"为什么"，下游强制读取并确认
4. **每 Phase ≥5 Agent**：保证专业化和审计覆盖
5. **分批修复 + 回归检查**：每批 ≤3 个 risk，修后全量审计
6. **固定编排优先**：Phase 1 用固定编排跑稳，动态编排放后续迭代
7. **severity 分级 Gate**：BLOCKER 必修，WARNING 可带过，INFO 仅记录

---

## 二、整体架构

### Phase 1: Blueprint（宏观拆分）

```
Solution Pro final_result.json
            │
            ▼
┌──────────────────────────────────────────────────────────────┐
│  Phase 1: Blueprint                                           │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  P1-1 Parser [LLM]                                   │     │
│  │  · 格式检测 (A/B/C/D)                                │     │
│  │  · 结构提取 (组件/需求/原则/SLA/数据流)               │     │
│  │  · 输入质量评分                                      │     │
│  │  输出: parsed_input.json (~5KB)                      │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  P1-2 Explorer [LLM] (可 spawn 1-3 个并行)           │     │
│  │  · 数据流追踪                                        │     │
│  │  · 隐含依赖挖掘 (必须带 evidence 引用原文)            │     │
│  │  · 边界条件识别                                      │     │
│  │  · 技术栈约束提取                                    │     │
│  │  输出: explorer_findings.json (~3KB)                 │     │
│  │  ⚠️ 每条 finding 必须含: evidence + confidence        │     │
│  │  ⚠️ 无 evidence 的标记为 hypothesis，不传递给 Architect│     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  P1-3 Architect [LLM] (两步输出)                     │     │
│  │  Step 1: WP 拆分列表 (JSON schema 约束)              │     │
│  │  Step 2: 推理链 (为什么这样拆 + 拒绝了什么替代方案)    │     │
│  │  输出: architect_blueprint.json (~10KB)              │     │
│  │  ⚠️ 推理链必须包含每个 WP 的 splitting_rationale      │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  [审计层 - 3 Critic 并行, temperature=0.3]           │     │
│  │                                                      │     │
│  │  P1-4 Coverage Critic                                │     │
│  │  · 必选模块覆盖率 (目标 100%)                        │     │
│  │  · 可选模块覆盖率 (目标 ≥80%)                        │     │
│  │  · 需求追溯完整性                                    │     │
│  │  · 原则覆盖映射                                      │     │
│  │                                                      │     │
│  │  P1-5 Granularity Critic                             │     │
│  │  · WP 粒度合理性 (单 WP 1-2 sprint 可交付)           │     │
│  │  · 工作量均衡性                                      │     │
│  │  · 可独立部署/测试                                   │     │
│  │                                                      │     │
│  │  P1-6 Feasibility Critic                             │     │
│  │  · 技术可行性                                        │     │
│  │  · 依赖合理性 (无循环依赖)                           │     │
│  │  · 关键路径分析                                      │     │
│  │                                                      │     │
│  │  每个 Critic 输出: {verdict, issues[], score}         │     │
│  │  ⚠️ 强制"至少找 2 个问题"模式                        │     │
│  │  ⚠️ 审计 Agent 输入包含 Architect 的 prompt 摘要      │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  P1-Consolidator [LLM]                               │     │
│  │  · 合并 3 个 Critic 意见                             │     │
│  │  · 冲突检测 + 优先级裁决                             │     │
│  │  · 分批 Fix (≤3 个 risk/批)                          │     │
│  │  · 回归检查 (Fix 后重审，引入新问题则回滚)            │     │
│  │                                                      │     │
│  │  Critic 优先级: Coverage > Feasibility > Granularity  │     │
│  │  通过条件: 0 BLOCKER + WARNING ≤ 3                   │     │
│  │  max_fix_rounds: 2                                   │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  [Gate: Pydantic + 必选模块覆盖 100% + 0 BLOCKER]            │
│                         │                                    │
│  输出: blueprint.json (~15KB)                                │
│  包含: _reasoning_chain (parser→explorer→architect 全链)      │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
```

### Phase 2: Delivery（微观交付）

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 2: Delivery                                            │
│                                                              │
│  读取 blueprint.json + _reasoning_chain                       │
│  ⚠️ 每个 Agent prompt 强制包含:                               │
│  "你必须读取 _reasoning_chain 并在输出中确认已理解"             │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  P2-1 AC Writer [LLM] (可按 WP 分批并行)             │     │
│  │  · L3+ 验收标准撰写                                  │     │
│  │  · 量化指标填充 (从 SLA/原则 推导数值)                │     │
│  │  · 测试命令模板 (command_template, 非可执行命令)       │     │
│  │                                                      │     │
│  │  Prompt: 150 行 + 8 示例                             │     │
│  │  (功能/性能/可靠性/安全 各 1 good + 1 bad)            │     │
│  │  输出: wp_ac_drafts.json (~15KB)                     │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  P2-2 Constraint Propagator [代码]                   │     │
│  │  · 原则 → WP serving_principles (规则映射)           │     │
│  │  · SLA → AC 数值阈值 (确定性推导)                    │     │
│  │  · 平台能力 → WP constraints                         │     │
│  │                                                      │     │
│  │  实现: Python 函数，不需要 LLM                       │     │
│  │  输出: wp_constraints.json (~5KB)                    │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  P2-3 DepGraph Builder [代码]                        │     │
│  │  · 从 WP dependencies 提取边列表                     │     │
│  │  · 拓扑排序 (Kahn 算法)                              │     │
│  │  · 并行分组                                          │     │
│  │  · 关键路径 (最长路径)                               │     │
│  │                                                      │     │
│  │  实现: Python + networkx，不需要 LLM                 │     │
│  │  输出: dependency_graph.json (~3KB)                  │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  合并: AC + Constraints + DepGraph → draft_package   │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  [审计层 - 3 Judge 并行, temperature=0.3]            │     │
│  │                                                      │     │
│  │  P2-4 Consistency Judge [代码+LLM 混合]              │     │
│  │  Step 1 [代码]: 提取所有数值声明 → 按指标分组         │     │
│  │  Step 2 [代码]: 同指标不同值 → 自动标记冲突           │     │
│  │  Step 3 [LLM]: 判断冲突是否为真正矛盾                 │     │
│  │           (排除单位换算/条件差异等合理差异)             │     │
│  │                                                      │     │
│  │  P2-5 Quality Judge [LLM]                            │     │
│  │  · AC Rubric 评分 (L1-L4)                            │     │
│  │  · 确定性检查 [代码]: 含数值? 含验证手段? 含模糊词?   │     │
│  │  · LLM 精细评分: 仅区分 L3 vs L4 (范围窄,稳定)       │     │
│  │  · 对抗性审计 (实施者视角)                            │     │
│  │                                                      │     │
│  │  P2-6 Completeness Judge [LLM]                       │     │
│  │  · WP→AC 覆盖 (每个 WP 有 AC?)                      │     │
│  │  · 必选工作覆盖 (部署/测试/文档/合规)                 │     │
│  │  · 端到端场景完整性                                   │     │
│  │                                                      │     │
│  │  每个 Judge 输出: {verdict, issues[], score}          │     │
│  │  ⚠️ 强制"至少找 2 个问题"模式                        │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐     │
│  │  P2-Consolidator [LLM]                               │     │
│  │  · 合并 3 个 Judge 意见                              │     │
│  │  · 冲突检测 + 优先级裁决                             │     │
│  │  · 分批 Fix (≤3 个 risk/批)                          │     │
│  │  · 回归检查 (Fix 后全量重审)                          │     │
│  │                                                      │     │
│  │  Judge 优先级: Consistency > Quality > Completeness   │     │
│  │  通过条件: 0 BLOCKER + WARNING ≤ 3                   │     │
│  │  max_fix_rounds: 2                                   │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │                                    │
│  [Gate: Pydantic + 数值校验(代码) + 0 BLOCKER]               │
│                         │                                    │
│  输出: ship_package.json (~30KB)                             │
│  包含: _reasoning_chain (完整链路)                            │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
                     最终交付物
```

---

## 三、Gate Severity 分级（关键设计）

```python
class GateSeverity(Enum):
    BLOCKER = "blocker"   # 必须修复，不可带过
    WARNING = "warning"   # 记录，可带过（需 written justification）
    INFO = "info"         # 仅记录，供人工参考

# Phase 1 Gate 规则
P1_GATE_RULES = {
    "blocker": [
        "必选模块覆盖率 < 95%",
        "循环依赖",
        "任何 WP 缺少 source_modules",
        "推理链缺失",
    ],
    "warning": [
        "必选模块覆盖率 95-99%",
        "可选模块覆盖率 < 80%",
        "单 WP 粒度偏大但可交付",
    ],
    "info": [
        "命名风格建议",
        "可选优化项",
    ],
}

# Phase 2 Gate 规则
P2_GATE_RULES = {
    "blocker": [
        "数值矛盾 (major 级别, 代码检测)",
        "任何 WP 缺少 AC",
        "AC 全部 L1/L2 (无 L3+)",
        "循环依赖",
        "字段名不合规 (req_id/from/to)",
    ],
    "warning": [
        "数值 minor 不一致 (精度/四舍五入)",
        "单 WP AC 质量 L2 (可接受但非 L3+)",
        "command_template 格式不规范",
    ],
    "info": [
        "AC 措辞建议",
        "可选的额外集成测试",
    ],
}

# 通过条件
def gate_passed(issues: list[Issue]) -> bool:
    blockers = [i for i in issues if i.severity == "blocker"]
    warnings = [i for i in issues if i.severity == "warning"]
    return len(blockers) == 0 and len(warnings) <= 3
```

---

## 四、Fix 机制（分批 + 回归检查）

```python
def fix_cycle(issues: list[Issue], max_rounds: int = 2, batch_size: int = 3):
    """分批修复 + 回归检查"""
    
    # 按 severity 排序: blocker > warning
    sorted_issues = sorted(issues, key=lambda x: severity_order(x.severity))
    batches = chunk(sorted_issues, batch_size)
    
    for round_num in range(max_rounds):
        for batch in batches:
            # 1. 执行修复
            fix_result = run_fix_agent(batch)
            
            # 2. 回归检查: 全量重审
            new_issues = run_full_audit(fix_result)
            regressions = [i for i in new_issues if i not in previous_issues]
            
            # 3. 如果回归比修复更严重 → 回滚
            if severity_sum(regressions) > severity_sum(batch):
                rollback()
                continue
            
            # 4. 检查收敛
            remaining_blockers = [i for i in new_issues if i.severity == "blocker"]
            if not remaining_blockers:
                return "converged"
    
    return "max_rounds_reached"
```

---

## 五、推理链传递格式

```json
{
  "_reasoning_chain": {
    "parser": {
      "input_format": "A",
      "quality_score": 0.91,
      "key_findings": ["..."],
      "confidence": "high"
    },
    "explorer": {
      "findings": [
        {
          "dependency": "Redis → Query API",
          "evidence": "Section 3.2: 'Query API uses Redis for response caching'",
          "confidence": 0.9,
          "type": "explicit"
        }
      ],
      "hypotheses": [
        {
          "dependency": "Kafka → Auth Service",
          "reasoning": "Security requirements imply...",
          "confidence": 0.4,
          "type": "inferred"
        }
      ]
    },
    "architect": {
      "splitting_rationale": {
        "WP-001": "Agent Collector 独立部署(DaemonSet)，可先行交付",
        "WP-002": "Gateway 依赖 Agent，但 Tail Sampling 可后续上线"
      },
      "rejected_alternatives": [
        "考虑合并 WP-001/002，但部署模式不同"
      ],
      "confidence": "high"
    }
  }
}
```

**下游 Agent 强制读取确认**：
```json
{
  "_chain_acknowledgment": {
    "read_sections": ["parser", "explorer", "architect"],
    "key_insights_used": [
      "Architect 拆分 WP-003 独立是因为 Kafka 是数据管道核心",
      "Explorer 发现 Redis → Query API 隐含依赖"
    ]
  }
}
```

---

## 六、代码实现模块

### 6.1 Constraint Propagator（P2-2，纯代码）

```python
def propagate_constraints(blueprint: dict) -> dict:
    """从原则/SLA/平台能力推导到 WP 级约束"""
    wp_constraints = {}
    
    for wp in blueprint["work_packages"]:
        constraints = {
            "serving_principles": [],
            "sla_thresholds": [],
            "platform_requirements": [],
        }
        
        # 原则 → WP
        for principle in blueprint["architecture_principles"]:
            covered_modules = principle.get("covered_by_modules", [])
            if any(m in wp["source_modules"] for m in covered_modules):
                constraints["serving_principles"].append({
                    "principle_id": principle["id"],
                    "obligation": f"本 WP 必须遵守: {principle['description']}",
                    "anti_patterns": principle.get("anti_patterns", []),
                })
        
        # SLA → AC 数值
        for sla in blueprint.get("sla_constraints", []):
            if any(m in wp["source_modules"] for m in sla.get("affected_modules", [])):
                constraints["sla_thresholds"].append({
                    "metric": sla["metric"],
                    "threshold": sla["threshold"],
                    "operator": sla.get("operator", ">="),
                })
        
        wp_constraints[wp["id"]] = constraints
    
    return wp_constraints
```

### 6.2 DepGraph Builder（P2-3，纯代码）

```python
from collections import defaultdict, deque

def build_dependency_graph(work_packages: list[dict]) -> dict:
    """拓扑排序 + 并行分组 + 关键路径"""
    
    # 构建邻接表
    graph = defaultdict(list)
    in_degree = defaultdict(int)
    wp_ids = [wp["id"] for wp in work_packages]
    
    for wp in work_packages:
        for dep in wp.get("dependencies", []):
            graph[dep].append(wp["id"])
            in_degree[wp["id"]] += 1
    
    # Kahn 算法拓扑排序
    queue = deque([wp for wp in wp_ids if in_degree[wp] == 0])
    topo_order = []
    levels = {}  # 用于并行分组
    
    while queue:
        node = queue.popleft()
        topo_order.append(node)
        level = 0
        for wp in work_packages:
            if wp["id"] == node:
                for dep in wp.get("dependencies", []):
                    level = max(level, levels.get(dep, 0) + 1)
        levels[node] = level
        
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    # 并行分组
    parallel_groups = defaultdict(list)
    for wp_id, level in levels.items():
        parallel_groups[level].append(wp_id)
    
    # 关键路径 (最长路径)
    critical_path = find_longest_path(graph, wp_ids)
    
    # 检测循环依赖
    has_cycle = len(topo_order) != len(wp_ids)
    
    return {
        "execution_order": topo_order,
        "parallel_groups": [parallel_groups[k] for k in sorted(parallel_groups.keys())],
        "critical_path": critical_path,
        "edges": [{"from": dep, "to": wp["id"]} 
                  for wp in work_packages for dep in wp.get("dependencies", [])],
        "has_cycle": has_cycle,
    }
```

### 6.3 数值一致性检查（P2-4 代码部分）

```python
import re

def extract_numeric_claims(data: dict, path: str = "") -> list[dict]:
    """递归提取所有数值声明"""
    claims = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            claims.extend(extract_numeric_claims(value, new_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            claims.extend(extract_numeric_claims(item, f"{path}[{i}]"))
    elif isinstance(data, str):
        # 提取数值 + 单位
        numbers = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*(k|K|M|G|T|%|ms|s|MB|GB|TB|TPS|ops)?', data)
        for num_str, unit in numbers:
            num = float(num_str.replace(',', ''))
            if unit in ('k', 'K'): num *= 1000
            elif unit == 'M': num *= 1000000
            elif unit == 'G': num *= 1000000000
            claims.append({
                "value": num,
                "unit": unit,
                "raw": f"{num_str}{unit}",
                "source_path": path,
                "context": data[:100],
            })
    
    return claims

def find_numeric_conflicts(claims: list[dict]) -> list[dict]:
    """按语义分组，找同指标不同值"""
    # 简单分组：按 source_path 的关键词
    groups = defaultdict(list)
    for claim in claims:
        # 提取关键词 (如 TPS, latency, storage)
        keywords = extract_keywords(claim["source_path"], claim["context"])
        for kw in keywords:
            groups[kw].append(claim)
    
    conflicts = []
    for keyword, group_claims in groups.items():
        values = set(c["value"] for c in group_claims)
        if len(values) > 1:
            conflicts.append({
                "metric": keyword,
                "claims": group_claims,
                "values": list(values),
                "severity": "major" if max(values) / min(values) > 1.5 else "minor",
            })
    
    return conflicts
```

---

## 七、可观测性设计

### 7.1 Agent 运行记录

```json
{
  "agent": "p1_architect",
  "run_id": "20260627_080000",
  "phase": 1,
  "input_hash": "sha256:abc123",
  "output_hash": "sha256:def456",
  "latency_ms": 45000,
  "tokens": {"prompt": 8000, "completion": 3000},
  "model": "qwen3.7-max",
  "temperature": 0.3,
  "retry_count": 0,
  "gate_passed": true,
  "gate_issues": []
}
```

### 7.2 持久化路径

```
output_dir/
├── v5/
│   ├── p1_parser/
│   │   ├── output.json
│   │   └── metadata.json
│   ├── p1_explorer/
│   │   ├── output.json
│   │   └── metadata.json
│   ├── p1_architect/
│   │   ├── output.json
│   │   └── metadata.json
│   ├── p1_critics/
│   │   ├── coverage.json
│   │   ├── granularity.json
│   │   └── feasibility.json
│   ├── p1_consolidator/
│   │   ├── output.json
│   │   └── fix_rounds.json
│   ├── blueprint.json                    # Phase 1 交付物
│   ├── p2_ac_writer/
│   │   ├── output.json
│   │   └── metadata.json
│   ├── p2_propagator/output.json         # 代码生成
│   ├── p2_depgraph/output.json           # 代码生成
│   ├── p2_judges/
│   │   ├── consistency.json
│   │   ├── quality.json
│   │   └── completeness.json
│   ├── p2_consolidator/
│   │   ├── output.json
│   │   └── fix_rounds.json
│   └── ship_package.json                 # 最终交付物
├── reasoning_chain.json                  # 推理链汇总
├── run_log.jsonl                         # 全流程审计日志
└── numeric_conflicts.json                # 数值冲突报告
```

---

## 八、与现有系统集成

### 8.1 run_pipeline.py 扩展

```python
AGENT_ORDER_V5 = [
    # Phase 1
    "p1_parser", "p1_explorer", "p1_architect",
    "p1_coverage_critic", "p1_granularity_critic", "p1_feasibility_critic",
    "p1_consolidator",
    # Phase 2
    "p2_ac_writer", "p2_constraint_propagator", "p2_depgraph_builder",
    "p2_consistency_judge", "p2_quality_judge", "p2_completeness_judge",
    "p2_consolidator",
]

# CLI 接口不变
# python3 run_pipeline.py prepare <project_dir> --version v5
# python3 run_pipeline.py task <agent_name> <output_dir>
# python3 run_pipeline.py gate <output_dir>
# python3 run_pipeline.py next <output_dir>
```

### 8.2 Blackboard 集成

```python
STAGE_PATH_REGISTRY_V5 = {
    "p1_parser": "v5/p1_parser",
    "p1_explorer": "v5/p1_explorer",
    "p1_architect": "v5/p1_architect",
    "p1_critics": "v5/p1_critics",
    "p1_consolidator": "v5/p1_consolidator",
    "blueprint": "v5/blueprint",
    "p2_ac_writer": "v5/p2_ac_writer",
    "p2_propagator": "v5/p2_propagator",
    "p2_depgraph": "v5/p2_depgraph",
    "p2_judges": "v5/p2_judges",
    "p2_consolidator": "v5/p2_consolidator",
    "ship_package": "v5/ship_package",
}
```

### 8.3 Watcher Cron 集成

复用现有 `start_ship_pro.py` 的 `watcher_cron_payload`，Watcher 检测 `ship_package.json` 文件出现即为完成。

### 8.4 Pydantic 契约笼子

复用现有 `contracts/` 目录，新增：
- `contracts/v5_blueprint.py` → Blueprint 模型
- `contracts/v5_ship_package.py` → ShipPackage 2.0.0 模型
- `contracts/v5_reasoning_chain.py` → ReasoningChain 模型

---

## 九、质量目标

| 指标 | 2.0.0 实际 | 2.0.0 目标 | 验证方式 |
|------|---------|---------|---------|
| WP 数量变异系数 | 48% | <20% | ≥5 次运行统计 |
| AC 数量变异系数 | 40% | <25% | ≥5 次运行统计 |
| Judge 首轮 PASS 率 | 25% | >50% | 首次 Judge 即 pass |
| 数值矛盾 (major) | 2/run | 0 | 代码检测 |
| 数值矛盾 (minor) | ~5/run | ≤2 | 代码检测 |
| Fix 修复率 | 14% | >70% | 修复项/总项 |
| 端到端耗时 | ~15min | <45min | 含 Fix |
| 单次成本 | ~$2-5 | <¥25 | Token 统计 |

---

## 十、实施计划

| 阶段 | 内容 | 工时 | 验收 |
|------|------|:---:|------|
| **M1** 框架 + 核心 Agent | runner + 4 LLM Agent (Parser/Architect/AC Writer/Consistency Judge) + 2 代码模块 + Gate | 25h | 端到端跑通 |
| **M2** 审计层补全 | Explorer + 3 Critic + 3 Judge + 2 Consolidator | 30h | Judge 首轮 PASS >50% |
| **M3** 加固 | Fix 分批 + 回归检查 + 推理链传递 + 可观测性 + 集成 | 20h | Fix 修复率 >70% |
| **M4** 动态编排（可选） | Orchestrator LLM 决策 | 10h | 不降低质量 |

**M1-M3 总计: 75h (~5 人周)**
