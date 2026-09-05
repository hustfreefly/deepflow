"""
ADR-009 MD Track Extractor — 9 Test Scenarios

1. spec_pro 合法 MD 通过
2. solution_pro 合法 MD 通过
3. ship_pro 合法 MD 通过
4. deliver_pro 合法 MD 通过
5. research_pro 合法 MD 通过
6. 缺失章节 → 拒绝
7. 畸形表格 → 告警（extract 阶段放宽，不 raise）
8. track.json schema 验证
9. 边界长度（deliver_pro 200字符刚好通过）
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.md_track_extractor import validate_md_structure, extract_track_json


# ─── Fixtures ───────────────────────────────────────────────────────────────

VALID_SPEC_MD = """---
domain: spec_pro
version: "1.0.0"
session: spec_001
created: "2026-07-11T20:00:00Z"
---

# Spec Requirements: 测试项目

## meta_info

| 字段 | 值 |
|------|-----|
| spec_version | 1 |
| quality_score | 85 |
| quality_level | A |
| conversation_rounds | 2 |
| domain_id | software |
| domain_label | 软件工程 |

## overview

> **角色**: 上下文参考

构建一个自动化订单通知系统，解决手动发邮件漏发的问题。系统需要支持多渠道通知（邮件、短信、站内信），
并且提供发送状态看板供运营人员实时查看。核心目标是减少人工操作失误，提高订单确认邮件的送达率。

## confirmed_reqs

> **角色**: 权威数据

| REQ-ID | 维度 | 需求描述 | 优先级 | 来源轮次 | 状态 |
|--------|------|----------|--------|----------|------|
| REQ-001 | 功能 | 自动发送订单确认邮件 | P0 | Round 1 | confirmed |
| REQ-002 | 功能 | 发送状态看板 | P1 | Round 1 | confirmed |
| REQ-003 | 质量 | 邮件送达率 99.9% | P0 | Round 1 | confirmed |

## capability_boundary

> **角色**: 权威数据

| 分类 | 内容 |
|------|------|
| Always Do | 自动发送订单确认邮件 |
| Should Do | 多渠道通知扩展 |
| Never Do | 微服务架构 |

## constraints

> **角色**: 权威数据

| 约束 | 说明 |
|------|------|
| 阿里云平台 | 部署在阿里云 ECS + RDS |
| 技术栈 | Vue3 + NestJS |


## gate_decisions

| check_layer | result | reason |
|-------------|--------|--------|
| L1 | PASS | test |
| L3 | PASS | test |

## quality_attrs

> **角色**: 上下文参考

| 类别 | 规格 | 优先级 |
|------|------|--------|
| 可靠性 | 邮件送达率 99.9% | P0 |
| 可用性 | 系统可用性 99.95% | P0 |

## gate_decisions

> **Gate 结果语义**: PASS=*** CONDITIONAL=下游需额外验证, FAIL=阻塞需上游重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | PASS | 所有必填字段存在 |
| L2 (LLM Judge) | PASS (85/100) | 语义完整 |
| L3 (合并) | PASS | 进入交接阶段 |
"""


VALID_SOLUTION_MD = """---
domain: solution_pro
version: "1.0.0"
session: solution_001
upstream: spec_001
created: "2026-07-11T21:00:00Z"
---

# Solution Design: 自动化订单通知系统

## meta_info

| 字段 | 值 |
|------|-----|
| solution_version | 1.0.0 |
| domain_id | software |
| covered_req_count | 3 |
| architecture_layers | 3 |
| total_components | 5 |

## requirement_coverage矩阵

> **角色**: 权威数据

| REQ-ID | 覆盖状态 | 对应组件 | 设计决策 |
|--------|----------|----------|----------|
| REQ-001 | covered | EmailService | 采用阿里云 DirectMail API |
| REQ-002 | covered | DashboardUI | Vue3 + Element Plus 看板 |
| REQ-003 | covered | EmailService | 3次重试 + 死信队列 + 告警 |

## solution_structure

> **角色**: 权威数据

### 分层架构

| 层 | 组件 | 职责 |
|----|------|------|
| 表现层 | DashboardUI | 用户界面，展示发送状态 |
| 业务层 | OrderService | 订单处理逻辑 |
| 业务层 | EmailService | 邮件发送 + 重试 |
| 数据层 | PostgreSQL | 订单数据存储 |
| 数据层 | Redis | 消息队列缓存 |

### 数据流

