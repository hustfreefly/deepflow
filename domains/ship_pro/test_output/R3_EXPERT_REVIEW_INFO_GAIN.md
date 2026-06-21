# 信息增益评估报告：Ship Pro v3.1.2 → v3.1.3

**评估时间**: 2026-06-19  
**评估范围**: Case 3 (简历) + Case 4 (跨境AI) Architect/Specifier 输出  
**评估方法**: 逐字段对比 + 信息可操作性分析

---

## A. 新增的有价值信息

### 1. [R3-1] 需求提取完全恢复 — 价值：**高**
- Case 4 需求从 v3.1.2 的 12 条恢复到 v3.1.3 的 71 条
- 根因修复：删除 `expected_req_count` 字段，消除数字锚点对 LLM 的误导
- **信息净值**: +59 条需求，覆盖商业模式/支付/合规/运维等全部维度
- **验证**: architect_output_v313.json 确认 `expected_req_count` 已移除

### 2. [R3-2] context_files 自引用消除 — 价值：**中**
- v3.1.2 的 context_files 包含自身 outputs 路径（如 WP-001 的 context_files 含 "docker-compose.yml"，outputs 也含 "docker-compose.yml"）
- v3.1.3 完全消除自引用，27/27 WP 通过 `context_no_self_reference` Gate
- **但**: context_files 现在只含 `["blueprint.json", "wp_structure.json"]`，丢失了上游 WP 产出物的具体引用（见 C 部分）

### 3. [R3-3] outputs 与 wp_file_mapping 对齐 — 价值：**中**
- v3.1.3 的 outputs 从 `wp_file_mapping.expected_outputs` 继承
- 消除了 v3.1.2 中 outputs 自行改名的问题
- **但**: 引入新问题 — 多个 WP 的 outputs 出现重叠（见 C.3）

### 4. [SLA]/[RISK] 标签系统化传递 — 价值：**中**
- v3.1.3 的 constraints 系统性标注 `[SLA]` 和 `[RISK]` 标签
- 每个标签可追溯到 blueprint 的 sla_constraints 和 risks
- 示例: `"[SLA] 故障切换时间: <3秒"` + `"[RISK] 供应商ToS转售合规: Day 1并行申请..."`
- Case 4 Specifier: 47 个 [SLA] 标签 + 35 个 [RISK] 标签

### 5. [ARCH_INFERRED] 新标签 — 价值：**低-中**
- v3.1.3 新增 `[ARCH_INFERRED]` 标签，标记 Architect 推导但 blueprint 未显式指定的技术选型
- 示例: `"使用 PyMuPDF [ARCH_INFERRED]"`, `"使用 TF-IDF [ARCH_INFERRED]"`
- **注意**: 验证报告未追踪此标签类型，存在 Harness 盲区

### 6. 财务预测结构化改进 — 价值：**低**
- v3.1.3 architect 的 `financial_projections.scale_economics` 新增 `monthly_cost` 字段
- 从 `{revenue, margin}` 扩展为 `{revenue, cost, margin}`，信息更完整

---

## B. 修复的信息失真

### B1. 需求提取回退 → **完全修复** ✅
| 维度 | v3.1.2 | v3.1.3 |
|------|--------|--------|
| Case 4 需求数 | 12 条（回退 83%） | 71 条（100% 恢复） |
| 根因 | `expected_req_count: 71` 误导 LLM 压缩 | 删除该字段 |
| 覆盖度 | 仅核心需求 | 全维度覆盖 |

### B2. context_files 自引用 → **完全修复** ✅
| 维度 | v3.1.2 | v3.1.3 |
|------|--------|--------|
| 自引用 WP 数 | 27/27 违规 | 0/27 违规 |
| Gate 检查 | 无 | `set(context_files) ∩ set(outputs) == ∅` |

### B3. outputs 命名不一致 → **修复，但引入新问题** ⚠️
| 维度 | v3.1.2 | v3.1.3 |
|------|--------|--------|
| 继承方式 | LLM 自行决定 | 从 wp_file_mapping 继承 |
| 一致性 | 部分不一致 | 全部一致 |
| 重叠问题 | 无 | **WP-001/WP-002 outputs 重叠**（见 C.3） |

