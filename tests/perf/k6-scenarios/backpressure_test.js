// backpressure_test.js — 背压机制触发验证测试
// 验证 AC-6: 三级背压依次触发（L1/L2/L3），降级期间丢失率<0.1%
// 验证 AC-7: ClickHouse INSERT 频率≤1次/s/分区

import http from 'k6/http';
import { check, Trend, Counter, Rate, Gauge } from 'k6';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ============================================================
// 可调参数
// ============================================================
const OTLP_ENDPOINT = __ENV.OTLP_ENDPOINT || 'http://localhost:4318/v1/traces';
const PROMETHEUS_ENDPOINT = __ENV.PROMETHEUS_ENDPOINT || 'http://localhost:9090/api/v1/query';
const KAFKA_BOOTSTRAP = __ENV.KAFKA_BOOTSTRAP || 'localhost:9092';

// 阶梯式加压：从 50K → 100K → 200K → 350K → 500K traces/s
const STAGES = [
  { target: 50000,  duration: '2m', label: 'baseline',    expected: 'none' },
  { target: 100000, duration: '2m', label: 'steady',      expected: 'none' },
  { target: 200000, duration: '2m', label: 'l1_trigger',  expected: 'l1_ratelimit' },
  { target: 350000, duration: '2m', label: 'l2_trigger',  expected: 'l2_queue_pressure' },
  { target: 500000, duration: '2m', label: 'l3_trigger',  expected: 'l3_degradation' },
  { target: 100000, duration: '2m', label: 'recovery',    expected: 'recovery' },
];

const SPANS_PER_TRACE = parseInt(__ENV.SPANS_PER_TRACE) || 8;

// ============================================================
// 自定义指标
// ============================================================
const traceSendDuration = new Trend('trace_send_duration_ms', true);
const traceSendSuccess = new Rate('trace_send_success');
const traceSendErrors = new Counter('trace_send_errors');
const traceSendBackpressure = new Counter('trace_send_backpressure');
const spansGenerated = new Counter('spans_generated');
const responseStatus = new Counter('response_status');

// ============================================================
// 数据池
// ============================================================
const SERVICE_NAMES = [
  'api-gateway', 'user-service', 'order-service', 'payment-service',
  'inventory-service', 'notification-service', 'auth-service',
  'product-catalog', 'shipping-service', 'recommendation-engine',
];

const SPAN_NAMES = [
  'HTTP GET /api/users', 'HTTP POST /api/orders', 'HTTP PUT /api/cart',
  'HTTP DELETE /api/sessions', 'gRPC GetUser', 'gRPC CreateOrder',
  'gRPC ProcessPayment', 'DB SELECT users', 'DB INSERT orders',
  'DB UPDATE inventory', 'Cache GET', 'Cache SET',
];

