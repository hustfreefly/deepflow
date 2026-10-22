"""
Redis 客户端 — 连接池、熔断、Key 命名

提供:
- RedisClientConfig: 连接池与超时配置
- CircuitBreaker: 熔断器，防止 Redis 故障雪崩
- RedisClient: 异步 Redis 客户端封装
- build_key: 统一的 Key 命名工具
- validate_key: Key 命名规范校验

需求覆盖: REQ-007 (实时查询缓存)
验收标准: AC-2 (Key 命名规范), AC-4 (连接池配置)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)

# ============================================================================
# Key 命名规范常量
# ============================================================================

KEY_SEPARATOR = ":"
KEY_ENV_VALUES = ("prod", "staging", "dev")
KEY_SERVICE = "analysis"
KEY_MAX_LENGTH = 128


# ============================================================================
# 熔断器
# ============================================================================

class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "CLOSED"          # 正常，请求通过
    OPEN = "OPEN"              # 熔断，直接拒绝
    HALF_OPEN = "HALF_OPEN"    # 半开，探测恢复


@dataclass
class CircuitBreaker:
    """
    熔断器 — 防止 Redis 故障引发调用链雪崩。

    状态机:
        CLOSED ──(failure_count >= threshold)──> OPEN
        OPEN   ──(timeout elapsed)────────────> HALF_OPEN
        HALF_OPEN ──(success)──────────────────> CLOSED
        HALF_OPEN ──(failure)──────────────────> OPEN
    """
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_requests: int = 3

    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _last_failure_time: float = 0.0
    _half_open_requests: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def before_request(self) -> bool:
        """请求前检查：返回 True 允许通过，False 拒绝"""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                    logger.info("Circuit breaker: OPEN → HALF_OPEN (recovery probe)")
                    return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_requests < self.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                return False

            return False

    async def on_success(self) -> None:
        """请求成功回调"""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_requests = 0
                logger.info("Circuit breaker: HALF_OPEN → CLOSED (recovered)")

    async def on_failure(self) -> None:
        """请求失败回调"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker: CLOSED → OPEN (failures=%d/%d)",
                    self._failure_count, self.failure_threshold,
                )
            elif self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker: HALF_OPEN → OPEN (probe failed)")

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN


# ============================================================================
# 连接池配置
# ============================================================================

@dataclass
class RedisClientConfig:
    """Redis 客户端连接池配置 — 覆盖 AC-4 连接池压测要求"""
    # 连接地址
    url: str = "redis://localhost:6379/0"
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None

    # 连接池 (AC-4: 可压测通过的配置)
    max_connections: int = 50
    min_connections: int = 5
    max_idle_time: float = 300.0  # 空闲连接超时 (秒)

    # 超时
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 3.0
    socket_keepalive: bool = True

    # 重试
    retry_max_attempts: int = 3
    retry_min_delay: float = 0.1  # 秒
    retry_max_delay: float = 2.0  # 秒

    # 熔断
    circuit_breaker_enabled: bool = True
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 30.0

    # 序列化
    decode_responses: bool = True

    # 环境
    env: str = "prod"

    def __post_init__(self) -> None:
        if self.env not in KEY_ENV_VALUES:
            raise ValueError(f"env must be one of {KEY_ENV_VALUES}, got '{self.env}'")

    def to_connection_kwargs(self) -> dict[str, Any]:
        """转换为 redis-py 连接参数"""
        return {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "password": self.password,
            "max_connections": self.max_connections,
            "socket_timeout": self.socket_timeout,
            "socket_connect_timeout": self.socket_connect_timeout,
            "socket_keepalive": self.socket_keepalive,
            "retry_on_timeout": True,
            "decode_responses": self.decode_responses,
        }

    @staticmethod
    def for_stress_test() -> "RedisClientConfig":
        """压测专用配置 — 高并发连接池"""
        return RedisClientConfig(
            max_connections=200,
            min_connections=20,
            socket_timeout=2.0,
            socket_connect_timeout=1.0,
            retry_max_attempts=1,
            circuit_breaker_enabled=True,
            circuit_failure_threshold=10,
            circuit_recovery_timeout=10.0,
        )


# ============================================================================
# Key 命名工具
# ============================================================================

