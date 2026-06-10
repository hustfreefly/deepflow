"""URL 安全验证工具测试。"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
import unittest
from domains.research_pro.url_utils import validate_safe_url, _is_private_or_disallowed_host


class TestValidateSafeUrl(unittest.TestCase):
    def test_valid_http(self):
        parsed, canonical = validate_safe_url("http://example.com/path")
        assert parsed.hostname == "example.com"
        assert canonical == "http://example.com/path"

    def test_valid_https(self):
        parsed, canonical = validate_safe_url("https://reuters.com/article/123?q=test")
        assert parsed.scheme == "https"
        assert "reuters.com" in canonical

    def test_reject_ftp(self):
        with self.assertRaises(ValueError):
            validate_safe_url("ftp://example.com/file")

    def test_reject_no_hostname(self):
        with self.assertRaises(ValueError):
            validate_safe_url("http://")

    def test_reject_userinfo(self):
        with self.assertRaises(ValueError):
            validate_safe_url("http://user:pass@example.com")

    def test_reject_localhost(self):
        with self.assertRaises(ValueError):
            validate_safe_url("http://localhost/admin")

    def test_reject_private_ip(self):
        with self.assertRaises(ValueError):
            validate_safe_url("http://192.168.1.1")

    def test_reject_loopback(self):
        with self.assertRaises(ValueError):
            validate_safe_url("http://127.0.0.1")

    def test_canonical_default_port_removed(self):
        _, canonical = validate_safe_url("http://example.com:80/path")
        assert ":80" not in canonical

    def test_canonical_non_default_port_kept(self):
        _, canonical = validate_safe_url("http://example.com:8080/path")
        assert ":8080" in canonical


class TestIsPrivateOrDisallowedHost(unittest.TestCase):
    def test_empty_hostname(self):
        assert _is_private_or_disallowed_host("") is True

    def test_localhost(self):
        assert _is_private_or_disallowed_host("localhost") is True

    def test_subdomain_localhost(self):
        assert _is_private_or_disallowed_host("api.localhost") is True

    def test_public_domain(self):
        assert _is_private_or_disallowed_host("reuters.com") is False

    def test_private_ip(self):
        assert _is_private_or_disallowed_host("10.0.0.1") is True


if __name__ == "__main__":
    unittest.main()
