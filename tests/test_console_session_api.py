from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from monitor.models import (
    CrawlFailure,
    DingTalkChannel,
    NotificationLog,
    Product,
    Region,
    Site,
    StockEvent,
    StockStatus,
    Variant,
)


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

    def test_dashboard_returns_expected_summaries(self):
        site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        product = Product.objects.create(
            site=site,
            url="https://smokingpipes.com/product/dashboard",
            name="Dashboard Product",
        )
        variant = Variant.objects.create(product=product, external_id="50g", name="50g", status=StockStatus.IN_STOCK)
        event = StockEvent.objects.create(
            variant=variant,
            old_status=StockStatus.OUT_OF_STOCK,
            new_status=StockStatus.IN_STOCK,
        )
        channel = DingTalkChannel.objects.create(
            name="Operations",
            region=Region.US,
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test",
        )
        NotificationLog.objects.create(event=event, channel=channel, success=False)
        CrawlFailure.objects.create(
            product=product,
            error_type="ParserConfigurationError",
            message="SECRET_PARSER_SELECTOR=https://internal.example/selector",
        )
        product.last_error = "SECRET_PARSER_SELECTOR=https://internal.example/selector"
        product.save(update_fields=["last_error"])

        self.client.force_login(self.staff)
        response = self.client.get("/api/console/v1/dashboard")

        data = response.json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(data), {
            "monitored_products",
            "in_stock_variants",
            "restocks_24h",
            "failures_24h",
            "active_failures",
            "recent_products",
            "recent_events",
            "recent_failures",
            "pending_failures",
            "region_summaries",
        })
        self.assertEqual(data["monitored_products"], 1)
        self.assertEqual(data["in_stock_variants"], 1)
        self.assertEqual(data["restocks_24h"], 1)
        self.assertEqual(data["failures_24h"], 2)
        self.assertEqual(data["active_failures"], 2)
        self.assertEqual(data["recent_products"][0]["id"], product.id)
        self.assertEqual(data["recent_events"][0]["id"], event.id)
        us_summary = next(item for item in data["region_summaries"] if item["region"] == Region.US)
        self.assertEqual(us_summary["monitored_products"], 1)
        self.assertEqual(us_summary["in_stock_variants"], 1)
        self.assertEqual(us_summary["restocks_24h"], 1)
        self.assertEqual(us_summary["failures_24h"], 2)
        self.assertEqual(us_summary["active_failures"], 2)
        self.assertEqual(us_summary["products"][0]["id"], product.id)
        self.assertEqual(data["recent_failures"][0]["product"]["id"], product.id)
        self.assertEqual(data["recent_failures"][0]["error_type"], "crawl_failed")
        self.assertEqual(data["recent_failures"][0]["message"], "商品抓取失败，请稍后重试")
        self.assertEqual(len(data["pending_failures"]), 2)
        response_body = response.content.decode()
        self.assertNotIn("ParserConfigurationError", response_body)
        self.assertNotIn("SECRET_PARSER_SELECTOR=https://internal.example/selector", response_body)

    def create_notification_failure(self):
        site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        product = Product.objects.create(site=site, url="https://smokingpipes.com/p/notify", name="Notify Product")
        variant = Variant.objects.create(product=product, external_id="50g", name="50g")
        event = StockEvent.objects.create(
            variant=variant, old_status=StockStatus.OUT_OF_STOCK, new_status=StockStatus.IN_STOCK,
        )
        channel = DingTalkChannel.objects.create(name="Test", region=Region.US, webhook_url="https://oapi.dingtalk.com/robot/send?access_token=SECRET")
        notification = NotificationLog.objects.create(
            event=event, channel=channel, success=False,
            response_text="RuntimeError: SECRET raw response access_token=SECRET",
        )
        self.client.force_login(self.staff)
        return product, notification

    def test_dashboard_shows_safe_notification_only_failure(self):
        product, notification = self.create_notification_failure()

        response = self.client.get("/api/console/v1/dashboard")

        data = response.json()["data"]
        self.assertEqual(data["failures_24h"], 1)
        self.assertEqual(data["active_failures"], 1)
        self.assertEqual(len(data["recent_failures"]), 1)
        self.assertEqual(len(data["pending_failures"]), 1)
        summary = data["recent_failures"][0]
        self.assertEqual(summary["id"], f"notification:{notification.pk}")
        self.assertEqual(summary["product"]["id"], product.pk)
        self.assertEqual(summary["message"], "通知发送失败，请稍后重试")
        self.assertNotIn("SECRET", response.content.decode())
        self.assertNotIn("RuntimeError", response.content.decode())
        self.assertNotIn("response_text", summary)

    def test_dashboard_merges_failure_types_with_stable_order_and_cap(self):
        product, notification = self.create_notification_failure()
        failures = [CrawlFailure.objects.create(product=product, error_type="RawException", message="SECRET") for _ in range(10)]
        tied_at = timezone.now() - timedelta(minutes=1)
        CrawlFailure.objects.update(occurred_at=tied_at)
        NotificationLog.objects.update(attempted_at=tied_at)
        newest = failures[0]
        CrawlFailure.objects.filter(pk=newest.pk).update(occurred_at=timezone.now())
        expected = [f"crawl:{newest.pk}", f"notification:{notification.pk}"] + [
            f"crawl:{failure.pk}" for failure in reversed(failures[1:])
        ][:6]

        for _ in range(2):
            response = self.client.get("/api/console/v1/dashboard")
            self.assertEqual([item["id"] for item in response.json()["data"]["recent_failures"]], expected)
            self.assertNotIn("SECRET", response.content.decode())
            self.assertNotIn("RawException", response.content.decode())
