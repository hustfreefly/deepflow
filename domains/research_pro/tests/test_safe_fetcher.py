"""
ResearchPro 单元测试 — _SafeFetcher
"""

import core.bootstrap

import socket
import unittest
from unittest.mock import patch, MagicMock

from domains.research_pro.safe_fetcher import (
    MAX_BODY_BYTES,
    _SafeFetcher,
    SafeFetchError,
    SafeFetchResponse,
)


def _public_addrinfo(host: str, port: int, *args, **kwargs):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", port),
        )
    ]


class _FakeHTTPResponse:
    status = 200

    def getheaders(self):
        return []

    def read(self, size=-1):
        return b"x" * size


class _FakeConnection:
    def __init__(self, *args, **kwargs):
        self.closed = False

    def request(self, *args, **kwargs):
        return None

    def getresponse(self):
        return _FakeHTTPResponse()

    def close(self):
        self.closed = True


class TestSafeFetcher(unittest.TestCase):
    def test_rejects_hostname_resolving_to_private_ip(self):
        fetcher = _SafeFetcher()

        with patch(
            "domains.research_pro.safe_fetcher.socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 80),
                )
            ],
        ):
            with self.assertRaises(SafeFetchError):
                fetcher.get("http://safe-looking.example/")

    def test_redirect_target_is_revalidated(self):
        fetcher = _SafeFetcher()

        with patch.object(
            fetcher,
            "_single_request",
            return_value=SafeFetchResponse(
                url="http://example.com/",
                status=302,
                headers={"location": "http://127.0.0.1/admin"},
                body=b"",
            ),
        ):
            with self.assertRaises(ValueError):
                fetcher.get("http://example.com/")

    def test_get_body_is_limited_and_truncation_recorded(self):
        fetcher = _SafeFetcher(max_body_bytes=MAX_BODY_BYTES)

        with patch("domains.research_pro.safe_fetcher.socket.getaddrinfo", side_effect=_public_addrinfo):
            with patch("domains.research_pro.safe_fetcher._ResolvedHTTPConnection", _FakeConnection):
                response = fetcher.get("http://example.com/big")

        self.assertEqual(len(response.body), MAX_BODY_BYTES)
        self.assertTrue(response.truncated)

    def test_default_max_body_bytes_uses_module_constant(self):
        fetcher = _SafeFetcher()
        self.assertEqual(fetcher.max_body_bytes, MAX_BODY_BYTES)

    def test_timeout_handling(self):
        """模拟超时场景（mock socket 超时）"""
        fetcher = _SafeFetcher()

        class _TimeoutConnection:
            def __init__(self, *args, **kwargs): pass
            def request(self, *args, **kwargs):
                raise socket.timeout("Connection timed out")
            def getresponse(self):
                return _FakeHTTPResponse()
            def close(self): pass

        with patch("domains.research_pro.safe_fetcher.socket.getaddrinfo", side_effect=_public_addrinfo):
            with patch("domains.research_pro.safe_fetcher._ResolvedHTTPConnection", _TimeoutConnection):
                with self.assertRaises((SafeFetchError, socket.timeout)):
                    fetcher.get("http://example.com/")

    def test_dns_resolution_failure(self):
        """模拟 DNS 解析失败（mock socket.gaierror）"""
        fetcher = _SafeFetcher()

        with patch("domains.research_pro.safe_fetcher.socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
            with self.assertRaises(SafeFetchError) as ctx:
                fetcher.get("http://nonexistent.domain.xyz/")
            self.assertIn("DNS resolution failed", str(ctx.exception))

    def test_non_200_status(self):
        """测试非 200 状态码处理"""
        fetcher = _SafeFetcher()

        class _Fake404Response:
            status = 404
            def getheaders(self):
                return [("content-type", "text/html")]
            def read(self, size=-1):
                return b"Not Found"

        class _Fake404Connection:
            def __init__(self, *args, **kwargs): pass
            def request(self, *args, **kwargs):
                return None
            def getresponse(self):
                return _Fake404Response()
            def close(self):
                pass

        with patch("domains.research_pro.safe_fetcher.socket.getaddrinfo", side_effect=_public_addrinfo):
            with patch("domains.research_pro.safe_fetcher._ResolvedHTTPConnection", _Fake404Connection):
                response = fetcher.get("http://example.com/notfound")

        self.assertEqual(response.status, 404)
        self.assertEqual(response.body, b"Not Found")

    def test_max_redirects_exceeded(self):
        """测试超过最大重定向次数"""
        fetcher = _SafeFetcher(max_redirects=2)

        class _FakeRedirectResponse:
            def __init__(self, location):
                self.status = 302
                self._location = location
            def getheaders(self):
                return [("location", self._location)]
            def read(self, size=-1):
                return b""

        class _FakeRedirectConnection:
            _call_count = 0
            def __init__(self, *args, **kwargs): pass
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                _FakeRedirectConnection._call_count += 1
                return _FakeRedirectResponse(f"http://example.com/redirect{_FakeRedirectConnection._call_count}")
            def close(self):
                pass

        with patch("domains.research_pro.safe_fetcher.socket.getaddrinfo", side_effect=_public_addrinfo):
            with patch("domains.research_pro.safe_fetcher._ResolvedHTTPConnection", _FakeRedirectConnection):
                with self.assertRaises(SafeFetchError) as ctx:
                    fetcher.get("http://example.com/start")
                self.assertIn("Too many redirects", str(ctx.exception))

    def test_head_method(self):
        """独立测试 head() 方法"""
        fetcher = _SafeFetcher()

        class _FakeHeadResponse:
            status = 200
            def getheaders(self):
                return [("content-length", "1024")]
            def read(self, size=-1):
                return b""  # HEAD should not return body

        class _FakeHeadConnection:
            def __init__(self, *args, **kwargs): pass
            def request(self, method, path, headers=None):
                pass
            def getresponse(self):
                return _FakeHeadResponse()
            def close(self):
                pass

        with patch("domains.research_pro.safe_fetcher.socket.getaddrinfo", side_effect=_public_addrinfo):
            with patch("domains.research_pro.safe_fetcher._ResolvedHTTPConnection", _FakeHeadConnection):
                response = fetcher.head("http://example.com/resource")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"")
        self.assertFalse(response.truncated)

    def test_unsupported_method(self):
        """测试不支持的 HTTP 方法"""
        fetcher = _SafeFetcher()

        with self.assertRaises(SafeFetchError) as ctx:
            fetcher.fetch("http://example.com/", method="POST")
        self.assertIn("Unsupported HTTP method", str(ctx.exception))

        with self.assertRaises(SafeFetchError) as ctx:
            fetcher.fetch("http://example.com/", method="DELETE")
        self.assertIn("Unsupported HTTP method", str(ctx.exception))

        with self.assertRaises(SafeFetchError) as ctx:
            fetcher.fetch("http://example.com/", method="PUT")
        self.assertIn("Unsupported HTTP method", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
