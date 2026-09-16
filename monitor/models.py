from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .fields import EncryptedTextField


class Region(models.TextChoices):
    US = "US", "美站"
    DE = "DE", "德站"
    HK = "HK", "港站"
    SG = "SG", "新加坡站"
    UK = "UK", "英站"
    ALL = "ALL", "综合群"


class StockStatus(models.TextChoices):
    UNKNOWN = "unknown", "无法判断"
    OUT_OF_STOCK = "out_of_stock", "缺货"
    IN_STOCK = "in_stock", "有货"
    DISCONTINUED = "discontinued", "下架"


class ActiveProductManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Site(models.Model):
    code = models.SlugField("代码", unique=True)
    name = models.CharField("商城名称", max_length=100)
    region = models.CharField("所属站点", max_length=8, choices=Region.choices)
    domain = models.CharField("主域名", max_length=255, unique=True)
    adapter = models.CharField("解析器", max_length=64, default="generic")
    enabled = models.BooleanField("启用", default=True)
    default_interval_minutes = models.PositiveSmallIntegerField("默认检查间隔（分钟）", default=5)
    parser_config = models.JSONField("自定义解析配置", default=dict, blank=True)
    last_success_at = models.DateTimeField("最近成功", null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField("连续失败", default=0)

    class Meta:
        verbose_name = "商城"
        verbose_name_plural = "商城"

    def __str__(self):
        return f"{self.name}（{self.get_region_display()}）"

    def accepts_url(self, url):
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        domain = self.domain.lower().rstrip(".")
        return host == domain or host.endswith("." + domain)


class ChannelPlatform(models.TextChoices):
    DINGTALK = "dingtalk", "钉钉"
    FEISHU = "feishu", "飞书"


class NotificationChannel(models.Model):
    name = models.CharField("群名称", max_length=100)
    region = models.CharField("兼容站点", max_length=8, choices=Region.choices)
    regions = models.JSONField("接收范围", default=list, blank=True)
    platform = models.CharField("平台", max_length=16, choices=ChannelPlatform.choices, default=ChannelPlatform.DINGTALK)
    webhook_url = EncryptedTextField("Webhook 地址")
    secret = EncryptedTextField("加签密钥", blank=True)
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "通知渠道"
        verbose_name_plural = "通知渠道"

    def __str__(self):
        return f"{self.name}（{self.receive_scope_label}）"

    @property
    def effective_regions(self):
        values = self.regions or ([self.region] if self.region else [])
        return [Region.ALL] if Region.ALL in values else list(dict.fromkeys(values))

    @property
    def receive_scope_label(self):
        values = self.effective_regions
        if Region.ALL in values:
            return "全部站点"
        labels = dict(Region.choices)
        return "、".join(labels[value] for value in values if value in labels) or "未配置"

    def receives_product(self, product):
        values = self.effective_regions
        if Region.ALL in values:
            return product.notify_all_group
        return product.notify_site_group and product.site.region in values

    def clean(self):
        super().clean()
        invalid_regions = set(self.effective_regions) - set(Region.values)
        if invalid_regions or not self.effective_regions:
            raise ValidationError({"regions": "请选择至少一个有效的接收范围。"})
        self.regions = self.effective_regions
        self.region = Region.ALL if Region.ALL in self.regions else self.regions[0]
        host = (urlparse(self.webhook_url).hostname or "").lower()
        allowed_hosts = {
            ChannelPlatform.DINGTALK: {"oapi.dingtalk.com", "api.dingtalk.com"},
            ChannelPlatform.FEISHU: {"open.feishu.cn", "open.larksuite.com"},
        }
        if host not in allowed_hosts.get(self.platform, set()):
            platform_name = dict(ChannelPlatform.choices).get(self.platform, "通知平台")
            raise ValidationError({"webhook_url": f"只允许{platform_name}官方机器人 Webhook 地址。"})


# Keep imports used by older maintenance scripts working during the transition.
DingTalkChannel = NotificationChannel


class Product(models.Model):
    objects = ActiveProductManager()
    all_objects = models.Manager()

    site = models.ForeignKey(Site, verbose_name="商城", on_delete=models.PROTECT)
    url = models.URLField("商品 URL", max_length=1000, unique=True)
    name = models.CharField("商品名称", max_length=300, blank=True)
    image_url = models.URLField("商品图片", max_length=1000, blank=True)
    enabled = models.BooleanField("启用监控", default=True)
    interval_minutes = models.PositiveSmallIntegerField("检查间隔（分钟）", null=True, blank=True)
    notify_site_group = models.BooleanField("通知站点群", default=True)
    notify_all_group = models.BooleanField("通知综合群", default=True)
    notes = models.TextField("运营备注", blank=True)
    last_checked_at = models.DateTimeField("最近检查", null=True, blank=True)
    next_check_at = models.DateTimeField("下次检查", default=timezone.now, db_index=True)
    last_error = models.TextField("最近错误", blank=True)
    deleted_at = models.DateTimeField("删除时间", null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="创建人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="monitored_products",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "监控商品"
        verbose_name_plural = "监控商品"
        base_manager_name = "all_objects"

    def clean(self):
        super().clean()
        if self.site_id and not self.site.accepts_url(self.url):
            raise ValidationError({"url": f"URL 必须属于 {self.site.domain}"})

    def __str__(self):
        return self.name or self.url

    def soft_delete(self):
        self.enabled = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["enabled", "deleted_at", "updated_at"])

    def restore(self):
        self.enabled = True
        self.deleted_at = None
        self.next_check_at = timezone.now()
        self.save(update_fields=["enabled", "deleted_at", "next_check_at", "updated_at"])

    @property
    def effective_interval(self):
        return self.interval_minutes or self.site.default_interval_minutes

    @property
    def stock_status(self):
        statuses = [item.status for item in self.variants.all()]
        if statuses and all(value == StockStatus.IN_STOCK for value in statuses):
            return StockStatus.IN_STOCK
        if StockStatus.IN_STOCK in statuses:
            return "partial_stock"
        if statuses and all(value in {StockStatus.OUT_OF_STOCK, StockStatus.DISCONTINUED} for value in statuses):
            return StockStatus.OUT_OF_STOCK
        return StockStatus.UNKNOWN

    @property
    def stock_status_label(self):
        if self.stock_status == "partial_stock":
            statuses = [item.status for item in self.variants.all()]
            in_stock = statuses.count(StockStatus.IN_STOCK)
            return f"部分有货 {in_stock}/{len(statuses)}"
        return dict(StockStatus.choices).get(self.stock_status, "无法判断")


class Variant(models.Model):
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    external_id = models.CharField("规格标识", max_length=200, default="default")
    name = models.CharField("规格名称", max_length=200, default="单规格")
    price = models.DecimalField("价格", max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField("币种", max_length=8, blank=True)
    status = models.CharField("确认库存", max_length=32, choices=StockStatus.choices, default=StockStatus.UNKNOWN)
    candidate_status = models.CharField("待确认库存", max_length=32, choices=StockStatus.choices, default=StockStatus.UNKNOWN)
    candidate_count = models.PositiveSmallIntegerField("连续确认次数", default=0)
    last_seen_at = models.DateTimeField("最近出现", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "商品规格"
        verbose_name_plural = "商品规格"
        constraints = [models.UniqueConstraint(fields=["product", "external_id"], name="unique_product_variant")]

    def __str__(self):
        return f"{self.product} / {self.name}"


class StockSnapshot(models.Model):
    product = models.ForeignKey(Product, related_name="snapshots", on_delete=models.CASCADE)
    variant = models.ForeignKey(Variant, related_name="snapshots", null=True, blank=True, on_delete=models.SET_NULL)
    observed_status = models.CharField("检测库存", max_length=32, choices=StockStatus.choices)
    price = models.DecimalField("价格", max_digits=12, decimal_places=2, null=True, blank=True)
    checked_at = models.DateTimeField("检测时间", auto_now_add=True, db_index=True)
    raw_hint = models.CharField("判断依据", max_length=500, blank=True)

    class Meta:
        verbose_name = "库存快照"
        verbose_name_plural = "库存快照"


class StockEvent(models.Model):
    variant = models.ForeignKey(Variant, related_name="events", on_delete=models.CASCADE)
    old_status = models.CharField("原库存", max_length=32, choices=StockStatus.choices)
    new_status = models.CharField("新库存", max_length=32, choices=StockStatus.choices)
    price = models.DecimalField("补货价格", max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField("发生时间", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "补货记录"
        verbose_name_plural = "补货记录"


class NotificationLog(models.Model):
    event = models.ForeignKey(StockEvent, related_name="notifications", on_delete=models.CASCADE)
    channel = models.ForeignKey(NotificationChannel, on_delete=models.PROTECT)
    success = models.BooleanField("成功", default=False)
    response_text = models.TextField("响应", blank=True)
    attempted_at = models.DateTimeField("发送时间", auto_now_add=True)

    class Meta:
        verbose_name = "通知记录"
        verbose_name_plural = "通知记录"
        constraints = [models.UniqueConstraint(fields=["event", "channel"], name="unique_event_channel")]


class CrawlFailure(models.Model):
    product = models.ForeignKey(Product, related_name="failures", on_delete=models.CASCADE)
    error_type = models.CharField("错误类型", max_length=100)
    message = models.TextField("错误信息")
    occurred_at = models.DateTimeField("发生时间", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "抓取异常"
        verbose_name_plural = "抓取异常"
