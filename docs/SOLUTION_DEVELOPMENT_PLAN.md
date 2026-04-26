# DeepFlow Solution 领域开发计划指导

> 文档版本: 2026-04-26-v1  
> 目标: 让 Solution 模块达到 Investment 同等质量水平  
> 约束: 不影响已适配的 Investment 场景

---

## 一、当前状态快照

### 1.1 已完成的基座（✅）

| 组件 | 状态 | 说明 |
|:---|:---:|:---|
| Pipeline 框架 | ✅ | 6 阶段：planning→research→design→audit→fix→deliver |
| 契约笼子 | ✅ | `cage/domain_solution.yaml` + `validate_solution.py`，67/67 通过 |
| 收敛检测 | ✅ | 支持迭代，max_iterations=3，target_score=0.90 |
| 渐进交付 | ✅ | planning(30s)/design(2min)/deliver(final) 三检查点 |
| 质量门禁 | ✅ | 5 维度加权评分（correctness/completeness/feasibility/innovation/clarity） |
| Blackboard | ✅ | 文件持久化 + shared_state |
| P0/P1/P2 修复 | ✅ | 并发控制、prompt 缓存、模型降级链、输入校验、路径解耦 |

### 1.2 关键缺失（❌）

| 缺失项 | 严重程度 | 影响 |
|:---|:---:|:---|
| **数据层** | 🔴 P0 | 没有事实基础，方案可能基于过时/错误信息 |
| **Researcher 覆盖不足** | 🟡 P1 | 缺少成本、竞品、团队匹配维度 |
| **真实端到端验证** | 🟡 P1 | 未在 OpenClaw 环境跑过真实模型调用 |
| **Prompt 深度优化** | 🟢 P2 | 输出质量依赖 prompt 设计，尚未精细调优 |

---

## 二、开发原则

### 2.1 契约先行（强制执行）

```
每个 Phase 开始 → 写契约 cage/*.yaml → 实现代码 → 运行验证 → 通过才进入下一阶段
```

**违反后果**: 无契约的代码不得进入 main 分支。

### 2.2 零影响保证（Investment 模块）

```
所有修改限于 domains/solution/ 目录内
禁止修改: domains/investment/*, core/orchestrator_base.py（除非修复 bug）
```

**验证方式**: 每次提交前运行 `git diff --name-only`，确认无 investment 文件被修改。

### 2.3 禁止 Mock（强制执行）

```
所有测试必须使用真实模型调用
禁止添加: _mock_model(), test_mode 标志, _generate_mock_response()
```

**防御措施**: 代码审查时检查是否出现 "mock" 字符串。

---

## 三、分阶段开发计划

### Phase 1: 补齐数据层（🔴 最高优先级）

**目标**: 让 Solution 模块像 Investment 一样，基于事实数据做方案设计。

**任务清单**:

| # | 任务 | 交付物 | 验收标准 |
|:---|:---|:---|:---|
| 1.1 | 创建数据层契约 | `cage/data_collection_contract.yaml` | 定义输入/输出 schema、数据源列表、验证规则 |
| 1.2 | 创建数据源配置 | `domains/solution/data_sources/solution.yaml` | 包含技术文档、行业报告、竞品分析三类数据源 |
| 1.3 | 实现数据采集方法 | `domains/solution/orchestrator.py` 新增 `_execute_data_collection()` | 能调用搜索工具获取外部数据 |
| 1.4 | 实现数据验证方法 | `domains/solution/orchestrator.py` 新增 `_verify_data_collection()` | 检查关键数据文件是否存在 |
| 1.5 | 修改 pipeline | `domains/solution.yaml` | 在 planning 前插入 data_collection 阶段 |
| 1.6 | 运行契约验证 | `python3 cage/validate_solution.py` | 67/67 通过 |
| 1.7 | 运行数据层专用验证 | `python3 cage/check_data_collection.py` | 全部通过 |

#### 数据源设计

```yaml
# domains/solution/data_sources/solution.yaml
data_sources:
  tech_documentation:
    - name: "mdn"
      base_url: "https://developer.mozilla.org"
      description: "Web 技术文档"
    - name: "github_readme"
      pattern: "https://github.com/{org}/{repo}/blob/main/README.md"
      description: "开源项目文档"
  
  industry_reports:
    - name: "gartner"
      search_query: "site:gartner.com {topic}"
      description: "Gartner 行业报告"
    - name: "forrester"
      search_query: "site:forrester.com {topic}"
      description: "Forrester 研究报告"
  
  competitor_analysis:
    - name: "crunchbase"
      search_query: "site:crunchbase.com {topic}"
      description: "竞品公司信息"
    - name: "stackshare"
      search_query: "site:stackshare.io {topic}"
      description: "技术栈对比"
```