def build_key(env: str, domain: str, entity: str, identifier: str,
              field: Optional[str] = None) -> str:
    """
    构建 Redis Key 遵循命名规范: {env}:{service}:{domain}:{entity}:{id}[:{field}]

    Args:
        env: 环境 (prod|staging|dev)
        domain: 领域 (cache|metrics|traces|ranking|alerts|session|ratelimit)
        entity: 实体类型 (query|latest|svc_stats|services|active|context|...)
        identifier: 实体标识 (tenant_id, query_hash, session_id, ...)
        field: 可选字段名

    Returns:
        符合规范的 Redis key 字符串

    Raises:
        ValueError: key 不符合规范时抛出
    """
    if env not in KEY_ENV_VALUES:
        raise ValueError(f"Invalid env '{env}', must be one of {KEY_ENV_VALUES}")

    parts = [env, KEY_SERVICE, domain, entity, identifier]
    if field:
        parts.append(field)

    key = KEY_SEPARATOR.join(parts)

    if len(key) > KEY_MAX_LENGTH:
        raise ValueError(
            f"Key length {len(key)} exceeds maximum {KEY_MAX_LENGTH}: {key[:64]}..."
        )

    if not validate_key(key):
        raise ValueError(f"Key validation failed (contains uppercase or space): {key}")

    return key


def validate_key(key: str, max_length: int = KEY_MAX_LENGTH) -> bool:
    """
    验证 Redis key 是否符合命名规范:
    - 全小写字母
    - 使用冒号 : 作为分隔符
    - 长度不超过 max_length
    - 不包含空格或特殊字符
    """
    if len(key) > max_length:
        return False
    if key != key.lower():
        return False
    if " " in key:
        return False
    # 只允许小写字母、数字、冒号、连字符、下划线
    for ch in key:
        if not (ch.islower() or ch.isdigit() or ch in (':', '-', '_')):
            return False
    return True


def compute_query_hash(query: str) -> str:
    """计算查询语句的 SHA256 哈希前 16 位"""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


# ============================================================================
# Redis 异步客户端
# ============================================================================

