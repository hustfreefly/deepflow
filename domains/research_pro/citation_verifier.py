"""
CitationVerifier — ResearchPro 引用验证器
契约: cage/research_pro_v1.0.yaml (L1: citation_verifier, RED-DC-001, RED-DC-005)

五步验证循环:
1. 正则提取 [N] 引用标记
2. 映射引用编号到 source_registry
3. HTTP HEAD 验证 URL 可达性
4. 内容一致性验证 (content_hash)
5. 验证失败处理

所有引用必须来自 Source Registry (RED-DC-001)。
报告生成前必须执行引用验证循环 (RED-DC-005)。
"""

import re
import json
import hashlib
import hashlib
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# RED-DC-001: 引用必须来自 source_registry
from domains.research_pro.source_registry import SourceRegistry


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
        步骤 3: HTTP HEAD 验证 URL 可达性
        步骤 4: 内容一致性验证 (content_hash)
        步骤 5: 验证失败处理
        
        Args:
            source_id: 引用编号 (对应 source_registry 中的 id)
        
        Returns:
            dict: {status: 'verified'|'failed'|'suspect', detail: str}
        """
        # 步骤 2: 映射引用编号到 source_registry
        source = self.source_registry.get(source_id)
        if source is None:
            return {"status": "failed", "detail": f"Source ID {source_id} not found in registry"}
        
        url = source["url"]
        stored_hash = source.get("content_hash", "")
        
        # URL 协议验证 (防 SSRF)
        if not url.startswith(("http://", "https://")):
            return {"status": "failed", "detail": f"Invalid URL protocol: {url}"}
        
        # 步骤 3: HTTP HEAD 验证 URL 可达性
        try:
            req = Request(url, method='HEAD')
            req.add_header('User-Agent', 'ResearchPro/1.0')
            with urlopen(req, timeout=10) as response:
                if response.status >= 400:
                    return {
                        "status": "failed",
                        "detail": f"HTTP {response.status} for {url}"
                    }
        except (URLError, HTTPError, OSError, ValueError, TimeoutError) as e:
            return {
                "status": "failed",
                "detail": f"URL unreachable: {url} ({str(e)})"
            }
        
        # 步骤 4: 内容一致性验证 (content_hash)
        # P1-4/P2-11: 真正 GET url → 计算 hash → 对比 stored_hash
        # P2-11 修复: 无 hash 时返回 failed 而非 suspect，防止绕过
        if not stored_hash:
            return {
                "status": "failed",
                "detail": f"No content_hash stored for {url}, content integrity cannot be verified"
            }
        
        try:
            req = Request(url, method='GET')
            req.add_header('User-Agent', 'ResearchPro/1.0')
            with urlopen(req, timeout=15) as response:
                fetched_content = response.read().decode('utf-8', errors='replace')
            
            fetched_hash = hashlib.sha256(fetched_content.encode('utf-8')).hexdigest()[:16]
            
            if fetched_hash == stored_hash:
                return {
                    "status": "verified",
                    "detail": f"URL reachable and content_hash matches for {url}"
                }
            else:
                return {
                    "status": "suspect",
                    "detail": f"Content hash mismatch for {url}: stored={stored_hash}, fetched={fetched_hash}"
                }
        except (URLError, HTTPError, OSError, ValueError, TimeoutError) as e:
            # GET 失败但 HEAD 成功，降级为 suspect
            return {
                "status": "suspect",
                "detail": f"URL reachable (HEAD OK) but GET failed for content verification: {url} ({str(e)})"
            }
    
    def verify_all(self, report_md: str) -> dict:
        """
        验证报告中所有引用。
        
        Args:
            report_md: 报告 Markdown 内容
        
        Returns:
            dict: {
                verified: int,
                failed: int,
                suspect: int,
                details: list[dict {citation_id, source_id, status, detail}]
            }
        """
        # 步骤 1: 提取引用
        citation_ids = self.extract_citations(report_md)
        
        # 验证每个引用
        details = []
        counts = {"verified": 0, "failed": 0, "suspect": 0}
        
        for cid in citation_ids:
            result = self.verify_citation(cid)
            status = result["status"]
            counts[status] += 1
            
            details.append({
                "citation_id": cid,
                "source_id": cid,
                "status": status,
                "detail": result["detail"]
            })
        
        return {
            "verified": counts["verified"],
            "failed": counts["failed"],
            "suspect": counts["suspect"],
            "details": details
        }
