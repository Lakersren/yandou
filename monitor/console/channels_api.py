from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.module_loading import import_string
from django.views.decorators.http import require_http_methods, require_POST

from monitor.models import ChannelPlatform, NotificationChannel, Region
from monitor.services.notifier import build_test_message, send_channel

from .auth import error, json_body, ok, staff_json_required


def serialize_channel(channel):
    webhook = channel.webhook_url or ""
    secret = channel.secret or ""
    return {
        "id": channel.id,
        "platform": channel.platform,
        "name": channel.name,
        "region": channel.region,
        "regions": channel.effective_regions,
        "receive_scope_label": channel.receive_scope_label,
        "enabled": channel.enabled,
        "webhook_configured": bool(webhook),
        "webhook_mask": _webhook_mask(webhook),
        "secret_configured": bool(secret),
    }


def _webhook_mask(webhook):
    if not webhook:
        return None
    parsed = urlparse(webhook)
    token = parse_qs(parsed.query).get("access_token", [""])[0]
    if not token and parsed.path:
        token = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    suffix = token[-4:] if token else ""
    return f"{parsed.hostname or ''} (...{suffix})" if suffix else (parsed.hostname or None)


def _validation_error(exc):
    fields = {}
    for name, messages in exc.message_dict.items():
        api_name = "webhook" if name == "webhook_url" else name
        fields[api_name] = messages[0]
    return error("invalid_fields", "提交内容无效", fields=fields)


def _payload_or_error(request):
    try:
        payload = json_body(request)
    except ValueError:
        return None, error("invalid_json", "请求内容不是有效 JSON")
    if not isinstance(payload, dict):
        return None, error("invalid_json", "请求内容不是有效 JSON")
    return payload, None


def _validate_payload(payload, required=False):
    allowed = {"name", "region", "regions", "enabled", "webhook", "secret"}
    fields = {}
    unexpected = set(payload) - allowed
    if unexpected:
        fields["fields"] = "包含不支持的字段"
    for field in ("name", "webhook") if required else ():
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            fields[field] = "此字段不能为空"
    if required and "region" not in payload and "regions" not in payload:
        fields["regions"] = "请选择接收范围"
    if "name" in payload and (not isinstance(payload["name"], str) or not payload["name"].strip()):
        fields["name"] = "请输入群名称"
    if "region" in payload and payload["region"] not in Region.values:
        fields["region"] = "请选择有效站点"
    if "regions" in payload:
        regions = payload["regions"]
        if not isinstance(regions, list) or not regions or any(value not in Region.values for value in regions):
            fields["regions"] = "请选择至少一个有效的接收范围"
    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        fields["enabled"] = "必须是布尔值"
    for field in ("webhook", "secret"):
        if field in payload and not isinstance(payload[field], str):
            fields[field] = "必须是字符串"
    return fields


def _apply_payload(channel, payload, create=False):
    if "name" in payload:
        channel.name = payload["name"].strip()
    if "region" in payload:
        channel.region = payload["region"]
        channel.regions = [payload["region"]]
    if "regions" in payload:
        channel.regions = payload["regions"]
        channel.region = Region.ALL if Region.ALL in payload["regions"] else payload["regions"][0]
    if "enabled" in payload:
        channel.enabled = payload["enabled"]
    if payload.get("webhook", "").strip():
        channel.webhook_url = payload["webhook"].strip()
    if payload.get("secret", "").strip():
        channel.secret = payload["secret"].strip()
    if create:
        # Required creation fields have been validated before this point.
        channel.webhook_url = payload["webhook"].strip()


@require_http_methods(["GET", "POST"])
@staff_json_required
def channels(request, platform):
    if request.method == "GET":
        queryset = NotificationChannel.objects.filter(platform=platform).order_by("-created_at", "-id")
        return ok([serialize_channel(channel) for channel in queryset])

    payload, response = _payload_or_error(request)
    if response:
        return response
    fields = _validate_payload(payload, required=True)
    if fields:
        return error("invalid_fields", "提交内容无效", fields=fields)
    channel = NotificationChannel(platform=platform)
    _apply_payload(channel, payload, create=True)
    try:
        channel.full_clean()
    except ValidationError as exc:
        return _validation_error(exc)
    channel.save()
    return ok(serialize_channel(channel), status=201)


@require_http_methods(["PATCH"])
@staff_json_required
def channel_detail(request, channel_id, platform):
    try:
        channel = NotificationChannel.objects.get(pk=channel_id, platform=platform)
    except NotificationChannel.DoesNotExist:
        return error("not_found", "通知群不存在", status=404)
    payload, response = _payload_or_error(request)
    if response:
        return response
    fields = _validate_payload(payload)
    if fields:
        return error("invalid_fields", "提交内容无效", fields=fields)
    _apply_payload(channel, payload)
    try:
        channel.full_clean()
    except ValidationError as exc:
        return _validation_error(exc)
    channel.save()
    return ok(serialize_channel(channel))


def _channel_sender():
    configured_sender = import_string(settings.CONSOLE_CHANNEL_SENDER)
    # Retain this module symbol for the standard sender so unit tests can patch it,
    # while non-default settings still support isolated end-to-end injection.
    if settings.CONSOLE_CHANNEL_SENDER == "monitor.services.notifier.send_channel":
        return send_channel
    return configured_sender


@require_POST
@staff_json_required
def test_channel(_request, channel_id, platform):
    try:
        channel = NotificationChannel.objects.get(pk=channel_id, platform=platform)
    except NotificationChannel.DoesNotExist:
        return error("not_found", "通知群不存在", status=404)
    if not channel.enabled:
        return error("channel_disabled", "已停用的通知群不能发送测试消息")
    payload = build_test_message(channel.platform)
    try:
        _channel_sender()(channel, payload)
    except Exception:
        platform_name = channel.get_platform_display()
        return error("channel_test_failed", f"测试消息发送失败，请检查{platform_name}群配置", status=502)
    return ok({"sent": True})
