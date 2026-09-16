# Ant Design Pro Operations Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standard Ant Design Pro operations console at `/console/` while preserving the existing Django inventory monitor, scheduler, and DingTalk notification behavior.

**Architecture:** A React/TypeScript console uses same-origin JSON endpoints implemented in Django. Django Session and CSRF remain the only authentication mechanism; Celery owns checks and notification work; Django Admin remains a technical maintenance surface.

**Tech Stack:** Python 3.13, Django 5.2, PostgreSQL 17, Redis 7, Celery 5.6, React 19, TypeScript 5.9, Vite 7, Ant Design 5, Ant Design Pro Components 2, Vitest, Playwright, Docker Compose, Nginx

**Spec:** `docs/superpowers/specs/2026-09-14-ant-design-pro-console-design.md`

## Global Constraints

- The operations console lives at `/console/`; Django Admin remains at `/admin/` for technical maintenance only.
- The sidebar contains Workbench, Products, Restock Events, Failures, and DingTalk Channels.
- Adding a monitored product has exactly one required field: a supported product URL.
- The system supplies site, interval, baseline, site-group notification, and all-group notification defaults.
- Existing first-check baseline, two-confirmation restock detection, retry, and notification deduplication behavior must not regress.
- Console API endpoints require an authenticated Django staff user and valid CSRF for mutations.
- Full DingTalk webhook URLs, signing secrets, raw pages, parser selectors, Redis, and Celery details never appear in Console API responses.
- UI tokens are `#f0f2f5` page background, `#1677ff` primary, `#001529` sidebar, `#52c41a` success, `#faad14` warning, and `#ff4d4f` error.
- Desktop viewports 1440x900 and 1280x800 and mobile viewport 390x844 must have no overlap, clipped controls, or unreadable text.

---

## File Structure

New backend files:

- `monitor/services/catalog.py`: create, restore, pause, and soft-delete products without HTTP concerns.
- `monitor/console/__init__.py`: Console API package marker.
- `monitor/console/auth.py`: staff JSON guard, request JSON parser, and response helpers.
- `monitor/console/serializers.py`: stable model-to-JSON mappings.
- `monitor/console/session_api.py`: session, logout, dashboard, and scheduler health.
- `monitor/console/products_api.py`: product list, detail, add, update, delete, and check endpoints.
- `monitor/console/activity_api.py`: restock event and failure endpoints.
- `monitor/console/channels_api.py`: masked DingTalk channel CRUD and test endpoint.
- `monitor/console/urls.py`: versioned API URL table.
- `monitor/templates/console/index.html`: authenticated React shell.
- `monitor/migrations/0003_product_soft_delete_and_creator.py`: product lifecycle fields.
- `tests/test_catalog.py`, `tests/test_console_session_api.py`, `tests/test_console_products_api.py`, `tests/test_console_activity_api.py`, `tests/test_console_channels_api.py`: backend coverage.

New frontend files:

- `console/package.json`, `console/tsconfig.json`, `console/vite.config.ts`, `console/index.html`: frontend toolchain.
- `console/src/main.tsx`: React entry.
- `console/src/app.tsx`: routes and query provider.
- `console/src/api/client.ts`, `console/src/api/types.ts`: typed same-origin API boundary.
- `console/src/test/render.tsx`, `console/src/test/mocks.ts`: shared isolated router/query renderer and typed API mocks.
- `console/src/layout/ConsoleLayout.tsx`, `console/src/layout/layout.css`: Ant Design Pro shell.
- `console/src/pages/DashboardPage.tsx`: summary view.
- `console/src/pages/ProductsPage.tsx`: product table and filters.
- `console/src/components/AddProductModal.tsx`: URL-only add flow.
- `console/src/components/ProductDrawer.tsx`: product details and variants.
- `console/src/pages/EventsPage.tsx`, `console/src/pages/FailuresPage.tsx`, `console/src/pages/ChannelsPage.tsx`: remaining modules.
- `console/src/test/setup.ts` and colocated `*.test.tsx`: frontend tests.
- `console/e2e/console.spec.ts`: browser workflow and viewport checks.

Modified integration files:

- `monitor/models.py`, `monitor/tasks.py`, `monitor/admin.py`: lifecycle and heartbeat integration.
- `restock/settings.py`, `restock/urls.py`: Redis cache, Console shell, and API routes.
- `Dockerfile`, `docker-compose.yml`, `deploy/nginx/default.conf`, `.dockerignore`, `.gitignore`: frontend build and serving.
- `README.md`: operator and deployment instructions.

---

### Task 1: Product Lifecycle and Scheduler Heartbeat

**Files:**
- Modify: `monitor/models.py`
- Modify: `monitor/tasks.py`
- Modify: `restock/settings.py`
- Create: `monitor/migrations/0003_product_soft_delete_and_creator.py`
- Create: `tests/test_product_lifecycle.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Produces: `Product.objects` for non-deleted products, `Product.all_objects` for all rows, `Product.soft_delete()`, `Product.restore()`, and cache key `monitor:scheduler:heartbeat` containing an ISO timestamp.
- Consumes: existing `Product`, `dispatch_due_products()`, Redis URL, and Django user model.

- [ ] **Step 1: Write failing lifecycle tests**

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from monitor.models import Product, Region, Site


class ProductLifecycleTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")

    def test_soft_delete_hides_product_but_preserves_row(self):
        product = Product.objects.create(site=self.site, url="https://smokingpipes.com/p/1")
        product.soft_delete()
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(Product.all_objects.filter(pk=product.pk).exists())
        self.assertFalse(Product.all_objects.get(pk=product.pk).enabled)

    def test_restore_reactivates_product(self):
        product = Product.objects.create(site=self.site, url="https://smokingpipes.com/p/2")
        product.soft_delete()
        product.restore()
        self.assertTrue(Product.objects.get(pk=product.pk).enabled)
        self.assertIsNone(Product.objects.get(pk=product.pk).deleted_at)

    def test_created_by_accepts_existing_staff_user(self):
        user = get_user_model().objects.create_user("operator")
        product = Product.objects.create(site=self.site, url="https://smokingpipes.com/p/3", created_by=user)
        self.assertEqual(product.created_by, user)
```

