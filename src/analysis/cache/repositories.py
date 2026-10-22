"""
Redis 缓存 Repository 层 — 业务级缓存操作

提供:
- QueryCacheRepository: 热点查询结果缓存 (Hash + TTL)
- MetricCacheRepository: 指标最新值缓存
- ServiceStatsRepository: 服务 Trace 统计缓存
- RankingRepository: 实时指标排行榜 (ZSet)
- SessionContextRepository: 分析会话上下文
- DistributedLock: 分布式锁 (分析任务去重)
- WriteThroughCache: write-through 缓存失效策略

需求覆盖: REQ-007 (实时查询缓存)
验收标准: AC-1 (缓存命中率), AC-2 (Key 命名), AC-3 (分布式锁), AC-4 (连接池)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional, TypeVar, Generic

from src.analysis.cache.redis_client import (
    RedisClient,
    build_key,
    compute_query_hash,
    KEY_SEPARATOR,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ============================================================================
# 分布式锁 — Lua 脚本
# ============================================================================

# 原子释放锁 Lua 脚本: 仅当 value 匹配时才删除 key
_RELEASE_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""

# 原子续期 Lua 脚本: 仅当 value 匹配时才更新 TTL
_EXTEND_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("PEXPIRE", KEYS[1], ARGV[2])
else
    return 0
end
"""


class LockAcquireError(Exception):
    """分布式锁获取失败"""
    pass


class DistributedLock:
    """
    分布式锁 — 基于 Redis SET NX PX + Lua 原子释放。

    用于分析任务去重，确保同一分析任务不被并发执行。

    用法:
        lock = DistributedLock(client, "analysis:task:abc123")
        async with lock:
            await run_analysis_task()

    特性:
    - 自动续期: 持有期间自动刷新 TTL
    - 原子释放: 使用 Lua 脚本 compare-and-delete
    - 唯一令牌: 每次获取生成 UUID，防止误释放
    """

    def __init__(
        self,
        client: RedisClient,
        resource_key: str,
        lock_ttl_ms: int = 30000,
        auto_extend: bool = True,
        extend_interval_ms: int = 10000,
        retry_times: int = 3,
        retry_delay_ms: int = 200,
    ):
        self._client = client
        self._resource_key = resource_key
        self._lock_key = f"lock{KEY_SEPARATOR}{resource_key}"
        self._lock_ttl_ms = lock_ttl_ms
        self._auto_extend = auto_extend
        self._extend_interval_ms = extend_interval_ms
        self._retry_times = retry_times
        self._retry_delay_ms = retry_delay_ms
        self._token: Optional[str] = None
        self._extend_task: Optional[asyncio.Task] = None

    @property
    def is_locked(self) -> bool:
        return self._token is not None

    async def acquire(self) -> bool:
        """
        获取锁。使用构造时配置的重试参数。

        Returns:
            True 表示获取成功
        """
        self._token = uuid.uuid4().hex

        for attempt in range(self._retry_times):
            acquired = await self._client.set_nx_px(
                self._lock_key, self._token, self._lock_ttl_ms,
            )
            if acquired:
                logger.debug("Lock acquired: %s (attempt=%d)", self._resource_key, attempt + 1)
                if self._auto_extend:
                    self._start_extend()
                return True

            if attempt < self._retry_times - 1:
                await asyncio.sleep(self._retry_delay_ms / 1000.0)

        self._token = None
        raise LockAcquireError(
            f"Failed to acquire lock '{self._resource_key}' after {self._retry_times} attempts"
        )

    async def release(self) -> bool:
        """释放锁 (原子 compare-and-delete)"""
        if not self._token:
            return False

        self._stop_extend()
        try:
            result = await self._client.eval_lua(
                _RELEASE_LOCK_SCRIPT, 1, self._lock_key, self._token,
            )
            success = bool(result)
            if success:
                logger.debug("Lock released: %s", self._resource_key)
            else:
                logger.warning(
                    "Lock release failed (token mismatch or key expired): %s", self._resource_key,
                )
            return success
        finally:
            self._token = None

    async def extend(self) -> bool:
        """续期锁 (原子 compare-and-extend)"""
        if not self._token:
            return False

        result = await self._client.eval_lua(
            _EXTEND_LOCK_SCRIPT, 1, self._lock_key, self._token, str(self._lock_ttl_ms),
        )
        return bool(result)

    def _start_extend(self) -> None:
        """启动自动续期后台任务"""
        async def _extend_loop():
            while self._token:
                await asyncio.sleep(self._extend_interval_ms / 1000.0)
                if self._token:
                    success = await self.extend()
                    if not success:
                        logger.warning(
                            "Lock auto-extend failed (lost?): %s", self._resource_key,
                        )
                        break

        self._extend_task = asyncio.ensure_future(_extend_loop())

    def _stop_extend(self) -> None:
        """停止自动续期"""
        if self._extend_task and not self._extend_task.done():
            self._extend_task.cancel()
        self._extend_task = None

    async def __aenter__(self) -> "DistributedLock":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.release()


