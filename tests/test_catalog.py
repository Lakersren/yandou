from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from monitor.models import Product, Region, Site, StockEvent, StockStatus
from monitor.services.catalog import UnsupportedSite, add_product
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

    @patch("monitor.services.catalog.get_adapter")
    def test_restore_discontinues_absent_variants_without_losing_history(self, get_adapter):
        get_adapter.return_value.fetch.return_value = ProductObservation(
            name="Old Product", canonical_url=self.observation.canonical_url,
            variants=[VariantObservation(external_id="old", name="Old tin", status=StockStatus.IN_STOCK)],
        )
        original, _ = add_product(self.observation.canonical_url, self.user)
        old_variant = original.variants.get()
        old_snapshot = old_variant.snapshots.get()
        old_variant.candidate_count = 1
        old_variant.save(update_fields=["candidate_count"])
        original.soft_delete()
        get_adapter.return_value.fetch.return_value = self.observation

        restored, outcome = add_product(self.observation.canonical_url, self.user)

        self.assertEqual(outcome, "restored")
        self.assertEqual(restored.pk, original.pk)
        self.assertEqual(restored.stock_status, StockStatus.OUT_OF_STOCK)
        old_variant.refresh_from_db()
        self.assertEqual(old_variant.status, StockStatus.DISCONTINUED)
        self.assertEqual(old_variant.candidate_status, StockStatus.DISCONTINUED)
        self.assertEqual(old_variant.candidate_count, 0)
        self.assertEqual(old_variant.snapshots.get().pk, old_snapshot.pk)
        self.assertEqual(old_variant.snapshots.get().observed_status, StockStatus.IN_STOCK)
        self.assertEqual(restored.variants.count(), 2)
        self.assertEqual(restored.snapshots.count(), 2)
        self.assertFalse(StockEvent.objects.filter(variant__product=restored).exists())

    def test_rejects_unknown_domain(self):
        with self.assertRaises(UnsupportedSite):
            add_product("https://example.com/p/1", self.user)
