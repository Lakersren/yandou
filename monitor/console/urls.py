from django.urls import path

from monitor.models import ChannelPlatform

from . import activity_api, channels_api, products_api, session_api


urlpatterns = [
    path("session", session_api.session, name="console_session"),
    path("logout", session_api.logout_view, name="console_logout"),
    path("dashboard", session_api.dashboard, name="console_dashboard"),
    path("products", products_api.products, name="console_products"),
    path("products/<int:product_id>", products_api.product_detail, name="console_product_detail"),
    path("products/<int:product_id>/check", products_api.check, name="console_product_check"),
    path("events", activity_api.events, name="console_events"),
    path("failures", activity_api.failures, name="console_failures"),
    path("failures/<str:failure_id>/retry", activity_api.retry_failure, name="console_failure_retry"),
    path("notification-channels", channels_api.channels, {"platform": ChannelPlatform.FEISHU}, name="console_notification_channels"),
    path("notification-channels/<int:channel_id>", channels_api.channel_detail, {"platform": ChannelPlatform.FEISHU}, name="console_notification_channel_detail"),
    path("notification-channels/<int:channel_id>/test", channels_api.test_channel, {"platform": ChannelPlatform.FEISHU}, name="console_notification_channel_test"),
    path("dingtalk-channels", channels_api.channels, {"platform": ChannelPlatform.DINGTALK}, name="console_dingtalk_channels"),
    path("dingtalk-channels/<int:channel_id>", channels_api.channel_detail, {"platform": ChannelPlatform.DINGTALK}, name="console_dingtalk_channel_detail"),
    path("dingtalk-channels/<int:channel_id>/test", channels_api.test_channel, {"platform": ChannelPlatform.DINGTALK}, name="console_dingtalk_channel_test"),
]
