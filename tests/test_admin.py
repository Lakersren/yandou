from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from monitor.models import Product, Region, Site, StockStatus
from monitor.services.scraper import ProductObservation, VariantObservation


class ProductAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", "admin@example.com", "password")
        self.client.force_login(self.user)

    def test_preview_page_loads(self):
        response = self.client.get(reverse("admin:monitor_product_preview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "商品 URL")

    def test_dashboard_loads(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "商品监控")
        self.assertContains(response, "开始监控")

    def test_quick_add_creates_baseline(self):
        site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        observation = ProductObservation(
            name="Test Flake", canonical_url="https://smokingpipes.com/p/1",
            variants=[VariantObservation(external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK)],
        )
        with patch("monitor.services.catalog.get_adapter") as get_adapter:
            get_adapter.return_value.fetch.return_value = observation
            response = self.client.post(
                reverse("admin:monitor_product_quick_add"),
                {"url": "https://smokingpipes.com/p/1"},
            )
        self.assertRedirects(response, reverse("admin:index"))
        product = Product.objects.get()
        self.assertTrue(product.enabled)
        self.assertEqual(product.name, "Test Flake")
        self.assertEqual(product.variants.get().status, StockStatus.OUT_OF_STOCK)

    def test_quick_add_restores_existing_soft_deleted_product(self):
        site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        product = Product.objects.create(site=site, url="https://smokingpipes.com/p/deleted-quick-add")
        product.soft_delete()

        observation = ProductObservation(
            name="Restored Flake", canonical_url=product.url,
            variants=[VariantObservation(external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK)],
        )
        with patch("monitor.services.catalog.get_adapter") as get_adapter:
            get_adapter.return_value.fetch.return_value = observation
            response = self.client.post(
                reverse("admin:monitor_product_quick_add"),
                {"url": product.url},
            )

        get_adapter.assert_called_once_with(site)
        self.assertRedirects(response, reverse("admin:monitor_product_change", args=[product.pk]))
        product.refresh_from_db()
        self.assertTrue(product.enabled)
        self.assertIsNone(product.deleted_at)
        self.assertEqual(Product.all_objects.filter(url=product.url).count(), 1)

    def test_preview_save_restores_existing_soft_deleted_product(self):
        site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        product = Product.objects.create(site=site, url="https://smokingpipes.com/p/deleted-preview")
        product.soft_delete()
        observation = ProductObservation(
            name="Test Flake", canonical_url=product.url,
            variants=[VariantObservation(external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK)],
        )

        with (
            patch("monitor.admin.get_adapter") as preview_adapter,
            patch("monitor.services.catalog.get_adapter") as catalog_adapter,
        ):
            preview_adapter.return_value.fetch.return_value = observation
            catalog_adapter.return_value.fetch.return_value = observation
            response = self.client.post(
                reverse("admin:monitor_product_preview"),
                {
                    "url": product.url,
                    "interval_minutes": "5",
                    "notify_site_group": "on",
                    "notify_all_group": "on",
                    "notes": "",
                    "save": "1",
                },
            )

        self.assertRedirects(response, reverse("admin:monitor_product_change", args=[product.pk]))
        product.refresh_from_db()
        self.assertTrue(product.enabled)
        self.assertIsNone(product.deleted_at)
        self.assertEqual(Product.all_objects.filter(url=product.url).count(), 1)
