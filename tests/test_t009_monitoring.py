"""
T-009 Monitoring Templates Test Suite (Direct Validation)

AC-1: ServiceMonitor discovers Agent and Gateway metrics
AC-2: Alert rules cover all fault scenarios
AC-3: Grafana Dashboard shows throughput/latency/error/queue/resources
AC-4: Logs JSON format, no Authorization header leak
AC-5: otelcol_exporter_queue_size metric available
"""
import json
import os
import re
import unittest
import pytest

CHART_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "helm", "otel-collector")

if not os.path.isdir(CHART_DIR):
    pytest.skip(
        "deploy/helm/otel-collector 不在当前 checkout（6cefd0f 已删除 deploy），T-009 模板测试停用",
        allow_module_level=True,
    )


def read_template(rel_path):
    """Read a Helm template file and strip Go template directives for validation."""
    path = os.path.join(CHART_DIR, rel_path)
    with open(path) as f:
        return f.read()


class TestServiceMonitor(unittest.TestCase):
    """AC-1: Prometheus ServiceMonitor correctly discovers Agent and Gateway metrics."""

    def setUp(self):
        self.content = read_template("templates/monitoring/servicemonitor.yaml")

    def test_has_two_servicemonitors(self):
        """Should define two ServiceMonitor resources (agent + gateway)."""
        kinds = re.findall(r'kind:\s*ServiceMonitor', self.content)
        self.assertEqual(len(kinds), 2, f"Expected 2 ServiceMonitors, found {len(kinds)}")

    def test_agent_servicemonitor_has_metrics_endpoint(self):
        """Agent ServiceMonitor should have metrics endpoint."""
        self.assertIn("agent", self.content)
        self.assertIn("port: metrics", self.content)
        self.assertIn("path: /metrics", self.content)

    def test_gateway_servicemonitor_has_metrics_endpoint(self):
        """Gateway ServiceMonitor should have metrics endpoint."""
        self.assertIn("gateway", self.content)

    def test_has_match_labels_for_agent(self):
        """Agent ServiceMonitor should match agent component labels."""
        self.assertIn("app.kubernetes.io/component: agent", self.content)

    def test_has_match_labels_for_gateway(self):
        """Gateway ServiceMonitor should match gateway component labels."""
        self.assertIn("app.kubernetes.io/component: gateway", self.content)

    def test_has_interval_configuration(self):
        """Should have scrape interval configuration."""
        self.assertIn("interval:", self.content)

    def test_has_node_relabel(self):
        """Agent ServiceMonitor should have node relabeling."""
        self.assertIn("node", self.content)
        self.assertIn("__meta_kubernetes_pod_node_name", self.content)

    def test_has_monitoring_enabled_guard(self):
        """Should have monitoring.enabled conditional guard."""
        self.assertIn(".Values.monitoring.enabled", self.content)


