#!/usr/bin/env python3
"""
ResearchPro E2E 真实测试管线

用法:
  1. 主 Agent 执行 web_search，收集数据
  2. 调用 collect_sources() 注册 sources
  3. 子 Agent 生成报告
  4. 主 Agent 验证引用

管线:
  search_phase (主 Agent) → collect_sources → report_phase (子 Agent) → verify_citations → done

P2 修复覆盖:
  - P2-9: completion_criteria 校验
  - P2-10: 并发锁
  - P2-11: content_hash 绕过防护
  - P2-12: 路径穿越防护
  - P2-Mode C: spawn_fn 注入
"""

import sys
import os
import json
import hashlib
import tempfile
import shutil
from datetime import datetime
from typing import Optional

# 添加 deep-research lib 到路径
DEEPFLOW_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SKILL_LIB = os.path.join(DEEPFLOW_ROOT, 'skills', 'deep-research', 'lib')
SKILL_ROOT = os.path.join(DEEPFLOW_ROOT, 'skills', 'deep-research')
sys.path.insert(0, SKILL_ROOT)  # for lib.xxx imports
sys.path.insert(0, SKILL_LIB)   # for direct module imports

from orchestrator import ResearchProOrchestrator
from source_registry import SourceRegistry
from tier_classifier import TierClassifier
from citation_verifier import CitationVerifier


class ResearchProE2ETest:
    """真实 E2E 测试管线。"""

    def __init__(self, session_id: str = '', base_path: str = ''):
        if not base_path:
            base_path = tempfile.mkdtemp(prefix=f'research_pro_e2e_{session_id}_')
        self.base_path = base_path
        self.session_id = session_id or os.path.basename(base_path)
        self.orch: Optional[ResearchProOrchestrator] = None
        self.collected_sources: list = []
        self.tc = TierClassifier()

    def phase1_init_session(self, query: str) -> dict:
        """阶段 1: 初始化会话，生成研究计划。"""
        self.orch = ResearchProOrchestrator(base_path=self.base_path)
        result = self.orch.init_session(query)
        return {
            'status': 'init_done',
            'stage': result['state']['current_stage'],
            'keyword_groups': result['analysis_plan'].get('keyword_groups', []),
            'subtasks': result['analysis_plan'].get('subtasks', []),
            'message': result['message'],
        }

    def phase2_confirm(self) -> dict:
        """阶段 2: 用户确认计划。"""
        result = self.orch.confirm_plan({'action': 'approve'})
        return {
            'status': 'confirmed',
            'stage': result['state']['current_stage'],
        }

    def phase3_register_source(
        self,
        url: str,
        title: str,
        content: str,
        summary: str = '',
        quality_tier: str = '',
    ) -> dict:
        """阶段 3: 注册真实搜索到的 source。
        
        P2-11: 自动计算 content_hash
        """
        # 自动分类 tier
        if not quality_tier:
            domain = url.split('/')[2] if '://' in url else url
            quality_tier = self.tc.classify(domain)
        
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
        
        source_id = len(self.orch.registry.sources) + 1
        entry = {
            "id": source_id,
            "url": url,
            "title": title,
            "content": content,
            "quality_tier": quality_tier,
            "summary": summary or title[:80],
            "content_hash": content_hash,
            "registered_at": datetime.now().isoformat(),
        }
        self.orch.registry.sources.append(entry)
        self.collected_sources.append(entry)
        
        return {
            'source_id': source_id,
            'tier': quality_tier,
            'content_hash': content_hash[:8] + '...',
        }

    def phase3_batch_register(self, sources: list) -> dict:
        """批量注册 sources。
        
        每个 source: {url, title, content, summary?, quality_tier?}
        """
        results = []
        for src in sources:
            r = self.phase3_register_source(
                url=src['url'],
                title=src['title'],
                content=src['content'],
                summary=src.get('summary', ''),
                quality_tier=src.get('quality_tier', ''),
            )
            results.append(r)
        return {
            'registered': len(results),
            'total': len(self.orch.registry.sources),
            'details': results,
        }

    def phase4_execute(self) -> dict:
        """阶段 4: 执行研究（含 completion_check）。"""
        result = self.orch.execute_research()
        return {
            'sources_count': result['sources_count'],
            'completion_check': result.get('completion_check', {}),
            'batches': len(result.get('batches', [])),
        }

    def phase5_report(self, report_content: str) -> dict:
        """阶段 5: 保存报告并验证引用。
        
        Args:
            report_content: LLM 生成的报告 Markdown
        """
        if self.orch.state["current_stage"] != "reporting":
            return {"error": "当前状态不是 reporting"}

        # 保存报告
        report_path = os.path.join(self.base_path, "report", "final.md")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        # P2-9: completion_check 未通过的标注
        completion_check = self.orch.state.get("completion_check", {})
        if not completion_check.get("overall_pass", True):
            note = (
                f"\n> ⚠️ 完成标准未通过: "
                f"数据源 {completion_check.get('actual_sources', 0)}/{completion_check.get('min_sources_required', 0)}"
            )
            with open(report_path, 'a', encoding='utf-8') as f:
                f.write(note)

        # 引用验证 (RED-DC-005)
        verifier = CitationVerifier(self.orch.registry)
        citations = verifier.verify_all(report_content)

        self.orch.state["current_stage"] = "completed"
        self.orch.state["stage_status"] = "done"
        self.orch.state["report_path"] = report_path
        self.orch.state["citations"] = citations
        self.orch._save_state(self.orch.state)

        return {
            'report_path': report_path,
            'report_length': len(report_content),
            'citations': citations,
            'state': self.orch.state["current_stage"],
        }

    def get_registry_summary(self) -> dict:
        """获取 registry 摘要。"""
        sources = self.orch.registry.sources if self.orch else []
        tier_counts = {}
        for s in sources:
            tier = s.get('quality_tier', 'unknown')
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        return {
            'total': len(sources),
            'tier_counts': tier_counts,
            'sources': [
                {'id': s['id'], 'tier': s['quality_tier'], 'title': s['title'][:80]}
                for s in sources
            ],
        }

    def cleanup(self):
        """清理临时目录。"""
        if self.base_path and os.path.exists(self.base_path):
            shutil.rmtree(self.base_path, ignore_errors=True)

    def save_state(self) -> str:
        """导出完整管线状态到 JSON，供子 Agent 消费。"""
        state_file = os.path.join(self.base_path, 'e2e_state.json')
        export = {
            'session_id': self.session_id,
            'base_path': self.base_path,
            'orchestrator_state': self.orch.state if self.orch else {},
            'registry_summary': self.get_registry_summary(),
            'sources': self.orch.registry.sources if self.orch else [],
        }
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        return state_file