class RedisClient:
    """
    异步 Redis 客户端 — 封装连接池与熔断逻辑。

    用法:
        config = RedisClientConfig(host="localhost", port=6379)
        client = RedisClient(config)
        await client.connect()
        value = await client.get("prod:analysis:cache:query:abc123")
        await client.close()
    """

    def __init__(self, config: Optional[RedisClientConfig] = None):
        self.config = config or RedisClientConfig()
        self._redis: Any = None
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_failure_threshold,
            recovery_timeout=self.config.circuit_recovery_timeout,
        )

    async def connect(self) -> None:
        """建立 Redis 连接池"""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "redis-py with async support is required. "
                "Install with: pip install redis[hiredis]"
            )

        self._redis = aioredis.from_url(
            self.config.url,
            **self.config.to_connection_kwargs(),
        )
        await self._redis.ping()
        logger.info(
            "Redis connected: %s (pool=max=%d,min=%d)",
            self.config.url, self.config.max_connections, self.config.min_connections,
        )

    async def close(self) -> None:
        """关闭 Redis 连接池"""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            logger.info("Redis connection pool closed")

    async def _execute(self, operation: Callable, *args, **kwargs) -> Any:
        """
        执行 Redis 操作，带熔断和重试保护。

        熔断器在 Redis 故障时快速失败，避免雪崩。
        重试使用指数退避 + 随机抖动。
        """
        if not self._redis:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        if self.config.circuit_breaker_enabled:
            allowed = await self._circuit_breaker.before_request()
            if not allowed:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN — Redis is unavailable")

        last_error: Optional[Exception] = None
        for attempt in range(self.config.retry_max_attempts):
            try:
                result = await operation(self._redis, *args, **kwargs)
                if self.config.circuit_breaker_enabled:
                    await self._circuit_breaker.on_success()
                return result
            except Exception as e:
                last_error = e
                if self.config.circuit_breaker_enabled:
                    await self._circuit_breaker.on_failure()

                if attempt < self.config.retry_max_attempts - 1:
                    delay = min(
                        self.config.retry_min_delay * (2 ** attempt),
                        self.config.retry_max_delay,
                    )
                    import random
                    delay *= (1 + random.random() * 0.5)  # jitter
                    logger.warning(
                        "Redis operation failed (attempt %d/%d): %s. Retrying in %.2fs",
                        attempt + 1, self.config.retry_max_attempts, e, delay,
                    )
                    await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]

    # === 基础操作委托 ===

    async def get(self, key: str) -> Optional[str]:
        return await self._execute(lambda r, k: r.get(k), key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        return await self._execute(lambda r, k, v, ex: r.set(k, v, ex=ex), key, value, ex)

    async def delete(self, *keys: str) -> int:
        return await self._execute(lambda r, *ks: r.delete(*ks), *keys)

    async def exists(self, *keys: str) -> int:
        return await self._execute(lambda r, *ks: r.exists(*ks), *keys)

    async def expire(self, key: str, seconds: int) -> bool:
        return await self._execute(lambda r, k, s: r.expire(k, s), key, seconds)

    async def ttl(self, key: str) -> int:
        return await self._execute(lambda r, k: r.ttl(k), key)

    # === Hash 操作 ===

    async def hget(self, key: str, field: str) -> Optional[str]:
        return await self._execute(lambda r, k, f: r.hget(k, f), key, field)

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        return await self._execute(lambda r, k, m: r.hset(k, mapping=m), key, mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return await self._execute(lambda r, k: r.hgetall(k), key)

    async def hdel(self, key: str, *fields: str) -> int:
        return await self._execute(lambda r, k, *fs: r.hdel(k, *fs), key, *fields)

    async def hexists(self, key: str, field: str) -> bool:
        return await self._execute(lambda r, k, f: r.hexists(k, f), key, field)

    # === ZSet 操作 ===

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        return await self._execute(lambda r, k, m: r.zadd(k, m), key, mapping)

    async def zincrby(self, key: str, amount: float, member: str) -> float:
        return await self._execute(lambda r, k, a, m: r.zincrby(k, a, m), key, amount, member)

    async def zscore(self, key: str, member: str) -> Optional[float]:
        return await self._execute(lambda r, k, m: r.zscore(k, m), key, member)

    async def zrevrank(self, key: str, member: str) -> Optional[int]:
        return await self._execute(lambda r, k, m: r.zrevrank(k, m), key, member)

    async def zrevrange(self, key: str, start: int, end: int,
                        withscores: bool = False) -> list:
        return await self._execute(
            lambda r, k, s, e, ws: r.zrevrange(k, s, e, withscores=ws),
            key, start, end, withscores,
        )

    async def zcard(self, key: str) -> int:
        return await self._execute(lambda r, k: r.zcard(k), key)

    async def zrem(self, key: str, *members: str) -> int:
        return await self._execute(lambda r, k, *ms: r.zrem(k, *ms), key, *members)

    async def zremrangebyrank(self, key: str, start: int, end: int) -> int:
        return await self._execute(
            lambda r, k, s, e: r.zremrangebyrank(k, s, e), key, start, end,
        )

    # === 分布式锁专用 (SET NX PX) ===

    async def set_nx_px(self, key: str, value: str, px: int) -> bool:
        """SET key value NX PX milliseconds — 分布式锁获取"""
        return await self._execute(
            lambda r, k, v, px: r.set(k, v, nx=True, px=px), key, value, px,
        )

    async def eval_lua(self, script: str, numkeys: int, *keys_and_args) -> Any:
        """执行 Lua 脚本 — 分布式锁释放 (原子 compare-and-delete)"""
        return await self._execute(
            lambda r, s, n, *ka: r.eval(s, n, *ka), script, numkeys, *keys_and_args,
        )

    # === Pipeline ===

    async def pipeline(self) -> Any:
        """获取 pipeline 对象"""
        if not self._redis:
            raise RuntimeError("Redis client not connected.")
        return self._redis.pipeline()

    # === 健康检查 ===

    async def ping(self) -> bool:
        """健康检查"""
        try:
            return await self._execute(lambda r: r.ping())
        except Exception:
            return False

    @property
    def circuit_state(self) -> CircuitState:
        return self._circuit_breaker.state

    @property
    def is_circuit_open(self) -> bool:
        return self._circuit_breaker.is_open


class CircuitBreakerOpenError(Exception):
    """熔断器打开异常 — Redis 不可用时抛出"""
    pass