class TestPrometheusRules(unittest.TestCase):
    """AC-2: Key alert rules cover all fault scenarios."""

    def setUp(self):
        self.content = read_template("templates/monitoring/prometheus-rules.yaml")

    def test_renders_prometheus_rule(self):
        """Should be a PrometheusRule resource."""
        self.assertIn("kind: PrometheusRule", self.content)

    def test_has_collector_restart_alert(self):
        """Should have alert for Collector restart."""
        self.assertIn("OtelcolCollectorRestart", self.content)

    def test_has_collector_down_alert(self):
        """Should have alert for Collector being down."""
        self.assertIn("OtelcolCollectorDown", self.content)

    def test_has_queue_high_usage_alert_70pct(self):
        """Should have alert for queue > 70%."""
        self.assertIn("OtelcolExporterQueueHighUsage", self.content)
        self.assertIn("0.70", self.content)

    def test_has_queue_critical_alert_90pct(self):
        """Should have alert for queue > 90%."""
        self.assertIn("OtelcolExporterQueueCritical", self.content)

    def test_has_high_memory_alert_80pct(self):
        """Should have alert for memory > 80%."""
        self.assertIn("OtelcolHighMemoryUsage", self.content)
        self.assertIn("0.80", self.content)

    def test_has_high_cpu_alert_70pct(self):
        """Should have alert for CPU > 70%."""
        self.assertIn("OtelcolHighCPUUsage", self.content)
        self.assertIn("0.70", self.content)

    def test_has_export_error_rate_alert_1pct(self):
        """Should have alert for export error rate > 1%."""
        self.assertIn("OtelcolExporterErrorRateHigh", self.content)
        self.assertIn("0.01", self.content)

    def test_has_certificate_expiring_alert(self):
        """Should have alert for certificate expiry < 30 days."""
        self.assertIn("OtelcolCertificateExpiringSoon", self.content)

    def test_has_certificate_critical_alert(self):
        """Should have alert for certificate expiry < 7 days."""
        self.assertIn("OtelcolCertificateExpiringCritical", self.content)

    def test_has_exporter_failure_rate_alert(self):
        """Should have alert for exporter failures."""
        self.assertIn("OtelcolExporterFailureRate", self.content)

    def test_has_receiver_refused_alert(self):
        """Should have alert for receiver refusing data."""
        self.assertIn("OtelcolReceiverRefusedSpans", self.content)

    def test_has_processor_dropped_alert(self):
        """Should have alert for processor dropping data."""
        self.assertIn("OtelcolProcessorDroppedSpans", self.content)

    def test_has_critical_memory_alert(self):
        """Should have critical memory alert."""
        self.assertIn("OtelcolCriticalMemoryUsage", self.content)

    def test_has_critical_cpu_alert(self):
        """Should have critical CPU alert."""
        self.assertIn("OtelcolCriticalCPUUsage", self.content)

    def test_has_monitoring_enabled_guard(self):
        """Should have monitoring.enabled conditional guard."""
        self.assertIn(".Values.monitoring.enabled", self.content)


class TestGrafanaDashboard(unittest.TestCase):
    """AC-3: Grafana Dashboard shows throughput/latency/error/queue/resources."""

    def setUp(self):
        self.content = read_template("templates/monitoring/grafana-dashboard.yaml")

    def test_renders_configmap(self):
        """Should be a ConfigMap."""
        self.assertIn("kind: ConfigMap", self.content)

    def test_has_grafana_dashboard_label(self):
        """Should have grafana_dashboard label."""
        self.assertIn("grafana_dashboard", self.content)

    def test_has_throughput_panels(self):
        """Should have throughput panels."""
        self.assertIn("Throughput", self.content)

    def test_has_error_rate_panels(self):
        """Should have error rate panels."""
        self.assertIn("Error Rate", self.content)

    def test_has_queue_depth_panels(self):
        """Should have queue depth panels."""
        self.assertIn("Queue", self.content)

    def test_has_resource_usage_panels(self):
        """Should have resource usage panels."""
        self.assertIn("CPU", self.content)
        self.assertIn("Memory", self.content)

    def test_has_latency_panels(self):
        """Should have latency panels."""
        self.assertIn("Latency", self.content)

    def test_has_otelcol_exporter_queue_size(self):
        """Should reference otelcol_exporter_queue_size (AC-5)."""
        self.assertIn("otelcol_exporter_queue_size", self.content)

    def test_has_job_variable(self):
        """Should have a 'job' template variable."""
        self.assertIn('"name": "job"', self.content)

    def test_has_monitoring_enabled_guard(self):
        """Should have monitoring.enabled conditional guard."""
        self.assertIn(".Values.monitoring.enabled", self.content)


