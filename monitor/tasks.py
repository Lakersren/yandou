from celery import shared_task
from datetime import timedelta
import random
from uuid import uuid4

from django.core.cache import cache
from django.utils import timezone

from .models import CrawlFailure, NotificationChannel, NotificationLog, Product, StockEvent, StockSnapshot
from .services.checker import check_product as run_check
from .services.notifier import build_message, send_channel


PRODUCT_CHECK_LOCK_TIMEOUT = 3600
DEFAULT_CHECK_QUEUE = "celery"
BRIGHT_DATA_CHECK_QUEUE = "bright_data"


def _product_check_lock_key(product_id):
    return f"monitor:product-check:{product_id}"


def product_check_queue(product):
    protected_adapters = {"havanahouse", "smokingpipes"}
    return BRIGHT_DATA_CHECK_QUEUE if product.site.adapter in protected_adapters else DEFAULT_CHECK_QUEUE


def enqueue_product_check(product, priority=9):
    lock_key = _product_check_lock_key(product.pk)
    task_id = str(uuid4())
    if not cache.add(lock_key, task_id, timeout=PRODUCT_CHECK_LOCK_TIMEOUT):
        return False
    try:
        check_product.apply_async(
            args=[product.pk],
            task_id=task_id,
            queue=product_check_queue(product),
            priority=priority,
        )
    except Exception:
        cache.delete(lock_key)
        raise
    return True


@shared_task(name="monitor.tasks.dispatch_due_products")
def dispatch_due_products():
    now = timezone.now()
    cache.set("monitor:scheduler:heartbeat", now.isoformat(), timeout=300)
    products = list(
        Product.objects.filter(enabled=True, site__enabled=True, next_check_at__lte=now)
        .select_related("site")
        .order_by("next_check_at")[:500]
    )
    dispatched = 0
    for product in products:
        lock_key = _product_check_lock_key(product.pk)
        task_id = str(uuid4())
        if not cache.add(lock_key, task_id, timeout=PRODUCT_CHECK_LOCK_TIMEOUT):
            continue
        next_check_at = now + timedelta(
            minutes=product.effective_interval,
            seconds=random.randint(0, 45),
        )
        claimed = Product.objects.filter(
            pk=product.pk,
            enabled=True,
            site__enabled=True,
            next_check_at__lte=now,
        ).update(next_check_at=next_check_at)
        if claimed:
            try:
                check_product.apply_async(
                    args=[product.pk],
                    task_id=task_id,
                    queue=product_check_queue(product),
                )
                dispatched += 1
            except Exception:
                cache.delete(lock_key)
                Product.objects.filter(pk=product.pk).update(next_check_at=now)
                raise
        else:
            cache.delete(lock_key)
    return dispatched


@shared_task(bind=True, name="monitor.tasks.check_product", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def check_product(self, product_id):
    lock_key = _product_check_lock_key(product_id)
    task_id = self.request.id or f"sync:{uuid4()}"
    lock_owner = cache.get(lock_key)
    if lock_owner is None:
        if not cache.add(lock_key, task_id, timeout=PRODUCT_CHECK_LOCK_TIMEOUT):
            return []
    elif lock_owner != task_id:
        return []
    try:
        event_ids = run_check(product_id)
        for event_id in event_ids:
            notify_event.delay(event_id)
        return event_ids
    finally:
        if cache.get(lock_key) == task_id:
            cache.delete(lock_key)


@shared_task(name="monitor.tasks.notify_event", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def notify_event(event_id):
    event = StockEvent.objects.select_related("variant__product__site").get(pk=event_id)
    product = event.variant.product
    failures = []
    channels = (
        channel for channel in NotificationChannel.objects.filter(enabled=True)
        if channel.receives_product(product)
    )
    for channel in channels:
        if NotificationLog.objects.filter(event=event, channel=channel, success=True).exists():
            continue
        try:
            payload = build_message(event, channel.platform)
            response = send_channel(channel, payload)
            NotificationLog.objects.update_or_create(
                event=event, channel=channel,
                defaults={"success": True, "response_text": str(response)[:2000]},
            )
        except Exception as exc:
            NotificationLog.objects.update_or_create(
                event=event, channel=channel,
                defaults={"success": False, "response_text": str(exc)[:2000]},
            )
            failures.append(str(exc))
    if failures:
        raise RuntimeError("；".join(failures))


@shared_task(name="monitor.tasks.purge_old_records")
def purge_old_records():
    now = timezone.now()
    snapshots, _ = StockSnapshot.objects.filter(checked_at__lt=now - timedelta(days=30)).delete()
    failures, _ = CrawlFailure.objects.filter(occurred_at__lt=now - timedelta(days=90)).delete()
    return {"snapshots": snapshots, "failures": failures}