OrderService → EmailQueue → EmailService → DirectMail API

## implementation_plan

> **角色**: 权威数据

| 阶段 | 内容 | 预估工时 | 风险 |
|------|------|----------|------|
| Phase 1 | 数据库 Schema + 基础 API | 16h | 低 |
| Phase 2 | 邮件服务集成（DirectMail） | 24h | 中（第三方 API） |
| Phase 3 | 看板 UI | 16h | 低 |
| Phase 4 | 监控告警 | 8h | 低 |

## quality_attrs实现

> **角色**: 权威数据

| REQ-ID | 质量属性 | 实现策略 |
|--------|----------|----------|
| REQ-001 | 功能 | DirectMail API + 模板引擎 |
| REQ-002 | 功能 | Vue3 + Element Plus 实时看板 |
| REQ-003 | 可靠性 99.9% | 3次指数退避重试 + 死信队列 + 监控告警 |

## gate_decisions

> **Gate 结果语义**: PASS=*** CONDITIONAL=下游需额外验证, FAIL=阻塞需上游重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | PASS | 所有组件有明确职责 |
| L2 (LLM Judge) | PASS (88/100) | 架构合理，覆盖完整 |
| L3 (合并) | PASS | 进入 Ship Pro |
"""

VALID_SHIP_MD = """---
domain: ship_pro
version: "1.0.0"
session: ship_001
upstream: solution_001
created: "2026-07-11T22:00:00Z"
---

# Ship Package: 自动化订单通知系统

## meta_info

| 字段 | 值 |
|------|-----|
| package_version | 1.0.0 |
| total_wp | 4 |
| total_estimated_hours | 64 |
| critical_path | WP-001 → WP-002 → WP-003 |

## work_packages

> **角色**: 权威数据

| WP-ID | 名称 | 优先级 | 依赖 | 预估工时 | 交付物 | 验收标准 |
|-------|------|--------|------|----------|--------|----------|
| WP-001 | 数据库 Schema | P0 | - | 8h | schema.sql | 支持订单 CRUD |
| WP-002 | 基础 API 框架 | P0 | WP-001 | 16h | api/ | RESTful 端点可用 |
| WP-003 | 邮件服务集成 | P0 | WP-002 | 24h | email_service/ | 发送成功率 ≥ 99.9% |
| WP-004 | 看板 UI | P1 | WP-002 | 16h | dashboard/ | 实时状态展示 |

## execution_order

> **角色**: 权威数据

WP-001 → WP-002 → WP-003 → 集成测试
                  ↘ WP-004 ↗

## req_traceability

> **角色**: 权威数据

| REQ-ID | 覆盖 WP | 验收标准关联 |
|--------|---------|--------------|
| REQ-001 | WP-003 | 邮件发送成功 |
| REQ-002 | WP-004 | 看板可访问 |
| REQ-003 | WP-003 | 送达率 ≥ 99.9% |

## 风险评估

> **角色**: 上下文参考

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| DirectMail API 变更 | 低 | 高 | 抽象接口层 |
| 数据库性能瓶颈 | 中 | 中 | 读写分离 + 索引优化 |

## gate_decisions

> **Gate 结果语义**: PASS=*** CONDITIONAL=下游需额外验证, FAIL=阻塞需上游重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | PASS | 所有 WP 字段完整 |
| L2 (LLM Judge) | PASS (90/100) | WP 拆分合理，依赖无环 |
| L3 (合并) | PASS | 进入 Deliver Pro |
"""

VALID_DELIVER_MD = """---
domain: deliver_pro
version: "1.0.0"
session: deliver_001
upstream: ship_001
created: "2026-07-11T23:00:00Z"
---

# Deliver Final: 自动化订单通知系统

## meta_info

| 字段 | 值 |
|------|-----|
| deliverable_version | 1.0.0 |
| total_files | 42 |
| total_size_kb | 380 |
| format | code_bundle |

## deliverables

> **角色**: 权威数据

| 交付物 | 类型 | 来源 WP | 路径 |
|--------|------|---------|------|
| 数据库脚本 | SQL | WP-001 | sql/schema.sql |
| API 代码 | TypeScript | WP-002 | src/api/ |
| 邮件服务 | TypeScript | WP-003 | src/email/ |
| 看板前端 | Vue | WP-004 | src/dashboard/ |

## execution_guide

> **角色**: 权威数据

