import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from monitor.models import ChannelPlatform, DingTalkChannel, NotificationChannel, Region


recorded_test_sends = []


def record_sender(channel, payload):
    recorded_test_sends.append((channel.pk, payload))


class ConsoleChannelsApiTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("operator", is_staff=True)
        self.channel = DingTalkChannel.objects.create(
            name="Operations",
            region=Region.US,
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=private",
            secret="SECprivate",
        )
        self.feishu_channel = NotificationChannel.objects.create(
            name="Feishu Operations",
            region=Region.ALL,
            platform=ChannelPlatform.FEISHU,
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/private",
            secret="feishu-private",
        )
        self.client.force_login(self.staff)
        self.client.get("/console/")
        self.csrf = self.client.cookies["csrftoken"].value

    def csrf_request(self, method, url, payload):
        return getattr(self.client, method)(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

    def csrf_post(self, url, payload):
        return self.csrf_request("post", url, payload)

    def test_channel_response_never_contains_secret_values(self):
        response = self.client.get("/api/console/v1/dingtalk-channels")

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn("access_token=private", body)
        self.assertNotIn("SECprivate", body)
        item = response.json()["data"][0]
        self.assertTrue(item["webhook_configured"])
        self.assertTrue(item["secret_configured"])
        self.assertEqual(item["webhook_mask"], "oapi.dingtalk.com (...vate)")

    def test_create_requires_name_region_and_webhook(self):
        response = self.csrf_post("/api/console/v1/dingtalk-channels", {"name": "Missing"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("fields", response.json())

    def test_feishu_response_is_platform_scoped_and_hides_credentials(self):
        response = self.client.get("/api/console/v1/notification-channels")

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn("/hook/private", body)
        self.assertNotIn("feishu-private", body)
        items = response.json()["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["platform"], ChannelPlatform.FEISHU)
        self.assertEqual(items[0]["webhook_mask"], "open.feishu.cn (...vate)")

    def test_create_feishu_channel_forces_platform(self):
        response = self.csrf_post("/api/console/v1/notification-channels", {
            "name": "UK Feishu",
            "regions": [Region.UK, Region.US],
            "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/new-hook",
        })

        self.assertEqual(response.status_code, 201)
        channel = NotificationChannel.objects.get(name="UK Feishu")
        self.assertEqual(channel.platform, ChannelPlatform.FEISHU)
        self.assertEqual(channel.regions, [Region.UK, Region.US])

    def test_create_feishu_channel_rejects_non_feishu_webhook(self):
        response = self.csrf_post("/api/console/v1/notification-channels", {
            "name": "Invalid",
            "region": Region.UK,
            "webhook": "https://oapi.dingtalk.com/robot/send?access_token=test",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("webhook", response.json()["fields"])

    def test_all_scope_replaces_other_regions(self):
        response = self.csrf_post("/api/console/v1/notification-channels", {
            "name": "All Feishu",
            "regions": [Region.US, Region.ALL, Region.UK],
            "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/all-hook",
        })

        self.assertEqual(response.status_code, 201)
        item = response.json()["data"]
        self.assertEqual(item["regions"], [Region.ALL])
        self.assertEqual(item["receive_scope_label"], "全部站点")

    @patch("monitor.console.channels_api.send_channel")
    def test_feishu_channel_test_uses_interactive_card(self, send_channel):
        response = self.csrf_post(
            f"/api/console/v1/notification-channels/{self.feishu_channel.pk}/test",
            {},
        )

        self.assertEqual(response.status_code, 200)
        channel, payload = send_channel.call_args.args
        self.assertEqual(channel.pk, self.feishu_channel.pk)
        self.assertEqual(payload["msg_type"], "interactive")

    def test_create_rejects_invalid_region(self):
        response = self.csrf_post("/api/console/v1/dingtalk-channels", {
            "name": "Invalid",
            "region": "XX",
            "webhook": "https://oapi.dingtalk.com/robot/send?access_token=test",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("region", response.json()["fields"])

    def test_create_rejects_non_dingtalk_webhook(self):
        response = self.csrf_post("/api/console/v1/dingtalk-channels", {
            "name": "Invalid",
            "region": Region.US,
            "webhook": "https://example.com/hook?access_token=test",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("webhook", response.json()["fields"])

    def test_patch_blank_secret_and_webhook_preserve_stored_values(self):
        response = self.csrf_request("patch", f"/api/console/v1/dingtalk-channels/{self.channel.pk}", {
            "name": "Renamed",
            "webhook": "",
            "secret": "",
        })

        self.assertEqual(response.status_code, 200)
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.name, "Renamed")
        self.assertEqual(self.channel.webhook_url, "https://oapi.dingtalk.com/robot/send?access_token=private")
        self.assertEqual(self.channel.secret, "SECprivate")

    @patch("monitor.console.channels_api.send_channel")
    def test_channel_test_uses_server_side_secret(self, send_channel):
        response = self.csrf_post(f"/api/console/v1/dingtalk-channels/{self.channel.pk}/test", {
            "message": "untrusted user content",
            "secret": "untrusted secret",
        })

        self.assertEqual(response.status_code, 200)
        send_channel.assert_called_once()
        channel, payload = send_channel.call_args.args
        self.assertEqual(channel.pk, self.channel.pk)
        self.assertEqual(channel.secret, "SECprivate")
        self.assertEqual(payload["markdown"]["title"], "补货机器人测试")
        self.assertNotIn("untrusted user content", payload["markdown"]["text"])

    def test_disabled_channel_test_is_rejected(self):
        self.channel.enabled = False
        self.channel.save(update_fields=["enabled"])

        response = self.csrf_post(f"/api/console/v1/dingtalk-channels/{self.channel.pk}/test", {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "channel_disabled")

    @override_settings(CONSOLE_CHANNEL_SENDER="tests.test_console_channels_api.record_sender")
    def test_channel_test_uses_configured_sender(self):
        response = self.csrf_post(f"/api/console/v1/dingtalk-channels/{self.channel.pk}/test", {})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(recorded_test_sends[-1][0], self.channel.pk)
