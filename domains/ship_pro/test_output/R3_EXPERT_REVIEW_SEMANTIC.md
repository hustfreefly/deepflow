# 语义保真度评估报告

**评估人**: 语义保真度评估专家（Subagent）  
**评估时间**: 2026-06-19 10:39 GMT+8  
**版本对比**: Ship Pro v3.1.2 → v3.1.3  
**评估范围**: 4 案例 × 2 版本（Architect + Specifier 输出）

---

## R3-1 需求提取稳定性

| 案例 | v3.1.2 需求数 | v3.1.3 需求数 | 变化 | 状态 |
|------|-------------|-------------|------|------|
| Case 1 (TODO) | 3 | 3 | ±0 | ✅ 稳定 |
| Case 2 (电商) | 15 | 15 | ±0 | ✅ 稳定 |
| Case 3 (简历) | 6 | 6 | ±0 | ✅ 稳定 |
| Case 4 (跨境AI) | **12** | **71** | +59 | ✅ 恢复 |

**详细分析**:
- Case 4 v3.1.2 的 `expected_req_count: 71` 字段存在但仅输出 12 条（回退 83%），确认 `expected_req_count` 数字锚点导致 LLM 过度压缩的根因
- Case 4 v3.1.3 删除 `expected_req_count` 后恢复 71 条，且每条均有完整的 `req_id` + `description` + `priority` + `mapped_components`
- v3.1.3 的 71 条需求覆盖了商业模式、技术架构、支付、合规、运维等全部维度，无过度压缩

**结论**: **PASS** — 需求提取稳定性问题完全解决，Case 4 恢复 100%

---

## 模块边界保真度

### 模块数量与结构

| 案例 | v3.1.2 modules | v3.1.3 modules | 一致性 |
|------|---------------|---------------|--------|
| Case 1 (TODO) | 1 | 1 | ✅ 完全一致 |
| Case 2 (电商) | 12 | 12 | ✅ 完全一致 |
| Case 3 (简历) | 8 | 8 | ✅ 完全一致 |
| Case 4 (跨境AI) | 6 | 6 | ✅ 完全一致 |

### technology_stack 具体性

| 案例 | v3.1.2 泛称 | v3.1.3 泛称 | 改进 |
|------|-----------|-----------|------|
| Case 1 | `["React", "SQLite", "frontend"]` | `["React", "SQLite"]` | ✅ 移除 "frontend" 泛称 |
| Case 4 COMP-001 | `["New API", "Docker", "Railway", "Go"]` | `["New API", "Docker", "PostgreSQL"]` | ⚠️ 移除 Railway/Go，新增 PostgreSQL |
| Case 4 COMP-003 | `["Paddle MoR", "Stripe"]` | `["Paddle", "Stripe"]` | ⚠️ "Paddle MoR" → "Paddle"，丢失 MoR 语义 |
| Case 4 COMP-006 | `["UptimeRobot", "Telegram Bot"]` | `["UptimeRobot", "Telegram Bot API"]` | ✅ 更具体 |

**关键发现**:
1. Case 1 v3.1.3 移除了 "frontend" 泛称 — **正面改进**
2. Case 4 COMP-001 v3.1.3 丢失了 "Railway"（部署平台）和 "Go"（网关语言）— **信息损失**
3. Case 4 COMP-003 v3.1.3 "Paddle MoR" 简化为 "Paddle" — MoR（Merchant of Record）是关键合规语义，不应丢失

### wp_file_mapping 输出具体性

| 案例 | v3.1.2 | v3.1.3 | 评价 |
|------|--------|--------|------|
| Case 1 COMP-01 | 8 个具体文件 | `["src/", "public/index.html", "package.json"]` | ❌ 退化为目录级 |
| Case 4 COMP-001 | 4 个具体文件 | `["docker-compose.yml", "Dockerfile", "new-api-config/"]` | ⚠️ 部分退化 |
| Case 4 COMP-002 | 7 个具体路径 | `["frontend/", "frontend/app/page.tsx", ...]` | ⚠️ 含目录级 |
| Case 4 COMP-003 | 4 个具体文件 | `["src/payment/", "src/payment/paddle.ts", ...]` | ⚠️ 含目录级 |

**结论**: **PARTIAL PASS** — 模块边界整体稳定，但 wp_file_mapping 输出具体性在 v3.1.3 中有所下降（目录级 vs 文件级）。technology_stack 有少量语义丢失（Railway、Go、MoR）。

---

## 约束传递完整性

### [SLA] 标签传递

