import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from monitor.models import CrawlFailure, Product, StockEvent, StockSnapshot, StockStatus, Variant

from .scraper import get_adapter


def check_product(product_id):
    product = Product.objects.select_related("site").get(pk=product_id)
    now = timezone.now()
    try:
        observation = get_adapter(product.site).fetch(product.url)
        if not observation.variants:
            raise ValueError("页面没有可识别的商品规格")
        if all(item.status == StockStatus.UNKNOWN for item in observation.variants):
            raise ValueError("页面可访问，但无法可靠判断库存")
    except Exception as exc:
        message = str(exc)[:2000]
        Product.objects.filter(pk=product.pk).update(last_checked_at=now, last_error=message)
        CrawlFailure.objects.create(product=product, error_type=type(exc).__name__, message=message)
        product.site.consecutive_failures += 1
        product.site.save(update_fields=["consecutive_failures"])
        raise

    event_ids = []
    with transaction.atomic():
        product = Product.objects.select_for_update().select_related("site").get(pk=product_id)
        if observation.name:
            product.name = observation.name
        if observation.image_url:
            product.image_url = observation.image_url
        product.last_checked_at = now
        product.last_error = ""
        product.next_check_at = now + timedelta(minutes=product.effective_interval, seconds=random.randint(0, 45))
        product.save()

        has_existing_variants = product.variants.exists()
        for item in observation.variants:
            variant, created = Variant.objects.get_or_create(
                product=product, external_id=item.external_id,
                defaults={"name": item.name, "status": item.status, "candidate_status": item.status, "last_seen_at": now},
            )
            StockSnapshot.objects.create(
                product=product, variant=variant, observed_status=item.status,
                price=item.price, raw_hint=item.hint,
            )
            if created:
                variant.price = item.price
                variant.currency = item.currency
                variant.save()
                continue
            variant.name = item.name
            variant.price = item.price
            variant.currency = item.currency
            variant.last_seen_at = now
            if item.status != StockStatus.UNKNOWN and item.status != variant.status:
                if variant.candidate_status == item.status:
                    variant.candidate_count += 1
                else:
                    variant.candidate_status = item.status
                    variant.candidate_count = 1
                required = 2 if item.status == StockStatus.IN_STOCK else 1
                if variant.candidate_count >= required:
                    old_status = variant.status
                    variant.status = item.status
                    variant.candidate_count = 0
                    if has_existing_variants and old_status in {StockStatus.OUT_OF_STOCK, StockStatus.DISCONTINUED} and item.status == StockStatus.IN_STOCK:
                        event = StockEvent.objects.create(
                            variant=variant, old_status=old_status, new_status=item.status, price=item.price,
                        )
                        event_ids.append(event.pk)
            else:
                variant.candidate_status = item.status
                variant.candidate_count = 0
            variant.save()

        product.site.last_success_at = now
        product.site.consecutive_failures = 0
        product.site.save(update_fields=["last_success_at", "consecutive_failures"])
    return event_ids

