from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import CrawlFailure, Product, Site, StockEvent, StockStatus, Variant


def admin_dashboard(request):
    if request.path.rstrip("/") != "/admin" or not getattr(request.user, "is_staff", False):
        return {}
    since = timezone.now() - timedelta(hours=24)
    sites = Site.objects.filter(enabled=True)
    stats = {
        "product_count": Product.objects.filter(enabled=True).count(),
        "in_stock_count": Variant.objects.filter(product__enabled=True, status=StockStatus.IN_STOCK).count(),
        "events_today": StockEvent.objects.filter(created_at__gte=since).count(),
        "failures_today": CrawlFailure.objects.filter(occurred_at__gte=since).count(),
        "site_count": sites.count(),
        "unhealthy_site_count": sites.filter(consecutive_failures__gte=3).count(),
    }
    return {
        "monitor_stats": stats,
        "monitor_recent_events": StockEvent.objects.select_related("variant__product__site").order_by("-created_at")[:8],
        "monitor_site_health": sites.annotate(
            active_products=Count("product", filter=Q(product__enabled=True))
        ).order_by("-consecutive_failures", "name"),
        "monitor_recent_failures": CrawlFailure.objects.select_related("product__site").order_by("-occurred_at")[:5],
        "monitor_products": Product.objects.select_related("site").prefetch_related("variants").filter(enabled=True).order_by("-created_at")[:30],
    }