1. **环境准备**: 阿里云 ECS (4核8G) + RDS PostgreSQL
2. **部署顺序**: 数据库迁移 → API 服务 → 邮件服务 → 前端看板
3. **验证步骤**: 
   - 创建测试订单 → 检查邮件发送
   - 访问看板 → 确认状态更新
   - 模拟 API 故障 → 验证重试机制

## acceptance_summary

> **角色**: 权威数据

| REQ-ID | 验收标准 | 验证方法 |
|--------|----------|----------|
| REQ-001 | 邮件发送成功 | 发送 10 封测试邮件 |
| REQ-002 | 看板可访问 | 浏览器访问 + 状态更新 |
| REQ-003 | 送达率 ≥ 99.9% | 7天统计 |

## gate_decisions

> **Gate 结果语义**: PASS=*** CONDITIONAL=下游需额外验证, FAIL=阻塞需上游重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (完整性) | PASS | 所有 WP 有对应交付物 |
| L2 (LLM Judge) | PASS (92/100) | 交付物完整，指南清晰 |
| L3 (合并) | PASS | 交付完成 |
"""

VALID_RESEARCH_MD = """---
domain: research_pro
version: "1.0.0"
session: research_001
trigger: on_demand
created: "2026-07-11T15:00:00Z"
---

# Research Report: 邮件服务最佳实践

## meta_info

| 字段 | 值 |
|------|-----|
| research_topic | 邮件服务最佳实践 |
| sources_count | 8 |
| confidence_level | high |

## research_questions

> **角色**: 上下文参考

1. 阿里云 DirectMail 的最佳重试策略是什么？
2. 邮件送达率 99.9% 的行业实现方案有哪些？
3. 如何设计可靠的死信队列处理机制？

## findings

> **角色**: 权威数据

### 发现 1: 重试策略

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| 指数退避 | 避免雪崩效应 | 延迟增加 | ⭐⭐⭐⭐⭐ |
| 固定间隔 | 实现简单 | 可能引发雪崩 | ⭐⭐ |
| 自适应退避 | 动态调整 | 实现复杂 | ⭐⭐⭐⭐ |

### 发现 2: 送达率保障

| 策略 | 预期效果 | 实施成本 |
|------|----------|----------|
| 多通道 fallback | +0.5% | 中 |
| DNS 预热 | +0.2% | 低 |
| IP 信誉管理 | +0.3% | 高 |

## recommendations

> **角色**: 权威数据

1. 采用指数退避重试（初始 1s，最大 60s，3 次）
2. 配置死信队列处理永久失败邮件
3. 监控 bounce rate，阈值设为 0.1%
4. 使用多通道 fallback（DirectMail → SMTP → 第三方）

## references

> **角色**: 上下文参考

| # | 来源 | URL | 访问日期 |
|---|------|-----|----------|
| 1 | 阿里云 DirectMail 文档 | https://help.aliyun.com/directmail | 2026-07-11 |
| 2 | AWS SES Best Practices | https://docs.aws.amazon.com/ses | 2026-07-11 |

## gate_decisions

> **Gate 结果语义**: PASS=*** CONDITIONAL=下游需额外验证, FAIL=阻塞需上游重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | PASS | 所有章节完整 |
| L2 (LLM Judge) | PASS (87/100) | 研究发现有据可查 |
| L3 (合并) | PASS | 研究完成 |
"""


# ─── Test Scenarios ─────────────────────────────────────────────────────────

class TestValidateMdStructure:
    """Phase 2a: validate_md_structure tests"""

    def test_1_spec_pro_valid(self):
        passed, msg, warnings = validate_md_structure(VALID_SPEC_MD, "spec_pro")
        assert passed, f"应通过校验: {msg}"

    def test_2_solution_pro_valid(self):
        passed, msg, warnings = validate_md_structure(VALID_SOLUTION_MD, "solution_pro")
        assert passed, f"应通过校验: {msg}"

    def test_3_ship_pro_valid(self):
        passed, msg, warnings = validate_md_structure(VALID_SHIP_MD, "ship_pro")
        assert passed, f"应通过校验: {msg}"

    def test_4_deliver_pro_valid(self):
        passed, msg, warnings = validate_md_structure(VALID_DELIVER_MD, "deliver_pro")
        assert passed, f"应通过校验: {msg}"

    def test_5_research_pro_valid(self):
        passed, msg, warnings = validate_md_structure(VALID_RESEARCH_MD, "research_pro")
        assert passed, f"应通过校验: {msg}"

    def test_6_missing_section_rejected(self):
        bad_md = """---
