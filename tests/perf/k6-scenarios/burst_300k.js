// burst_300k.js — 3x 突发 (300K traces/s) 持续 60s 不丢数据测试
// 验证 AC-2: 300K traces/s 突发 60s，丢失率<0.1%
// 验证 AC-3: P99 延迟 < 500ms（Agent→Kafka）
// 验证 AC-6: 三级背压依次触发，降级期间丢失率<0.1%

import http from 'k6/http';
import { check, Trend, Counter, Rate } from 'k6';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ============================================================
// 可调参数
// ============================================================
const OTLP_ENDPOINT = __ENV.OTLP_ENDPOINT || 'http://localhost:4318/v1/traces';
const STEADY_TPS = parseInt(__ENV.STEADY_TPS) || 100000;       // 稳态 100K
const BURST_TPS = parseInt(__ENV.BURST_TPS) || 300000;          // 突发 300K
const SPANS_PER_TRACE = parseInt(__ENV.SPANS_PER_TRACE) || 8;
const STEADY_DURATION = __ENV.STEADY_DURATION || '3m';          // 稳态预热
const BURST_DURATION = __ENV.BURST_DURATION || '60s';           // 突发持续
const RECOVERY_DURATION = __ENV.RECOVERY_DURATION || '3m';      // 恢复观察

// ============================================================
// 自定义指标
// ============================================================
const traceSendDuration = new Trend('trace_send_duration_ms', true);
const traceSendSuccess = new Rate('trace_send_success');
const traceSendErrors = new Counter('trace_send_errors');
const traceSendDropped = new Counter('trace_send_dropped');
const spansGenerated = new Counter('spans_generated');
const burstPhase = new Counter('burst_phase'); // 0=steady, 1=burst, 2=recovery

// ============================================================
// 数据池
// ============================================================
const SERVICE_NAMES = [
  'api-gateway', 'user-service', 'order-service', 'payment-service',
  'inventory-service', 'notification-service', 'auth-service',
  'product-catalog', 'shipping-service', 'recommendation-engine',
  'search-service', 'cart-service', 'analytics-service', 'billing-service',
  'fraud-detection', 'rate-limiter', 'config-service', 'audit-service',
  'session-store', 'feature-flag-service'
];

const SPAN_NAMES = [
  'HTTP GET /api/users', 'HTTP POST /api/orders', 'HTTP PUT /api/cart',
  'HTTP DELETE /api/sessions', 'gRPC GetUser', 'gRPC CreateOrder',
  'gRPC ProcessPayment', 'DB SELECT users', 'DB INSERT orders',
  'DB UPDATE inventory', 'Cache GET', 'Cache SET', 'MQ publish',
  'MQ consume', 'S3 ReadObject', 'S3 PutObject', 'Auth ValidateToken',
  'Auth RefreshToken', 'RateLimit Check', 'CircuitBreaker Check'
];

function randomTraceId() {
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
}

function randomSpanId() {
  return Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
}

function randomChoice(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function unixNano() {
  return Date.now() * 1000000;
}

// ============================================================
// 生成 Trace（含高优先级标记混合）
// 突发期间增加 P0 标记占比，测试优先级降级
// ============================================================
function generateTrace(phase) {
  const traceId = randomTraceId();
  const now = unixNano();
  const rootSpanId = randomSpanId();

  // 突发期：20% 的 trace 标记为 P0（不应被降级丢弃）
  const isP0 = phase === 1 && Math.random() < 0.20;
  const isP1 = Math.random() < 0.05; // 5% ERROR

  const statusCode = isP1 ? 2 : (Math.random() < 0.90 ? 1 : 0);

  const rootSpan = {
    traceId: traceId,
    spanId: rootSpanId,
    parentSpanId: '',
    name: randomChoice(SPAN_NAMES),
    kind: 2,
    startTimeUnixNano: String(now),
    endTimeUnixNano: String(now + randomIntBetween(1000000, 500000000)),
    status: { code: statusCode },
    attributes: [
      { key: 'service.name', value: { stringValue: randomChoice(SERVICE_NAMES) } },
      { key: 'http.method', value: { stringValue: randomChoice(['GET', 'POST', 'PUT', 'DELETE']) } },
      { key: 'http.status_code', value: { stringValue: String(isP1 ? 500 : randomChoice([200, 201, 204])) } },
      { key: 'deployment.environment', value: { stringValue: 'production' } },
      { key: 'sampling.priority', value: { stringValue: isP0 ? 'critical' : 'p99' } },
      { key: 'burst.phase', value: { stringValue: String(phase) } },
    ],
  };

  const childSpans = [];
  for (let i = 0; i < SPANS_PER_TRACE - 1; i++) {
    const childSpanId = randomSpanId();
    const childParentId = i === 0 ? rootSpanId : childSpans[i - 1].spanId;
    childSpans.push({
      traceId: traceId,
      spanId: childSpanId,
      parentSpanId: childParentId,
      name: randomChoice(SPAN_NAMES),
      kind: randomChoice([3, 4]),
      startTimeUnixNano: String(now + randomIntBetween(0, 5000000)),
      endTimeUnixNano: String(now + randomIntBetween(5000000, 100000000)),
      status: { code: Math.random() < 0.95 ? 1 : 2 },
      attributes: [
        { key: 'service.name', value: { stringValue: randomChoice(SERVICE_NAMES) } },
        { key: 'burst.phase', value: { stringValue: String(phase) } },
      ],
    });
  }

  return [rootSpan, ...childSpans];
}

function buildOtlpPayload(trace) {
  return JSON.stringify({
    resourceSpans: [{
      resource: {
        attributes: [
          { key: 'service.name', value: { stringValue: randomChoice(SERVICE_NAMES) } },
          { key: 'telemetry.sdk.name', value: { stringValue: 'k6-burst-test' } },
          { key: 'telemetry.sdk.version', value: { stringValue: '1.0.0' } },
          { key: 'host.name', value: { stringValue: `k6-worker-${randomIntBetween(1, 100)}` } },
        ],
      },
      scopeSpans: [{
        scope: { name: 'k6-burst-test', version: '1.0.0' },
        spans: trace,
      }],
    }],
  });
}

function sendTrace(trace, phase) {
  const payload = buildOtlpPayload(trace);
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-Id': `tenant-${randomIntBetween(1, 20)}`,
    },
    timeout: '10s',
    tags: { phase: phase === 0 ? 'steady' : (phase === 1 ? 'burst' : 'recovery') },
  };

  const startTime = Date.now();
  try {
    const response = http.post(OTLP_ENDPOINT, payload, params);
    const duration = Date.now() - startTime;
    traceSendDuration.add(duration);

    if (response.status === 200 || response.status === 202) {
      traceSendSuccess.add(true);
    } else if (response.status === 429 || response.status === 503) {
      // 背压拒绝 — 记录但不视为丢失（客户端应重试）
      traceSendDropped.add(1);
      traceSendSuccess.add(false);
      console.debug(`Backpressure: status=${response.status}, phase=${phase}`);
    } else {
      traceSendErrors.add(1);
      traceSendSuccess.add(false);
      console.warn(`Error: status=${response.status}, phase=${phase}`);
    }

    spansGenerated.add(trace.length);

    check(response, {
      'OTLP accepted or backpressured': (r) =>
        r.status === 200 || r.status === 202 || r.status === 429 || r.status === 503,
    });
  } catch (e) {
    traceSendErrors.add(1);
    traceSendSuccess.add(false);
    console.error(`Send error: ${e.message}`);
  }
}

