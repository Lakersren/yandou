from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0004_alter_variant_name_default"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="DingTalkChannel",
            new_name="NotificationChannel",
        ),
        migrations.AddField(
            model_name="notificationchannel",
            name="platform",
            field=models.CharField(
                choices=[("dingtalk", "钉钉"), ("feishu", "飞书")],
                default="dingtalk",
                max_length=16,
                verbose_name="平台",
            ),
        ),
        migrations.AlterModelOptions(
            name="notificationchannel",
            options={"verbose_name": "通知渠道", "verbose_name_plural": "通知渠道"},
        ),
    ]