### B4. constraints 泛称 → **部分修复** ⚠️
| 维度 | v3.1.2 | v3.1.3 |
|------|--------|--------|
| 泛称问题 | "高性能"/"可扩展" | 全部具体名称 |
| 标签来源 | 无标注 | `[ARCH_INFERRED]` 标注推导来源 |
| 验证报告声称 | "全部具体" | "全部具体，无需推导" |
| **实际** | — | **存在 [ARCH_INFERRED] 标签**，验证报告遗漏 |

---

## C. 仍然存在的问题

### C1. context_files 信息空洞化 — 严重程度：**高** 🔴
- v3.1.2 的 context_files 虽有自引用问题，但至少列出了具体的上游产出物路径
- v3.1.3 的 context_files **仅包含** `["blueprint.json", "wp_structure.json"]`
- **影响**: 实现者无法知道应该读取哪些上游 WP 的输出作为输入
- **示例**: Case 4 WP-002（用户管理）的 context_files 不含 WP-001（网关）的任何产出物，但 WP-002 逻辑上依赖 WP-001 的 docker-compose 配置

### C2. 验收测试从可执行命令退化为方向描述 — 严重程度：**高** 🔴
- v3.1.2 的 acceptance_tests 包含可直接执行的命令:
  ```
  "docker-compose up -d && curl http://localhost:3000/api/status"
  "bash scripts/verify-api.sh --failover-test"
  "pytest frontend/tests/test_auth.py"
  ```
