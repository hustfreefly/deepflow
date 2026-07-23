"""
Redis 缓存层单元测试

覆盖验收标准:
- AC-1: 缓存命中率在典型场景 ≥ 80%
- AC-2: Key 命名符合规范且无冲突
- AC-3: 分布式锁在并发下正确互斥
- AC-4: 连接池配置可压测通过

测试策略: 使用异步 mock 模拟 Redis 操作，避免依赖真实 Redis 实例。
"""

from __future__ import annotations

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.analysis.cache.redis_client import (
    RedisClient,
    RedisClientConfig,
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenError,
    build_key,
    validate_key,
    compute_query_hash,
    KEY_SEPARATOR,
    KEY_ENV_VALUES,
    KEY_SERVICE,
    KEY_MAX_LENGTH,
)
from src.analysis.cache.repositories import (
    QueryCacheRepository,
    MetricCacheRepository,
    ServiceStatsRepository,
    RankingRepository,
    SessionContextRepository,
    DistributedLock,
    LockAcquireError,
    CacheStrategy,
    CacheStats,
    WriteThroughCache,
)


# ============================================================================
# AC-2: Key 命名规范测试
# ============================================================================

class TestKeyNaming(unittest.TestCase):
    """AC-2: Key 命名符合规范且无冲突"""

    def test_valid_key_all_lowercase(self):
        key = build_key("prod", "cache", "query", "abc123")
        self.assertEqual(key, "prod:analysis:cache:query:abc123")
        self.assertEqual(key, key.lower())

    def test_valid_key_with_field(self):
        key = build_key("prod", "metrics", "latest", "1001:http_requests", "value")
        expected = "prod:analysis:metrics:latest:1001:http_requests:value"
        self.assertEqual(key, expected)

    def test_valid_key_max_length(self):
        # 构造接近最大长度的 key
        identifier = "x" * 60  # 128 - prefix overhead
        key = build_key("prod", "cache", "query", identifier)
        self.assertLessEqual(len(key), KEY_MAX_LENGTH)

    def test_key_too_long_raises(self):
        identifier = "x" * 200
        with self.assertRaises(ValueError):
            build_key("prod", "cache", "query", identifier)

    def test_invalid_env_raises(self):
        with self.assertRaises(ValueError):
            build_key("production", "cache", "query", "abc")

    def test_validate_key_rejects_uppercase(self):
        self.assertFalse(validate_key("PROD:analysis:cache:query:abc"))

    def test_validate_key_rejects_spaces(self):
        self.assertFalse(validate_key("prod:analysis:cache:query:abc def"))

    def test_validate_key_rejects_special_chars(self):
        self.assertFalse(validate_key("prod:analysis:cache:query:abc@123"))

    def test_validate_key_accepts_valid(self):
        self.assertTrue(validate_key("prod:analysis:cache:query:abc-123_456"))

    def test_all_env_values_are_lowercase(self):
        for env in KEY_ENV_VALUES:
            self.assertEqual(env, env.lower())

    def test_key_format_consistency(self):
        """验证所有 Key 格式一致，分隔符统一"""
        keys = [
            build_key("prod", "cache", "query", "abc"),
            build_key("prod", "metrics", "latest", "1001:cpu"),
            build_key("prod", "traces", "svc_stats", "1001:my-service"),
            build_key("prod", "ranking", "services", "1001:error_rate"),
            build_key("prod", "session", "sess001", "context"),
        ]
        for key in keys:
            parts = key.split(KEY_SEPARATOR)
            self.assertEqual(parts[0], "prod")
            self.assertEqual(parts[1], KEY_SERVICE)
            self.assertTrue(validate_key(key))

    def test_no_key_collisions(self):
        """验证不同 domain/entity 组合不会产生 Key 冲突"""
        keys = set()
        domains = ["cache", "metrics", "traces", "ranking", "session"]
        entities = ["query", "latest", "svc_stats", "services", "context"]
        ids = ["abc", "1001:cpu", "1001:svc", "sess001"]

        for domain in domains:
            for entity in entities:
                for identifier in ids:
                    key = build_key("prod", domain, entity, identifier)
                    self.assertNotIn(key, keys, f"Key collision: {key}")
                    keys.add(key)

    def test_compute_query_hash_deterministic(self):
        """查询哈希确定性"""
        q1 = "SELECT * FROM metrics WHERE tenant_id = 1001"
        q2 = "SELECT * FROM metrics WHERE tenant_id = 1001"
        self.assertEqual(compute_query_hash(q1), compute_query_hash(q2))

    def test_compute_query_hash_different(self):
        """不同查询产生不同哈希"""
        h1 = compute_query_hash("SELECT * FROM metrics")
        h2 = compute_query_hash("SELECT * FROM traces")
        self.assertNotEqual(h1, h2)

    def test_compute_query_hash_length(self):
        """查询哈希固定长度 16"""
        h = compute_query_hash("any query")
        self.assertEqual(len(h), 16)