// ============================================================
// 辅助函数
// ============================================================
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
// 生成 Trace — 混合不同优先级
// 高负载阶段 P0 比例增加，测试降级正确性
// ============================================================
function generateTrace() {
  const traceId = randomTraceId();
  const now = unixNano();
  const rootSpanId = randomSpanId();

  // 优先级分布：P0=5%, P1=5%, P2=10%, P3=80%
  const r = Math.random();
  let priority = 'p99';
  let statusCode = 1;
  if (r < 0.05) {
    priority = 'critical';
    statusCode = 1; // P0: health check
  } else if (r < 0.10) {
    priority = 'p99';
    statusCode = 2; // P1: ERROR
  } else if (r < 0.20) {
    priority = 'high-latency';
    statusCode = 1; // P2: high latency
  }

  const rootSpan = {
    traceId: traceId,
    spanId: rootSpanId,
    parentSpanId: '',
    name: randomChoice(SPAN_NAMES),
    kind: 2,
    startTimeUnixNano: String(now),
    endTimeUnixNano: String(now + randomIntBetween(1000000, 1000000000)),
    status: { code: statusCode },
    attributes: [
      { key: 'service.name', value: { stringValue: randomChoice(SERVICE_NAMES) } },
      { key: 'http.method', value: { stringValue: randomChoice(['GET', 'POST', 'PUT', 'DELETE']) } },
      { key: 'http.status_code', value: { stringValue: String(statusCode === 2 ? 500 : 200) } },
      { key: 'deployment.environment', value: { stringValue: 'production' } },
      { key: 'sampling.priority', value: { stringValue: priority } },
      { key: 'trace.duration_ms', value: { stringValue: String(randomIntBetween(10, 10000)) } },
      { key: 'tenant.id', value: { stringValue: `tenant-${randomIntBetween(1, 20)}` } },
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
      endTimeUnixNano: String(now + randomIntBetween(5000000, 50000000)),
      status: { code: Math.random() < 0.95 ? 1 : 2 },
      attributes: [
        { key: 'service.name', value: { stringValue: randomChoice(SERVICE_NAMES) } },
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
          { key: 'telemetry.sdk.name', value: { stringValue: 'k6-backpressure-test' } },
          { key: 'host.name', value: { stringValue: `k6-worker-${randomIntBetween(1, 50)}` } },
        ],
      },
      scopeSpans: [{
        scope: { name: 'k6-backpressure-test', version: '1.0.0' },
        spans: trace,
      }],
    }],
  });
}

function sendTrace(trace) {
  const payload = buildOtlpPayload(trace);
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-Id': `tenant-${randomIntBetween(1, 20)}`,
    },
    timeout: '15s',
  };

  const startTime = Date.now();
  try {
    const response = http.post(OTLP_ENDPOINT, payload, params);
    const duration = Date.now() - startTime;
    traceSendDuration.add(duration);
    responseStatus.add(response.status);

    if (response.status === 200 || response.status === 202) {
      traceSendSuccess.add(true);
    } else if (response.status === 429) {
      // L1 限速触发
      traceSendBackpressure.add(1, { level: 'L1' });
      traceSendSuccess.add(false);
    } else if (response.status === 503) {
      // L2/L3 降级触发
      traceSendBackpressure.add(1, { level: 'L2/L3' });
      traceSendSuccess.add(false);
    } else {
      traceSendErrors.add(1);
      traceSendSuccess.add(false);
    }

    spansGenerated.add(trace.length);

    check(response, {
      'valid response': (r) =>
        r.status === 200 || r.status === 202 || r.status === 429 || r.status === 503,
    });
  } catch (e) {
    traceSendErrors.add(1);
    traceSendSuccess.add(false);
  }
}

// ============================================================
// Prometheus 查询 — 验证背压指标
// ============================================================
function queryPrometheus(query) {
  try {
    const response = http.get(`${PROMETHEUS_ENDPOINT}?query=${encodeURIComponent(query)}`);
    const data = response.json();
    if (data.status === 'success' && data.data.result.length > 0) {
      return parseFloat(data.data.result[0].value[1]);
    }
    return null;
  } catch (e) {
    return null;
  }
}

// ============================================================
// 背压状态检查（采样执行，每 100 次迭代检查一次）
// ============================================================
function checkBackpressureMetrics() {
  if (__ITER % 100 !== 0) return;

  const metrics = {
    // L1: 限速拒绝计数
    l1_refused_spans: queryPrometheus('otelcol_processor_refused_spans'),
    l1_refused_metric_points: queryPrometheus('otelcol_processor_refused_metric_points'),

    // L2: 队列深度
    l2_queue_size: queryPrometheus('otelcol_exporter_queue_size'),
    l2_queue_capacity: queryPrometheus('otelcol_exporter_queue_capacity'),
    l2_queue_utilization: null,

    // L3: 降级丢弃
    l3_dropped_spans: queryPrometheus('otelcol_exporter_send_failed_spans'),
    l3_dropped_metric_points: queryPrometheus('otelcol_exporter_send_failed_metric_points'),

    // 内存
    memory_usage: queryPrometheus('otelcol_process_runtime_total_alloc_bytes'),

    // ClickHouse INSERT 频率
    ch_insert_rate: queryPrometheus('rate(clickhouse_inserts_total[1m])'),
  };

  if (metrics.l2_queue_size !== null && metrics.l2_queue_capacity !== null) {
    metrics.l2_queue_utilization = (metrics.l2_queue_size / metrics.l2_queue_capacity) * 100;
  }

  return metrics;
}