#### 风险控制

| 风险 | 概率 | 应对措施 |
|:---|:---:|:---|
| 搜索工具返回垃圾数据 | 中 | 增加 `_verify_data_collection()` 验证数据相关性 |
| 数据获取耗时过长 | 高 | 设置超时 60s，超时时降级为模型内部知识 |
| 外部 API 限流 | 中 | 实现指数退避重试，最多 3 次 |

---

### Phase 2: 增强 Researcher 覆盖（🟡 中优先级）

**目标**: 扩展 researcher 数量，覆盖方案设计的全部关键维度。

**任务清单**:

| # | 任务 | 交付物 | 验收标准 |
|:---|:---|:---|:---|
| 2.1 | 新增 cost_analyst | `prompts/solution/cost_analyst.md` | 能估算基础设施成本、人力成本、时间成本 |
| 2.2 | 新增 competitor_analyst | `prompts/solution/competitor_analyst.md` | 能分析 3-5 个竞品方案，对比优缺点 |
| 2.3 | 修改 pipeline 配置 | `domains/solution.yaml` | research 阶段包含 5 个并行 researcher |
| 2.4 | 更新 Orchestrator | `domains/solution/orchestrator.py` | 支持 5 个并行 worker（Semaphore 仍为 3，分两批） |
| 2.5 | 运行契约验证 | `python3 cage/validate_solution.py` | 67/67 通过 |

#### Researcher 分工

| Researcher | 职责 | 输出 |
|:---|:---|:---|
| constraint_analyst | 分析约束条件可行性 | 约束优先级列表、风险点 |
| best_practice_researcher | 研究行业最佳实践 | 3-5 个参考架构/方案 |
| tech_evaluator | 评估技术选型 | 技术对比矩阵、推荐方案 |
| **cost_analyst** (新增) | 估算实施成本 | 成本拆解表、ROI 分析 |
| **competitor_analyst** (新增) | 分析竞品方案 | 竞品对比表、差异化建议 |

---

### Phase 3: 真实端到端测试（🟡 验证必须）

**目标**: 在 OpenClaw 主环境中运行完整 pipeline，验证产出质量。

**任务清单**:

| # | 任务 | 交付物 | 验收标准 |
|:---|:---|:---|:---|
| 3.1 | 创建测试脚本 | `tests/e2e_solution_test.py` | 使用真实模型调用，非 mock |
| 3.2 | 设计测试用例 | `tests/test_cases.yaml` | 覆盖 architecture/business/technical 三种类型 |
| 3.3 | 运行 architecture 测试 | 测试报告 | 产出包含 C4 模型的架构设计 |
| 3.4 | 运行 business 测试 | 测试报告 | 产出包含实施路线的业务方案 |
| 3.5 | 运行 technical 测试 | 测试报告 | 产出包含 API 设计的技术方案 |
| 3.6 | 质量评估 | `tests/quality_report.md` | 人工检查：技术选型是否有依据？是否有明显事实错误？ |

#### 测试用例设计

```yaml
test_cases:
  - name: "高并发电商订单系统"
    type: "architecture"
    constraints: ["日均百万订单", "99.99%可用性", "<200ms响应"]
    expected_sections: ["context_diagram", "container_diagram", "tech_stack"]
  
  - name: "中小企业数字化转型方案"
    type: "business"
    stakeholders: ["CEO", "IT部门", "财务部门"]
    expected_sections: ["problem_analysis", "implementation_roadmap", "success_metrics"]
  
  - name: "微服务网关技术方案"
    type: "technical"
    constraints: ["支持10万QPS", "OAuth2认证", "速率限制"]
    expected_sections: ["architecture_decisions", "api_design", "security_design"]
```

#### 质量检查清单

```
□ 架构设计是否包含 C4 模型（至少 L1-L2）？
□ 技术选型是否有明确依据（非随意选择）？
□ 是否有明显事实错误（如已淘汰的技术被推荐）？
□ 成本估算是否合理（数量级正确）？
□ 竞品分析是否提到真实存在的竞品？
□ 方案是否针对用户约束条件做了具体设计？
□ 输出格式是否符合 solution.yaml 中定义的 sections？
```

---

### Phase 4: Prompt 深度优化（🟢 持续改进）

**目标**: 提升每个 Agent 的产出质量，让输出更接近 Investment 模块的专业水准。

**任务清单**:

