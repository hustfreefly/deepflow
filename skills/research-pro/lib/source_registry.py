"""
SourceRegistry — ResearchPro 防幻觉核心
契约: cage/research_pro_v1.0.yaml (L3: source_registry)

所有引用必须来自 Source Registry, 禁止自由生成 URL (RED-DC-001)。
"""

import json
import os
import hashlib
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse


class SourceRegistry:
    """
    管理所有抓取页面的登记、验证和引用映射。
    
    契约约束:
    - 报告生成时只能从此 Registry 选取引用源 (RED-DC-001)
    - 每个条目必须包含完整 schema (L3: source_registry.item_schema)
    """
    
    def __init__(self, registry_path: str) -> None:
        """
        初始化 SourceRegistry。
        
        Args:
            registry_path: source_registry.json 文件路径
        """
        self.registry_path = registry_path
        self.sources: list[dict] = []
        
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r', encoding='utf-8') as f:
                    self.sources = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.sources = []
    
    def register(
        self,
        url: str,
        title: str,
        content: str,
        quality_tier: str,
        summary: str = ""
    ) -> int:
        """
        登记新来源。
        
        Args:
            url: 来源 URL (必须为合法 URL)
            title: 页面标题
            content: 页面内容 (用于计算 content_hash)
            quality_tier: 质量等级 (tier_1|tier_2|tier_3|unverified)
            summary: 内容摘要 (≤200字)
        
        Returns:
            source_id: 分配的 ID (顺序递增, 从 1 开始)
        
        Raises:
            ValueError: URL 格式非法或协议不是 http/https
        """
        # P1-5: URL scheme 校验 (CWE-918: 防止 SSRF)
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            raise ValueError(f"非法 URL 协议: {parsed.scheme}, 仅支持 http/https")
        if not parsed.netloc:
            raise ValueError(f"非法 URL: 缺少域名")
        
        # 计算 content_hash (sha256 前 16 位)
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
        
        # 提取 domain
        domain = parsed.netloc
        
        # 分配 ID
        source_id = len(self.sources) + 1
        
        entry = {
            "id": source_id,
            "url": url,
            "fetched_at": datetime.now().isoformat(),
            "content_hash": content_hash,
            "title": title,
            "domain": domain,
            "quality_tier": quality_tier,
            "summary": summary[:200] if summary else "",
            "verification_status": "pending",
            "verification_detail": None
        }
        
        self.sources.append(entry)
        self._save()
        
        return source_id
    
    def get(self, source_id: int) -> Optional[dict]:
        """
        获取指定 source_id 的条目。
        
        Args:
            source_id: 来源 ID
        
        Returns:
            来源条目 dict, 或 None (不存在时)
        """
        for source in self.sources:
            if source["id"] == source_id:
                return source
        return None
    
    def verify_all(self) -> dict:
        """
        统计所有来源的验证状态。
        
        Returns:
            dict: {verified: int, failed: int, suspect: int}
        """
        counts = {"verified": 0, "failed": 0, "suspect": 0}
        
        for source in self.sources:
            status = source.get("verification_status", "pending")
            if status in counts:
                counts[status] += 1
        
        return counts
    
    def to_json(self) -> str:
        """
        导出 Registry 为 JSON 字符串。
        
        Returns:
            JSON 字符串
        """
        return json.dumps(self.sources, ensure_ascii=False, indent=2)
    
    def _save(self) -> None:
        """保存 Registry 到文件 (原子写入)。"""
        tmp_path = self.registry_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(self.sources, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.registry_path)
