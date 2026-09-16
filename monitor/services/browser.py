import atexit
import os
import socket
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .http import FetchError, _assert_public_host


_browser_lock = threading.Lock()
_browser_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="restock-browser")
_playwright = None
_context = None


def _profile_dir():
    configured = os.getenv("RESTOCK_BROWSER_PROFILE_DIR")
    if configured:
        return configured
    return str(Path(tempfile.gettempdir()) / f"restock-browser-{os.getpid()}")


def _clear_stale_profile_lock(profile_dir):
    profile = Path(profile_dir)
    lock = profile / "SingletonLock"
    try:
        owner = os.readlink(lock)
    except OSError:
        return
    owner_host, separator, owner_pid = owner.rpartition("-")
    belongs_to_live_process = (
        separator
        and owner_host == socket.gethostname()
        and owner_pid.isdigit()
        and Path(f"/proc/{owner_pid}").exists()
    )
    if belongs_to_live_process:
        return
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (profile / name).unlink()
        except FileNotFoundError:
            pass


def _start_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError("浏览器抓取依赖未安装") from exc
    return sync_playwright().start()


def _get_context():
    global _context, _playwright
    if _context is not None:
        return _context

    playwright = _start_playwright()
    try:
        executable_path = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or None
        profile_dir = _profile_dir()
        _clear_stale_profile_lock(profile_dir)
        context = playwright.chromium.launch_persistent_context(
            profile_dir,
            executable_path=executable_path,
            headless=True,
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
    except Exception:
        playwright.stop()
        raise

    _playwright = playwright
    _context = context
    _context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    _context.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in {"image", "media", "font"}
        else route.continue_(),
    )
    return _context


def _shutdown_browser():
    global _context, _playwright
    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass
        _context = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


atexit.register(_shutdown_browser)


def fetch_html_browser(url, allowed_domain, timeout=35_000, max_bytes=5_000_000):
    return _browser_executor.submit(
        _fetch_html_browser,
        url,
        allowed_domain,
        timeout,
        max_bytes,
    ).result()


def _fetch_html_browser(url, allowed_domain, timeout, max_bytes):
    _assert_public_host(url, allowed_domain)
    with _browser_lock:
        context = _get_context()
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_function(
                """
                () => {
                  const hasProductJson = Array.from(
                    document.querySelectorAll('script[type="application/ld+json"]')
                  ).some((script) => {
                    try {
                      const data = JSON.parse(script.textContent || 'null');
                      const nodes = Array.isArray(data) ? data : [data];
                      return nodes.some((node) => node && ['Product', 'ProductGroup'].includes(node['@type']));
                    } catch (_) {
                      return false;
                    }
                  });
                  const hasWooCommerceProduct = Boolean(
                    document.body?.classList.contains('single-product') &&
                    document.querySelector('h1.product_title, .summary.entry-summary')
                  );
                  const hasSmokingPipesProduct = Boolean(
                    document.querySelector('h1') &&
                    Array.from(document.querySelectorAll('h3')).some((node) =>
                      (node.textContent || '').trim().startsWith('Product Number:')
                    )
                  );
                  return hasProductJson || hasWooCommerceProduct || hasSmokingPipesProduct;
                }
                """,
                timeout=timeout,
            )
            final_url = page.url
            _assert_public_host(final_url, allowed_domain)
            html = page.content()
            if len(html.encode("utf-8")) > max_bytes:
                raise FetchError("商品页面超过 5MB 限制")
            return html, final_url
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(f"浏览器无法读取商品页面：{exc}") from exc
        finally:
            page.close()