# ============================================================================
# 缓存策略
# ============================================================================

class CacheStrategy(Enum):
    """缓存策略枚举"""
    WRITE_THROUGH = "write_through"  # 写入时同步更新缓存
    WRITE_BEHIND = "write_behind"    # 异步更新缓存
    TTL_BASED = "ttl_based"          # 纯 TTL 过期


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    writes: int = 0
    evictions: int = 0

    @property
    def total_requests(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests

    def record_hit(self) -> None:
        self.hits += 1

    def record_miss(self) -> None:
        self.misses += 1

    def record_write(self) -> None:
        self.writes += 1

    def record_eviction(self) -> None:
        self.evictions += 1


class WriteThroughCache(Generic[T]):
    """
    Write-Through 缓存策略 — 写入时同步更新数据库和缓存。

    查询流程:
        1. 查缓存 → 命中返回
        2. 未命中 → 查数据库
        3. 回写缓存 + 设置 TTL
        4. 返回结果

    写入流程:
        1. 写数据库
        2. 更新缓存 (同步)
        3. 返回结果
    """

    def __init__(
        self,
        client: RedisClient,
        cache_key_prefix: str,
        ttl_seconds: int = 300,
    ):
        self._client = client
        self._cache_key_prefix = cache_key_prefix
        self._ttl_seconds = ttl_seconds
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        return self._stats

    def _cache_key(self, identifier: str) -> str:
        return f"{self._cache_key_prefix}{KEY_SEPARATOR}{identifier}"

    async def get(
        self, identifier: str, db_fetcher, serializer=None, deserializer=None,
    ) -> Optional[T]:
        """
        读取缓存，未命中时从数据库获取并回写。

        Args:
            identifier: 缓存键标识
            db_fetcher: async callable 从数据库获取数据
            serializer: 序列化函数 (默认 json.dumps)
            deserializer: 反序列化函数 (默认 json.loads)
        """
        _serialize = serializer or json.dumps
        _deserialize = deserializer or json.loads

        cache_key = self._cache_key(identifier)

        # 1. 查缓存
        cached = await self._client.get(cache_key)
        if cached is not None:
            self._stats.record_hit()
            try:
                return _deserialize(cached)
            except Exception:
                logger.warning("Cache deserialization failed for key: %s", cache_key)

        # 2. 缓存未命中 → 查数据库
        self._stats.record_miss()
        data = await db_fetcher()

        # 3. 回写缓存
        if data is not None:
            serialized = _serialize(data) if not isinstance(data, str) else data
            await self._client.set(cache_key, serialized, ex=self._ttl_seconds)
            self._stats.record_write()

        return data

    async def set(self, identifier: str, data: T, serializer=None) -> None:
        """Write-Through: 写入缓存"""
        _serialize = serializer or json.dumps
        cache_key = self._cache_key(identifier)
        serialized = _serialize(data) if not isinstance(data, str) else data
        await self._client.set(cache_key, serialized, ex=self._ttl_seconds)
        self._stats.record_write()

    async def invalidate(self, identifier: str) -> None:
        """失效缓存条目"""
        cache_key = self._cache_key(identifier)
        await self._client.delete(cache_key)
        self._stats.record_eviction()

    async def invalidate_pattern(self, identifier_pattern: str) -> int:
        """
        按模式失效缓存条目 (使用 SCAN，非 KEYS)。

        Args:
            identifier_pattern: 匹配模式

        Returns:
            删除的键数量
        """
        pattern = self._cache_key(identifier_pattern)
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await self._client._execute(
                lambda r, c, p: r.scan(cursor=c, match=p, count=100),
                0, pattern,
            )
            if keys:
                deleted += await self._client.delete(*keys)
            if cursor == 0:
                break
        return deleted


# ============================================================================
# 查询结果缓存 Repository
# ============================================================================

class QueryCacheRepository:
    """
    热点查询结果缓存 — 使用 String 类型存储序列化 JSON。

    缓存 Key: prod:analysis:cache:query:{query_hash}
    数据类型: String (JSON)
    默认 TTL: 300 秒

    覆盖 AC-1: 缓存命中率 ≥ 80%
    """

    def __init__(self, client: RedisClient, env: str = "prod", ttl_seconds: int = 300):
        self._client = client
        self._env = env
        self._ttl_seconds = ttl_seconds
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        return self._stats

    def _cache_key(self, query_hash: str) -> str:
        return build_key(self._env, "cache", "query", query_hash)

    async def get(self, query: str, deserializer=None) -> Optional[dict]:
        """
        获取查询缓存结果。

        Args:
            query: 原始查询语句
            deserializer: 反序列化函数 (默认 json.loads)

        Returns:
            缓存的查询结果 dict，未命中返回 None
        """
        _deserialize = deserializer or json.loads
        query_hash = compute_query_hash(query)
        cache_key = self._cache_key(query_hash)

        cached = await self._client.get(cache_key)
        if cached is not None:
            self._stats.record_hit()
            try:
                return _deserialize(cached)
            except Exception:
                logger.warning("Query cache deserialization failed: hash=%s", query_hash)
                await self._client.delete(cache_key)

        self._stats.record_miss()
        return None

    async def set(self, query: str, result: dict, ttl_seconds: Optional[int] = None,
                  serializer=None) -> None:
        """
        设置查询结果缓存。

        Args:
            query: 原始查询语句
            result: 查询结果 dict
            ttl_seconds: 覆盖默认 TTL
            serializer: 序列化函数
        """
        _serialize = serializer or json.dumps
        query_hash = compute_query_hash(query)
        cache_key = self._cache_key(query_hash)
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl_seconds

        await self._client.set(cache_key, _serialize(result), ex=ttl)
        self._stats.record_write()

    async def invalidate(self, query: str) -> None:
        """失效指定查询缓存"""
        query_hash = compute_query_hash(query)
        cache_key = self._cache_key(query_hash)
        await self._client.delete(cache_key)
        self._stats.record_eviction()

    async def exists(self, query: str) -> bool:
        """检查查询缓存是否存在"""
        query_hash = compute_query_hash(query)
        cache_key = self._cache_key(query_hash)
        return await self._client.exists(cache_key) > 0


# ============================================================================
# 指标最新值缓存 Repository
# ============================================================================

class MetricCacheRepository:
    """
    指标最新值缓存 — 使用 Hash 存储指标快照。

    缓存 Key: prod:analysis:metrics:latest:{tenant_id}:{metric_name}
    数据类型: Hash (value, timestamp, attributes)
    默认 TTL: 600 秒
    """

    def __init__(self, client: RedisClient, env: str = "prod", ttl_seconds: int = 600):
        self._client = client
        self._env = env
        self._ttl_seconds = ttl_seconds

    def _cache_key(self, tenant_id: int, metric_name: str) -> str:
        return build_key(self._env, "metrics", "latest", f"{tenant_id}{KEY_SEPARATOR}{metric_name}")

    async def set_metric(
        self, tenant_id: int, metric_name: str,
        value: float, timestamp_ms: int, attributes: dict,
    ) -> None:
        """设置指标最新值"""
        cache_key = self._cache_key(tenant_id, metric_name)
        await self._client.hset(cache_key, {
            "value": str(value),
            "timestamp": str(timestamp_ms),
            "attributes": json.dumps(attributes, ensure_ascii=False),
        })
        await self._client.expire(cache_key, self._ttl_seconds)

    async def get_metric(self, tenant_id: int, metric_name: str) -> Optional[dict]:
        """获取指标最新值"""
        cache_key = self._cache_key(tenant_id, metric_name)
        fields = await self._client.hgetall(cache_key)
        if not fields:
            return None

        try:
            return {
                "value": float(fields["value"]),
                "timestamp": int(fields["timestamp"]),
                "attributes": json.loads(fields.get("attributes", "{}")),
            }
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.warning("Metric cache deserialization failed: %s", e)
            return None

    async def invalidate(self, tenant_id: int, metric_name: str) -> None:
        """失效指标缓存"""
        cache_key = self._cache_key(tenant_id, metric_name)
        await self._client.delete(cache_key)


# ============================================================================
# 服务 Trace 统计缓存 Repository
# ============================================================================

class ServiceStatsRepository:
    """
    服务级 Trace 统计缓存 — 使用 Hash 存储。

    缓存 Key: prod:analysis:traces:svc_stats:{tenant_id}:{service_name}
    数据类型: Hash (span_count, error_count, p50_latency_ns, p99_latency_ns, updated_at)
    默认 TTL: 120 秒
    """

    def __init__(self, client: RedisClient, env: str = "prod", ttl_seconds: int = 120):
        self._client = client
        self._env = env
        self._ttl_seconds = ttl_seconds

    def _cache_key(self, tenant_id: int, service_name: str) -> str:
        return build_key(
            self._env, "traces", "svc_stats",
            f"{tenant_id}{KEY_SEPARATOR}{service_name}",
        )

    async def set_stats(
        self, tenant_id: int, service_name: str,
        span_count: int, error_count: int,
        p50_latency_ns: int, p99_latency_ns: int,
    ) -> None:
        """设置服务统计"""
        cache_key = self._cache_key(tenant_id, service_name)
        await self._client.hset(cache_key, {
            "span_count": str(span_count),
            "error_count": str(error_count),
            "p50_latency_ns": str(p50_latency_ns),
            "p99_latency_ns": str(p99_latency_ns),
            "updated_at": str(int(time.time() * 1000)),
        })
        await self._client.expire(cache_key, self._ttl_seconds)

    async def get_stats(self, tenant_id: int, service_name: str) -> Optional[dict]:
        """获取服务统计"""
        cache_key = self._cache_key(tenant_id, service_name)
        fields = await self._client.hgetall(cache_key)
        if not fields:
            return None

        try:
            return {
                "span_count": int(fields["span_count"]),
                "error_count": int(fields["error_count"]),
                "p50_latency_ns": int(fields["p50_latency_ns"]),
                "p99_latency_ns": int(fields["p99_latency_ns"]),
                "updated_at": int(fields.get("updated_at", "0")),
                "error_rate": (
                    int(fields["error_count"]) / int(fields["span_count"])
                    if int(fields["span_count"]) > 0 else 0.0
                ),
            }
        except (KeyError, ValueError) as e:
            logger.warning("Service stats deserialization failed: %s", e)
            return None

    async def invalidate(self, tenant_id: int, service_name: str) -> None:
        """失效服务统计缓存"""
        cache_key = self._cache_key(tenant_id, service_name)
        await self._client.delete(cache_key)


# ============================================================================
# 实时排行榜 Repository (ZSet)
# ============================================================================

class RankingRepository:
    """
    实时指标排行榜 — 使用 ZSet 存储。

    缓存 Key: prod:analysis:ranking:services:{tenant_id}:{metric}
    数据类型: ZSet (score=排名指标值, member=service_name)
    默认 TTL: 300 秒

    支持:
    - 按错误率/延迟/请求量排序
    - 获取 Top N
    - 获取指定服务排名
    - 获取服务周边排名
    - 原子增量更新 (ZINCRBY)
    """

    # 支持的排名指标
    VALID_METRICS = ("error_rate", "latency_p99", "request_count", "error_count")

    def __init__(self, client: RedisClient, env: str = "prod", ttl_seconds: int = 300):
        self._client = client
        self._env = env
        self._ttl_seconds = ttl_seconds

    def _cache_key(self, tenant_id: int, metric: str) -> str:
        if metric not in self.VALID_METRICS:
            raise ValueError(f"Invalid metric '{metric}'. Must be one of {self.VALID_METRICS}")
        return build_key(
            self._env, "ranking", "services",
            f"{tenant_id}{KEY_SEPARATOR}{metric}",
        )

    async def set_score(self, tenant_id: int, metric: str,
                        service_name: str, score: float) -> None:
        """设置/更新服务排名分数"""
        cache_key = self._cache_key(tenant_id, metric)
        await self._client.zadd(cache_key, {service_name: score})
        await self._client.expire(cache_key, self._ttl_seconds)

    async def increment_score(self, tenant_id: int, metric: str,
                              service_name: str, delta: float) -> float:
        """原子增量更新排名分数"""
        cache_key = self._cache_key(tenant_id, metric)
        new_score = await self._client.zincrby(cache_key, delta, service_name)
        await self._client.expire(cache_key, self._ttl_seconds)
        return new_score

    async def get_score(self, tenant_id: int, metric: str,
                        service_name: str) -> Optional[float]:
        """获取服务排名分数"""
        cache_key = self._cache_key(tenant_id, metric)
        return await self._client.zscore(cache_key, service_name)

    async def get_rank(self, tenant_id: int, metric: str,
                       service_name: str) -> Optional[int]:
        """
        获取服务排名 (1-based, 1=最高分)。

        Returns:
            None 如果服务不在排行榜中
        """
        cache_key = self._cache_key(tenant_id, metric)
        rank_0 = await self._client.zrevrank(cache_key, service_name)
        if rank_0 is None:
            return None
        return rank_0 + 1

    async def get_top_n(self, tenant_id: int, metric: str,
                        n: int = 10) -> list[dict]:
        """
        获取 Top N 排名。

        Returns:
            [{"rank": 1, "service_name": "svc-a", "score": 99.5}, ...]
        """
        cache_key = self._cache_key(tenant_id, metric)
        results = await self._client.zrevrange(cache_key, 0, n - 1, withscores=True)

        return [
            {"rank": i + 1, "service_name": member, "score": round(score, 4)}
            for i, (member, score) in enumerate(results)
        ]

    async def get_around(self, tenant_id: int, metric: str,
                         service_name: str, radius: int = 2) -> list[dict]:
        """
        获取指定服务周边排名。

        Returns:
            包含目标服务及其上下 radius 个邻居的排名列表
        """
        cache_key = self._cache_key(tenant_id, metric)
        rank_0 = await self._client.zrevrank(cache_key, service_name)
        if rank_0 is None:
            return []

        start = max(0, rank_0 - radius)
        end = rank_0 + radius
        results = await self._client.zrevrange(cache_key, start, end, withscores=True)

        return [
            {"rank": start + i + 1, "service_name": member, "score": round(score, 4)}
            for i, (member, score) in enumerate(results)
        ]

    async def get_size(self, tenant_id: int, metric: str) -> int:
        """获取排行榜条目数"""
        cache_key = self._cache_key(tenant_id, metric)
        return await self._client.zcard(cache_key)

    async def remove(self, tenant_id: int, metric: str,
                     service_name: str) -> int:
        """移除服务排名"""
        cache_key = self._cache_key(tenant_id, metric)
        return await self._client.zrem(cache_key, service_name)

    async def trim(self, tenant_id: int, metric: str,
                   max_size: int = 1000) -> int:
        """
        裁剪排行榜，仅保留 Top N。

        Returns:
            移除的条目数量
        """
        cache_key = self._cache_key(tenant_id, metric)
        return await self._client.zremrangebyrank(cache_key, 0, -(max_size + 1))

    async def batch_set_scores(self, tenant_id: int, metric: str,
                               scores: dict[str, float]) -> None:
        """批量设置排名分数 (使用 Pipeline)"""
        cache_key = self._cache_key(tenant_id, metric)
        pipe = await self._client.pipeline()
        pipe.zadd(cache_key, scores)
        pipe.expire(cache_key, self._ttl_seconds)
        await pipe.execute()

    async def clear(self, tenant_id: int, metric: str) -> None:
        """清空排行榜"""
        cache_key = self._cache_key(tenant_id, metric)
        await self._client.delete(cache_key)


# ============================================================================
# 会话上下文 Repository
# ============================================================================

class SessionContextRepository:
    """
    分析会话上下文 — 使用 Hash 存储当前筛选条件与时间范围。

    缓存 Key: prod:analysis:session:{session_id}:context
    数据类型: Hash (tenant_id, time_range_start, time_range_end, filters, created_at)
    默认 TTL: 3600 秒
    """

    def __init__(self, client: RedisClient, env: str = "prod", ttl_seconds: int = 3600):
        self._client = client
        self._env = env
        self._ttl_seconds = ttl_seconds

    def _cache_key(self, session_id: str) -> str:
        return build_key(self._env, "session", self._context, f"{session_id}{KEY_SEPARATOR}context")

    @property
    def _context(self) -> str:
        return "context"

    def _cache_key_v2(self, session_id: str) -> str:
        return build_key(self._env, "session", session_id, "context")

    async def save(self, session_id: str, tenant_id: int,
                   time_range_start: int, time_range_end: int,
                   filters: dict) -> None:
        """保存会话上下文"""
        cache_key = self._cache_key_v2(session_id)
        await self._client.hset(cache_key, {
            "tenant_id": str(tenant_id),
            "time_range_start": str(time_range_start),
            "time_range_end": str(time_range_end),
            "filters": json.dumps(filters, ensure_ascii=False),
            "created_at": str(int(time.time() * 1000)),
        })
        await self._client.expire(cache_key, self._ttl_seconds)

    async def load(self, session_id: str) -> Optional[dict]:
        """加载会话上下文"""
        cache_key = self._cache_key_v2(session_id)
        fields = await self._client.hgetall(cache_key)
        if not fields:
            return None

        try:
            return {
                "tenant_id": int(fields["tenant_id"]),
                "time_range_start": int(fields["time_range_start"]),
                "time_range_end": int(fields["time_range_end"]),
                "filters": json.loads(fields.get("filters", "{}")),
                "created_at": int(fields.get("created_at", "0")),
            }
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.warning("Session context deserialization failed: %s", e)
            return None

    async def delete(self, session_id: str) -> None:
        """删除会话上下文"""
        cache_key = self._cache_key_v2(session_id)
        await self._client.delete(cache_key)

    async def refresh_ttl(self, session_id: str) -> None:
        """刷新会话 TTL"""
        cache_key = self._cache_key_v2(session_id)
        await self._client.expire(cache_key, self._ttl_seconds)