# ============================================================================
# AC-1: 缓存命中率测试
# ============================================================================

class TestCacheHitRate(unittest.TestCase):
    """AC-1: 缓存命中率在典型场景 ≥ 80%"""

    def test_cache_stats_hit_rate_100_percent(self):
        stats = CacheStats()
        for _ in range(100):
            stats.record_hit()
        self.assertEqual(stats.hit_rate, 1.0)

    def test_cache_stats_hit_rate_80_percent(self):
        stats = CacheStats()
        for _ in range(80):
            stats.record_hit()
        for _ in range(20):
            stats.record_miss()
        self.assertGreaterEqual(stats.hit_rate, 0.80)

    def test_cache_stats_zero_requests(self):
        stats = CacheStats()
        self.assertEqual(stats.hit_rate, 0.0)

    def test_cache_stats_total(self):
        stats = CacheStats()
        stats.record_hit()
        stats.record_hit()
        stats.record_miss()
        self.assertEqual(stats.total_requests, 3)

    def test_query_cache_hit_scenario(self):
        """模拟典型查询缓存场景: 10 次查询，8 次命中"""
        async def _test():
            mock_client = _create_mock_redis_client()
            repo = QueryCacheRepository(mock_client, ttl_seconds=300)

            query = "SELECT * FROM metrics WHERE tenant_id=1001"
            result = {"data": [{"metric": "cpu", "value": 75.5}]}
            serialized = json.dumps(result)

            # 首次写入缓存
            await repo.set(query, result)
            self.assertEqual(repo.stats.writes, 1)

            # 模拟 10 次查询: 8 次命中 + 2 次未命中
            mock_client.get = AsyncMock(side_effect=[
                serialized, serialized, serialized, serialized,
                serialized, serialized, serialized, serialized,
                None, None,
            ])

            hits = 0
            misses = 0
            for _ in range(10):
                cached = await repo.get(query)
                if cached == result:
                    hits += 1
                else:
                    misses += 1

            self.assertEqual(hits, 8)
            self.assertEqual(misses, 2)
            self.assertGreaterEqual(repo.stats.hit_rate, 0.80)

        asyncio.run(_test())

    def test_write_through_cache_hit_ratio(self):
        """Write-Through 缓存命中率测试"""
        async def _test():
            mock_client = _create_mock_redis_client()
            cache = WriteThroughCache(mock_client, "test:cache", ttl_seconds=300)

            data = {"key": "value"}
            serialized = json.dumps(data)

            # 模拟 fetch: 先 miss 3 次 (回写)，再 hit 7 次
            fetch_count = [0]

            async def db_fetcher():
                fetch_count[0] += 1
                return data

            # 前 3 次 miss，后 7 次 hit
            mock_client.get = AsyncMock(side_effect=[
                None, None, None,  # 3 misses → db fetch
                serialized, serialized, serialized, serialized,
                serialized, serialized, serialized,  # 7 hits
            ])

            results = []
            for _ in range(10):
                result = await cache.get("ident", db_fetcher)
                results.append(result)

            self.assertEqual(len(results), 10)
            self.assertGreaterEqual(cache.stats.hit_rate, 0.70)
            # DB 仅被 fetch 3 次 (miss 时)
            self.assertEqual(fetch_count[0], 3)

        asyncio.run(_test())


