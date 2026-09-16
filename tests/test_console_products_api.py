import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from monitor.models import Product, Region, Site, StockSnapshot, StockStatus, Variant
from monitor.services.scraper import ProductObservation, VariantObservation


class ConsoleProductsApiTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("operator", is_staff=True)
        self.site = Site.objects.create(code="sp", name="SP", region=Region.US, domain="smokingpipes.com")
        self.product = Product.objects.create(
            site=self.site,
            url="https://smokingpipes.com/p/existing",
            name="Existing Product",
        )
        Variant.objects.create(product=self.product, external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK)
        deleted = Product.objects.create(site=self.site, url="https://smokingpipes.com/p/deleted")
        deleted.soft_delete()
        self.client.force_login(self.staff)
        self.client.get("/console/")
        self.csrf = self.client.cookies["csrftoken"].value
        self.observation = ProductObservation(
            name="New Product",
            canonical_url="https://smokingpipes.com/p/1",
            variants=[VariantObservation(external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK)],
        )

    def test_product_list_excludes_soft_deleted(self):
        response = self.client.get("/api/console/v1/products")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 1)

    @patch("monitor.services.catalog.get_adapter")
    def test_add_requires_only_url(self, get_adapter):
        get_adapter.return_value.fetch.return_value = self.observation

        response = self.client.post(
            "/api/console/v1/products",
            data=json.dumps({"url": "https://smokingpipes.com/p/1"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["outcome"], "created")

    @patch("monitor.services.catalog.get_adapter")
    def test_created_and_restored_products_appear_first_on_page_one(self, get_adapter):
        get_adapter.return_value.fetch.return_value = self.observation
        Product.objects.bulk_create([
            Product(site=self.site, url=f"https://smokingpipes.com/p/filler-{index}")
            for index in range(21)
        ])
        Product.all_objects.filter(pk=self.product.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        for outcome, url in [("created", self.observation.canonical_url), ("restored", self.product.url)]:
            with self.subTest(outcome=outcome):
                if outcome == "restored":
                    self.product.soft_delete()
                response = self.client.post(
                    "/api/console/v1/products", data=json.dumps({"url": url}),
                    content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf,
                )
                self.assertEqual(response.json()["data"]["outcome"], outcome)
                page = self.client.get("/api/console/v1/products?page=1&page_size=20").json()["data"]
                self.assertGreater(page["total"], 20)
                self.assertEqual(page["items"][0]["id"], response.json()["data"]["product"]["id"])

    def test_product_freshness_ties_use_descending_id(self):
        later = Product.objects.create(site=self.site, url="https://smokingpipes.com/p/later")
        Product.objects.update(updated_at=timezone.now(), created_at=timezone.now())
        data = self.client.get("/api/console/v1/products").json()["data"]
        self.assertEqual([item["id"] for item in data["items"]], [later.pk, self.product.pk])

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

    def test_invalid_url_has_field_error(self):
        response = self.client.post(
            "/api/console/v1/products",
            data=json.dumps({"url": "not a URL"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["fields"], {"url": "请输入有效的商品 URL"})

    def test_detail_hides_raw_snapshot_hint(self):
        variant = self.product.variants.get()
        StockSnapshot.objects.create(
            product=self.product,
            variant=variant,
            observed_status=StockStatus.OUT_OF_STOCK,
            raw_hint="internal parser data",
        )

        response = self.client.get(f"/api/console/v1/products/{self.product.pk}")

        data = response.json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("image_url", self.client.get("/api/console/v1/products").json()["data"]["items"][0])
        self.assertEqual(data["snapshots"][0]["variant_name"], "50g")
        self.assertNotIn("raw_hint", data["snapshots"][0])

    @patch("monitor.console.products_api.enqueue_product_check", return_value=True)
    def test_check_queues_product(self, enqueue):
        response = self.client.post(
            f"/api/console/v1/products/{self.product.pk}/check",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["data"], {"queued": True})
        self.assertEqual(enqueue.call_args.args[0].pk, self.product.pk)
