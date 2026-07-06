"""
CitationVerifier — ResearchPro 引用验证器
契约: cage/active/research_pro_v1.0.yaml (L1: citation_verifier, RED-DC-001, RED-DC-005)

五步验证循环:
1. 正则提取 [N] 引用标记
2. 映射引用编号到 source_registry
3. HTTP HEAD 验证 URL 可达性
4. 内容一致性验证 (content_hash)
5. 验证失败处理

所有引用必须来自 Source Registry (RED-DC-001)。
报告生成前必须执行引用验证循环 (RED-DC-005)。
"""

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import re
import hashlib

# RED-DC-001: 引用必须来自 source_registry
from domains.research_pro.source_registry import SourceRegistry, _validate_safe_url
from domains.research_pro.safe_fetcher import _SafeFetcher, SafeFetchError


CITATION_FETCH_TIMEOUT = 10


class CitationVerifier:
    """
    引用验证器 — 五步验证循环。
    
    契约约束:
    - 所有引用必须来自 Source Registry (RED-DC-001)
    - 报告生成前必须执行引用验证循环 (RED-DC-005)
    """
    
    def __init__(self, source_registry: SourceRegistry) -> None:
        """
        初始化 CitationVerifier。
        
        Args:
            source_registry: SourceRegistry 实例
        """
        self.source_registry = source_registry
        self._fetcher = _SafeFetcher(timeout=CITATION_FETCH_TIMEOUT)
    
    def extract_citations(self, report_md: str) -> list[int]:
        """
        步骤 1: 正则提取报告中的 [N] 引用标记。
        
        Args:
            report_md: 报告 Markdown 内容
        
        Returns:
            引用编号列表 (去重后, 升序)
        """
        pattern = r'\[(\d+)\]'
        matches = re.findall(pattern, report_md)
        citation_ids = sorted(set(int(m) for m in matches))
        return citation_ids
    
    def verify_citation(self, source_id: int) -> dict:
        """
        步骤 2-5: 验证单个引用。
        
        步骤 2: 映射引用编号到 source_registry
        步骤 2.5 (P0 fix): 检查 eligible_for_citation，拒绝 ineligible source
        步骤 3: HTTP HEAD 验证 URL 可达性
        步骤 4: 内容一致性验证 (content_hash)
        步骤 5: 验证失败处理
        
        Args:
            source_id: 引用编号 (对应 source_registry 中的 id)
        
        Returns:
            dict: 单条引用验证结果
        """
        # 步骤 2: 映射引用编号到 source_registry
        source = self.source_registry.get(source_id)
        if source is None:
            return {
                "source_id": source_id,
                "url": "",
                "status": "not_found",
                "http_status": None,
                "content_hash_match": False,
                "quality_tier": "unverified",
                "verification_detail": f"Source ID {source_id} not found in registry",
            }

        # 步骤 2.5 (P0 fix): 检查 eligible_for_citation
        # 如果源是 fallback/synthetic 且未真正 fetch 成功，拒绝引用
        if not source.get("eligible_for_citation", False):
            return {
                "source_id": source_id,
                "url": source.get("url", ""),
                "status": "ineligible_source",
                "http_status": None,
                "content_hash_match": False,
                "quality_tier": source.get("quality_tier", "unverified"),
                "verification_detail": (
                    f"Source ID {source_id} is not eligible for citation: "
                    f"source_kind={source.get('source_kind', 'unknown')}, "
                    f"content_origin={source.get('content_origin', 'unknown')}, "
                    f"fetch_status={source.get('fetch_status', 'unknown')}. "
                    f"Only sources with successful web_fetch are eligible."
                ),
            }

        url = source["url"]
        stored_hash = source.get("content_hash", "")
        quality_tier = source.get("quality_tier", "unverified")

        # URL 安全验证 (防 SSRF)
        try:
            _validate_safe_url(url)
        except ValueError as e:
            return {
                "source_id": source_id,
                "url": url,
                "status": "unreachable",
                "http_status": None,
                "content_hash_match": False,
                "quality_tier": quality_tier,
                "verification_detail": f"Invalid URL: {url} ({str(e)})",
            }

        http_status = None

        # 步骤 3: HTTP HEAD 验证 URL 可达性
        try:
            head_response = self._fetcher.head(url)
            http_status = head_response.status
            if head_response.status >= 400:
                return {
                    "source_id": source_id,
                    "url": url,
                    "status": "unreachable",
                    "http_status": head_response.status,
                    "content_hash_match": False,
                    "quality_tier": quality_tier,
                    "verification_detail": f"HTTP {head_response.status} for {url}",
                }
        except (SafeFetchError, OSError, ValueError, TimeoutError) as e:
            return {
                "source_id": source_id,
                "url": url,
                "status": "unreachable",
                "http_status": http_status,
                "content_hash_match": False,
                "quality_tier": quality_tier,
                "verification_detail": f"URL unreachable: {url} ({str(e)})",
            }
        
        # 步骤 4: 内容一致性验证 (content_hash)
        # P1-4/P2-11: 真正 GET url → 计算 hash → 对比 stored_hash
        # P2-11 修复: 无 hash 时返回 failed 而非 suspect，防止绕过
        if not stored_hash:
            return {
                "source_id": source_id,
                "url": url,
                "status": "content_mismatch",
                "http_status": http_status,
                "content_hash_match": False,
                "quality_tier": quality_tier,
                "verification_detail": f"No content_hash stored for {url}, content integrity cannot be verified",
            }
        
        try:
            get_response = self._fetcher.get(url)
            if get_response.status >= 400:
                raise SafeFetchError(f"HTTP {get_response.status} for {url}")
            fetched_content = get_response.text
            
            fetched_hash = hashlib.sha256(fetched_content.encode('utf-8')).hexdigest()[:16]
            truncation_note = " (response truncated at 512 KiB)" if get_response.truncated else ""
            
            if fetched_hash == stored_hash:
                return {
                    "status": "verified",
                    "source_id": source_id,
                    "url": url,
                    "http_status": http_status,
                    "content_hash_match": True,
                    "quality_tier": quality_tier,
                    "verification_detail": f"URL reachable and content_hash matches for {url}{truncation_note}",
                }
            else:
                return {
                    "status": "content_mismatch",
                    "source_id": source_id,
                    "url": url,
                    "http_status": http_status,
                    "content_hash_match": False,
                    "quality_tier": quality_tier,
                    "verification_detail": (
                        f"Content hash mismatch for {url}: stored={stored_hash}, fetched={fetched_hash}"
                        f"{truncation_note}"
                    ),
                }
        except (SafeFetchError, OSError, ValueError, TimeoutError) as e:
            # GET 失败但 HEAD 成功，归类为内容不一致/待复核
            return {
                "status": "content_mismatch",
                "source_id": source_id,
                "url": url,
                "http_status": http_status,
                "content_hash_match": False,
                "quality_tier": quality_tier,
                "verification_detail": f"URL reachable (HEAD OK) but GET failed for content verification: {url} ({str(e)})",
            }
    
    def verify_all(self, report_md: str) -> dict:
        """
        验证报告中所有引用。
        
        Args:
            report_md: 报告 Markdown 内容
        
        Returns:
            dict: prompt/schema 对齐后的验证摘要
        """
        # 步骤 1: 提取引用
        citation_ids = self.extract_citations(report_md)
        total_citations = len(re.findall(r'\[(\d+)\]', report_md))

        # 验证每个引用
        details = []
        counts = {"verified": 0, "unreachable": 0, "not_found": 0, "content_mismatch": 0, "ineligible_source": 0}

        for cid in citation_ids:
            result = self.verify_citation(cid)
            status = result["status"]
            if status in counts:
                counts[status] += 1

            details.append({
                "citation_id": cid,
                "source_id": result["source_id"],
                "url": result["url"],
                "status": status,
                "http_status": result["http_status"],
                "content_hash_match": result["content_hash_match"],
                "quality_tier": result["quality_tier"],
                "verification_detail": result["verification_detail"],
            })

        # P0 fix: ineligible sources are treated as failures for trust score
        trust_score = counts["verified"] / total_citations if total_citations else 0.0
        if trust_score >= 0.9:
            recommendation = "accept"
        elif trust_score >= 0.7:
            recommendation = "review"
        else:
            recommendation = "reject"

        return {
            "total_citations": total_citations,
            "unique_citations": len(citation_ids),
            "verification_summary": counts,
            "ineligible_source_count": counts.get("ineligible_source", 0),
            "citations": details,
            "trust_score": round(trust_score, 2),
            "recommendation": recommendation,
        }
