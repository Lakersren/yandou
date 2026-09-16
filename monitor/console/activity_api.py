from django.db.models import Count, Q
from django.views.decorators.http import require_GET, require_POST

from monitor.models import CrawlFailure, NotificationLog, StockEvent
from monitor.tasks import enqueue_product_check, notify_event

from .auth import error, ok, staff_json_required
from .serializers import serialize_crawl_failure, serialize_event, serialize_notification_failure


def _positive_int(value, default, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _pagination(request, total):
    page = _positive_int(request.GET.get("page"), 1, minimum=1)
    page_size = _positive_int(request.GET.get("page_size"), 20, minimum=10, maximum=100)
    return page, page_size, (page - 1) * page_size, total


@require_GET
@staff_json_required
def events(request):
    queryset = (
        StockEvent.objects.select_related("variant__product__site")
        .annotate(
            notification_total=Count("notifications"),
            notification_success=Count("notifications", filter=Q(notifications__success=True)),
        )
        .order_by("-created_at")
    )
    page, page_size, start, total = _pagination(request, queryset.count())
    return ok({
        "items": [serialize_event(event) for event in queryset[start:start + page_size]],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@require_GET
@staff_json_required
def failures(request):
    crawl_failures = CrawlFailure.objects.select_related("product__site").order_by("-occurred_at", "-pk")
    if request.GET.get("active") == "1":
        current_product_ids = set(
            CrawlFailure.objects.filter(product__enabled=True)
            .exclude(product__last_error="")
            .values_list("product_id", flat=True)
        )
        latest_by_product = {}
        for failure in crawl_failures.filter(product_id__in=current_product_ids):
            latest_by_product.setdefault(failure.product_id, failure)
        crawl_failures = latest_by_product.values()
    notification_failures = (
        NotificationLog.objects.filter(success=False)
        .select_related("event__variant__product__site")
        .order_by("-attempted_at", "-pk")
    )
    items = [serialize_crawl_failure(failure) for failure in crawl_failures]
    items.extend(serialize_notification_failure(notification) for notification in notification_failures)
    items.sort(
        key=lambda item: (
            item["occurred_at"],
            item["kind"] == "notification",
            int(item["id"].partition(":")[2]),
        ),
        reverse=True,
    )
    page, page_size, start, total = _pagination(request, len(items))
    return ok({
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


def _parse_failure_id(failure_id):
    kind, separator, object_id = failure_id.partition(":")
    if separator != ":" or kind not in {"crawl", "notification"} or not object_id.isdecimal():
        return None, None
    return kind, int(object_id)


@require_POST
@staff_json_required
def retry_failure(_request, failure_id):
    kind, object_id = _parse_failure_id(failure_id)
    if kind is None:
        return error("invalid_failure_id", "异常记录标识无效")

    if kind == "crawl":
        try:
            failure = CrawlFailure.objects.select_related("product__site").get(pk=object_id)
        except CrawlFailure.DoesNotExist:
            return error("not_found", "异常记录不存在", status=404)
        queued = enqueue_product_check(failure.product)
    else:
        try:
            notification = NotificationLog.objects.only("event_id").get(pk=object_id, success=False)
        except NotificationLog.DoesNotExist:
            return error("not_found", "异常记录不存在", status=404)
        notify_event.delay(notification.event_id)
        queued = True
    return ok({"queued": queued}, status=202)
