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
