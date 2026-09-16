import base64
import hashlib
import hmac
import time
from urllib.parse import quote_plus, urlparse, parse_qsl, urlencode, urlunparse

import httpx
from django.utils import timezone

from monitor.models import ChannelPlatform


def signed_webhook_url(webhook_url, secret, timestamp=None):
    if not secret:
        return webhook_url
    timestamp = timestamp or int(time.time() * 1000)
    string_to_sign = f"{timestamp}\n{secret}".encode()
    signature = quote_plus(base64.b64encode(hmac.new(secret.encode(), string_to_sign, hashlib.sha256).digest()))
    parsed = urlparse(webhook_url)
    query = dict(parse_qsl(parsed.query))
    query.update({"timestamp": str(timestamp), "sign": signature})
    return urlunparse(parsed._replace(query=urlencode(query, safe="%")))


def feishu_signature(secret, timestamp):
    string_to_sign = f"{timestamp}\n{secret}".encode()
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _event_content(event):
    variant = event.variant
    product = variant.product
    price = f"{variant.currency} {event.price}" if event.price is not None else "以商城页面为准"
    title = f"【{product.site.name} 补货提醒】{product.name}"
    return product, variant, price, title


def build_message(event, platform=ChannelPlatform.DINGTALK):
    product, variant, price, title = _event_content(event)
    if platform == ChannelPlatform.FEISHU:
        details = "\n".join([
            f"**规格：** {variant.name}",
            f"**价格：** {price}",
            f"**站点：** {product.site.get_region_display()}",
            f"**检测时间：** {timezone.localtime(event.created_at):%Y-%m-%d %H:%M:%S}",
            "库存变化较快，请以商城页面为准。",
        ])
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "green",
                    "title": {"tag": "plain_text", "content": title[:100]},
                },
                "elements": [
                    {"tag": "markdown", "content": details},
                    {
                        "tag": "action",
                        "actions": [{
                            "tag": "button",
                            "type": "primary",
                            "text": {"tag": "plain_text", "content": "立即查看商品"},
                            "url": product.url,
                        }],
                    },
                ],
            },
        }

    text = "\n\n".join([
        f"### {title}",
        f"![商品图片]({product.image_url})" if product.image_url else "",
        f"**规格：** {variant.name}",
        f"**价格：** {price}",
        f"**站点：** {product.site.get_region_display()}",
        f"**检测时间：** {timezone.localtime(event.created_at):%Y-%m-%d %H:%M:%S}",
        f"[立即查看商品]({product.url})",
        "> 库存变化较快，请以商城页面为准。",
    ]).replace("\n\n\n\n", "\n\n")
    return {"msgtype": "markdown", "markdown": {"title": title[:60], "text": text}}


def build_test_message(platform):
    timestamp = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
    if platform == ChannelPlatform.FEISHU:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "template": "blue",
                    "title": {"tag": "plain_text", "content": "补货机器人测试"},
                },
                "elements": [{
                    "tag": "markdown",
                    "content": f"后台连接正常。\n\n测试时间：{timestamp}",
                }],
            },
        }
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": "补货机器人测试",
            "text": f"### 补货机器人测试\n\n后台连接正常。\n\n测试时间：{timestamp}",
        },
    }


def send_channel(channel, payload):
    if channel.platform == ChannelPlatform.FEISHU:
        request_payload = dict(payload)
        if channel.secret:
            timestamp = int(time.time())
            request_payload.update({
                "timestamp": str(timestamp),
                "sign": feishu_signature(channel.secret, timestamp),
            })
        url = channel.webhook_url
    else:
        request_payload = payload
        url = signed_webhook_url(channel.webhook_url, channel.secret)

    response = httpx.post(url, json=request_payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    if channel.platform == ChannelPlatform.FEISHU:
        code = data.get("code", data.get("StatusCode", 0))
        if code != 0:
            raise RuntimeError(f"飞书返回错误：{data}")
    elif data.get("errcode") != 0:
        raise RuntimeError(f"钉钉返回错误：{data}")
    return data
