## 信息增益评估报告（R4）

> 评估时间: 2026-06-19 11:07
> 评估对象: Ship Pro v3.1.3 → v3.1.4 (specifier prompt)
> 评估人: 信息增益评估专家 (Subagent)

---

### R4-1 acceptance_tests 质量

| 案例 | v3.1.3 | v3.1.4 | 状态 |
|------|--------|--------|------|
| Case 1 (TODO) | 4条，均为可执行命令 (`npm run build`, `npx vitest run`) | 5条，可执行命令+精确参数 (`--reporter=verbose`, `node -e "..."`, `npx lighthouse`) | **PASS** ✅ |
| Case 2 (电商) | 60条，**100% 模糊** ("测试方向 1: ...", "测试方向 2: ...") | 54条，**0% 模糊**，全部为 `curl`/`docker-compose`/`wrk`/`redis-cli`/`kafka-console-consumer` 可执行命令 | **PASS** ✅ |
| Case 3 (简历) | 44条，**100% 模糊** ("测试方向 1: ...") | 34条，**0% 模糊**，全部为 `python -c "..."`/`pytest`/`pdftotext` 可执行命令 | **PASS** ✅ |
| Case 4 (跨境AI) | 44条，**100% 模糊** ("测试方向 1: ...") | 35条，**0% 模糊**，全部为 `curl`/`docker-compose`/`openssl`/`dig` 可执行命令 | **PASS** ✅ |

**详细对比示例 (Case 2 WP-001)**:

| v3.1.3 (模糊) | v3.1.4 (可执行) |
|:---|:---|
| `测试方向 1: 运行 docker-compose up 成功启动 Kong + Nginx，所有服务健康检查返回 200...` | `docker-compose up -d && sleep 5 && curl -s http://localhost:8001/status \| jq '.status'` |
| `测试方向 3: 并发 1000 请求/秒压测，限流策略触发后返回 429...` | `wrk -t4 -c100 -d30s http://localhost:8000/products 2>&1 \| grep 'requests in'` |

**详细对比示例 (Case 3 WP-001)**:

| v3.1.3 (模糊) | v3.1.4 (可执行) |
|:---|:---|
| `测试方向 1: 运行 pytest tests/test_knowledge/ tests/test_parser/ -v，所有测试通过...` | `pytest tests/test_parser/ tests/test_knowledge/ -v --tb=short` |
| `测试方向 2: 知识库包含 ≥ 30 个半导体封装工艺术语...` | `python -c "import json; d=json.load(open('src/knowledge/data/terms.json')); assert len(d)>=30; ..."` |

**结论**: ✅ **PASS** — v3.1.3 中 148/192 条 (77%) acceptance_tests 为模糊描述，v3.1.4 中 0/127 条为模糊描述。修复彻底。

---

### R4-2 context_files 信息净值

| 案例 | v3.1.3 平均长度 | v3.1.4 平均长度 | 自引用违规 | 状态 |
|------|:---:|:---:|:---:|:---:|
| Case 1 (TODO) | 2.0 | 4.0 (+100%) | 0 | **PASS** ✅ |
| Case 2 (电商) | 5.2 | 4.8 (-8%) | 0 | **PASS** ✅ |
| Case 3 (简历) | 8.9 | 4.9 (-45%) | 0 | **PASS** ⚠️ |
| Case 4 (跨境AI) | 3.9 | 5.9 (+51%) | 0 | **PASS** ✅ |

**自引用检查**: 所有 4 案例 × 2 版本 = 8 组输出中，**0 例** 自引用违规 (outputs ∩ context_files = ∅ 全部满足)。

**信息密度分析**:

| 案例 | v3.1.3 特征 | v3.1.4 特征 | 变化 |
|------|:---|:---|:---|
| Case 1 | 仅 `blueprint.json` + `wp_structure.json` (空洞化) | 增加 `architect_output_v313.json` + `decomposer_output.json` | ✅ 上游依赖补全 |
| Case 2 | 含上游 WP 输出 (如 `services/user-service/**/*.go`) | 替换为精确文件 (如 `services/user-service/go.mod`) | ✅ 从通配符→精确文件 |
| Case 3 | 大量目录级引用 (19条，含 `src/knowledge/`, `src/parser/` 等) | 精简为具体文件 (如 `src/knowledge/data/terms.json`, `requirements.txt`) | ⚠️ 信息密度提升但覆盖范围缩减 |
| Case 4 | 仅 `blueprint.json` + `wp_structure.json` + 少量配置 | 增加 `architect_output_v313.json` + `decomposer_output.json` | ✅ 上游依赖补全 |

