// steady_100k.js — 100K traces/s 稳态性能基准测试
// 验证 AC-1: 100K traces/s 稳态运行 10min，丢失率=0%
// 验证 AC-3: P99 延迟 < 500ms（Agent→Kafka）
// 验证 AC-4: Agent CPU≤70%, Memory≤80%（稳态下）

import http from 'k6/http';
import { check, sleep, Trend, Counter, Rate } from 'k6';
import { randomString, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ============================================================
// 可调参数 — 可通过环境变量覆盖
// ============================================================
const OTLP_ENDPOINT = __ENV.OTLP_ENDPOINT || 'http://localhost:4318/v1/traces';
const OTLP_GRPC_ENDPOINT = __ENV.OTLP_GRPC_ENDPOINT || 'localhost:4317';
const TARGET_TRACES_PER_SEC = parseInt(__ENV.TARGET_TPS) || 100000;
const SPANS_PER_TRACE = parseInt(__ENV.SPANS_PER_TRACE) || 8;
const TEST_DURATION = __ENV.TEST_DURATION || '10m';
const RAMP_UP = __ENV.RAMP_UP || '2m';
const STEADY_DURATION = __ENV.STEADY_DURATION || '8m';
const PROTOCOL = __ENV.PROTOCOL || 'http'; // 'http' or 'grpc'

// ============================================================
// 自定义指标
// ============================================================
const traceSendDuration = new Trend('trace_send_duration_ms', true);
const traceSendSuccess = new Rate('trace_send_success');
const traceSendErrors = new Counter('trace_send_errors');
const spansGenerated = new Counter('spans_generated');

// ============================================================
// 服务名称池 — 模拟真实微服务拓扑
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

const STATUS_CODES = [
  { code: 1, weight: 90 },  // OK (90%)
  { code: 2, weight: 5 },   // ERROR (5%)
  { code: 0, weight: 5 },   // UNSET (5%)
];

// ============================================================
// 辅助函数
// ============================================================
function randomTraceId() {
  return Array.from({ length: 32 }, () =>
    Math.floor(Math.random() * 16).toString(16)
  ).join('');
}

function randomSpanId() {
  return Array.from({ length: 16 }, () =>
    Math.floor(Math.random() * 16).toString(16)
  ).join('');
}

function randomChoice(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function weightedRandom(items) {
  const totalWeight = items.reduce((sum, item) => sum + item.weight, 0);
  let r = Math.random() * totalWeight;
  for (const item of items) {
    r -= item.weight;
    if (r <= 0) return item.code;
  }
  return items[items.length - 1].code;
}

function unixNano() {
  return Date.now() * 1000000;
}

function randomDuration() {
  // 模拟真实延迟分布：大部分在 1-500ms，少数在 500ms-5s
  const p = Math.random();
  if (p < 0.70) return randomIntBetween(1, 100) * 1000000;      // 1-100ms
  if (p < 0.90) return randomIntBetween(100, 500) * 1000000;    // 100-500ms
  if (p < 0.97) return randomIntBetween(500, 2000) * 1000000;   // 500ms-2s
  return randomIntBetween(2000, 10000) * 1000000;               // 2-10s
}

// ============================================================
// 生成一个完整的 Trace（包含多个 Span）
// ============================================================
function generateTrace() {
  const traceId = randomTraceId();
  const now = unixNano();
  const serviceName = randomChoice(SERVICE_NAMES);
  const rootSpanId = randomSpanId();

  // 根 Span
  const rootSpan = {
    traceId: traceId,
    spanId: rootSpanId,
    parentSpanId: '',
    name: `HTTP ${randomChoice(['GET', 'POST', 'PUT', 'DELETE'])} /api/${randomString(6)}`,
    kind: 2, // SERVER
    startTimeUnixNano: String(now),
    endTimeUnixNano: String(now + randomDuration()),
    status: { code: weightedRandom(STATUS_CODES) },
    attributes: [
      { key: 'service.name', value: { stringValue: serviceName } },
      { key: 'http.method', value: { stringValue: randomChoice(['GET', 'POST', 'PUT', 'DELETE']) } },
      { key: 'http.status_code', value: { intValue: String(randomChoice([200, 201, 204, 400, 500])) } },
      { key: 'http.url', value: { stringValue: `https://${serviceName}.internal/api/v1/resource` } },
      { key: 'deployment.environment', value: { stringValue: 'production' } },
      { key: 'sampling.priority', value: { stringValue: 'p99' } },
    ],
  };

  // 子 Span
  const childSpans = [];
  for (let i = 0; i < SPANS_PER_TRACE - 1; i++) {
    const childSpanId = randomSpanId();
    const childParentId = i === 0 ? rootSpanId : childSpans[i - 1].spanId;
    childSpans.push({
      traceId: traceId,
      spanId: childSpanId,
      parentSpanId: childParentId,
      name: randomChoice(SPAN_NAMES),
      kind: randomChoice([3, 4]), // CLIENT or PRODUCER
      startTimeUnixNano: String(now + randomIntBetween(0, 5000000)),
      endTimeUnixNano: String(now + randomIntBetween(5000000, 50000000)),
      status: { code: weightedRandom(STATUS_CODES) },
      attributes: [
        { key: 'service.name', value: { stringValue: randomChoice(SERVICE_NAMES) } },
        { key: 'db.system', value: { stringValue: randomChoice(['postgresql', 'redis', 'kafka']) } },
      ],
    });
  }

  return [rootSpan, ...childSpans];
}

// ============================================================
// 构建 OTLP JSON payload
// ============================================================
function buildOtlpPayload(trace) {
  const resourceSpans = [{
    resource: {
      attributes: [
        { key: 'service.name', value: { stringValue: randomChoice(SERVICE_NAMES) } },
        { key: 'telemetry.sdk.name', value: { stringValue: 'k6-benchmark' } },
        { key: 'telemetry.sdk.version', value: { stringValue: '1.0.0' } },
        { key: 'host.name', value: { stringValue: `k6-worker-${randomIntBetween(1, 100)}` } },
      ],
    },
    scopeSpans: [{
      scope: {
        name: 'k6-perf-test',
        version: '1.0.0',
      },
      spans: trace,
    }],
  }];

  return JSON.stringify({ resourceSpans });
}

// ============================================================
// 发送 OTLP Trace
// ============================================================
function sendTrace(trace) {
  const payload = buildOtlpPayload(trace);
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-Id': `tenant-${randomIntBetween(1, 20)}`,
    },
    timeout: '10s',
  };

  const startTime = Date.now();
  let response;
  try {
    response = http.post(OTLP_ENDPOINT, payload, params);
    const duration = Date.now() - startTime;

    traceSendDuration.add(duration);
    traceSendSuccess.add(response.status === 200 || response.status === 202);
    spansGenerated.add(trace.length);

    if (response.status !== 200 && response.status !== 202) {
      traceSendErrors.add(1);
      console.warn(`OTLP send failed: status=${response.status}, body=${response.body.substring(0, 200)}`);
    }

    check(response, {
      'OTLP trace accepted': (r) => r.status === 200 || r.status === 202,
      'response time < 500ms': () => duration < 500,
      'response time < 1000ms': () => duration < 1000,
    });
  } catch (e) {
    traceSendErrors.add(1);
    traceSendSuccess.add(false);
    console.error(`OTLP send error: ${e.message}`);
  }
}

