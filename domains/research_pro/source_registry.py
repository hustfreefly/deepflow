"""
SourceRegistry — ResearchPro 防幻觉核心
契约: cage/active/research_pro_v1.0.yaml (L3: source_registry)

所有引用必须来自 Source Registry, 禁止自由生成 URL (RED-DC-001)。
"""

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import os
import hashlib
import threading
import copy
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

from typing import Optional

# URL 安全验证从 url_utils 导入（解决 safe_fetcher ↔ source_registry 循环导入）
from domains.research_pro.url_utils import validate_safe_url as _validate_safe_url

SUMMARY_MAX_LENGTH = 200


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
        self._sources: list[dict] = []
        self._lock = threading.RLock()
        
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r', encoding='utf-8') as f:
                    self._sources = json.load(f)
            except json.JSONDecodeError:
                self._backup_corrupt_registry()
                self._sources = []
            except OSError:
                self._sources = []

    @property
    def sources(self) -> list[dict]:
        """返回所有来源的深拷贝，避免调用方修改内部状态。"""
        with self._lock:
            return copy.deepcopy(self._sources)
    
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
        parsed, canonical_url = _validate_safe_url(url)
        
        # 计算 content_hash (sha256 前 16 位)
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

        with self._lock:
            for source in self._sources:
                try:
                    _, existing_canonical_url = _validate_safe_url(source.get("url", ""))
                except ValueError:
                    continue
                if existing_canonical_url == canonical_url and source.get("content_hash") == content_hash:
                    return source["id"]

            source_id = (max((source["id"] for source in self._sources), default=0) + 1)
            entry = {
                "id": source_id,
                "url": url,
                "fetched_at": datetime.now().isoformat(),
                "content_hash": content_hash,
                "title": title,
                "domain": parsed.hostname or "",
                "quality_tier": quality_tier,
                "summary": summary[:SUMMARY_MAX_LENGTH] if summary else "",
                "verification_status": "pending",
                "verification_detail": None,
            }

            self._sources.append(entry)
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
        with self._lock:
            for source in self._sources:
                if source["id"] == source_id:
                    return copy.deepcopy(source)
        return None
    
    def verify_all(self) -> dict:
        """
        统计所有来源的验证状态。
        
        Returns:
            dict: {verified: int, failed: int, suspect: int}
        """
        counts = {"verified": 0, "failed": 0, "suspect": 0}
        
        with self._lock:
            for source in self._sources:
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
        with self._lock:
            return json.dumps(copy.deepcopy(self._sources), ensure_ascii=False, indent=2)
    
    def _save(self) -> None:
        """保存 Registry 到文件 (原子写入)。"""
        with self._lock:
            tmp_path = self.registry_path + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self._sources, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.registry_path)

    def _backup_corrupt_registry(self) -> None:
        """损坏 JSON 备份为 source_registry.json.corrupt.{timestamp}。"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = f"{self.registry_path}.corrupt.{timestamp}"
        try:
            os.replace(self.registry_path, backup_path)
        except OSError as e:
            logger.debug(f"registry backup: {e}")