| # | 任务 | 交付物 | 验收标准 |
|:---|:---|:---|:---|
| 4.1 | 优化 Planner prompt | `prompts/solution/planner.md` | 能准确识别方案类型，提取关键维度 |
| 4.2 | 优化 Architect prompt | `prompts/solution/architect.md` | 产出包含 C4 模型、技术选型依据 |
| 4.3 | 优化 Auditor prompt | `prompts/solution/auditor.md` | 能发现事实错误、逻辑漏洞、遗漏点 |
| 4.4 | 优化 Designer prompt | `prompts/solution/designer.md` | 整合多阶段产出为统一文档 |
| 4.5 | 增加 Few-shot 示例 | `prompts/solution/examples/` | 每个方案类型提供 1-2 个示例 |
| 4.6 | A/B 测试 | 测试报告 | 对比优化前后的产出质量分数 |

#### Prompt 优化原则

1. **具体化**: 避免"请设计一个架构"，改为"请设计一个支持 10万 QPS 的微服务架构，使用 C4 模型表达"
2. **结构化**: 强制输出使用 JSON/Markdown 格式，方便后续解析
3. **约束明确**: 在 prompt 中重复用户的约束条件，防止模型遗忘
4. **自检要求**: 要求模型在输出末尾做自我检查，列出潜在问题

---

## 四、里程碑与验收

### 里程碑 1: 数据层完成（Phase 1 结束）

**验收标准**:
- [ ] `cage/validate_solution.py` 67/67 通过
- [ ] `python3 domains/solution/check_contract.py` 通过
- [ ] 运行测试：`_execute_data_collection()` 能获取外部数据
- [ ] 数据验证：`_verify_data_collection()` 检查数据完整性

### 里程碑 2: 完整 Pipeline 跑通（Phase 2 结束）

**验收标准**:
- [ ] Pipeline 完整执行：data_collection → planning → research → design → audit → fix → deliver
- [ ] 5 个 researcher 并行执行成功
- [ ] 渐进交付检查点触发正常
- [ ] 产出保存到 Blackboard

### 里程碑 3: 质量达标（Phase 3 结束）

**验收标准**:
- [ ] 3 个测试用例全部通过
- [ ] 质量检查清单 7/7 通过
- [ ] 人工评估：产出质量与 Investment 模块相当

### 里程碑 4: 可交付（Phase 4 结束）

**验收标准**:
- [ ] Prompt 优化后的产出质量分数 > 0.85
- [ ] 与 Investment 模块对比无明显劣势
- [ ] 用户验收通过

---

## 五、风险管控

| 风险 | 概率 | 影响 | 应对措施 |
|:---|:---:|:---:|:---|
| 数据层实现复杂度高 | 高 | 延迟 1-2 天 | 先实现最小可用版本（只搜索不下载），再迭代 |
| 外部搜索工具不稳定 | 中 | 测试失败 | 实现降级策略：搜索失败时用模型内部知识 |
| 5 个 researcher 并行超时 | 中 | Pipeline 失败 | Semaphore=3 分两批执行，第一批 3 个，第二批 2 个 |
| Prompt 优化效果不明显 | 中 | 质量不达预期 | 采用迭代优化，每次只改一个 prompt，A/B 测试验证 |
| 修改影响 Investment 模块 | 低 | 回滚成本 | 每次提交前检查 diff，确认只修改 solution 目录 |

---

## 六、每日检查清单

### 开发前
```
□ 读取本开发计划文档
□ 确认当前 Phase 和任务
□ 编写/更新契约文件
```

### 开发中
```
□ 实现代码
□ 运行单元测试
□ 运行契约验证（67/67）
□ 检查是否影响 Investment（git diff --name-only）
```

### 开发后
```
□ 提交代码（附清晰 commit message）
□ 推送到 GitHub
□ 更新本计划文档（标记已完成任务）
□ 记录教训到 memory/2026-04-26.md
```

---

## 七、附录

### A. 参考文件

| 文件 | 说明 |
|:---|:---|
| `domains/investment.yaml` | Investment 领域配置（参考数据层设计） |
| `domains/investment/orchestrator.py` | Investment Orchestrator（参考 `_execute_data_collection()`） |
| `cage/domain_solution.yaml` | Solution 契约笼子 |
| `cage/validate_solution.py` | 自动化验证脚本 |
| `DEVELOPMENT_RULES.md` | 开发规范宪法 |

### B. 关键命令

```bash
# 验证契约
cd ~/.openclaw/workspace/.deepflow
python3 cage/validate_solution.py

# 检查修改范围
git diff --name-only

# 运行测试
python3 tests/e2e_solution_test.py

# 提交代码
git add -A
git commit -m "feat(solution): [具体描述]

- [变更点1]
- [变更点2]

Validation: [验证结果]"
git push origin main
```

### C. 联系人

- **决策人**: 姬忠礼
- **开发执行**: 小满（AI Agent）
- **代码审查**: 契约笼子自动化验证 + 人工抽查

---

*文档创建时间: 2026-04-26 13:35*  
*下次更新: Phase 1 完成后*