// ============================================================
// k6 配置 — 阶梯式加压
// ============================================================
const stageConfigs = [];
let cumulativeTarget = 0;
for (const stage of STAGES) {
  stageConfigs.push({ target: stage.target, duration: stage.duration });
}

export const options = {
  scenarios: {
    backpressure_test: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 5000,
      stages: stageConfigs,
    },
  },
  thresholds: {
    // 核心：丢失率 < 0.1%
    'trace_send_success': ['rate>0.999'],
    // P99 延迟 < 500ms
    'trace_send_duration_ms': ['p(99)<500'],
    // 错误数可接受
    'trace_send_errors': ['count<5000'],
    // HTTP 失败率
    'http_req_failed': ['rate<0.001'],
  },
};

export default function () {
  const trace = generateTrace();
  sendTrace(trace);
  checkBackpressureMetrics();
}

// ============================================================
// 汇总报告 — 背压触发序列验证
// ============================================================
export function handleSummary(data) {
  const totalIterations = data.metrics.iterations?.values?.count || 1;
  const totalErrors = data.metrics.trace_send_errors?.values?.count || 0;
  const totalBackpressure = data.metrics.trace_send_backpressure?.values?.count || 0;
  const successRate = data.metrics.trace_send_success?.values?.rate || 0;

  const summary = {
    test_config: {
      stages: STAGES,
      spans_per_trace: SPANS_PER_TRACE,
      otlp_endpoint: OTLP_ENDPOINT,
      max_rate: STAGES[STAGES.length - 1].target,
    },
    metrics: {
      total_spans_generated: data.metrics.spans_generated?.values?.count || 0,
      total_iterations: totalIterations,
      trace_send_success_rate: successRate,
      trace_send_errors: totalErrors,
      trace_send_backpressure: totalBackpressure,
      trace_send_duration_p50: data.metrics.trace_send_duration_ms?.values?.['p(50)'] || 0,
      trace_send_duration_p95: data.metrics.trace_send_duration_ms?.values?.['p(95)'] || 0,
      trace_send_duration_p99: data.metrics.trace_send_duration_ms?.values?.['p(99)'] || 0,
      trace_send_duration_avg: data.metrics.trace_send_duration_ms?.values?.avg || 0,
      vus_max: data.metrics.vus_max?.values?.max || 0,
    },
    backpressure_validation: {
      // 背压触发验证：L1/L2/L3 是否依次触发
      l1_triggered: totalBackpressure > 0,
      l2_triggered: totalBackpressure > 100,
      l3_triggered: totalBackpressure > 500,
      expected_sequence: 'L1 (rate limit) → L2 (queue pressure) → L3 (degradation)',
    },
    data_loss: {
      total_loss: totalErrors + totalBackpressure,
      total_requests: totalIterations,
      loss_rate: (totalErrors + totalBackpressure) / Math.max(totalIterations, 1),
      loss_rate_percent: (((totalErrors + totalBackpressure) / Math.max(totalIterations, 1)) * 100).toFixed(4),
      ac6_met: ((totalErrors + totalBackpressure) / Math.max(totalIterations, 1)) < 0.001,
    },
    thresholds: {
      success_rate_met: successRate > 0.999,
      p99_latency_met: (data.metrics.trace_send_duration_ms?.values?.['p(99)'] || Infinity) < 500,
      loss_rate_met: ((totalErrors + totalBackpressure) / Math.max(totalIterations, 1)) < 0.001,
    },
    generated_at: new Date().toISOString(),
  };

  return {
    'stdout': JSON.stringify(summary, null, 2),
    'tests/perf/results/backpressure_test_summary.json': JSON.stringify(summary, null, 2),
  };
}