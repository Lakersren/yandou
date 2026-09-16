from datetime import timedelta

import httpx
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from monitor.models import Product, Site, StockSnapshot, StockStatus, Variant

from .http import FetchError
from .scraper import ProductObservation, get_adapter


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


def fetch_observation(site: Site, url: str) -> ProductObservation:
    return get_adapter(site).fetch(url)


def apply_baseline(product: Product, observation: ProductObservation) -> None:
    now = timezone.now()
    product.name = observation.name
    product.image_url = observation.image_url
    product.last_checked_at = now
    product.last_error = ""
    product.next_check_at = now + timedelta(minutes=product.site.default_interval_minutes)
    product.save(update_fields=[
        "name", "image_url", "last_checked_at", "last_error", "next_check_at", "updated_at",
    ])

    # Preserve identities and observations, but retire stock absent from the fresh baseline.
    product.variants.exclude(external_id__in=[item.external_id for item in observation.variants]).update(
        status=StockStatus.DISCONTINUED,
        candidate_status=StockStatus.DISCONTINUED,
        candidate_count=0,
    )

    for item in observation.variants:
        variant, _created = Variant.objects.update_or_create(
            product=product,
            external_id=item.external_id,
            defaults={
                "name": item.name,
                "price": item.price,
                "currency": item.currency,
                "status": item.status,
                "candidate_status": item.status,
                "candidate_count": 0,
                "last_seen_at": now,
            },
        )
        StockSnapshot.objects.create(
            product=product,
            variant=variant,
            observed_status=item.status,
            price=item.price,
            raw_hint=item.hint,
        )

    product.site.last_success_at = now
    product.site.consecutive_failures = 0
    product.site.save(update_fields=["last_success_at", "consecutive_failures"])


def add_product(url: str, user=None) -> tuple[Product, str]:
    try:
        URLValidator(schemes=["http", "https"])(url)
    except (TypeError, ValidationError) as exc:
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
            product = Product.all_objects.select_for_update().select_related("site").get(pk=existing.pk)
            product.restore()
            outcome = "restored"
        else:
            product = Product.all_objects.create(site=site, url=url, created_by=user)
            outcome = "created"
        apply_baseline(product, observation)
    return product, outcome