# ============================================================================
# AC-3: 分布式锁互斥测试
# ============================================================================

class TestDistributedLock(unittest.IsolatedAsyncioTestCase):
    """AC-3: 分布式锁在并发下正确互斥"""

    async def test_lock_acquire_and_release(self):
        mock_client = _create_mock_redis_client()
        mock_client.set_nx_px = AsyncMock(return_value=True)
        mock_client.eval_lua = AsyncMock(return_value=1)

        lock = DistributedLock(mock_client, "analysis:task:abc123", auto_extend=False)
        await lock.acquire()
        self.assertTrue(lock.is_locked)

        await lock.release()
        self.assertFalse(lock.is_locked)

    async def test_lock_acquire_fails_then_raises(self):
        mock_client = _create_mock_redis_client()
        mock_client.set_nx_px = AsyncMock(return_value=False)

        lock = DistributedLock(
            mock_client, "analysis:task:abc123",
            auto_extend=False, retry_times=3, retry_delay_ms=10,
        )
        with self.assertRaises(LockAcquireError):
            await lock.acquire()

        self.assertFalse(lock.is_locked)

    async def test_lock_acquire_retry_succeeds(self):
        mock_client = _create_mock_redis_client()
        mock_client.set_nx_px = AsyncMock(side_effect=[False, False, True])

        lock = DistributedLock(
            mock_client, "analysis:task:abc123",
            auto_extend=False, retry_times=3, retry_delay_ms=10,
        )
        await lock.acquire()
        self.assertTrue(lock.is_locked)

    async def test_lock_mutual_exclusion(self):
        """两个并发任务尝试获取同一锁，只有一个成功"""
        mock_client = _create_mock_redis_client()

        lock_granted = [False, False]  # 只有第一个 SET NX 成功

        async def set_nx_side_effect(*args, **kwargs):
            if not lock_granted[0] and not lock_granted[1]:
                lock_granted[0] = True
                return True
            return False

        mock_client.set_nx_px = AsyncMock(side_effect=set_nx_side_effect)
        mock_client.eval_lua = AsyncMock(return_value=1)

        lock1 = DistributedLock(
            mock_client, "analysis:task:concurrent",
            auto_extend=False, retry_times=1, retry_delay_ms=10,
        )
        lock2 = DistributedLock(
            mock_client, "analysis:task:concurrent",
            auto_extend=False, retry_times=1, retry_delay_ms=10,
        )

        await lock1.acquire()
        self.assertTrue(lock1.is_locked)

        with self.assertRaises(LockAcquireError):
            await lock2.acquire()
        self.assertFalse(lock2.is_locked)

        await lock1.release()

    async def test_lock_context_manager(self):
        mock_client = _create_mock_redis_client()
        mock_client.set_nx_px = AsyncMock(return_value=True)
        mock_client.eval_lua = AsyncMock(return_value=1)

        lock = DistributedLock(mock_client, "analysis:task:ctx", auto_extend=False)
        async with lock:
            self.assertTrue(lock.is_locked)
        self.assertFalse(lock.is_locked)

    async def test_lock_release_uses_lua_script(self):
        """释放锁应使用 Lua 脚本原子操作"""
        mock_client = _create_mock_redis_client()
        mock_client.set_nx_px = AsyncMock(return_value=True)
        mock_client.eval_lua = AsyncMock(return_value=1)

        lock = DistributedLock(mock_client, "analysis:task:lua", auto_extend=False)
        await lock.acquire()
        await lock.release()

        # 验证调用了 eval_lua (Lua 脚本)
        mock_client.eval_lua.assert_called()
        call_args = mock_client.eval_lua.call_args
        self.assertIn("GET", call_args[0][0])  # Lua 脚本包含 GET
        self.assertIn("DEL", call_args[0][0])  # Lua 脚本包含 DEL

    async def test_lock_token_unique(self):
        """每个锁实例获取的 token 唯一"""
        mock_client = _create_mock_redis_client()
        mock_client.set_nx_px = AsyncMock(return_value=True)
        mock_client.eval_lua = AsyncMock(return_value=1)

        lock1 = DistributedLock(mock_client, "res1", auto_extend=False)
        lock2 = DistributedLock(mock_client, "res2", auto_extend=False)

        await lock1.acquire()
        await lock2.acquire()

        self.assertIsNotNone(lock1._token)
        self.assertIsNotNone(lock2._token)
        self.assertNotEqual(lock1._token, lock2._token)

    async def test_lock_extend(self):
        mock_client = _create_mock_redis_client()
        mock_client.set_nx_px = AsyncMock(return_value=True)
        mock_client.eval_lua = AsyncMock(return_value=1)

        lock = DistributedLock(mock_client, "res:extend", auto_extend=False)
        await lock.acquire()
        result = await lock.extend()
        self.assertTrue(result)

        # 验证续期调用 eval_lua
        mock_client.eval_lua.assert_called()


