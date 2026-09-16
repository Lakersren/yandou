import logging

from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from monitor.models import Product
from monitor.services.catalog import (
    InvalidProductUrl,
    SiteUnavailable,
    UnreadableStock,
    UnsupportedSite,
    add_product,
)
from monitor.tasks import enqueue_product_check

from .auth import error, json_body, ok, staff_json_required
from .serializers import serialize_product


logger = logging.getLogger(__name__)


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


def _product_or_error(product_id):
    try:
        return Product.objects.select_related("site").prefetch_related("variants").get(pk=product_id)
    except Product.DoesNotExist:
        return None


@require_http_methods(["GET", "POST"])
@staff_json_required
def products(request):
    if request.method == "GET":
        queryset = Product.objects.select_related("site").prefetch_related("variants").order_by("-updated_at", "-pk")
        query = request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(url__icontains=query))
        if site := request.GET.get("site"):
            queryset = queryset.filter(site__code=site)
        if status := request.GET.get("status"):
            queryset = queryset.filter(variants__status=status).distinct()

        page = _positive_int(request.GET.get("page"), 1, minimum=1)
        page_size = _positive_int(request.GET.get("page_size"), 20, minimum=10, maximum=100)
        total = queryset.count()
        start = (page - 1) * page_size
        return ok({
            "items": [serialize_product(product) for product in queryset[start:start + page_size]],
            "total": total,
            "page": page,
            "page_size": page_size,
        })

    try:
        payload = json_body(request)
    except ValueError:
        return error("invalid_json", "请求内容不是有效 JSON")
    if not isinstance(payload, dict):
        return error("invalid_json", "请求内容不是有效 JSON")
    try:
        product, outcome = add_product(payload.get("url"), request.user)
    except InvalidProductUrl as exc:
        return error(exc.code, str(exc), fields={"url": "请输入有效的商品 URL"})
    except (UnsupportedSite, UnreadableStock) as exc:
        return error(exc.code, str(exc))
    except SiteUnavailable as exc:
        return error(exc.code, str(exc), status=502)
    except Exception:
        logger.exception("Console product add failed")
        return error("catalog_error", "添加失败，请稍后重试", status=500)
    product = Product.objects.select_related("site").prefetch_related("variants").get(pk=product.pk)
    return ok({"product": serialize_product(product), "outcome": outcome}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@staff_json_required
def product_detail(request, product_id):
    product = _product_or_error(product_id)
    if product is None:
        return error("not_found", "商品不存在", status=404)

    if request.method == "GET":
        return ok(serialize_product(product, include_detail=True))

    if request.method == "PATCH":
        try:
            payload = json_body(request)
        except ValueError:
            return error("invalid_json", "请求内容不是有效 JSON")
        if not isinstance(payload, dict) or set(payload) != {"enabled"} or not isinstance(payload["enabled"], bool):
            return error("invalid_fields", "只允许更新 enabled")
        product.enabled = payload["enabled"]
        product.save(update_fields=["enabled", "updated_at"])
        return ok(serialize_product(product))

    product.soft_delete()
    return HttpResponse(status=204)


@require_http_methods(["POST"])
@staff_json_required
def check(request, product_id):
    product = Product.objects.select_related("site").filter(pk=product_id).first()
    if product is None:
        return error("not_found", "商品不存在", status=404)
    queued = enqueue_product_check(product)
    return ok({"queued": queued}, status=202)