| 案例 | v3.1.2 architect SLA 数 | v3.1.2 specifier [SLA] 数 | v3.1.3 architect SLA 数 | v3.1.3 specifier [SLA] 数 | 评价 |
|------|----------------------|-------------------------|----------------------|-------------------------|------|
| Case 1 | 0 | 0 | 0 | 0 | ✅ 无 SLA 需求 |
| Case 2 | 1 | 2 | 1 | 2 | ✅ 稳定 |
| Case 3 | 10 | 8 | 10 | 25 | ✅ 增强传递 |
| Case 4 | 5 | 6 | 4 | 20 | ✅ 大幅增强 |

**分析**:
- v3.1.3 的 [SLA] 标签传递显著增强：Case 3 从 8→25，Case 4 从 6→20
- v3.1.3 每个 WP 的 constraints 中系统性传递所有 SLA 约束（如 `[SLA] 故障切换时间: <3秒`、`[SLA] 系统可用性: ≥99.9%`）
- Case 4 v3.1.3 的 SLA 从 5 条减为 4 条（丢失"月固定成本 $6-26/月"），但 specifier 层面通过 [RISK] 标签补偿

### [SPEC_INFERRED] 标签

| 案例 | v3.1.2 | v3.1.3 |
|------|--------|--------|
| 全部 | 0 | 0 |

**分析**: 两个版本均无 [SPEC_INFERRED] 标签，说明所有 tech_stack 和 constraints 均可追溯到 blueprint，无需推导。这是正面指标。

### constraints 具体性

**v3.1.2 典型约束**:
- `使用 New API + Docker + Railway（来自 blueprint COMP-001 technology_stack）`
- `使用 Paddle MoR + Stripe（来自 blueprint COMP-003 technology_stack）`

**v3.1.3 典型约束**:
- `使用 New API（来自 blueprint COMP-001.technology_stack）`
- `使用 Docker（来自 blueprint COMP-001.technology_stack）`
- `使用 PostgreSQL（来自 blueprint COMP-001.technology_stack）`

**分析**: v3.1.3 将 technology_stack 拆分为独立约束条目，每条引用具体来源，可追溯性更好。但丢失了 "Railway" 和 "Go"。

### [SHIP_DERIVED] 标签变化

| 案例 | v3.1.2 | v3.1.3 | 变化 |
|------|--------|--------|------|
| Case 1 | 2 | 0 | -2 |
| Case 2 | 20 | 0 | -20 |
| Case 3 | 6 | 0 | -6 |
| Case 4 | 5 | 0 | -5 |
| **总计** | **33** | **0** | **-33** |

**关键发现**: v3.1.3 完全消除了 [SHIP_DERIVED] 标签。

**v3.1.2 [SHIP_DERIVED] 示例**（Case 1）:
- `[SHIP_DERIVED] 筛选功能：FilterBar 支持 All/Active/Completed 三种筛选...响应时间 < 50ms`
- `[SHIP_DERIVED] 本地存储容量：storage.ts 在任务数 ≤ 10000 条时正常读写`

**v3.1.3 对应处理**: 这些需求被转化为 acceptance_criteria 中的具体测试条件，但不再标记为 [SHIP_DERIVED]。

**评价**: ⚠️ 需确认这是设计意图（不再需要 SHIP_DERIVED 标签）还是遗漏。如果 R3-4 的目标是消除模糊推导，那么 v3.1.3 的做法是正确的（所有指标均有明确来源）。但如果 [SHIP_DERIVED] 用于标记"从非功能需求推导出的验收标准"，则消除该标签会丢失可追溯性。

**结论**: **PASS with NOTE** — [SLA] 传递增强，constraints 具体化，[SPEC_INFERRED] 为零（正面）。但 [SHIP_DERIVED] 完全消失需要确认是否为设计意图。

---

## 风险缓解传递

### [RISK] 标签统计

| 案例 | v3.1.2 architect risks | v3.1.2 specifier [RISK] | v3.1.3 architect risks | v3.1.3 specifier [RISK] | 评价 |
|------|----------------------|------------------------|----------------------|------------------------|------|
| Case 1 | 1 | 1 | 1 | 1 | ✅ 稳定 |
| Case 2 | 3 | 7 | 3 | 5 | ⚠️ 略降 |
| Case 3 | 5 | 5 | 5 | 12 | ✅ 增强 |
| Case 4 | 8 | 3 | 8 | 17 | ✅ 大幅增强 |

### 风险缓解措施具体性

**Case 4 v3.1.3 RISK 传递示例**（WP-001 constraints）:
```
[RISK] 供应商ToS转售合规: Day 1并行申请商业协议+Partner Program备选+开发者Key interim mode（日限500次）+3+供应商冗余
[RISK] 跨境网络稳定性: 多路径冗余+CDN+智能路由+自动切换<3s+客户端重连，设计基准一周≤5-10分钟停机
[RISK] GDPR合规: ZDR架构（不存储prompt/response）+DPA+SCCs+Privacy Policy+用户删除/导出功能
[RISK] 供应商涨价: 多供应商分散+动态定价传导（固定毛利率）+量级折扣谈判+预充值锁价
[RISK] 中国MSS政策: ZDR架构+政策监控（RSS+季度审查）+4步分级应急预案
[RISK] New API兼容性问题: Day 1-2验证（7维度checklist）+LiteLLM备选方案
```

