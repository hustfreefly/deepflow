"""
TierClassifier — ResearchPro 三层质量排序
契约: cage/active/research_pro_v1.0.yaml (L3: source_registry.quality_tier, RED-DC-006)

Tier 1 (官方/学术) 来源必须优先于 Tier 3 (社区/论坛) (RED-DC-006)。
"""

import json
import os
from pathlib import Path
from urllib.parse import urlparse


# RED-DC-006: Tier 1 weight 1.0, Tier 3 weight 0.4
TIER_WEIGHTS = {
    "tier_1": 1.0,   # 官方/学术
    "tier_2": 0.7,   # 权威媒体
    "tier_3": 0.4,   # 社区/论坛
    "unverified": 0.5,
}


class TierClassifier:
    """
    三层质量排序分类器。

    契约约束:
    - Tier 1 (官方/学术) 权重 1.0 (RED-DC-006)
    - Tier 3 (社区/论坛) 权重 0.4 (RED-DC-006)
    - 未知域名默认使用配置 default_tier
    """

    def __init__(self, config_path: str = "") -> None:
        """
        初始化 TierClassifier。

        Args:
            config_path: tier_domains.json 路径 (可选, 默认内置)
        """
        self._domains: dict[str, str] = {}
        self._blacklist: set[str] = set()
        self._default_tier = "tier_3"
        self._weights = dict(TIER_WEIGHTS)
        self._load_config(config_path)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """只保留 hostname，丢弃 scheme/path/query。"""
        candidate = (domain or "").strip().lower()
        if not candidate:
            return ""
        if "://" in candidate:
            parsed = urlparse(candidate)
            return (parsed.hostname or "").lower()
        candidate = candidate.split("/", 1)[0]
        candidate = candidate.split("?", 1)[0]
        candidate = candidate.split("#", 1)[0]
        return candidate.strip(".")

    def _load_config(self, config_path: str) -> None:
        """加载域名分类配置。"""
        resolved_config_path = config_path or str(Path(__file__).resolve().parent / "config" / "tier_domains.json")
        cfg = None
        if os.path.exists(resolved_config_path):
            try:
                with open(resolved_config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            except (json.JSONDecodeError, OSError):
                cfg = self._bundled_config()
        else:
            cfg = self._bundled_config()

        self._default_tier = cfg.get("default_tier", self._default_tier)
        blacklist = cfg.get("blacklist", {})
        for domain in blacklist.get("domains", []) if isinstance(blacklist, dict) else []:
            normalized = self._normalize_domain(domain)
            if normalized:
                self._blacklist.add(normalized)

        for tier_key in ["tier_1", "tier_2", "tier_3"]:
            tier_cfg = cfg.get(tier_key, {})
            if "weight" in tier_cfg:
                self._weights[tier_key] = float(tier_cfg["weight"])
            for domain in tier_cfg.get("domains", []):
                normalized = self._normalize_domain(domain)
                if normalized and normalized not in self._domains:
                    self._domains[normalized] = tier_key

    @staticmethod
    def _bundled_config() -> dict:
        """内置默认分类，用于配置文件缺失或损坏时回退。"""
        bundled_path = Path(__file__).resolve().parent / "config" / "tier_domains.json"
        try:
            with open(bundled_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {
                "tier_1": {
                    "weight": 1.0,
                    "domains": [
                        "sec.gov", "cninfo.com.cn", "sse.com.cn", "szse.cn",
                        "gov.cn", "arxiv.org", "nature.com", "pbc.gov.cn",
                        "stats.gov.cn", "who.int",
                    ],
                },
                "tier_2": {
                    "weight": 0.7,
                    "domains": [
                        "reuters.com", "bloomberg.com", "ft.com",
                        "finance.sina.com.cn", "caixin.com", "36kr.com",
                        "bbc.com", "cnbc.com", "wallstreetcn.com", "cls.cn",
                    ],
                },
                "tier_3": {
                    "weight": 0.4,
                    "domains": [
                        "xueqiu.com", "reddit.com", "weibo.com", "zhihu.com",
                        "eastmoney.com", "seekingalpha.com",
                    ],
                },
                "blacklist": {"domains": []},
                "default_tier": "tier_3",
            }

    def classify(self, domain: str) -> str:
        """
        分类域名。

        Args:
            domain: 域名字符串

        Returns:
            str: tier_1 | tier_2 | tier_3 | unverified
        """
        domain = self._normalize_domain(domain)
        if not domain:
            return "unverified"

        for blocked_domain in sorted(
            self._blacklist,
            key=lambda item: item.count("."),
            reverse=True,
        ):
            if domain == blocked_domain or domain.endswith(f".{blocked_domain}"):
                return "unverified"

        # 精确匹配
        if domain in self._domains:
            return self._domains[domain]

        # 子域名匹配。更具体的域名优先，避免 eastmoney.com 覆盖 guba.eastmoney.com。
        for registered_domain, tier in sorted(
            self._domains.items(),
            key=lambda item: item[0].count("."),
            reverse=True,
        ):
            if domain.endswith(f".{registered_domain}"):
                return tier

        return self._default_tier

    def get_weight(self, tier: str) -> float:
        """
        获取 Tier 权重。

        Args:
            tier: tier 名称

        Returns:
            float: 1.0 | 0.7 | 0.4
        """
        # RED-DC-006: tier_1 weight 1.0, tier_3 weight 0.4 by default.
        return self._weights.get(tier, 0.5)
