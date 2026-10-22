"""
Redis 缓存层 — 智能分析模块实时查询加速

覆盖:
- Redis 客户端连接池与熔断配置
- Key 命名规范 (ns:module:entity:id)
- 热点查询结果缓存 (Hash + TTL)
- 实时指标排行榜 (ZSet)
- 分布式锁 (分析任务去重)
- 缓存失效策略 (write-through + TTL)

依赖: REQ-007 (实时查询缓存)
"""

from src.analysis.cache.redis_client import (
    RedisClient,
    RedisClientConfig,
    CircuitBreaker,
    CircuitState,
    build_key,
    validate_key,
    KEY_SEPARATOR,
    KEY_ENV_VALUES,
    KEY_SERVICE,
)
from src.analysis.cache.repositories import (
    QueryCacheRepository,
    MetricCacheRepository,
    ServiceStatsRepository,
    RankingRepository,
    SessionContextRepository,
    DistributedLock,
    CacheStrategy,
    WriteThroughCache,
)

__all__ = [
    "RedisClient",
    "RedisClientConfig",
    "CircuitBreaker",
    "CircuitState",
    "build_key",
    "validate_key",
    "KEY_SEPARATOR",
    "KEY_ENV_VALUES",
    "KEY_SERVICE",
    "QueryCacheRepository",
    "MetricCacheRepository",
    "ServiceStatsRepository",
    "RankingRepository",
    "SessionContextRepository",
    "DistributedLock",
    "CacheStrategy",
    "WriteThroughCache",
]