**评价**: ✅ 所有 8 个风险均在 WP-001 constraints 中完整传递，mitigation 措施具体可执行，包含量化指标（日限500次、<3s、一周≤5-10分钟）。

### v3.1.2 vs v3.1.3 风险传递对比

| 维度 | v3.1.2 | v3.1.3 |
|------|--------|--------|
| 风险数量 | 稳定 | 稳定 |
| [RISK] 标签覆盖 | 部分 WP 缺失 | 每个 WP 系统性传递 |
| mitigation 具体性 | 具体 | 具体（保持） |
| 量化指标 | 部分 | 完整 |

**结论**: **PASS** — 风险缓解传递在 v3.1.3 中显著增强，特别是 Case 3 和 Case 4。

---

## 新发现的问题

### 问题 1: Case 4 v3.1.3 Specifier WP 需求列表过度广播

| WP | v3.1.2 requirements 数 | v3.1.3 requirements 数 |
|----|----------------------|----------------------|
| WP-001 | 3 | **45** |
| WP-002 | 2 | **45** |
| WP-003 | 2 | 27 |
| WP-004 | 2 | 21 |
| WP-005 | 2 | 16 |
| WP-006 | 2 | 16 |
| WP-007 | 2 | 7 |

**问题**: WP-001 和 WP-002 的 requirements 数组完全相同（45 条），包含大量与该 WP 无关的需求（如 WP-001 "API网关部署" 关联了 REQ-031 "目标用户：海外AI开发者"）。这是过度广播，降低了 WP 的聚焦度。

**影响**: 下游 coder 收到大量无关需求引用，可能分散实现注意力。

### 问题 2: wp_file_mapping 输出退化

v3.1.3 的 wp_file_mapping 输出从具体文件退化为目录级：
- Case 1: `["src/App.tsx", "src/components/TodoList.tsx", ...]` → `["src/", "public/index.html", "package.json"]`
- Case 4 COMP-002: `["frontend/pages/index.tsx", "frontend/pages/dashboard.tsx", ...]` → `["frontend/", "frontend/app/page.tsx", ...]`

**影响**: 下游 decomposer/coder 需要自行推断具体文件结构。

### 问题 3: acceptance_tests 格式退化

v3.1.2 的 acceptance_tests 是可执行命令：
```
"docker-compose up -d && curl http://localhost:3000/api/status"
```

v3.1.3 的 acceptance_tests 变为描述性文本：
```
"测试方向 1: 运行 `docker-compose up -d` 成功启动 New API 网关，健康检查端点返回 200..."
```

**影响**: 丧失了直接执行测试的能力，需要人工解析为可执行命令。

---

## 综合评分

| 维度 | v3.1.2 | v3.1.3 | 变化 |
|------|--------|--------|------|
| 需求提取稳定性 | 4/10 (Case 4 严重回退) | 10/10 | **+6** |
| 模块边界保真度 | 8/10 | 7/10 | -1 |
| 约束传递完整性 | 6/10 (部分缺失) | 9/10 | **+3** |
| 风险缓解传递 | 5/10 (覆盖不全) | 9/10 | **+4** |
| context_files 自引用 | 0/10 (27/27 违规) | 10/10 (0/27) | **+10** |
| WP 聚焦度 | 9/10 | 5/10 (过度广播) | -4 |
| 测试可执行性 | 9/10 | 5/10 (描述化) | -4 |

### 总评

| 指标 | 值 |
|------|-----|
| **语义保真度** | **8/10** |
| **相比 v3.1.2 提升** | **+2.3** (v3.1.2 综合 5.7 → v3.1.3 综合 8.0) |
| **关键改进** | ① 需求提取稳定性完全恢复 ② context_files 自引用清零 ③ [SLA]/[RISK] 标签系统性传递 ④ constraints 具体化 |
| **遗留问题** | ① WP 需求列表过度广播 ② wp_file_mapping 输出退化 ③ acceptance_tests 描述化 ④ technology_stack 少量语义丢失 |

### 改进建议

1. **P0**: 修复 WP requirements 过度广播 — 每个 WP 应仅引用与其 `related_modules` 直接相关的需求
2. **P1**: 恢复 wp_file_mapping 的文件级具体性 — 从 `wp_file_mapping.expected_outputs` 继承而非推导
3. **P1**: 恢复 acceptance_tests 的可执行命令格式
4. **P2**: technology_stack 保留完整语义（如 "Paddle MoR" 不简化为 "Paddle"）

---

*评估完成。报告写入: `test_output/R3_EXPERT_REVIEW_SEMANTIC.md`*
