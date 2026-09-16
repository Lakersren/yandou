from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from monitor.models import Product, Region, Site, StockEvent, StockStatus
from monitor.services.checker import check_product
from monitor.services.scraper import ProductObservation, VariantObservation
from monitor.tasks import check_product as check_product_task, dispatch_due_products, enqueue_product_check


class SiteUrlTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")

    def test_accepts_domain_and_subdomain(self):
        self.assertTrue(self.site.accepts_url("https://www.smokingpipes.com/item"))
        self.assertTrue(self.site.accepts_url("https://smokingpipes.com/item"))

    def test_rejects_lookalike_domain(self):
        self.assertFalse(self.site.accepts_url("https://smokingpipes.com.attacker.test/item"))

    def test_product_validation_rejects_other_site(self):
        product = Product(site=self.site, url="https://example.com/item")
        with self.assertRaises(Exception):
            product.full_clean()


class StockTransitionTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        self.product = Product.objects.create(site=self.site, url="https://smokingpipes.com/product/1")

    def observation(self, status):
        return ProductObservation(
            name="Test Flake",
            canonical_url=self.product.url,
            variants=[VariantObservation(external_id="50g", name="50g", status=status)],
        )

    @patch("monitor.services.checker.get_adapter")
    def test_restock_requires_two_in_stock_confirmations(self, get_adapter):
        adapter = get_adapter.return_value
        adapter.fetch.return_value = self.observation(StockStatus.OUT_OF_STOCK)
        self.assertEqual(check_product(self.product.pk), [])

        adapter.fetch.return_value = self.observation(StockStatus.IN_STOCK)
        self.assertEqual(check_product(self.product.pk), [])
        event_ids = check_product(self.product.pk)

        self.assertEqual(len(event_ids), 1)
        event = StockEvent.objects.get(pk=event_ids[0])
        self.assertEqual(event.old_status, StockStatus.OUT_OF_STOCK)
        self.assertEqual(event.new_status, StockStatus.IN_STOCK)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SchedulerHeartbeatTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")

    @patch("monitor.tasks.check_product.apply_async")
    def test_dispatch_sets_scheduler_heartbeat(self, apply_async):
        product = Product.objects.create(site=self.site, url="https://smokingpipes.com/product/heartbeat")

        dispatch_due_products()

        self.assertIsNotNone(cache.get("monitor:scheduler:heartbeat"))
        product.refresh_from_db()
        self.assertGreater(product.next_check_at, timezone.now() + timedelta(minutes=4))
        self.assertEqual(apply_async.call_count, 1)
        self.assertEqual(apply_async.call_args.kwargs["args"], [product.pk])
        self.assertEqual(apply_async.call_args.kwargs["queue"], "celery")

        Product.objects.filter(pk=product.pk).update(next_check_at=timezone.now())
        dispatch_due_products()
        self.assertEqual(apply_async.call_count, 1)

    @patch("monitor.tasks.check_product.apply_async")
    def test_havana_house_is_dispatched_to_bright_data_queue(self, apply_async):
        site = Site.objects.create(
            code="havanahouse",
            name="Havana House",
            region=Region.UK,
            domain="havanahouse.co.uk",
            adapter="havanahouse",
        )
        product = Product.objects.create(site=site, url="https://havanahouse.co.uk/product/test")

        dispatch_due_products()

        self.assertEqual(apply_async.call_args.kwargs["args"], [product.pk])
        self.assertEqual(apply_async.call_args.kwargs["queue"], "bright_data")

    @patch("monitor.tasks.check_product.apply_async")
    def test_smokingpipes_is_dispatched_to_bright_data_queue(self, apply_async):
        site = Site.objects.create(
            code="sp-bright",
            name="Smokingpipes Bright",
            region=Region.US,
            domain="www.smokingpipes.com",
            adapter="smokingpipes",
        )
        product = Product.objects.create(site=site, url="https://www.smokingpipes.com/product/1")

        dispatch_due_products()

        queued_call = next(
            call for call in apply_async.call_args_list
            if call.kwargs["args"] == [product.pk]
        )
        self.assertEqual(queued_call.kwargs["queue"], "bright_data")

    @patch("monitor.tasks.check_product.apply_async")
    def test_manual_check_uses_priority_and_deduplicates(self, apply_async):
        product = Product.objects.create(site=self.site, url="https://smokingpipes.com/product/manual")

        self.assertTrue(enqueue_product_check(product))
        self.assertFalse(enqueue_product_check(product))

        self.assertEqual(apply_async.call_count, 1)
        self.assertEqual(apply_async.call_args.kwargs["queue"], "celery")
        self.assertEqual(apply_async.call_args.kwargs["priority"], 9)

    @patch("monitor.tasks.run_check")
    def test_product_check_skips_an_existing_lock(self, run_check):
        product = Product.objects.create(site=self.site, url="https://smokingpipes.com/product/locked")
        cache.set(f"monitor:product-check:{product.pk}", "running", timeout=300)

        self.assertEqual(check_product_task(product.pk), [])

        run_check.assert_not_called()