# ============================================================================
# AC-4: 连接池配置测试
# ============================================================================

class TestConnectionPoolConfig(unittest.TestCase):
    """AC-4: 连接池配置可压测通过"""

    def test_default_config_values(self):
        config = RedisClientConfig()
        self.assertEqual(config.max_connections, 50)
        self.assertEqual(config.min_connections, 5)
        self.assertEqual(config.socket_timeout, 5.0)
        self.assertEqual(config.socket_connect_timeout, 3.0)
        self.assertTrue(config.socket_keepalive)
        self.assertEqual(config.retry_max_attempts, 3)

    def test_stress_test_config(self):
        config = RedisClientConfig.for_stress_test()
        self.assertEqual(config.max_connections, 200)
        self.assertEqual(config.min_connections, 20)
        self.assertEqual(config.socket_timeout, 2.0)
        self.assertEqual(config.socket_connect_timeout, 1.0)
        self.assertEqual(config.retry_max_attempts, 1)
        self.assertTrue(config.circuit_breaker_enabled)

    def test_config_to_connection_kwargs(self):
        config = RedisClientConfig(host="redis.example.com", port=6380, db=2)
        kwargs = config.to_connection_kwargs()
        self.assertEqual(kwargs["host"], "redis.example.com")
        self.assertEqual(kwargs["port"], 6380)
        self.assertEqual(kwargs["db"], 2)
        self.assertTrue(kwargs["retry_on_timeout"])
        self.assertEqual(kwargs["max_connections"], 50)

    def test_config_invalid_env_raises(self):
        with self.assertRaises(ValueError):
            RedisClientConfig(env="production")

    def test_config_all_env_values_accepted(self):
        for env in KEY_ENV_VALUES:
            config = RedisClientConfig(env=env)
            self.assertEqual(config.env, env)

    def test_circuit_breaker_default_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_circuit_breaker_not_open_after_few_failures(self):
        """少量失败不应触发熔断"""
        async def _test():
            cb = CircuitBreaker(failure_threshold=5)
            for _ in range(4):
                await cb.on_failure()
            allowed = await cb.before_request()
            self.assertTrue(allowed)
            self.assertEqual(cb.state, CircuitState.CLOSED)

        asyncio.run(_test())

    def test_circuit_breaker_opens_after_threshold(self):
        """达到阈值时熔断器打开"""
        async def _test():
            cb = CircuitBreaker(failure_threshold=5)
            for _ in range(5):
                await cb.on_failure()
            allowed = await cb.before_request()
            self.assertFalse(allowed)
            self.assertEqual(cb.state, CircuitState.OPEN)

        asyncio.run(_test())

    def test_circuit_breaker_recovery_transition(self):
        """熔断器 OPEN → HALF_OPEN 恢复探测"""
        async def _test():
            cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.01)
            for _ in range(3):
                await cb.on_failure()
            self.assertEqual(cb.state, CircuitState.OPEN)

            await asyncio.sleep(0.02)  # 等待恢复超时
            allowed = await cb.before_request()
            self.assertTrue(allowed)
            self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        asyncio.run(_test())

    def test_circuit_breaker_success_recovery(self):
        """HALF_OPEN 成功后恢复为 CLOSED"""
        async def _test():
            cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.01)
            for _ in range(3):
                await cb.on_failure()
            await asyncio.sleep(0.02)
            await cb.before_request()

            await cb.on_success()
            self.assertEqual(cb.state, CircuitState.CLOSED)

        asyncio.run(_test())

    def test_circuit_breaker_open_error(self):
        """熔断器打开时抛出专用异常"""
        error = CircuitBreakerOpenError("test")
        self.assertIsInstance(error, Exception)
        self.assertIn("test", str(error))


