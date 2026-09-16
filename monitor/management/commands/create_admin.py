import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "根据环境变量创建初始管理员"

    def handle(self, *args, **options):
        username = os.getenv("ADMIN_USERNAME")
        password = os.getenv("ADMIN_PASSWORD")
        email = os.getenv("ADMIN_EMAIL", "")
        if not username or not password:
            self.stdout.write("未设置 ADMIN_USERNAME/ADMIN_PASSWORD，跳过管理员创建")
            return
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=username, defaults={"email": email, "is_staff": True, "is_superuser": True})
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS("已创建初始管理员"))
        else:
            self.stdout.write("管理员已存在，未修改密码")