domain: spec_pro
version: "1.0.0"
---
# Spec
## meta_info
| 字段 | 值 |
|------|-----|
| x | y |
"""
        # Missing: confirmed_reqs, capability_boundary, constraints
        passed, msg, warnings = validate_md_structure(bad_md, "spec_pro")
        assert not passed, "缺少必填章节应拒绝"
        assert "confirmed_reqs" in msg or "capability_boundary" in msg or "constraints" in msg

    def test_9_boundary_length_deliver_pro(self):
        # deliver_pro min_length = 200
        minimal_md = """---
domain: deliver_pro
version: "1.0.0"
---
# Deliver Final

## meta_info

| 字段 | 值 |
|------|-----|
| total_files | 1 |

## deliverables

| 交付物 | 来源 WP |
|--------|---------|
| API | WP-001 |

## execution_guide

部署 API 即可运行。

## gate_decisions

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L3 (合并) | PASS | OK |
"""
        passed, msg, warnings = validate_md_structure(minimal_md, "deliver_pro")
        assert passed, f"deliver_pro 最小长度 200 字符应通过: {msg}"


class TestExtractTrackJson:
    """Phase 2b: extract_track_json tests"""

    def test_7_malformed_table_warns(self, caplog):
        # MD with valid frontmatter and sections but NO tables at all
        bad_table_md = """---
domain: deliver_pro
version: "1.0.0"
---
# Deliver Final

## meta_info

这不是一个表格，只是普通文本段落。内容足够长度达到两百字符以上。
补充更多内容以确保长度检查通过。补充更多内容以确保长度检查通过。
补充更多内容以确保长度检查通过。补充更多内容以确保长度检查通过。
补充更多内容以确保长度检查通过。补充更多内容以确保长度检查通过。

## deliverables

没有表格结构，只有纯文本描述。

## execution_guide

直接部署即可。

## gate_decisions

没有 Gate 表格。
"""
        track = extract_track_json(bad_table_md, "deliver_pro")
        assert track["metrics"]["req_count"] == 0
        assert "未找到任何表格" in caplog.text or "Gate 决策表提取为空" in caplog.text

    def test_8_track_json_schema_valid(self):
        track = extract_track_json(VALID_SPEC_MD, "spec_pro")
        # Schema validation
        assert track["schema_version"] == "3.1.0"
        assert track["domain"] == "spec_pro"
        assert "frontmatter" in track
        assert "gate_summary" in track
        assert "metrics" in track
        assert "anchors" in track
        # REQ-IDs extracted
        assert "REQ-001" in track["metrics"]["req_ids"]
        assert "REQ-002" in track["metrics"]["req_ids"]
        assert "REQ-003" in track["metrics"]["req_ids"]
        # Gate summary has L3
        l3_keys = [k for k in track["gate_summary"] if "L3" in k or "合并" in k]
        assert len(l3_keys) > 0, f"应有 L3 verdict，实际: {track['gate_summary']}"
        # Anchors computed
        assert len(track["anchors"]) > 0, "应有章节锚点"

    def test_unknown_domain_raises(self):
        with pytest.raises(ValueError, match="未知域"):
            extract_track_json("---\nversion: 1\n---\n## meta_info\n| x | y |\n|---|---|\n| a | b |", "nonexistent_domain")

    def test_no_frontmatter_raises(self):
        no_fm_md = "# No Frontmatter\n## meta_info\n| x | y |\n|---|---|\n| a | b |"
        with pytest.raises(ValueError, match="frontmatter|结构校验"):
            extract_track_json(no_fm_md, "spec_pro")

    def test_all_domains_extract(self):
        """所有 5 个域都能成功提取 track.json"""
        fixtures = [
            (VALID_SPEC_MD, "spec_pro"),
            (VALID_SOLUTION_MD, "solution_pro"),
            (VALID_SHIP_MD, "ship_pro"),
            (VALID_DELIVER_MD, "deliver_pro"),
            (VALID_RESEARCH_MD, "research_pro"),
        ]
        for md, domain in fixtures:
            track = extract_track_json(md, domain)
            assert track["domain"] == domain
            assert track["schema_version"] == "3.1.0"
            assert len(track["gate_summary"]) > 0, f"{domain}: gate_summary 为空"
            assert len(track["anchors"]) > 0, f"{domain}: anchors 为空"
