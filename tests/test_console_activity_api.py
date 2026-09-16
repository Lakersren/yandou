import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
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


class ConsoleActivityApiTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("operator", is_staff=True)
        self.site = Site.objects.create(code="sp", name="Smokingpipes", region=Region.US, domain="smokingpipes.com")
        self.product = Product.objects.create(
            site=self.site,
            url="https://smokingpipes.com/product/activity",
            name="Activity Product",
        )
        self.variant = Variant.objects.create(
            product=self.product,
            external_id="50g",
            name="50g",
            price="12.50",
            currency="USD",
            status=StockStatus.IN_STOCK,
        )
        self.event = StockEvent.objects.create(
            variant=self.variant,
            old_status=StockStatus.OUT_OF_STOCK,
            new_status=StockStatus.IN_STOCK,
            price="12.50",
        )
        self.channel = DingTalkChannel.objects.create(
            name="US", region=Region.US,
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test",
        )
        self.failure = CrawlFailure.objects.create(
            product=self.product,
            error_type="FetchError",
            message="request timed out",
        )
        self.notification = NotificationLog.objects.create(
            event=self.event,
            channel=self.channel,
            success=False,
            response_text="delivery timed out",
        )
        CrawlFailure.objects.filter(pk=self.failure.pk).update(occurred_at=timezone.now() - timedelta(minutes=2))
        NotificationLog.objects.filter(pk=self.notification.pk).update(attempted_at=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.staff)
        self.client.get("/console/")
        self.csrf = self.client.cookies["csrftoken"].value

    def csrf_post(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

    def test_events_include_product_site_variant_and_notification_summary(self):
        NotificationLog.objects.create(event=self.event, channel=DingTalkChannel.objects.create(
            name="All", region=Region.ALL,
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=all",
        ), success=True)

        response = self.client.get("/api/console/v1/events")

        self.assertEqual(response.status_code, 200)
        item = response.json()["data"]["items"][0]
        self.assertEqual(item["id"], self.event.pk)
        self.assertEqual(item["product"], {"id": self.product.pk, "name": "Activity Product"})
        self.assertEqual(item["site"], {"code": "sp", "name": "Smokingpipes", "region": "US"})
        self.assertEqual(item["variant"], {"id": self.variant.pk, "name": "50g"})
        self.assertEqual(item["price"], "12.50")
        self.assertEqual(item["currency"], "USD")
        self.assertEqual(item["notifications"], {"total": 2, "success": 1, "failed": 1})

    def test_failure_feed_combines_crawl_and_notification_failures_newest_first(self):
        response = self.client.get("/api/console/v1/failures")

        self.assertEqual(response.status_code, 200)
        items = response.json()["data"]["items"]
        self.assertEqual({item["kind"] for item in items}, {"crawl", "notification"})
        self.assertEqual(items[0]["id"], f"notification:{self.notification.pk}")
        self.assertEqual(items[1]["id"], f"crawl:{self.failure.pk}")
        self.assertEqual(items[0]["product"], {"id": self.product.pk, "name": "Activity Product"})
        self.assertEqual(items[0]["site"], {"code": "sp", "name": "Smokingpipes", "region": "US"})
        self.assertEqual(items[0]["message"], "通知发送失败，请稍后重试")

    def test_activity_page_size_is_clamped(self):
        events = self.client.get("/api/console/v1/events?page=0&page_size=1").json()["data"]
        failures = self.client.get("/api/console/v1/failures?page_size=1000").json()["data"]

        self.assertEqual(events["page"], 1)
        self.assertEqual(events["page_size"], 10)
        self.assertEqual(failures["page_size"], 100)

    def test_active_failures_only_returns_latest_current_crawl_failure(self):
        self.product.last_error = "request timed out"
        self.product.save(update_fields=["last_error"])
        latest = CrawlFailure.objects.create(
            product=self.product,
            error_type="FetchError",
            message="request timed out again",
        )

        response = self.client.get("/api/console/v1/failures?active=1")

        crawl_items = [item for item in response.json()["data"]["items"] if item["kind"] == "crawl"]
        self.assertEqual([item["id"] for item in crawl_items], [f"crawl:{latest.pk}"])

        self.product.last_error = ""
        self.product.save(update_fields=["last_error"])
        response = self.client.get("/api/console/v1/failures?active=1")
        self.assertFalse(any(item["kind"] == "crawl" for item in response.json()["data"]["items"]))

    def test_failure_pages_are_stable_when_timestamps_tie(self):
        crawls = [self.failure]
        notifications = [self.notification]
        for index in range(5):
            crawls.append(CrawlFailure.objects.create(
                product=self.product,
                error_type="FetchError",
                message=f"request timed out {index}",
            ))
            channel = DingTalkChannel.objects.create(
                name=f"US {index}",
                region=Region.US,
                webhook_url=f"https://oapi.dingtalk.com/robot/send?access_token=tied{index}",
            )
            notifications.append(NotificationLog.objects.create(
                event=self.event,
                channel=channel,
                success=False,
                response_text=f"delivery timed out {index}",
            ))
        timestamp = timezone.now().replace(microsecond=0)
        CrawlFailure.objects.filter(pk__in=[failure.pk for failure in crawls]).update(occurred_at=timestamp)
        NotificationLog.objects.filter(pk__in=[notification.pk for notification in notifications]).update(
            attempted_at=timestamp
        )
        expected_ids = (
            [f"notification:{notification.pk}" for notification in reversed(notifications)]
            + [f"crawl:{failure.pk}" for failure in reversed(crawls)]
        )

        first_page = self.client.get("/api/console/v1/failures?page=1&page_size=10").json()["data"]["items"]
        second_page = self.client.get("/api/console/v1/failures?page=2&page_size=10").json()["data"]["items"]
        repeated_first_page = self.client.get("/api/console/v1/failures?page=1&page_size=10").json()["data"]["items"]
        repeated_second_page = self.client.get("/api/console/v1/failures?page=2&page_size=10").json()["data"]["items"]

        first_ids = [item["id"] for item in first_page]
        second_ids = [item["id"] for item in second_page]
        self.assertEqual(first_ids, expected_ids[:10])
        self.assertEqual(second_ids, expected_ids[10:])
        self.assertEqual(first_ids, [item["id"] for item in repeated_first_page])
        self.assertEqual(second_ids, [item["id"] for item in repeated_second_page])
        self.assertFalse(set(first_ids) & set(second_ids))
        self.assertEqual(set(first_ids + second_ids), set(expected_ids))

    @patch("monitor.console.activity_api.enqueue_product_check", return_value=True)
    def test_retry_queues_associated_product(self, enqueue):
        response = self.csrf_post(f"/api/console/v1/failures/crawl:{self.failure.pk}/retry", {})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["data"], {"queued": True})
        self.assertEqual(enqueue.call_args.args[0].pk, self.product.pk)

    @patch("monitor.console.activity_api.notify_event.delay")
    def test_notification_retry_queues_associated_event(self, delay):
        response = self.csrf_post(f"/api/console/v1/failures/notification:{self.notification.pk}/retry", {})

        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with(self.event.pk)

    def test_retry_rejects_malformed_or_missing_failure_ids(self):
        malformed = self.csrf_post("/api/console/v1/failures/crawl:not-an-id/retry", {})
        missing = self.csrf_post("/api/console/v1/failures/crawl:99999/retry", {})

        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(missing.status_code, 404)