- [ ] **Step 2: Run lifecycle tests and verify failure**

Run: `.venv/bin/python manage.py test tests.test_product_lifecycle -v 2`

Expected: FAIL because `soft_delete`, `restore`, `all_objects`, `deleted_at`, and `created_by` do not exist.

- [ ] **Step 3: Implement product lifecycle fields and managers**

```python
class ActiveProductManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Product(models.Model):
    objects = ActiveProductManager()
    all_objects = models.Manager()
    deleted_at = models.DateTimeField("删除时间", null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="创建人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="monitored_products",
    )

    class Meta:
        verbose_name = "监控商品"
        verbose_name_plural = "监控商品"
        base_manager_name = "all_objects"

    def soft_delete(self):
        self.enabled = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["enabled", "deleted_at", "updated_at"])

    def restore(self):
        self.enabled = True
        self.deleted_at = None
        self.next_check_at = timezone.now()
        self.save(update_fields=["enabled", "deleted_at", "next_check_at", "updated_at"])
```

Import `settings` from `django.conf`. Generate the migration with `.venv/bin/python manage.py makemigrations monitor`; confirm it adds exactly the two fields and manager metadata.

- [ ] **Step 4: Add Redis cache and heartbeat behavior**

```python
# restock/settings.py
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# monitor/tasks.py
from django.core.cache import cache

@shared_task(name="monitor.tasks.dispatch_due_products")
def dispatch_due_products():
    now = timezone.now()
    cache.set("monitor:scheduler:heartbeat", now.isoformat(), timeout=300)
    ids = list(Product.objects.filter(
        enabled=True, site__enabled=True, next_check_at__lte=now,
    ).values_list("id", flat=True)[:500])
    for product_id in ids:
        Product.objects.filter(pk=product_id, next_check_at__lte=now).update(
            next_check_at=now + timedelta(minutes=2)
        )
        check_product.delay(product_id)
    return len(ids)
```

Add a test using `@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})` and `@patch("monitor.tasks.check_product.delay")`; assert the heartbeat is present after dispatch.

- [ ] **Step 5: Run backend regression tests**

Run: `.venv/bin/python manage.py test -v 2`

Expected: all existing and new tests PASS; `manage.py makemigrations --check --dry-run` prints `No changes detected`.

- [ ] **Step 6: Commit lifecycle support**

```bash
git add monitor/models.py monitor/tasks.py restock/settings.py monitor/migrations/0003_product_soft_delete_and_creator.py tests/test_product_lifecycle.py tests/test_models.py
git commit -m "feat: add product lifecycle and scheduler heartbeat"
```

---

### Task 2: Console Authentication, Session, and Dashboard API

**Files:**
- Create: `monitor/console/__init__.py`
- Create: `monitor/console/auth.py`
- Create: `monitor/console/serializers.py`
- Create: `monitor/console/session_api.py`
- Create: `monitor/console/urls.py`
- Modify: `restock/urls.py`
- Create: `monitor/templates/console/index.html`
- Create: `tests/test_console_session_api.py`

**Interfaces:**
- Produces: `staff_json_required(view)`, `json_body(request)`, `ok(data, status=200)`, `error(code, message, status, fields=None)`, `GET /api/console/v1/session`, `POST /api/console/v1/logout`, `GET /api/console/v1/dashboard`, and authenticated `/console/` shell.
- Consumes: Task 1 heartbeat cache key and existing Product, Variant, StockEvent, CrawlFailure, and NotificationLog models.

- [ ] **Step 1: Write failing session and dashboard tests**

```python
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ConsoleSessionApiTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("operator", is_staff=True)

    def test_anonymous_api_receives_json_401(self):
        response = self.client.get("/api/console/v1/session")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "authentication_required")

    def test_session_reports_real_scheduler_health(self):
        self.client.force_login(self.staff)
        cache.set("monitor:scheduler:heartbeat", timezone.now().isoformat(), 300)
        response = self.client.get("/api/console/v1/session")
        self.assertEqual(response.json()["data"]["scheduler"], "healthy")

    def test_stale_scheduler_is_unhealthy(self):
        self.client.force_login(self.staff)
        stale = timezone.now() - timedelta(seconds=181)
        cache.set("monitor:scheduler:heartbeat", stale.isoformat(), 300)
        response = self.client.get("/api/console/v1/session")
        self.assertEqual(response.json()["data"]["scheduler"], "unhealthy")

    def test_non_staff_cannot_open_console(self):
        user = get_user_model().objects.create_user("reader")
        self.client.force_login(user)
        response = self.client.get("/console/")
        self.assertEqual(response.status_code, 302)
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `.venv/bin/python manage.py test tests.test_console_session_api -v 2`

Expected: FAIL with unresolved Console routes.

- [ ] **Step 3: Implement JSON authentication helpers**

```python
# monitor/console/auth.py
import json
from functools import wraps

from django.http import JsonResponse


def ok(data, status=200):
    return JsonResponse({"data": data}, status=status)


def error(code, message, status=400, fields=None):
    payload = {"code": code, "message": message}
    if fields:
        payload["fields"] = fields
    return JsonResponse(payload, status=status)


def json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("请求内容不是有效 JSON") from exc


def staff_json_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error("authentication_required", "请先登录", 401)
        if not request.user.is_staff:
            return error("permission_denied", "没有后台访问权限", 403)
        return view(request, *args, **kwargs)
    return wrapped
