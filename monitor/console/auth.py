import json
from functools import wraps

from django.http import JsonResponse


def ok(data, status=200):
    return JsonResponse({"data": data}, status=status)


def error(code, message, status=400, fields=None):
    payload = {"code": code, "message": message}
    if fields:
        payload["fields"] = fields
    return JsonResponse(payload, status=status)


def json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("请求内容不是有效 JSON") from exc


def staff_json_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error("authentication_required", "请先登录", 401)
        if not request.user.is_staff:
            return error("permission_denied", "没有后台访问权限", 403)
        return view(request, *args, **kwargs)

    return wrapped