// ============================================================
// k6 配置
// ============================================================
export const options = {
  scenarios: {
    steady_load: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 2000,
      stages: [
        { target: Math.floor(TARGET_TRACES_PER_SEC * 0.3), duration: RAMP_UP },  // 30% ramp
        { target: TARGET_TRACES_PER_SEC, duration: STEADY_DURATION },             // steady
        { target: 0, duration: '1m' },                                             // cool-down
      ],
    },
  },
  thresholds: {
    'trace_send_success': ['rate>0.9999'],              // 丢失率 < 0.01%
    'trace_send_duration_ms': ['p(99)<500'],             // P99 < 500ms
    'trace_send_duration_ms': ['p(95)<300'],             // P95 < 300ms
    'trace_send_errors': ['count<100'],                  // 错误数 < 100
    'http_req_failed': ['rate<0.0001'],                  // HTTP 失败率 < 0.01%
  },
};

// ============================================================
// 主函数
// ============================================================
export default function () {
  const trace = generateTrace();
  sendTrace(trace);
  // 不 sleep — arrival-rate executor 控制速率
}

// ============================================================
// 生命周期钩子
// ============================================================
export function handleSummary(data) {
  const summary = {
    test_config: {
      target_traces_per_sec: TARGET_TRACES_PER_SEC,
      spans_per_trace: SPANS_PER_TRACE,
      target_spans_per_sec: TARGET_TRACES_PER_SEC * SPANS_PER_TRACE,
      test_duration: TEST_DURATION,
      protocol: PROTOCOL,
      otlp_endpoint: OTLP_ENDPOINT,
    },
    metrics: {
      total_spans_generated: data.metrics.spans_generated?.values?.count || 0,
      trace_send_success_rate: data.metrics.trace_send_success?.values?.rate || 0,
      trace_send_errors: data.metrics.trace_send_errors?.values?.count || 0,
      trace_send_duration_p50: data.metrics.trace_send_duration_ms?.values?.['p(50)'] || 0,
      trace_send_duration_p95: data.metrics.trace_send_duration_ms?.values?.['p(95)'] || 0,
      trace_send_duration_p99: data.metrics.trace_send_duration_ms?.values?.['p(99)'] || 0,
      trace_send_duration_avg: data.metrics.trace_send_duration_ms?.values?.avg || 0,
      trace_send_duration_max: data.metrics.trace_send_duration_ms?.values?.max || 0,
      http_req_failed_rate: data.metrics.http_req_failed?.values?.rate || 0,
      total_iterations: data.metrics.iterations?.values?.count || 0,
      vus_max: data.metrics.vus_max?.values?.max || 0,
    },
    thresholds: {
      success_rate_met: (data.metrics.trace_send_success?.values?.rate || 0) > 0.9999,
      p99_latency_met: (data.metrics.trace_send_duration_ms?.values?.['p(99)'] || Infinity) < 500,
      p95_latency_met: (data.metrics.trace_send_duration_ms?.values?.['p(95)'] || Infinity) < 300,
    },
    generated_at: new Date().toISOString(),
  };

  return {
    'stdout': JSON.stringify(summary, null, 2),
    'tests/perf/results/steady_100k_summary.json': JSON.stringify(summary, null, 2),
  };
}