"""
Safe HTTP fetcher for ResearchPro external requests.

The fetcher validates URLs and every redirect target, resolves hostnames before
connecting, rejects disallowed IP ranges, and caps response bodies.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urljoin, urlparse

from domains.research_pro.url_utils import validate_safe_url as _validate_safe_url


_MAX_REDIRECTS = 5
MAX_BODY_BYTES = 512 * 1024
_USER_AGENT = "ResearchPro/1.0"
_CONNECT_TIMEOUT_SECONDS = 10
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class SafeFetchError(Exception):
    """Raised when a URL cannot be fetched safely."""


@dataclass(frozen=True)
class SafeFetchResponse:
    """Minimal response shape used by ResearchPro callers."""

    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    truncated: bool = False

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _is_disallowed_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any(
        [
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        ]
    )


class _ResolvedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, resolved_ip: str, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._resolved_ip = resolved_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._resolved_ip, self.port),
            self.timeout,
            self.source_address,
        )


class _ResolvedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int,
        resolved_ip: str,
        timeout: float,
        context: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(host, port=port, timeout=timeout, context=context)
        self._resolved_ip = resolved_ip

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._resolved_ip, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _SafeFetcher:
    """Fetch external HTTP(S) URLs with DNS, redirect, timeout, and size guards."""

    def __init__(
        self,
        *,
        timeout: float = _CONNECT_TIMEOUT_SECONDS,
        max_body_bytes: int = MAX_BODY_BYTES,
        max_redirects: int = _MAX_REDIRECTS,
        user_agent: str = _USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.max_body_bytes = max_body_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent

    def head(self, url: str) -> SafeFetchResponse:
        return self.fetch(url, method="HEAD")

    def get(self, url: str) -> SafeFetchResponse:
        return self.fetch(url, method="GET")

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
    ) -> SafeFetchResponse:
        method = method.upper()
        if method not in {"GET", "HEAD"}:
            raise SafeFetchError(f"Unsupported HTTP method: {method}")

        current_url = url
        current_method = method
        for _ in range(self.max_redirects + 1):
            response = self._single_request(current_url, current_method, headers or {})
            if response.status not in _REDIRECT_STATUSES:
                return response

            location = response.headers.get("location")
            if not location:
                return response

            current_url = urljoin(current_url, location)
            _validate_safe_url(current_url)
            self._resolve_safe_ip(urlparse(current_url))
            if response.status == 303 or (response.status in {301, 302} and current_method == "POST"):
                current_method = "GET"

        raise SafeFetchError(f"Too many redirects for {url}")

    def _single_request(
        self,
        url: str,
        method: str,
        extra_headers: Mapping[str, str],
    ) -> SafeFetchResponse:
        parsed, canonical_url = _validate_safe_url(url)
        resolved_ip = self._resolve_safe_ip(parsed)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = parsed.hostname or ""

        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
            "Connection": "close",
            "Host": parsed.netloc,
            **extra_headers,
        }

        if parsed.scheme == "https":
            conn: http.client.HTTPConnection = _ResolvedHTTPSConnection(
                host,
                port,
                resolved_ip,
                self.timeout,
            )
        else:
            conn = _ResolvedHTTPConnection(host, port, resolved_ip, self.timeout)

        try:
            conn.request(method, path, headers=headers)
            response = conn.getresponse()
            body = b""
            truncated = False
            if method != "HEAD":
                body = response.read(self.max_body_bytes + 1)
                if len(body) > self.max_body_bytes:
                    body = body[: self.max_body_bytes]
                    truncated = True
            return SafeFetchResponse(
                url=canonical_url,
                status=response.status,
                headers={key.lower(): value for key, value in response.getheaders()},
                body=body,
                truncated=truncated,
            )
        finally:
            conn.close()

    def _resolve_safe_ip(self, parsed) -> str:
        host = parsed.hostname
        if not host:
            raise SafeFetchError("Missing hostname")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise SafeFetchError(f"DNS resolution failed for {host}: {exc}") from exc

        addresses: list[str] = []
        for info in infos:
            address = info[4][0]
            if address not in addresses:
                addresses.append(address)

        if not addresses:
            raise SafeFetchError(f"DNS resolution returned no addresses for {host}")

        for address in addresses:
            try:
                if _is_disallowed_ip(address):
                    raise SafeFetchError(f"Disallowed resolved IP for {host}: {address}")
            except ValueError as exc:
                raise SafeFetchError(f"Invalid resolved IP for {host}: {address}") from exc

        return addresses[0]