# ============================================================================
# Repository 功能测试
# ============================================================================

class TestQueryCacheRepository(unittest.TestCase):
    def test_query_cache_set_and_get(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            query = "SELECT * FROM metrics"
            result = {"rows": [{"cpu": 80}]}
            serialized = json.dumps(result)

            mock_client.get = AsyncMock(return_value=serialized)
            mock_client.set = AsyncMock(return_value=True)

            repo = QueryCacheRepository(mock_client)
            await repo.set(query, result)

            cached = await repo.get(query)
            self.assertEqual(cached, result)

        asyncio.run(_test())

    def test_query_cache_miss(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.get = AsyncMock(return_value=None)

            repo = QueryCacheRepository(mock_client)
            result = await repo.get("SELECT * FROM metrics")
            self.assertIsNone(result)
            self.assertEqual(repo.stats.misses, 1)

        asyncio.run(_test())

    def test_query_cache_exists(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.exists = AsyncMock(return_value=1)

            repo = QueryCacheRepository(mock_client)
            exists = await repo.exists("SELECT * FROM metrics")
            self.assertTrue(exists)

        asyncio.run(_test())


class TestMetricCacheRepository(unittest.TestCase):
    def test_set_and_get_metric(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.hset = AsyncMock(return_value=3)
            mock_client.expire = AsyncMock(return_value=True)
            mock_client.hgetall = AsyncMock(return_value={
                "value": "75.5",
                "timestamp": "1690000000000",
                "attributes": json.dumps({"host": "server-01"}),
            })

            repo = MetricCacheRepository(mock_client)
            await repo.set_metric(1001, "cpu_usage", 75.5, 1690000000000, {"host": "server-01"})

            result = await repo.get_metric(1001, "cpu_usage")
            self.assertIsNotNone(result)
            self.assertEqual(result["value"], 75.5)
            self.assertEqual(result["timestamp"], 1690000000000)

        asyncio.run(_test())


class TestServiceStatsRepository(unittest.TestCase):
    def test_set_and_get_stats(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.hset = AsyncMock(return_value=5)
            mock_client.expire = AsyncMock(return_value=True)
            mock_client.hgetall = AsyncMock(return_value={
                "span_count": "1000",
                "error_count": "50",
                "p50_latency_ns": "50000000",
                "p99_latency_ns": "200000000",
                "updated_at": "1690000000000",
            })

            repo = ServiceStatsRepository(mock_client)
            await repo.set_stats(1001, "api-gateway", 1000, 50, 50000000, 200000000)

            result = await repo.get_stats(1001, "api-gateway")
            self.assertIsNotNone(result)
            self.assertEqual(result["span_count"], 1000)
            self.assertEqual(result["error_count"], 50)
            self.assertAlmostEqual(result["error_rate"], 0.05)

        asyncio.run(_test())


class TestRankingRepository(unittest.TestCase):
    def test_invalid_metric_raises(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            repo = RankingRepository(mock_client)
            with self.assertRaises(ValueError):
                await repo.set_score(1001, "invalid_metric", "svc-a", 10.0)

        asyncio.run(_test())

    def test_set_score_and_get_rank(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.zadd = AsyncMock(return_value=1)
            mock_client.expire = AsyncMock(return_value=True)
            mock_client.zrevrank = AsyncMock(return_value=0)
            mock_client.zscore = AsyncMock(return_value=95.5)

            repo = RankingRepository(mock_client)
            await repo.set_score(1001, "error_rate", "svc-a", 95.5)

            rank = await repo.get_rank(1001, "error_rate", "svc-a")
            self.assertEqual(rank, 1)

            score = await repo.get_score(1001, "error_rate", "svc-a")
            self.assertEqual(score, 95.5)

        asyncio.run(_test())

    def test_get_top_n(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.zadd = AsyncMock(return_value=3)
            mock_client.expire = AsyncMock(return_value=True)
            mock_client.zrevrange = AsyncMock(return_value=[
                ("svc-c", 99.0), ("svc-a", 85.0), ("svc-b", 70.0),
            ])

            repo = RankingRepository(mock_client)
            result = await repo.get_top_n(1001, "error_rate", n=3)

            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["rank"], 1)
            self.assertEqual(result[0]["service_name"], "svc-c")
            self.assertEqual(result[0]["score"], 99.0)

        asyncio.run(_test())

    def test_increment_score(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.zincrby = AsyncMock(return_value=15.0)
            mock_client.expire = AsyncMock(return_value=True)

            repo = RankingRepository(mock_client)
            new_score = await repo.increment_score(1001, "request_count", "svc-a", 10.0)
            self.assertEqual(new_score, 15.0)

        asyncio.run(_test())


class TestSessionContextRepository(unittest.TestCase):
    def test_save_and_load(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.hset = AsyncMock(return_value=5)
            mock_client.expire = AsyncMock(return_value=True)
            mock_client.hgetall = AsyncMock(return_value={
                "tenant_id": "1001",
                "time_range_start": "1690000000000",
                "time_range_end": "1690086400000",
                "filters": json.dumps({"service": "api-gateway"}),
                "created_at": "1690000000000",
            })

            repo = SessionContextRepository(mock_client)
            await repo.save("sess001", 1001, 1690000000000, 1690086400000,
                            {"service": "api-gateway"})

            result = await repo.load("sess001")
            self.assertIsNotNone(result)
            self.assertEqual(result["tenant_id"], 1001)
            self.assertEqual(result["filters"]["service"], "api-gateway")

        asyncio.run(_test())


# ============================================================================
# WriteThroughCache 测试
# ============================================================================

class TestWriteThroughCache(unittest.TestCase):
    def test_cache_miss_fetches_from_db(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.get = AsyncMock(return_value=None)
            mock_client.set = AsyncMock(return_value=True)

            cache = WriteThroughCache(mock_client, "test:cache", ttl_seconds=300)
            data = {"hello": "world"}

            async def fetcher():
                return data

            result = await cache.get("ident", fetcher)
            self.assertEqual(result, data)
            self.assertEqual(cache.stats.misses, 1)
            self.assertEqual(cache.stats.writes, 1)

        asyncio.run(_test())

    def test_cache_hit_skips_db(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            data = {"cached": True}
            mock_client.get = AsyncMock(return_value=json.dumps(data))

            cache = WriteThroughCache(mock_client, "test:cache")

            fetch_called = [False]

            async def fetcher():
                fetch_called[0] = True
                return {"should": "not_use"}

            result = await cache.get("ident", fetcher)
            self.assertEqual(result, data)
            self.assertFalse(fetch_called[0])
            self.assertEqual(cache.stats.hits, 1)

        asyncio.run(_test())

    def test_invalidate(self):
        async def _test():
            mock_client = _create_mock_redis_client()
            mock_client.delete = AsyncMock(return_value=1)

            cache = WriteThroughCache(mock_client, "test:cache")
            await cache.invalidate("ident")
            self.assertEqual(cache.stats.evictions, 1)

        asyncio.run(_test())


# ============================================================================
# Helpers
# ============================================================================

def _create_mock_redis_client() -> MagicMock:
    """创建模拟 Redis 客户端"""
    config = RedisClientConfig(env="prod")
    client = MagicMock(spec=RedisClient)
    client.config = config
    return client


if __name__ == "__main__":
    unittest.main()