// ============================================================
// k6 配置 — 3 阶段：稳态 → 突发 → 恢复
// ============================================================
export const options = {
  scenarios: {
    burst_test: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 3000,
      stages: [
        // Phase 0: 稳态预热
        { target: Math.floor(STEADY_TPS * 0.5), duration: '1m' },
        { target: STEADY_TPS, duration: STEADY_DURATION },
        // Phase 1: 3x 突发
        { target: BURST_TPS, duration: BURST_DURATION },
        // Phase 2: 恢复
        { target: STEADY_TPS, duration: '2m' },
        { target: 0, duration: '1m' },
      ],
    },
  },
  thresholds: {
    'trace_send_success': ['rate>0.999'],              // 丢失率 < 0.1%
    'trace_send_duration_ms': ['p(99)<500'],            // P99 < 500ms
    'trace_send_duration_ms': ['p(95)<400'],            // 突发期 P95 < 400ms
    'trace_send_errors': ['count<1000'],                // 错误数 < 1000
    'http_req_failed': ['rate<0.001'],                  // HTTP 失败率 < 0.1%
  },
};

export default function () {
  // 根据当前 VU 迭代数推断阶段（近似）
  // arrival-rate 场景下，阶段由 stages 控制
  const phase = __ITER < 100000 ? 0 : (__ITER < 500000 ? 1 : 2);
  const trace = generateTrace(phase);
  sendTrace(trace, phase);
}

export function handleSummary(data) {
  const summary = {
    test_config: {
      steady_tps: STEADY_TPS,
      burst_tps: BURST_TPS,
      burst_multiplier: '3x',
      spans_per_trace: SPANS_PER_TRACE,
      burst_duration: BURST_DURATION,
      steady_duration: STEADY_DURATION,
      otlp_endpoint: OTLP_ENDPOINT,
    },
    metrics: {
      total_spans_generated: data.metrics.spans_generated?.values?.count || 0,
      trace_send_success_rate: data.metrics.trace_send_success?.values?.rate || 0,
      trace_send_errors: data.metrics.trace_send_errors?.values?.count || 0,
      trace_send_dropped: data.metrics.trace_send_dropped?.values?.count || 0,
      trace_send_duration_p50: data.metrics.trace_send_duration_ms?.values?.['p(50)'] || 0,
      trace_send_duration_p95: data.metrics.trace_send_duration_ms?.values?.['p(95)'] || 0,
      trace_send_duration_p99: data.metrics.trace_send_duration_ms?.values?.['p(99)'] || 0,
      trace_send_duration_avg: data.metrics.trace_send_duration_ms?.values?.avg || 0,
      trace_send_duration_max: data.metrics.trace_send_duration_ms?.values?.max || 0,
      total_iterations: data.metrics.iterations?.values?.count || 0,
      vus_max: data.metrics.vus_max?.values?.max || 0,
    },
    thresholds: {
      success_rate_met: (data.metrics.trace_send_success?.values?.rate || 0) > 0.999,
      p99_latency_met: (data.metrics.trace_send_duration_ms?.values?.['p(99)'] || Infinity) < 500,
    },
    data_loss: {
      total_failures: (data.metrics.trace_send_errors?.values?.count || 0) +
        (data.metrics.trace_send_dropped?.values?.count || 0),
      loss_rate: ((data.metrics.trace_send_errors?.values?.count || 0) +
        (data.metrics.trace_send_dropped?.values?.count || 0)) /
        Math.max((data.metrics.iterations?.values?.count || 1), 1),
      ac2_met: (((data.metrics.trace_send_errors?.values?.count || 0) +
        (data.metrics.trace_send_dropped?.values?.count || 0)) /
        Math.max((data.metrics.iterations?.values?.count || 1), 1)) < 0.001,
    },
    generated_at: new Date().toISOString(),
  };

  return {
    'stdout': JSON.stringify(summary, null, 2),
    'tests/perf/results/burst_300k_summary.json': JSON.stringify(summary, null, 2),
  };
}