from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from monitor.models import ChannelPlatform
from monitor.services.notifier import build_test_message, feishu_signature, send_channel, signed_webhook_url


class DingTalkSignatureTests(SimpleTestCase):
    def test_adds_timestamp_and_signature(self):
        result = signed_webhook_url("https://oapi.dingtalk.com/robot/send?access_token=x", "SECabc", 123456)
        query = parse_qs(urlparse(result).query)
        self.assertEqual(query["access_token"], ["x"])
        self.assertEqual(query["timestamp"], ["123456"])
        self.assertTrue(query["sign"][0])


class FeishuNotifierTests(SimpleTestCase):
    def test_signature_is_deterministic(self):
        self.assertEqual(
            feishu_signature("secret", 1700000000),
            "fiWS2+gh28DOydAv7hzONH/mDn9+b1Y4Y5ivXWXy8vA=",
        )

    def test_test_message_uses_interactive_card(self):
        payload = build_test_message(ChannelPlatform.FEISHU)

        self.assertEqual(payload["msg_type"], "interactive")
        self.assertEqual(payload["card"]["header"]["title"]["content"], "补货机器人测试")

    @patch("monitor.services.notifier.time.time", return_value=1700000000)
    @patch("monitor.services.notifier.httpx.post")
    def test_signature_is_sent_in_json_body(self, post, _time):
        post.return_value = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"code": 0},
        )
        channel = SimpleNamespace(
            platform=ChannelPlatform.FEISHU,
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/private",
            secret="secret",
        )

        send_channel(channel, {"msg_type": "interactive", "card": {}})

        url, = post.call_args.args
        self.assertEqual(url, channel.webhook_url)
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["timestamp"], "1700000000")
        self.assertEqual(request_payload["sign"], feishu_signature("secret", 1700000000))
