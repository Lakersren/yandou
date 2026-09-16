import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import httpx


class FetchError(RuntimeError):
    pass


def _assert_public_host(url, allowed_domain):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("只允许有效的 HTTP/HTTPS 商品地址")
    if parsed.username or parsed.password or (parsed.port and parsed.port not in {80, 443}):
        raise FetchError("商品地址不能包含账号信息或非标准端口")
    host = parsed.hostname.lower().rstrip(".")
    allowed = allowed_domain.lower().rstrip(".")
    if host != allowed and not host.endswith("." + allowed):
        raise FetchError("跳转到了商城域名之外")
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or default_port)}
    except socket.gaierror as exc:
        raise FetchError(f"域名解析失败：{exc}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise FetchError("商品地址解析到了非公网地址")


def fetch_html(url, allowed_domain, timeout=20, max_bytes=5_000_000):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RestockMonitor/1.0; +https://localhost)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    current = url
    transport = httpx.HTTPTransport(local_address="0.0.0.0")
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=False, transport=transport) as client:
        for _ in range(4):
            _assert_public_host(current, allowed_domain)
            with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("商城返回了无目标地址的跳转")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if not any(value in content_type for value in ("html", "json", "javascript")):
                    raise FetchError(f"不支持的页面类型：{content_type}")
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError("商品页面超过 5MB 限制")
                    chunks.append(chunk)
                encoding = response.encoding or "utf-8"
                return b"".join(chunks).decode(encoding, errors="replace"), str(response.url)
    raise FetchError("商城跳转次数过多")


def fetch_html_bright_data(url, allowed_domain, timeout=180, max_bytes=5_000_000):
    _assert_public_host(url, allowed_domain)
    api_key = os.getenv("BRIGHT_DATA_API_KEY", "").strip()
    zone = os.getenv("BRIGHT_DATA_ZONE", "web_unlocker1").strip()
    if not api_key:
        raise FetchError("Bright Data API Key 未配置")
    if not zone:
        raise FetchError("Bright Data Zone 未配置")

    request_timeout = httpx.Timeout(timeout, connect=20)
    last_error = None
    for attempt in range(2):
        chunks = []
        encoding = "utf-8"
        try:
            with httpx.Client(timeout=request_timeout) as client:
                with client.stream(
                    "POST",
                    "https://api.brightdata.com/request",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"zone": zone, "url": url, "format": "raw"},
                ) as response:
                    response.raise_for_status()
                    encoding = response.encoding or "utf-8"
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise FetchError("Bright Data 返回页面超过 5MB 限制")
                        chunks.append(chunk)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            html = b"".join(chunks).decode(encoding, errors="replace")
            if html.strip() and "</html>" in html.lower():
                return html, url
            last_error = exc
            if attempt == 0:
                continue
            raise FetchError(f"Bright Data 请求失败：{exc}") from exc

        html = b"".join(chunks).decode(encoding, errors="replace")
        if html.strip():
            return html, url
        last_error = FetchError("Bright Data 返回了空页面")

    raise last_error
