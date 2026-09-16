from django.db import migrations, models


def copy_region_to_regions(apps, schema_editor):
    channel_model = apps.get_model("monitor", "NotificationChannel")
    for channel in channel_model.objects.all().iterator():
        channel.regions = [channel.region]
        channel.save(update_fields=["regions"])


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0005_generalize_notification_channel"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationchannel",
            name="region",
            field=models.CharField(
                choices=[
                    ("US", "美站"),
                    ("DE", "德站"),
                    ("HK", "港站"),
                    ("SG", "新加坡站"),
                    ("UK", "英站"),
                    ("ALL", "综合群"),
                ],
                max_length=8,
                verbose_name="兼容站点",
            ),
        ),
        migrations.AddField(
            model_name="notificationchannel",
            name="regions",
            field=models.JSONField(blank=True, default=list, verbose_name="接收范围"),
        ),
        migrations.RunPython(copy_region_to_regions, migrations.RunPython.noop),
    ]
