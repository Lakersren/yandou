from django import forms

from .models import Product, Site


class ProductPreviewForm(forms.Form):
    url = forms.URLField(label="商品 URL", max_length=1000, widget=forms.URLInput(attrs={"size": 100}))
    interval_minutes = forms.IntegerField(label="检查间隔（分钟）", min_value=1, max_value=1440, required=False)
    notify_site_group = forms.BooleanField(label="通知站点群", required=False, initial=True)
    notify_all_group = forms.BooleanField(label="通知综合群", required=False, initial=True)
    notes = forms.CharField(label="运营备注", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_url(self):
        url = self.cleaned_data["url"]
        site = next((item for item in Site.objects.filter(enabled=True) if item.accepts_url(url)), None)
        if not site:
            raise forms.ValidationError("该 URL 不属于当前支持的商城，请先联系管理员添加商城适配。")
        self.site = site
        return url


class ProductQuickAddForm(forms.Form):
    url = forms.URLField(
        label="商品 URL",
        max_length=1000,
        widget=forms.URLInput(attrs={"placeholder": "粘贴商品页面 URL", "autocomplete": "off"}),
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        self.site = next((item for item in Site.objects.filter(enabled=True) if item.accepts_url(url)), None)
        if not self.site:
            raise forms.ValidationError("暂不支持这个商城。")
        return url


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        site = cleaned.get("site")
        url = cleaned.get("url")
        if site and url and not site.accepts_url(url):
            self.add_error("url", f"URL 必须属于 {site.domain}")
        return cleaned