```

Mutating views continue through Django `CsrfViewMiddleware`; do not add `csrf_exempt` anywhere in the Console package.

- [ ] **Step 4: Implement session, logout, dashboard, and shell views**

`session_api.py` must parse the cached ISO time with `datetime.fromisoformat`, treat missing/invalid/older-than-180-second values as `unhealthy`, and return:

```python
{
    "user": {"id": request.user.id, "username": request.user.get_username()},
    "scheduler": "healthy",
}
```

`dashboard` returns exact keys `monitored_products`, `in_stock_variants`, `restocks_24h`, `failures_24h`, `recent_products`, `recent_events`, and `recent_failures`. Count failed `NotificationLog` rows together with `CrawlFailure` rows for the failure total.

Implement the shell with `@staff_member_required(login_url="/admin/login/")` and `@ensure_csrf_cookie`, rendering `console/index.html`. Implement logout with `django.contrib.auth.logout(request)` on POST and return `{"redirect": "/admin/login/?next=/console/"}`.

- [ ] **Step 5: Register routes**

```python
# monitor/console/urls.py
from django.urls import path
from . import session_api

urlpatterns = [
    path("session", session_api.session, name="console_session"),
    path("logout", session_api.logout_view, name="console_logout"),
    path("dashboard", session_api.dashboard, name="console_dashboard"),
]

# restock/urls.py
urlpatterns = [
    path("healthz", healthz),
    path("api/console/v1/", include("monitor.console.urls")),
    path("console/", console_shell, name="console"),
    path("console/<path:route>", console_shell),
    path("admin/", admin.site.urls),
]
```

The shell contains `<div id="root"></div>`, `/static/console/assets/app.css`, and a module script for `/static/console/assets/app.js`.

- [ ] **Step 6: Run tests and commit**

Run: `.venv/bin/python manage.py test tests.test_console_session_api -v 2`

Expected: all Console session tests PASS.

```bash
git add monitor/console monitor/templates/console/index.html restock/urls.py tests/test_console_session_api.py
git commit -m "feat: add console session and dashboard API"
```

---

### Task 3: Catalog Service and Product API

**Files:**
- Create: `monitor/services/catalog.py`
- Create: `monitor/console/products_api.py`
- Modify: `monitor/console/serializers.py`
- Modify: `monitor/console/urls.py`
- Modify: `monitor/admin.py`
- Modify: `restock/settings.py`
- Create: `tests/test_catalog.py`
- Create: `tests/test_console_products_api.py`

**Interfaces:**
- Produces: `add_product(url: str, user: User | None) -> tuple[Product, str]`, where outcome is `created`, `existing`, or `restored`; `fetch_observation(site: Site, url: str) -> ProductObservation`; `apply_baseline(product: Product, observation: ProductObservation) -> None`; product list/detail JSON; mutation endpoints.
- Consumes: `get_adapter(site).fetch(url)`, Task 1 lifecycle methods, `check_product.delay(product_id)`, and Task 2 JSON helpers.

- [ ] **Step 1: Write failing catalog tests**

```python
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from monitor.models import Product, Region, Site, StockStatus
from monitor.services.catalog import UnsupportedSite, UnreadableStock, add_product
from monitor.services.scraper import ProductObservation, VariantObservation


class CatalogTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        self.user = get_user_model().objects.create_user("operator")
        self.observation = ProductObservation(
            name="Test Flake",
            canonical_url="https://smokingpipes.com/p/1",
            variants=[VariantObservation(external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK)],
        )

    @patch("monitor.services.catalog.get_adapter")
    def test_add_creates_baseline_without_event(self, get_adapter):
        get_adapter.return_value.fetch.return_value = self.observation
        product, outcome = add_product("https://smokingpipes.com/p/1", self.user)
        self.assertEqual(outcome, "created")
        self.assertEqual(product.created_by, self.user)
        self.assertEqual(product.variants.get().status, StockStatus.OUT_OF_STOCK)
        self.assertEqual(StockEvent.objects.filter(variant__product=product).count(), 0)

    @patch("monitor.services.catalog.get_adapter")
    def test_restore_preserves_product_identity(self, get_adapter):
        get_adapter.return_value.fetch.return_value = self.observation
        original, unused = add_product("https://smokingpipes.com/p/1", self.user)
        original.soft_delete()
        restored, outcome = add_product("https://smokingpipes.com/p/1", self.user)
        self.assertEqual(outcome, "restored")
        self.assertEqual(restored.pk, original.pk)

    def test_rejects_unknown_domain(self):
        with self.assertRaises(UnsupportedSite):
            add_product("https://example.com/p/1", self.user)
```

Import `StockEvent` from `monitor.models`; do not add an `events_count` model property.

- [ ] **Step 2: Run catalog tests and verify failure**

Run: `.venv/bin/python manage.py test tests.test_catalog -v 2`

Expected: FAIL because `monitor.services.catalog` does not exist.

- [ ] **Step 3: Extract URL-only catalog service**

```python
class CatalogError(RuntimeError):
    code = "catalog_error"

class InvalidProductUrl(CatalogError):
    code = "invalid_url"

class UnsupportedSite(CatalogError):
    code = "unsupported_site"

class SiteUnavailable(CatalogError):
    code = "site_unavailable"

class UnreadableStock(CatalogError):
    code = "unreadable_stock"


def fetch_observation(site, url):
    return get_adapter(site).fetch(url)


def add_product(url, user=None):
    try:
        URLValidator(schemes=["http", "https"])(url)
    except ValidationError as exc:
        raise InvalidProductUrl("请输入有效的商品 URL") from exc
    site = next((item for item in Site.objects.filter(enabled=True) if item.accepts_url(url)), None)
    if not site:
        raise UnsupportedSite("暂不支持这个商城")
    existing = Product.all_objects.filter(url=url).first()
    if existing and existing.deleted_at is None:
        return existing, "existing"
    try:
        observer = import_string(settings.CONSOLE_CATALOG_OBSERVER)
        observation = observer(site, url)
    except (FetchError, httpx.HTTPError) as exc:
        raise SiteUnavailable("商城页面暂时无法访问，请稍后重试") from exc
    if not observation.variants or all(item.status == StockStatus.UNKNOWN for item in observation.variants):
        raise UnreadableStock("暂时无法识别该商品库存")
    with transaction.atomic():
        if existing:
            product = Product.all_objects.select_for_update().get(pk=existing.pk)
            product.restore()
            outcome = "restored"
        else:
            product = Product.all_objects.create(site=site, url=url, created_by=user)
            outcome = "created"
        apply_baseline(product, observation)
    return product, outcome