- v3.1.3 退化为截断的方向描述:
  ```
  "测试方向 1: 运行 `docker-compose up -d` 成功启动 New API 网关，健康检查端点返回 200..."
  "测试方向 2: 发送 `curl -X POST https://api.example.com/v1/chat/completions..."
  ```
- **信息损失**: 丢失完整的测试命令、参数、预期输出
- **可操作性**: 从"复制粘贴即可运行"退化为"需要重新编写测试"

### C3. 多 WP outputs 重叠/冲突 — 严重程度：**中** 🟡
- Case 4 v3.1.3:
  - WP-001 outputs: `["docker-compose.yml", "Dockerfile", "new-api-config/"]`
  - WP-002 outputs: `["docker-compose.yml", "Dockerfile", "new-api-config/"]` ← **完全重复**
- Case 3 v3.1.3 也有类似重叠（WP-001/WP-002 均输出 knowledge/ 和 parser/ 目录）
- **影响**: 实现者无法判断哪个 WP 负责生成哪个文件，可能导致重复实现或冲突

### C4. [SHIP_DERIVED] 标签消失 — 严重程度：**中** 🟡
- v3.1.2 Case 4 Specifier 有 5 个 `[SHIP_DERIVED]` 标签:
  - "计费精度误差 < 0.1%"
  - "Dashboard 用量查询 P99 < 500ms"
  - "首屏加载 < 2s"
  - "支付到账延迟 < 30s"
  - "CDN 缓存命中率 ≥ 80%"
- v3.1.3 Case 4 Specifier: **0 个** [SHIP_DERIVED] 标签
- Case 3 同样: v3.1.2 有 4 个 [SHIP_DERIVED]，v3.1.3 降为 0 个
- **影响**: 从产品需求推导的隐含约束丢失，实现者失去性能/体验目标的指导

### C5. Architect 技术栈信息丢失 — 严重程度：**中** 🟡
- Case 4 COMP-001 technology_stack:
  - v3.1.2: `["New API", "Docker", "Railway", "Go"]`
  - v3.1.3: `["New API", "Docker", "PostgreSQL"]`
  - **丢失**: `Go`（实现语言）和 `Railway`（部署平台）
- 这是 Architect 阶段的纯信息丢失，无修复理由

### C6. 需求引用膨胀 — 严重程度：**低** 🟢
- v3.1.3 每个 WP 的 requirements 列表膨胀到 16-45 个 REQ-ID
- Case 4 WP-001 引用 45 个需求（几乎全部），失去聚焦
- v3.1.2 每个 WP 引用 2-3 个精准需求
- **影响**: 需求追溯性降低，无法快速判断 WP 的核心职责

### C7. 验证报告与实际输出不一致 — 严重程度：**中** 🟡
- 验证报告声称 `[SPEC_INFERRED]: 0`（全部具体名称）
- 实际 v3.1.3 Case 3 输出包含多个 `[ARCH_INFERRED]` 标签
- **影响**: Harness 的 Gate 检查未覆盖此标签类型，存在验证盲区

---

## D. 信息净值计算

### 信息增益（+项）
| # | 增益项 | 价值权重 |
|---|--------|---------|
| 1 | 需求提取恢复（+59 条） | 高 |
| 2 | context_files 自引用消除 | 中 |
| 3 | outputs 与 wp_file_mapping 对齐 | 中 |
| 4 | [SLA]/[RISK] 标签系统化 | 中 |
| 5 | [ARCH_INFERRED] 来源标注 | 低-中 |
| 6 | 财务预测结构化 | 低 |

**增益合计: 6 项**

### 信息损失（-项）
| # | 损失项 | 价值权重 |
|---|--------|---------|
| 1 | context_files 空洞化（丧失上游引用） | 高 |
| 2 | 验收测试从可执行命令退化为方向描述 | 高 |
| 3 | 多 WP outputs 重叠冲突 | 中 |
| 4 | [SHIP_DERIVED] 标签全部消失 | 中 |
| 5 | Architect 技术栈信息丢失（Go/Railway） | 中 |
| 6 | 需求引用膨胀失去聚焦 | 低 |
| 7 | 验证报告遗漏 [ARCH_INFERRED] 标签 | 中 |

**损失合计: 7 项**

### 净值评估

| 维度 | 评估 |
|------|------|
| **信息净值** | **负** |
| 增益总量 | 6 项（1 高 + 3 中 + 2 低） |
| 损失总量 | 7 项（2 高 + 4 中 + 1 低） |
| 高价值项净值 | +1 - 2 = **-1**（净损失） |
| 可操作性变化 | **显著下降**（验收测试 + context_files 双重退化） |

---

## 综合评分

| 维度 | 评分 |
|------|------|
| **信息净值** | **负** |
| **相比 v3.1.2 提升** | **轻微**（结构修复有进步，但可操作性退步更大） |
| **关键改进** | 需求提取恢复、自引用消除、[SLA]/[RISK] 标签系统化 |
| **遗留问题** | context_files 空洞化、验收测试退化、outputs 重叠、[SHIP_DERIVED] 消失、技术栈信息丢失 |

### 关键发现

1. **R3 修复是"结构正确性"改进，不是"信息丰富度"改进**  
   Gate 通过率 100% 说明结构合规，但合规 ≠ 信息增益。自引用消除后，context_files 变成空壳；outputs 对齐后，多个 WP 输出重叠。

2. **Specifier 的"方向描述"模式严重损害可操作性**  
   v3.1.2 的验收测试可以直接复制执行；v3.1.3 的"测试方向 1: ..."需要实现者重新编写。这是从"信息"退化为"提示"。

3. **[SHIP_DERIVED] 标签的消失是系统性信息丢失**  
   这些标签代表了从商业需求推导出的隐含技术约束（如 P99 < 500ms、首屏 < 2s），是 Specifier 的核心增值之一。v3.1.3 完全丢弃了这一信息维度。

4. **验证报告存在盲区**  
   [ARCH_INFERRED] 标签在 v3.1.3 中大量出现，但验证报告未追踪此类型，声称"无需推导"与实际输出矛盾。

### 建议

1. **context_files 策略需要折中**: 禁止自引用正确，但应保留对上游 WP outputs 的引用（如 `WP-001/outputs/`）
2. **验收测试必须保留可执行命令**: "测试方向"模式应回退为完整命令
3. **[SHIP_DERIVED] 标签需要恢复**: 这是 Specifier 的核心增值
4. **Architect 技术栈变更需要 Gate 检查**: 防止无理由的技术栈信息丢失
5. **验证报告应追踪 [ARCH_INFERRED]**: 补充 Gate 规则

---

*评估完成。报告写入: test_output/R3_EXPERT_REVIEW_INFO_GAIN.md*