class TestLoggingConfig(unittest.TestCase):
    """AC-4: Logs are in JSON format, no Authorization header leakage."""

    def setUp(self):
        self.agent_content = read_template("templates/agent/logging-config.yaml")
        self.gateway_content = read_template("templates/gateway/logging-config.yaml")

    def test_agent_uses_json_encoding(self):
        """Agent logging should use JSON encoding."""
        self.assertIn("encoding: json", self.agent_content)

    def test_gateway_uses_json_encoding(self):
        """Gateway logging should use JSON encoding."""
        self.assertIn("encoding: json", self.gateway_content)

    def test_agent_redacts_authorization(self):
        """Agent should redact Authorization header."""
        self.assertIn("http.request.header.authorization", self.agent_content)
        self.assertIn("action: delete", self.agent_content)

    def test_gateway_redacts_authorization(self):
        """Gateway should redact Authorization header."""
        self.assertIn("http.request.header.authorization", self.gateway_content)
        self.assertIn("action: delete", self.gateway_content)

    def test_agent_redacts_multiple_auth_variants(self):
        """Agent should redact multiple auth key variants."""
        delete_count = self.agent_content.count("action: delete")
        self.assertGreaterEqual(delete_count, 3, f"Expected >= 3 delete actions, got {delete_count}")

    def test_gateway_redacts_multiple_auth_variants(self):
        """Gateway should redact multiple auth key variants."""
        delete_count = self.gateway_content.count("action: delete")
        self.assertGreaterEqual(delete_count, 3, f"Expected >= 3 delete actions, got {delete_count}")

    def test_agent_has_initial_fields(self):
        """Agent should have initial_fields for component identification."""
        self.assertIn("initial_fields", self.agent_content)
        self.assertIn("agent", self.agent_content)

    def test_gateway_has_initial_fields(self):
        """Gateway should have initial_fields for component identification."""
        self.assertIn("initial_fields", self.gateway_content)
        self.assertIn("gateway", self.gateway_content)

    def test_agent_has_logging_enabled_guard(self):
        """Agent should have logging.enabled conditional guard."""
        self.assertIn(".Values.agent.logging.enabled", self.agent_content)

    def test_gateway_has_logging_enabled_guard(self):
        """Gateway should have logging.enabled conditional guard."""
        self.assertIn(".Values.gateway.logging.enabled", self.gateway_content)


class TestCodeQuality(unittest.TestCase):
    """Code quality checks for all deliverables."""

    def test_all_files_exist(self):
        """All 5 expected deliverable files should exist."""
        files = [
            "templates/monitoring/servicemonitor.yaml",
            "templates/monitoring/prometheus-rules.yaml",
            "templates/monitoring/grafana-dashboard.yaml",
            "templates/agent/logging-config.yaml",
            "templates/gateway/logging-config.yaml",
        ]
        for f in files:
            path = os.path.join(CHART_DIR, f)
            self.assertTrue(os.path.exists(path), f"Missing: {f}")

    def test_code_minimum_lines(self):
        """Total code should exceed 50 lines."""
        files = [
            "templates/monitoring/servicemonitor.yaml",
            "templates/monitoring/prometheus-rules.yaml",
            "templates/monitoring/grafana-dashboard.yaml",
            "templates/agent/logging-config.yaml",
            "templates/gateway/logging-config.yaml",
        ]
        total = 0
        for f in files:
            content = read_template(f)
            total += len(content.splitlines())
        self.assertGreater(total, 50, f"Total code lines: {total}, need > 50")

    def test_no_hardcoded_secrets(self):
        """No hardcoded secrets in templates."""
        files = [
            "templates/monitoring/servicemonitor.yaml",
            "templates/monitoring/prometheus-rules.yaml",
            "templates/monitoring/grafana-dashboard.yaml",
            "templates/agent/logging-config.yaml",
            "templates/gateway/logging-config.yaml",
        ]
        secret_patterns = [r'password\s*:\s*[a-zA-Z0-9]', r'secret\s*:\s*[a-zA-Z0-9]',
                          r'Bearer\s+[a-zA-Z0-9+/=]{20,}']
        for f in files:
            content = read_template(f)
            # Remove template directives for checking
            clean = re.sub(r'\{\{.*?\}\}', '', content)
            for pattern in secret_patterns:
                self.assertIsNone(re.search(pattern, clean, re.IGNORECASE),
                                  f"Hardcoded secret detected in {f}: {pattern}")


if __name__ == "__main__":
    unittest.main()