```

Import `settings`, `URLValidator`, `ValidationError`, `import_string`, `httpx`, and `FetchError` from their existing modules. Set `CONSOLE_CATALOG_OBSERVER = os.getenv("CONSOLE_CATALOG_OBSERVER", "monitor.services.catalog.fetch_observation")` in `restock/settings.py`; production therefore always uses the existing adapter, while Task 10 can select a deterministic observer in isolated E2E settings. `apply_baseline(product: Product, observation: ProductObservation) -> None` updates name, image, `last_checked_at`, clears `last_error`, schedules the next check using the site interval, upserts current variants by `external_id`, and creates one `StockSnapshot` per observed variant. It must not delete historical variants and must not create `StockEvent` rows. Exceptions outside the four `CatalogError` subclasses are logged server-side and returned by the API as `code="catalog_error"`, message `添加失败，请稍后重试`, never as raw exception text.

Replace the duplicate quick-add implementation in `monitor/admin.py` with this service so Admin and Console follow identical rules.

- [ ] **Step 4: Write failing Product API tests**

Cover these exact cases in `tests/test_console_products_api.py`:

```python
def test_product_list_excludes_soft_deleted(self):
    response = self.client.get("/api/console/v1/products")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["data"]["total"], 1)

def test_add_requires_only_url(self):
    response = self.client.post(
        "/api/console/v1/products",
        data=json.dumps({"url": "https://smokingpipes.com/p/1"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
    )
    self.assertEqual(response.status_code, 201)
    self.assertEqual(response.json()["data"]["outcome"], "created")

def test_patch_only_accepts_enabled(self):
    response = self.client.patch(
        f"/api/console/v1/products/{self.product.pk}",
        data=json.dumps({"name": "forbidden"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=self.csrf,
    )
    self.assertEqual(response.status_code, 400)

def test_delete_soft_deletes(self):
    response = self.client.delete(
        f"/api/console/v1/products/{self.product.pk}",
        HTTP_X_CSRFTOKEN=self.csrf,
    )
    self.assertEqual(response.status_code, 204)
    self.assertTrue(Product.all_objects.get(pk=self.product.pk).deleted_at)
```

- [ ] **Step 5: Implement Product API and serializers**

List query parameters are `q`, `site`, `status`, `page`, and `page_size`; clamp `page_size` to 10-100. `q` searches `name` and `url`; `status` filters `variants__status` with `distinct()`.

Product list items contain only:

```python
{
    "id": product.id,
    "name": product.name,
    "url": product.url,
    "site": {"code": product.site.code, "name": product.site.name, "region": product.site.region},
    "enabled": product.enabled,
    "stock_status": product.stock_status,
    "last_checked_at": iso(product.last_checked_at),
    "last_error": bool(product.last_error),
    "variants": [
        {"id": v.id, "name": v.name, "price": decimal_string(v.price), "currency": v.currency, "status": v.status}
        for v in product.variants.all()
    ],
}
```

POST maps `InvalidProductUrl`, `UnsupportedSite`, and `UnreadableStock` to 400, `SiteUnavailable` to 502, and an unexpected exception to the sanitized 500 response described above. The invalid URL response includes `fields={"url": "请输入有效的商品 URL"}`. PATCH rejects keys other than `enabled`. DELETE calls `soft_delete()`. Check action calls `check_product.delay(pk)` and returns status 202 with `{"queued": True}`.

`GET /products/{id}` returns the same fields as a list item plus `image_url`, `created_at`, and up to 20 newest `snapshots` with `variant_name`, `observed_status`, `price`, `currency`, and `checked_at`. It returns no raw hint or raw page data.

- [ ] **Step 6: Run API tests and commit**

Run: `.venv/bin/python manage.py test tests.test_catalog tests.test_console_products_api -v 2`

Expected: all catalog and product API tests PASS.

```bash
git add monitor/services/catalog.py monitor/console/products_api.py monitor/console/serializers.py monitor/console/urls.py monitor/admin.py restock/settings.py tests/test_catalog.py tests/test_console_products_api.py
git commit -m "feat: add URL-only product console API"
```

---

### Task 4: Activity and DingTalk Channel APIs

**Files:**
- Create: `monitor/console/activity_api.py`
- Create: `monitor/console/channels_api.py`
- Modify: `monitor/console/serializers.py`
- Modify: `monitor/console/urls.py`
- Modify: `restock/settings.py`
- Create: `tests/test_console_activity_api.py`
- Create: `tests/test_console_channels_api.py`

**Interfaces:**
- Produces: paginated event/failure APIs, failure retry, masked DingTalk channel CRUD, test-send endpoint, and `CONSOLE_CHANNEL_SENDER` dotted-path injection for isolated E2E tests.
- Consumes: Task 2 JSON helpers, Task 3 serializers, `check_product.delay`, and `send_channel`.

- [ ] **Step 1: Write failing activity API tests**

```python
def test_failure_feed_combines_crawl_and_notification_failures(self):
    response = self.client.get("/api/console/v1/failures")
    kinds = {item["kind"] for item in response.json()["data"]["items"]}
    self.assertEqual(kinds, {"crawl", "notification"})

@patch("monitor.console.activity_api.check_product.delay")
def test_retry_queues_associated_product(self, delay):
    response = self.csrf_post(f"/api/console/v1/failures/crawl:{self.failure.pk}/retry", {})
    self.assertEqual(response.status_code, 202)
    delay.assert_called_once_with(self.product.pk)
```

Create fixtures for one `CrawlFailure` and one failed `NotificationLog`. Verify newest-first sorting and `page_size` clamping.

- [ ] **Step 2: Implement activity endpoints**

`GET /events` returns event ID, product ID/name, site code/name/region, variant, price, currency, timestamp, and notification summary counts. `GET /failures` merges two querysets into normalized items with `kind`, a composite string `id` (`crawl:12` or `notification:34`), `product`, `site`, `message`, and `occurred_at`, sorts in Python by timestamp, then paginates. Retry splits and validates the composite ID; crawl retry queues its product, while notification retry invokes `notify_event.delay(notification.event_id)`.

Use these routes:

```python
path("events", activity_api.events),
path("failures", activity_api.failures),
path("failures/<str:failure_id>/retry", activity_api.retry_failure),
```

- [ ] **Step 3: Write failing DingTalk API tests**

```python
def test_channel_response_never_contains_secret_values(self):
    response = self.client.get("/api/console/v1/dingtalk-channels")
    body = response.content.decode()
    self.assertNotIn("access_token=private", body)
    self.assertNotIn("SECprivate", body)
    item = response.json()["data"][0]
    self.assertTrue(item["webhook_configured"])
    self.assertTrue(item["secret_configured"])

@patch("monitor.console.channels_api.send_channel")
def test_channel_test_uses_server_side_secret(self, send_channel):
    response = self.csrf_post(f"/api/console/v1/dingtalk-channels/{self.channel.pk}/test", {})
    self.assertEqual(response.status_code, 200)
    send_channel.assert_called_once()
```

Also test invalid region, non-DingTalk webhook, blank secret preserving the stored secret on PATCH, and disabled channel test rejection.

- [ ] **Step 4: Implement masked channel CRUD**

Channel responses contain `id`, `name`, `region`, `region_label`, `enabled`, `webhook_configured`, `webhook_mask`, and `secret_configured`. `webhook_mask` is the hostname plus the last four access-token characters and never the query string.

POST requires name, region, and webhook; secret is optional. PATCH accepts name, region, enabled, webhook, and secret; an absent or empty webhook/secret preserves the stored value. Call `full_clean()` before save. Test send uses the fixed title `补货机器人测试` and never accepts message content from the request. Set `CONSOLE_CHANNEL_SENDER = os.getenv("CONSOLE_CHANNEL_SENDER", "monitor.services.notifier.send_channel")` in settings and resolve it with `import_string` only in the test-send endpoint; production therefore uses the existing sender and Task 10 can replace it in isolated E2E settings. Celery notification delivery remains unchanged.

- [ ] **Step 5: Run tests and commit**

Run: `.venv/bin/python manage.py test tests.test_console_activity_api tests.test_console_channels_api -v 2`

Expected: all activity and DingTalk API tests PASS.

```bash
git add monitor/console/activity_api.py monitor/console/channels_api.py monitor/console/serializers.py monitor/console/urls.py restock/settings.py tests/test_console_activity_api.py tests/test_console_channels_api.py
git commit -m "feat: add console activity and DingTalk APIs"
```

---

### Task 5: React, Ant Design, and Test Toolchain

**Files:**
- Create: `console/package.json`
- Create: `console/tsconfig.json`
- Create: `console/tsconfig.node.json`
- Create: `console/vite.config.ts`
- Create: `console/index.html`
- Create: `console/src/main.tsx`
- Create: `console/src/app.tsx`
- Create: `console/src/api/types.ts`
- Create: `console/src/api/client.ts`
- Create: `console/src/test/setup.ts`
- Create: `console/src/test/render.tsx`
- Create: `console/src/test/mocks.ts`
- Create: `console/src/api/client.test.ts`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `api.get<T>()`, `api.post<T>()`, `api.patch<T>()`, `api.delete()`, shared TypeScript response types, `renderConsole(path: string)`, `mockSession(overrides?: Partial<SessionData>)`, and a routable React app.
- Consumes: Task 2-4 endpoints and Django `csrftoken` cookie.

- [ ] **Step 1: Create exact frontend dependencies and scripts**

```json
{
  "name": "restock-console",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "e2e": "playwright test"
  },
  "dependencies": {
    "@ant-design/icons": "^6.0.0",
    "@ant-design/pro-components": "^2.8.10",
    "@tanstack/react-query": "^5.87.1",
    "antd": "^5.27.0",
    "react": "^19.1.1",
    "react-dom": "^19.1.1",
    "react-router-dom": "^6.30.1"
  },
  "devDependencies": {
    "@playwright/test": "^1.55.0",
    "@testing-library/jest-dom": "^6.8.0",
    "@testing-library/react": "^16.3.0",
    "@types/react": "^19.1.12",
    "@types/react-dom": "^19.1.9",
    "@vitejs/plugin-react": "^5.0.2",
    "jsdom": "^26.1.0",
    "typescript": "^5.9.2",
    "vite": "^7.1.4",
    "vitest": "^3.2.4"
  }
}
```

Run: `cd console && npm install`

Expected: `package-lock.json` is created with no dependency resolution error.

- [ ] **Step 2: Configure deterministic production asset names**

Configure Vite base `/static/console/`, output directory `../monitor/static/console`, entry `assets/app.js`, chunks `assets/[name].js`, CSS `assets/app.css`, and development proxy `/api`, `/admin`, and `/console` to `http://127.0.0.1:8000`. Configure Vitest with `jsdom` and setup file `src/test/setup.ts`.

```ts
export default defineConfig({
  base: "/static/console/",
  plugins: [react()],
  build: {
    outDir: "../monitor/static/console",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: (asset) => asset.name?.endsWith(".css") ? "assets/app.css" : "assets/[name][extname]",
      },
    },
  },
  test: {environment: "jsdom", setupFiles: ["./src/test/setup.ts"]},
});
```

- [ ] **Step 3: Write failing API client tests**

```ts
it("sends CSRF header on mutations", async () => {
  document.cookie = "csrftoken=test-token";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({data: {ok: true}}), {
    status: 200,
    headers: {"Content-Type": "application/json"},
  })));
  await api.post("/products", {url: "https://example.com"});
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/console/v1/products"), expect.objectContaining({
    headers: expect.objectContaining({"X-CSRFToken": "test-token"}),
  }));
});

it("redirects to login on 401", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", {status: 401})));
  await expect(api.get("/session")).rejects.toMatchObject({status: 401});
});
```

- [ ] **Step 4: Implement typed API client and app entry**

The client prefixes `/api/console/v1`, sets `Accept: application/json`, sets `Content-Type` and `X-CSRFToken` for mutations, parses the standardized error body, and sets `window.location.href` to `/admin/login/?next=/console/` on 401.

`main.tsx` renders `App` inside `ConfigProvider` with the approved tokens. `app.tsx` creates a `QueryClient` and routes `/`, `/products`, `/events`, `/failures`, and `/dingtalk` under `BrowserRouter basename="/console"`.

`src/test/render.tsx` exports `renderConsole(path: string)`, creates a fresh retry-disabled `QueryClient`, and renders the route tree under `MemoryRouter initialEntries={[path]}`. `src/test/mocks.ts` exports typed `vi.spyOn(api, ...)` helpers including `mockSession`; every helper is restored in `afterEach` from `setup.ts`, so tests never depend on execution order.

- [ ] **Step 5: Run frontend tests and build**

Run: `cd console && npm test && npm run build`

Expected: API client tests PASS; TypeScript reports no errors; `monitor/static/console/assets/app.js` and `app.css` exist.

- [ ] **Step 6: Commit frontend foundation**

Add `console/node_modules/`, `console/coverage/`, `console/test-results/`, and `monitor/static/console/` to `.gitignore`; commit `console/package-lock.json`.

```bash
git add console/package.json console/package-lock.json console/tsconfig.json console/tsconfig.node.json console/vite.config.ts console/index.html console/src/main.tsx console/src/app.tsx console/src/api console/src/test .gitignore
git commit -m "feat: scaffold Ant Design console"
```

---

### Task 6: Console Layout and Workbench

**Files:**
- Create: `console/src/layout/ConsoleLayout.tsx`
- Create: `console/src/layout/layout.css`
- Create: `console/src/layout/ConsoleLayout.test.tsx`
- Create: `console/src/pages/DashboardPage.tsx`
- Create: `console/src/pages/DashboardPage.test.tsx`
- Modify: `console/src/app.tsx`

**Interfaces:**
- Produces: responsive Ant Design Pro shell and workbench using `GET /session` and `GET /dashboard`.
- Consumes: Task 5 API client and shared types.

- [ ] **Step 1: Write failing layout tests**

```tsx
it("shows only approved navigation modules", async () => {
  renderConsole("/");
  expect(await screen.findByText("工作台")).toBeInTheDocument();
  expect(screen.getByText("商品监控")).toBeInTheDocument();
  expect(screen.getByText("补货记录")).toBeInTheDocument();
  expect(screen.getByText("异常记录")).toBeInTheDocument();
  expect(screen.getByText("钉钉群")).toBeInTheDocument();
  expect(screen.queryByText("解析器")).not.toBeInTheDocument();
});

it("shows unhealthy scheduler status from API", async () => {
  server.use(sessionHandler({scheduler: "unhealthy"}));
  renderConsole("/");
  expect(await screen.findByText("调度异常")).toBeInTheDocument();
});
```

Dashboard tests assert the four approved statistics and recent sections from mocked API data.

- [ ] **Step 2: Implement Ant Design Pro shell**

Use `ProLayout` with `layout="mix"`, `navTheme="realDark"`, `fixedHeader`, `fixSiderbar`, `siderWidth={208}`, title `补货监控`, and route configuration for the five modules. Use icons from `@ant-design/icons`: `DashboardOutlined`, `ShoppingOutlined`, `NotificationOutlined`, `WarningOutlined`, and `DingdingOutlined`.

The header shows a `Badge` driven by session scheduler health and a `Dropdown` with only “退出登录”. Mobile width collapses the sider to a drawer; no horizontal viewport overflow is allowed.

- [ ] **Step 3: Implement Workbench**

Use four compact Ant Design `Card` components in a responsive `Row`: monitored products, in-stock variants, restocks in 24 hours, and failures in 24 hours. Below them render recent products in an unframed table band and recent events/failures in two columns. Do not nest cards.

Map statuses exactly:

```ts
const stockTag = {
  in_stock: {color: "success", label: "有货"},
  out_of_stock: {color: "default", label: "缺货"},
  discontinued: {color: "default", label: "已下架"},
  unknown: {color: "warning", label: "确认中"},
} as const;
```

- [ ] **Step 4: Run tests and commit**

Run: `cd console && npm test -- ConsoleLayout DashboardPage`

Expected: layout and Workbench tests PASS.

```bash
git add console/src/layout console/src/pages/DashboardPage.tsx console/src/pages/DashboardPage.test.tsx console/src/app.tsx
git commit -m "feat: add Ant Design console layout and workbench"
```

---

### Task 7: Product Table, URL Modal, and Detail Drawer

**Files:**
- Create: `console/src/pages/ProductsPage.tsx`
- Create: `console/src/pages/ProductsPage.test.tsx`
- Create: `console/src/components/AddProductModal.tsx`
- Create: `console/src/components/AddProductModal.test.tsx`
- Create: `console/src/components/ProductDrawer.tsx`
- Modify: `console/src/app.tsx`

**Interfaces:**
- Produces: complete daily product workflow.
- Consumes: Task 3 Product API and Task 5 API client.

- [ ] **Step 1: Write failing URL modal tests**

```tsx
it("contains exactly one editable business field", () => {
  render(<AddProductModal open onClose={vi.fn()} onCreated={vi.fn()} />);
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
  expect(screen.getByLabelText("商品 URL")).toBeRequired();
});

it("keeps modal open and shows API error", async () => {
  mockAddProduct.rejects(new ApiError(400, "unreadable_stock", "暂时无法识别该商品库存"));
  render(<AddProductModal open onClose={onClose} onCreated={vi.fn()} />);
  await userEvent.type(screen.getByLabelText("商品 URL"), "https://smokingpipes.com/p/1");
  await userEvent.click(screen.getByRole("button", {name: "开始监控"}));
  expect(await screen.findByText("暂时无法识别该商品库存")).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});
```

Add tests for loading-state duplicate prevention and existing-product drawer opening.

- [ ] **Step 2: Implement URL-only modal**

Use Ant Design `Modal` and vertical `Form`. Render one `Input` with URL validation and two buttons: cancel and primary “开始监控”. Do not show site, interval, push scope, notes, or parser controls. On success invalidate product/dashboard queries; call `onCreated(product, outcome)`; preserve API field errors inside the form.

- [ ] **Step 3: Write failing product table tests**

Test query serialization for search/site/status/page, status tags, disabled row state, immediate-check loading, pause/resume, delete confirmation, and drawer open. The delete test must click Ant Design `Popconfirm` confirm before expecting the API call.

- [ ] **Step 4: Implement Product page and drawer**

Use `ProTable<ProductListItem>` with manual request backed by React Query. Columns are product, site, variants/price, stock, last checked, enabled, and actions. Toolbar contains only “添加监控商品”. Search form fields are name/URL, site, and stock status. Use `Typography.Text ellipsis` for long URLs.

The drawer shows product link, site, current status, last check, last readable error, and a non-card variant table. Drawer actions are immediate check and pause/resume. Row overflow menu contains the same lifecycle actions plus remove.

- [ ] **Step 5: Run tests and commit**

Run: `cd console && npm test -- AddProductModal ProductsPage`

Expected: modal, product table, and drawer tests PASS.

```bash
git add console/src/pages/ProductsPage.tsx console/src/pages/ProductsPage.test.tsx console/src/components/AddProductModal.tsx console/src/components/AddProductModal.test.tsx console/src/components/ProductDrawer.tsx console/src/app.tsx
git commit -m "feat: add product monitoring workflow"
```

---

### Task 8: Events, Failures, and DingTalk Pages

**Files:**
- Create: `console/src/pages/EventsPage.tsx`
- Create: `console/src/pages/EventsPage.test.tsx`
- Create: `console/src/pages/FailuresPage.tsx`
- Create: `console/src/pages/FailuresPage.test.tsx`
- Create: `console/src/pages/ChannelsPage.tsx`
- Create: `console/src/pages/ChannelsPage.test.tsx`
- Modify: `console/src/app.tsx`

**Interfaces:**
- Produces: remaining approved Console modules.
- Consumes: Task 4 Activity and DingTalk APIs.

- [ ] **Step 1: Write failing page tests**

```tsx
it("renders notification result counts on events", async () => {
  renderConsole("/events");
  expect(await screen.findByText("发送成功 2/2")).toBeInTheDocument();
});

it("retries a crawl failure", async () => {
  renderConsole("/failures");
  await userEvent.click(await screen.findByRole("button", {name: "重新检查"}));
  expect(mockRetryFailure).toHaveBeenCalledWith("crawl:12");
});

it("does not render full channel credentials", async () => {
  renderConsole("/dingtalk");
  expect(await screen.findByText(/dingtalk.com/)).toBeInTheDocument();
  expect(screen.queryByText(/access_token=private/)).not.toBeInTheDocument();
  expect(screen.queryByText(/SECprivate/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Implement Events and Failures pages**

Events use `ProTable` columns product, site, variant, price, restock time, and notification result. Failures use columns kind, product, site, readable message, occurrence time, and action. Render crawl and notification failures with distinct Ant Design tags. Retry uses a per-row loading key and refreshes failures after success.

- [ ] **Step 3: Implement DingTalk Channels page**

Use a standard table and add/edit modal. Fields are name, region, webhook, signing secret, and enabled. On edit, webhook and secret inputs are blank with configured-state help; blank values preserve existing credentials. Test send uses `Popconfirm`, row loading, and success/error messages. Never place credentials in browser storage or logs.

- [ ] **Step 4: Run tests and commit**

Run: `cd console && npm test -- EventsPage FailuresPage ChannelsPage`

Expected: all remaining page tests PASS.

```bash
git add console/src/pages/EventsPage.tsx console/src/pages/EventsPage.test.tsx console/src/pages/FailuresPage.tsx console/src/pages/FailuresPage.test.tsx console/src/pages/ChannelsPage.tsx console/src/pages/ChannelsPage.test.tsx console/src/app.tsx
git commit -m "feat: add activity and DingTalk console pages"
```

---

### Task 9: Production Build and Routing Integration

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `deploy/nginx/default.conf`
- Modify: `.dockerignore`
- Modify: `README.md`
- Create: `tests/test_console_shell.py`

**Interfaces:**
- Produces: production image containing compiled Console assets and Nginx routes that serve Console, API, login, Admin, and static resources correctly.
- Consumes: Tasks 2 and 5 shell/asset contract.

- [ ] **Step 1: Write failing shell asset test**

```python
class ConsoleShellTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("operator", is_staff=True)
        self.client.force_login(self.staff)

    def test_shell_references_compiled_assets(self):
        response = self.client.get("/console/products")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/static/console/assets/app.js")
        self.assertContains(response, "/static/console/assets/app.css")
        self.assertContains(response, '<div id="root"></div>', html=True)
```

- [ ] **Step 2: Add multi-stage frontend build**

```dockerfile
FROM node:22-alpine AS console-build
WORKDIR /console
COPY console/package.json console/package-lock.json ./
RUN npm ci
COPY console/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=console-build /monitor/static/console /app/monitor/static/console
RUN chmod +x /app/deploy/entrypoint.sh
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["web"]
```

Verify the Vite output path in the builder. If Vite writes `/monitor/static/console` as configured, retain the shown copy source; do not copy `node_modules` into the Python image.

- [ ] **Step 3: Configure Nginx routes and cache policy**

Keep `/api/`, `/console/`, `/admin/`, and `/healthz` proxied to Django. Serve Console static assets through the existing WhiteNoise middleware for the current single-image topology. Because this plan uses stable asset names, set `Cache-Control: no-cache` for `/static/console/`; do not set immutable caching.

- [ ] **Step 4: Update operator documentation**

README must state:

```text
Daily URL: https://<domain>/console/
Technical maintenance: https://<domain>/admin/
Daily operation: click Add Monitored Product, paste one product URL, and submit.
One-time setup: configure DingTalk site groups and the all-sites group.
```

Include local commands for Django and Vite development, production build, migration, logs, and rollback to the previous image tag.

- [ ] **Step 5: Run integration checks and commit**

Run:

```bash
.venv/bin/python manage.py test tests.test_console_shell -v 2
cd console && npm run build
cd .. && .venv/bin/python manage.py collectstatic --noinput
ENV_FILE=.env.example docker compose --env-file .env.example config --quiet
```

Expected: test PASS, build and collectstatic succeed, Compose config exits 0.

```bash
git add Dockerfile docker-compose.yml deploy/nginx/default.conf .dockerignore README.md tests/test_console_shell.py
git commit -m "build: integrate console production assets"
```

---

### Task 10: End-to-End, Responsive, and Final Regression Verification

**Files:**
- Create: `console/playwright.config.ts`
- Create: `console/e2e/console.spec.ts`
- Create: `console/e2e/global-setup.ts`
- Create: `console/e2e/global-teardown.ts`
- Create: `restock/e2e_settings.py`
- Create: `monitor/e2e.py`
- Create: `monitor/management/__init__.py`
- Create: `monitor/management/commands/__init__.py`
- Create: `monitor/management/commands/seed_e2e.py`
- Modify: `README.md`

**Interfaces:**
- Produces: repeatable acceptance coverage for the complete approved workflow using an isolated `.e2e.sqlite3` database, deterministic product observations, and a no-network DingTalk test sender.
- Consumes: all prior tasks and local Docker Compose services.

- [ ] **Step 1: Create deterministic E2E fixtures**

`restock/e2e_settings.py` imports all base settings, sets SQLite `NAME = BASE_DIR / ".e2e.sqlite3"`, `CONSOLE_CATALOG_OBSERVER = "monitor.e2e.observe_product"`, and `CONSOLE_CHANNEL_SENDER = "monitor.e2e.send_channel"`. `monitor/e2e.py` exports these exact functions:

```python
def observe_product(site, url):
    if url != "https://smokingpipes.com/product/test":
        raise UnreadableStock("暂时无法识别该商品库存")
    return ProductObservation(
        name="Test Flake",
        canonical_url=url,
        variants=[VariantObservation(
            external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK,
            price=Decimal("12.50"), currency="USD",
        )],
    )


def send_channel(channel, payload):
    return {"errcode": 0, "errmsg": "ok"}
```

The `seed_e2e` command creates staff user `operator` with password `operator-e2e-only`, a Smokingpipes site, separate seeded out-of-stock and in-stock products, one restock event, one crawl failure, and site/all-region DingTalk channels using `https://oapi.dingtalk.com/robot/send?access_token=e2e1` and `SEC-e2e-only`. It must not create the `/product/test` product, so the add workflow exercises creation.

`global-setup.ts` runs `migrate --noinput` and `seed_e2e` with `DJANGO_SETTINGS_MODULE=restock.e2e_settings`. `global-teardown.ts` deletes only the resolved repository file `.e2e.sqlite3` after first verifying its basename is exactly `.e2e.sqlite3`. Configure Playwright `webServer` to run Django at `127.0.0.1:8011` with the same settings module and set `baseURL` to `http://127.0.0.1:8011`. This isolated configuration is the only place the deterministic observer and no-network sender are enabled.

- [ ] **Step 2: Write E2E workflow**

```ts
test("operator adds, pauses, checks, and removes a product", async ({page}) => {
  await page.goto("/console/");
  await loginAsFixtureStaff(page);
  await page.getByRole("button", {name: "添加监控商品"}).click();
  await page.getByLabel("商品 URL").fill("https://smokingpipes.com/product/test");
  await page.getByRole("button", {name: "开始监控"}).click();
  await expect(page.getByText("Test Flake")).toBeVisible();
  await openProductActions(page, "Test Flake");
  await page.getByRole("menuitem", {name: "暂停监控"}).click();
  await expect(productRow(page, "Test Flake").getByText("已暂停")).toBeVisible();
  await openProductActions(page, "Test Flake");
  await page.getByRole("menuitem", {name: "移除"}).click();
  await page.getByRole("button", {name: "确认移除"}).click();
  await expect(page.getByText("Test Flake")).not.toBeVisible();
});
```

Define `loginAsFixtureStaff`, `openProductActions`, and `productRow` at the top of `console.spec.ts`. Add separate tests for unreadable URL error, duplicate URL drawer opening, failure retry, and DingTalk test-send success through the isolated no-network sender.

- [ ] **Step 3: Add responsive screenshot assertions**

Run the workbench, products, add modal, events, failures, and DingTalk pages at 1440x900, 1280x800, and 390x844. Store approved baselines only under `console/e2e/console.spec.ts-snapshots/`. For each viewport assert:

```ts
await expect(page.locator("body")).toHaveScreenshot(`${name}-${width}x${height}.png`, {
  animations: "disabled",
  maxDiffPixelRatio: 0.01,
});
expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
```

On mobile, assert the sider is hidden until the menu button is pressed and that primary action labels remain fully visible.

- [ ] **Step 4: Run full verification**

Run:

```bash
.venv/bin/python manage.py test -v 2
cd console && npm test
npm run build
npx playwright test
cd .. && .venv/bin/python manage.py check --deploy
ENV_FILE=.env.example docker compose --env-file .env.example build
ENV_FILE=.env.example docker compose --env-file .env.example up -d
curl -fsS http://127.0.0.1/healthz
curl -fsS -o /dev/null http://127.0.0.1/console/
```

Expected: backend, frontend, E2E, screenshot, build, and health checks all pass. The Console redirects anonymous users to login and authenticated staff users see the Ant Design Pro shell.

- [ ] **Step 5: Review the final diff and commit**

Run `git diff --check`, inspect `git status --short`, and verify no `.env`, database, screenshots outside the approved snapshot folder, build output, or `.superpowers/` artifacts are staged.

```bash
git add console/playwright.config.ts console/e2e restock/e2e_settings.py monitor/e2e.py monitor/management README.md
git commit -m "test: verify console workflows and responsive layout"
```

Record the deployed image tag and migration number in the deployment log before switching production traffic.
