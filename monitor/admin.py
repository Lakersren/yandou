from django.contrib import admin, messages
from django.contrib.auth.models import Group, User
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone

from .forms import ProductAdminForm, ProductPreviewForm, ProductQuickAddForm
from .models import CrawlFailure, NotificationChannel, NotificationLog, Product, Site, StockEvent, StockSnapshot, Variant
from .services.scraper import get_adapter
from .services.catalog import CatalogError, add_product
from .services.notifier import build_test_message, send_channel
from .tasks import enqueue_product_check


admin.site.site_header = "海淘补货机器人"
admin.site.site_title = "补货运营后台"
admin.site.index_title = "运营管理"
admin.site.unregister(Group)
admin.site.unregister(User)


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "domain", "adapter", "enabled", "default_interval_minutes", "last_success_at", "consecutive_failures")
    list_filter = ("region", "enabled", "adapter")
    search_fields = ("name", "domain", "code")

    def has_module_permission(self, request):
        return False


@admin.action(description="立即检查所选商品")
def check_selected(_modeladmin, request, queryset):
    count = 0
    for product in queryset.filter(enabled=True).select_related("site"):
        if enqueue_product_check(product):
            count += 1
    messages.success(request, f"已提交 {count} 个商品检查任务。")


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0
    can_delete = False
    readonly_fields = ("external_id", "name", "price", "currency", "status", "candidate_status", "candidate_count", "last_seen_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    change_list_template = "admin/monitor/product/change_list.html"
    list_display = ("display_name", "site", "enabled", "variant_summary", "last_checked_at", "next_check_at", "error_summary")
    list_filter = ("enabled", "site__region", "site")
    search_fields = ("name", "url", "notes")
    fields = ("name", "site", "url", "enabled", "last_checked_at", "last_error")
    readonly_fields = ("name", "site", "url", "last_checked_at", "last_error")
    actions = (check_selected,)
    inlines = (VariantInline,)

    @admin.display(description="商品")
    def display_name(self, obj):
        return obj.name or "等待首次解析"

    @admin.display(description="库存")
    def variant_summary(self, obj):
        variants = list(obj.variants.all()[:4])
        return "；".join(f"{item.name}: {item.get_status_display()}" for item in variants) or "未检查"

    @admin.display(description="异常")
    def error_summary(self, obj):
        return (obj.last_error[:50] + "…") if len(obj.last_error) > 50 else obj.last_error

    def get_urls(self):
        return [
            path("quick-add/", self.admin_site.admin_view(self.quick_add_view), name="monitor_product_quick_add"),
            path("preview/", self.admin_site.admin_view(self.preview_view), name="monitor_product_preview"),
        ] + super().get_urls()

    def has_add_permission(self, request):
        return False

    def quick_add_view(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:index"))
        form = ProductQuickAddForm(request.POST)
        if not form.is_valid():
            messages.error(request, next(iter(form.errors.values()))[0])
            return HttpResponseRedirect(reverse("admin:index"))
        url = form.cleaned_data["url"]
        try:
            product, outcome = add_product(url, request.user)
        except CatalogError as exc:
            messages.error(request, f"添加失败：{exc}")
            return HttpResponseRedirect(reverse("admin:index"))
        if outcome == "existing":
            if not product.enabled:
                product.enabled = True
                product.save(update_fields=["enabled", "updated_at"])
                messages.success(request, "商品已重新启用监控。")
            else:
                messages.info(request, "这个商品已经在监控中。")
            return HttpResponseRedirect(reverse("admin:monitor_product_change", args=[product.pk]))
        if outcome == "restored":
            messages.success(request, "商品已恢复监控。")
            return HttpResponseRedirect(reverse("admin:monitor_product_change", args=[product.pk]))
        messages.success(request, f"已开始监控：{product.name or form.site.name}")
        return HttpResponseRedirect(reverse("admin:index"))

    def preview_view(self, request):
        form = ProductPreviewForm(request.POST or None)
        observation = None
        if request.method == "POST" and form.is_valid():
            try:
                observation = get_adapter(form.site).fetch(form.cleaned_data["url"])
            except Exception as exc:
                form.add_error("url", f"解析失败：{exc}")
            else:
                if "save" in request.POST:
                    try:
                        product, outcome = add_product(form.cleaned_data["url"], request.user)
                    except CatalogError as exc:
                        form.add_error("url", f"添加失败：{exc}")
                    else:
                        if outcome == "created":
                            product.interval_minutes = form.cleaned_data["interval_minutes"]
                            product.notify_site_group = form.cleaned_data["notify_site_group"]
                            product.notify_all_group = form.cleaned_data["notify_all_group"]
                            product.notes = form.cleaned_data["notes"]
                            product.save(update_fields=[
                                "interval_minutes", "notify_site_group", "notify_all_group", "notes", "updated_at",
                            ])
                            messages.success(request, "商品已保存并建立库存基线。")
                        elif outcome == "restored":
                            messages.success(request, "商品已恢复监控。")
                        else:
                            messages.warning(request, "该商品 URL 已存在，已打开原记录。")
                        return HttpResponseRedirect(reverse("admin:monitor_product_change", args=[product.pk]))
        context = {
            **self.admin_site.each_context(request),
            "title": "通过 URL 添加监控商品",
            "form": form,
            "observation": observation,
            "opts": self.model._meta,
        }
        return render(request, "admin/monitor/product/preview.html", context)


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "platform", "receive_scope", "enabled", "created_at")
    list_filter = ("platform", "enabled")
    actions = ("send_test_message",)

    @admin.display(description="接收范围")
    def receive_scope(self, obj):
        return obj.receive_scope_label

    @admin.action(description="向所选群发送测试消息")
    def send_test_message(self, request, queryset):
        success = 0
        errors = []
        for channel in queryset:
            try:
                send_channel(channel, build_test_message(channel.platform))
                success += 1
            except Exception as exc:
                errors.append(f"{channel.name}: {exc}")
        if success:
            messages.success(request, f"成功发送到 {success} 个群。")
        if errors:
            messages.error(request, "；".join(errors))


@admin.register(StockEvent)
class StockEventAdmin(admin.ModelAdmin):
    list_display = ("variant", "old_status", "new_status", "price", "created_at")
    list_filter = ("new_status", "variant__product__site__region")
    search_fields = ("variant__product__name",)
    readonly_fields = ("variant", "old_status", "new_status", "price", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CrawlFailure)
class CrawlFailureAdmin(admin.ModelAdmin):
    list_display = ("product", "error_type", "short_message", "occurred_at")
    list_filter = ("error_type", "product__site")
    search_fields = ("product__name", "message")
    readonly_fields = ("product", "error_type", "message", "occurred_at")

    @admin.display(description="错误")
    def short_message(self, obj):
        return obj.message[:100]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event", "channel", "success", "attempted_at")
    list_filter = ("success", "channel")
    readonly_fields = ("event", "channel", "success", "response_text", "attempted_at")

    def has_add_permission(self, request):
        return False

    def has_module_permission(self, request):
        return False


@admin.register(StockSnapshot)
class StockSnapshotAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "observed_status", "price", "checked_at")
    list_filter = ("observed_status", "product__site")
    readonly_fields = ("product", "variant", "observed_status", "price", "checked_at", "raw_hint")

    def has_add_permission(self, request):
        return False

    def has_module_permission(self, request):
        return False
