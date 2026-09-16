from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from monitor.models import (
    CrawlFailure,
    DingTalkChannel,
    Product,
    Region,
    Site,
    StockEvent,
    StockStatus,
    Variant,
)


class Command(BaseCommand):
    help = "Seed the isolated browser acceptance-test database."

    def handle(self, *args, **options):
        user_model = get_user_model()
        operator, _ = user_model.objects.update_or_create(
            username="operator",
            defaults={"is_staff": True, "is_active": True},
        )
        operator.set_password("operator-e2e-only")
        operator.save(update_fields=["password", "is_staff", "is_active"])

        site, _ = Site.objects.update_or_create(
            code="sp",
            defaults={
                "name": "Smokingpipes",
                "region": Region.US,
                "domain": "smokingpipes.com",
                "adapter": "generic",
                "enabled": True,
                "default_interval_minutes": 5,
            },
        )
        now = timezone.now()
        out_of_stock = self._product(
            site, operator, "https://smokingpipes.com/product/seed-out-of-stock",
            "Seed Out of Stock", StockStatus.OUT_OF_STOCK, now,
        )
        in_stock = self._product(
            site, operator, "https://smokingpipes.com/product/seed-in-stock",
            "Seed In Stock", StockStatus.IN_STOCK, now,
        )
        in_stock_variant = in_stock.variants.get(external_id="50g")
        StockEvent.objects.filter(variant=in_stock_variant).delete()
        StockEvent.objects.create(
            variant=in_stock_variant,
            old_status=StockStatus.OUT_OF_STOCK,
            new_status=StockStatus.IN_STOCK,
            price="12.50",
        )
        CrawlFailure.objects.filter(product=out_of_stock).delete()
        CrawlFailure.objects.create(
            product=out_of_stock,
            error_type="UnreadableStock",
            message="Fixture crawl failure for retry coverage",
        )
        self._channel("E2E 美站群", Region.US)
        self._channel("E2E 综合群", Region.ALL)
        self.stdout.write(self.style.SUCCESS("Seeded isolated console E2E fixtures."))

    @staticmethod
    def _product(site, user, url, name, status, now):
        product, _ = Product.all_objects.update_or_create(
            url=url,
            defaults={
                "site": site,
                "name": name,
                "enabled": True,
                "deleted_at": None,
                "last_checked_at": now,
                "next_check_at": now,
                "last_error": "",
                "created_by": user,
            },
        )
        Variant.objects.update_or_create(
            product=product,
            external_id="50g",
            defaults={
                "name": "50g",
                "price": "12.50",
                "currency": "USD",
                "status": status,
                "candidate_status": status,
                "candidate_count": 0,
                "last_seen_at": now,
            },
        )
        return product

    @staticmethod
    def _channel(name, region):
        DingTalkChannel.objects.update_or_create(
            name=name,
            region=region,
            defaults={
                "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=e2e1",
                "secret": "SEC-e2e-only",
                "enabled": True,
            },
        )
