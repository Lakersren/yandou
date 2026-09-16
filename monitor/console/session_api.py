from datetime import datetime, timedelta

from django.contrib.auth import logout as auth_logout
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from monitor.models import CrawlFailure, NotificationLog, Product, Region, StockEvent, StockStatus, Variant

from .auth import ok, staff_json_required
from .serializers import (
    serialize_datetime,
    serialize_event_summary,
    serialize_failure_summary,
    serialize_notification_failure_summary,
    serialize_product_summary,
)


HEARTBEAT_CACHE_KEY = "monitor:scheduler:heartbeat"
SCHEDULER_HEALTH_WINDOW = timedelta(seconds=180)


def scheduler_health():
    value = cache.get(HEARTBEAT_CACHE_KEY)
    if not isinstance(value, str):
        return "unhealthy"
    try:
        heartbeat = datetime.fromisoformat(value)
        age = timezone.now() - heartbeat
    except (TypeError, ValueError):
        return "unhealthy"
    return "healthy" if age <= SCHEDULER_HEALTH_WINDOW else "unhealthy"


@require_GET
@staff_json_required
def session(request):
    return ok({
        "user": {"id": request.user.id, "username": request.user.get_username()},
        "scheduler": scheduler_health(),
    })


@require_POST
@staff_json_required
def logout_view(request):
    auth_logout(request)
    return ok({"redirect": "/admin/login/?next=/console/"})


@require_GET
@staff_json_required
def dashboard(_request):
    since = timezone.now() - timedelta(hours=24)
    products = Product.objects.select_related("site").prefetch_related("variants")
    active_products = list(products.filter(enabled=True).order_by("site__region", "site__name", "name", "pk"))
    recent_products = products.order_by("-updated_at", "-pk")[:8]
    recent_events = StockEvent.objects.select_related("variant__product__site").order_by("-created_at")[:8]
    crawl_failures = CrawlFailure.objects.select_related("product__site").order_by("-occurred_at", "-pk")[:8]
    notification_failures = (
        NotificationLog.objects.filter(success=False)
        .select_related("event__variant__product__site")
        .order_by("-attempted_at", "-pk")[:8]
    )
    recent_failures = [serialize_failure_summary(failure) for failure in crawl_failures]
    recent_failures.extend(serialize_notification_failure_summary(failure) for failure in notification_failures)
    recent_failures.sort(
        key=lambda item: (
            item["occurred_at"],
            item["id"].startswith("notification:"),
            int(item["id"].partition(":")[2]),
        ),
        reverse=True,
    )

    current_error_products = [product for product in active_products if product.last_error]
    latest_crawl_failures = {}
    if current_error_products:
        current_product_ids = [product.pk for product in current_error_products]
        current_failure_rows = (
            CrawlFailure.objects.filter(product_id__in=current_product_ids)
            .select_related("product__site")
            .order_by("-occurred_at", "-pk")
        )
        for failure in current_failure_rows:
            latest_crawl_failures.setdefault(failure.product_id, failure)
    pending_failures = [
        serialize_failure_summary(failure)
        for failure in latest_crawl_failures.values()
    ]
    pending_failures.extend(
        serialize_notification_failure_summary(failure)
        for failure in notification_failures
    )
    pending_failures.sort(key=lambda item: item["occurred_at"], reverse=True)

    def counts_by_region(queryset, region_path):
        rows = queryset.values(region_path).annotate(total=Count("id"))
        return {row[region_path]: row["total"] for row in rows}

    in_stock_by_region = counts_by_region(
        Variant.objects.filter(product__enabled=True, status=StockStatus.IN_STOCK),
        "product__site__region",
    )
    restocks_by_region = counts_by_region(
        StockEvent.objects.filter(created_at__gte=since, variant__product__enabled=True),
        "variant__product__site__region",
    )
    crawl_failures_by_region = counts_by_region(
        CrawlFailure.objects.filter(occurred_at__gte=since, product__enabled=True),
        "product__site__region",
    )
    notification_failures_by_region = counts_by_region(
        NotificationLog.objects.filter(
            success=False,
            attempted_at__gte=since,
            event__variant__product__enabled=True,
        ),
        "event__variant__product__site__region",
    )
    active_crawl_failures_by_region = counts_by_region(
        Product.objects.filter(enabled=True).exclude(last_error=""),
        "site__region",
    )
    active_notification_failures_by_region = counts_by_region(
        NotificationLog.objects.filter(success=False, event__variant__product__enabled=True),
        "event__variant__product__site__region",
    )
    products_by_region = {value: [] for value, _label in Region.choices if value != Region.ALL}
    for product in active_products:
        products_by_region.setdefault(product.site.region, []).append(product)

    region_summaries = []
    for region, label in Region.choices:
        if region == Region.ALL:
            continue
        region_products = products_by_region.get(region, [])
        checked_values = [product.last_checked_at for product in region_products if product.last_checked_at]
        region_summaries.append({
            "region": region,
            "label": label,
            "monitored_products": len(region_products),
            "in_stock_variants": in_stock_by_region.get(region, 0),
            "restocks_24h": restocks_by_region.get(region, 0),
            "failures_24h": (
                crawl_failures_by_region.get(region, 0)
                + notification_failures_by_region.get(region, 0)
            ),
            "active_failures": (
                active_crawl_failures_by_region.get(region, 0)
                + active_notification_failures_by_region.get(region, 0)
            ),
            "last_checked_at": serialize_datetime(max(checked_values)) if checked_values else None,
            "products": [serialize_product_summary(product) for product in region_products],
        })

    return ok({
        "monitored_products": products.filter(enabled=True).count(),
        "in_stock_variants": Variant.objects.filter(
            product__enabled=True,
            status=StockStatus.IN_STOCK,
        ).count(),
        "restocks_24h": StockEvent.objects.filter(created_at__gte=since).count(),
        "failures_24h": (
            CrawlFailure.objects.filter(occurred_at__gte=since).count()
            + NotificationLog.objects.filter(success=False, attempted_at__gte=since).count()
        ),
        "active_failures": (
            len(current_error_products)
            + NotificationLog.objects.filter(success=False, event__variant__product__enabled=True).count()
        ),
        "recent_products": [serialize_product_summary(product) for product in recent_products],
        "recent_events": [serialize_event_summary(event) for event in recent_events],
        "recent_failures": recent_failures[:8],
        "pending_failures": pending_failures[:8],
        "region_summaries": region_summaries,
    })


@staff_member_required(login_url="/admin/login/")
@ensure_csrf_cookie
def console_shell(request, route=None):
    return render(request, "console/index.html")