**Case 3 特别说明**: context_files 从 8.9 降至 4.9（-45%），但这是因为 v3.1.3 存在"上下文膨胀"问题（每个 WP 包含所有上游 WP 的全部输出目录）。v3.1.4 改为引用具体文件（如 `src/optimizer/optimizer.py` 而非整个 `src/optimizer/` 目录），信息密度反而更高。但需注意：v3.1.4 中出现了 `src/jd_matcher/matcher.py` 这个路径，而 v3.1.3 中对应模块路径为 `src/matching/`，可能存在路径不一致风险。

**结论**: ✅ **PASS** — 空洞化问题已修复（所有案例均包含具体上游依赖路径），自引用零违规。Case 3 存在路径一致性风险需关注。

---

### 其他退化问题

#### 1. outputs 跨 WP 重叠 (遗留问题)

| 案例 | v3.1.3 | v3.1.4 | 状态 |
|------|--------|--------|------|
| Case 4 (跨境AI) | WP-001 与 WP-002 共享 `docker-compose.yml`, `Dockerfile`, `new-api-config/` | **未修复**，同样重叠 | ⚠️ 遗留 |

这是 v3.1.3 就存在的问题，v3.1.4 未修复。根因是 API 网关部署和用户管理两个 WP 都需要修改相同的部署配置文件。

#### 2. WP 需求膨胀

| 案例 | v3.1.3 WP数 | v3.1.4 WP数 | 状态 |
|------|:---:|:---:|:---:|
| Case 1 | 1 | 1 | ✅ 无变化 |
| Case 2 | 12 | 12 | ✅ 无变化 |
| Case 3 | 7 | 7 | ✅ 无变化 |
| Case 4 | 7 | 7 | ✅ 无变化 |

WP 数量无膨胀，符合预期。

#### 3. 标签使用

| 标签 | v3.1.3 | v3.1.4 | 状态 |
|------|--------|--------|------|
| `[SLA]` | 在 constraints 中正确使用 | 在 constraints 中正确使用 | ✅ 正常 |
| `[RISK]` | 在 constraints 中正确使用 | 在 constraints 中正确使用 | ✅ 正常 |
| `[SPEC_INFERRED]` | 未发现使用 | 未发现使用 | ⚠️ 未使用（可能是 prompt 未要求） |

#### 4. 其他观察

- **acceptance_tests 数量变化**: v3.1.4 总体从 192 条降至 127 条 (-34%)，但这是因为去除了冗余的"测试方向"描述，合并为更精确的可执行命令。信息量实际提升。
- **Case 3 v3.1.4 路径不一致**: `src/jd_matcher/matcher.py` 出现在 context_files 中，但 outputs 中对应模块为 `src/matching/`。可能是推理错误。

---

### 综合结论

| 维度 | 结果 |
|:---|:---|
| **信息增益** | **正向** ✅ |
| **相比 v3.1.3 提升** | acceptance_tests 可执行率: 23% → **100%** (+77pp) |
| **context_files 空洞化** | 已修复（所有案例均包含具体上游路径） |
| **自引用违规** | 0 例 |
| **遗留问题** | Case 4 outputs 跨 WP 重叠 (3 个文件)；Case 3 路径一致性风险 |

**总体评价**: R4 修复效果显著。核心问题（acceptance_tests 模糊化、context_files 空洞化）均已彻底解决。v3.1.4 的 specifier 输出从"方向性描述"升级为"可执行验证脚本"，信息增益明确为正。

**建议后续关注**:
1. Case 4 的 outputs 跨 WP 重叠问题需要 decomposer 或 specifier 层面解决
2. Case 3 中 `src/jd_matcher/` vs `src/matching/` 路径一致性问题
3. `[SPEC_INFERRED]` 标签未被使用，确认是否为预期行为
