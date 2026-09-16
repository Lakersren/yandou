from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from monitor import models


class Command(BaseCommand):
    help = "初始化运营和只读角色"

    def handle(self, *args, **options):
        managed_models = [
            models.Product, models.Variant, models.StockSnapshot, models.StockEvent,
            models.NotificationLog, models.CrawlFailure, models.Site, models.NotificationChannel,
        ]
        view_permissions = []
        for model in managed_models:
            content_type = ContentType.objects.get_for_model(model)
            view_permissions.extend(Permission.objects.filter(content_type=content_type, codename__startswith="view_"))

        viewer, _ = Group.objects.get_or_create(name="只读")
        viewer.permissions.set(view_permissions)

        operator, _ = Group.objects.get_or_create(name="运营")
        product_types = [ContentType.objects.get_for_model(models.Product), ContentType.objects.get_for_model(models.Variant)]
        operator_permissions = list(view_permissions) + list(Permission.objects.filter(
            content_type__in=product_types,
            codename__regex=r"^(add|change|delete)_",
        ))
        operator.permissions.set(operator_permissions)
        self.stdout.write(self.style.SUCCESS("已初始化运营和只读角色"))
