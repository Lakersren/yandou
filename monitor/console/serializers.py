def serialize_datetime(value):
    return value.isoformat() if value else None


def decimal_string(value):
    return str(value) if value is not None else None


def serialize_product(product, include_detail=False):
    data = {
        "id": product.id,
        "name": product.name,
        "url": product.url,
        "site": {
            "code": product.site.code,
            "name": product.site.name,
            "region": product.site.region,
        },
        "enabled": product.enabled,
        "stock_status": product.stock_status,
        "stock_status_label": product.stock_status_label,
        "last_checked_at": serialize_datetime(product.last_checked_at),
        "last_error": bool(product.last_error),
        "variants": [
            {
                "id": variant.id,
                "name": variant.name,
                "price": decimal_string(variant.price),
                "currency": variant.currency,
                "status": variant.status,
            }
            for variant in product.variants.all()
        ],
    }
    if include_detail:
        data.update({
            "image_url": product.image_url,
            "created_at": serialize_datetime(product.created_at),
            "snapshots": [
                {
                    "variant_name": snapshot.variant.name if snapshot.variant else "",
                    "observed_status": snapshot.observed_status,
                    "price": decimal_string(snapshot.price),
                    "currency": snapshot.variant.currency if snapshot.variant else "",
                    "checked_at": serialize_datetime(snapshot.checked_at),
                }
                for snapshot in product.snapshots.select_related("variant").order_by("-checked_at")[:20]
            ],
        })
    return data


def serialize_product_summary(product):
    return {
        "id": product.id,
        "name": product.name or product.url,
        "url": product.url,
        "image_url": product.image_url,
        "site": {
            "id": product.site_id,
            "name": product.site.name,
            "region": product.site.region,
        },
        "stock_status": product.stock_status,
        "stock_status_label": product.stock_status_label,
        "enabled": product.enabled,
        "last_checked_at": serialize_datetime(product.last_checked_at),
    }


def serialize_event_summary(event):
    product = event.variant.product
    return {
        "id": event.id,
        "product": {
            "id": product.id,
            "name": product.name or product.url,
            "site_name": product.site.name,
        },
        "variant": {"id": event.variant_id, "name": event.variant.name},
        "old_status": event.old_status,
        "new_status": event.new_status,
        "price": str(event.price) if event.price is not None else None,
        "created_at": serialize_datetime(event.created_at),
    }


def serialize_failure_summary(failure):
    product = failure.product
    return {
        "id": f"crawl:{failure.id}",
        "kind": "crawl",
        "product": {
            "id": product.id,
            "name": product.name or product.url,
            "site_name": product.site.name,
        },
        "error_type": "crawl_failed",
        "message": "商品抓取失败，请稍后重试",
        "occurred_at": serialize_datetime(failure.occurred_at),
    }


def serialize_notification_failure_summary(notification):
    product = notification.event.variant.product
    return {
        "id": f"notification:{notification.id}",
        "kind": "notification",
        "product": {
            "id": product.id,
            "name": product.name or product.url,
            "site_name": product.site.name,
        },
        "error_type": "notification_failed",
        "message": "通知发送失败，请稍后重试",
        "occurred_at": serialize_datetime(notification.attempted_at),
    }


def serialize_event(event):
    product = event.variant.product
    successful_notifications = getattr(event, "notification_success", 0)
    total_notifications = getattr(event, "notification_total", 0)
    return {
        "id": event.id,
        "product": {"id": product.id, "name": product.name or product.url},
        "site": {
            "code": product.site.code,
            "name": product.site.name,
            "region": product.site.region,
        },
        "variant": {"id": event.variant_id, "name": event.variant.name},
        "price": decimal_string(event.price),
        "currency": event.variant.currency,
        "timestamp": serialize_datetime(event.created_at),
        "notifications": {
            "total": total_notifications,
            "success": successful_notifications,
            "failed": total_notifications - successful_notifications,
        },
    }


def serialize_crawl_failure(failure):
    product = failure.product
    return {
        "id": f"crawl:{failure.id}",
        "kind": "crawl",
        "product": {"id": product.id, "name": product.name or product.url},
        "site": {
            "code": product.site.code,
            "name": product.site.name,
            "region": product.site.region,
        },
        "message": "商品抓取失败，请稍后重试",
        "occurred_at": serialize_datetime(failure.occurred_at),
    }


def serialize_notification_failure(notification):
    product = notification.event.variant.product
    return {
        "id": f"notification:{notification.id}",
        "kind": "notification",
        "product": {"id": product.id, "name": product.name or product.url},
        "site": {
            "code": product.site.code,
            "name": product.site.name,
            "region": product.site.region,
        },
        "message": "通知发送失败，请稍后重试",
        "occurred_at": serialize_datetime(notification.attempted_at),
    }
