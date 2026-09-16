from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0003_product_soft_delete_and_creator"),
    ]

    operations = [
        migrations.AlterField(
            model_name="variant",
            name="name",
            field=models.CharField(default="单规格", max_length=200, verbose_name="规格名称"),
        ),
    ]
