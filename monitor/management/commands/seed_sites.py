from django.core.management.base import BaseCommand

from monitor.models import Region, Site


SITES = [
    ("sp", "Smokingpipes", Region.US, "smokingpipes.com", "smokingpipes"),
    ("dp", "Dreaming Pipes", Region.US, "dreamingpipes.com", "woocommerce"),
    ("4n", "4Noggins", Region.US, "4noggins.com", "generic"),
    ("np", "Nova Pipes & Tobacco", Region.US, "novapipesandtobacco.com", "nova"),
    ("70", "70 Cigars", Region.US, "70cigars.com", "shopify"),
    ("tecon", "Tecon", Region.DE, "tecon-gmbh.de", "tecon"),
    ("ph", "Peter Heinrichs", Region.DE, "peterheinrichs.de", "generic"),
    ("pipeuncle", "Pipe Uncle", Region.HK, "pipeuncle.com", "generic"),
    ("lifestyle", "Tobacco Lifestyle", Region.HK, "tobaccolifestyle.com", "shopify"),
    ("ps", "Pipes Space", Region.SG, "pipesspace.com", "generic"),
    ("cg", "C.Gars", Region.UK, "cgarsltd.co.uk", "cgars"),
    ("gq", "GQ Tobaccos", Region.UK, "gqtobaccos.com", "bigcommerce"),
    ("hh", "Hava Havana", Region.UK, "havahavana.com", "shopify"),
    ("havanahouse", "Havana House", Region.UK, "havanahouse.co.uk", "havanahouse"),
    ("jb", "James Barber", Region.UK, "smoke.co.uk", "jamesbarber"),
]

SITE_PARSER_CONFIG = {
    "dp": {"currency": "USD"},
    "70": {"country": "US", "currency": "USD"},
    "lifestyle": {"country": "HK", "currency": "HKD"},
    "hh": {"country": "GB", "currency": "GBP"},
}

SITE_DEFAULT_INTERVALS = {
    "havanahouse": 15,
}


class Command(BaseCommand):
    help = "初始化支持的商城"

    def handle(self, *args, **options):
        for code, name, region, domain, adapter in SITES:
            defaults = {"name": name, "region": region, "domain": domain, "adapter": adapter}
            if code in SITE_DEFAULT_INTERVALS:
                defaults["default_interval_minutes"] = SITE_DEFAULT_INTERVALS[code]
            if code in SITE_PARSER_CONFIG:
                defaults["parser_config"] = SITE_PARSER_CONFIG[code]
            Site.objects.update_or_create(
                code=code,
                defaults=defaults,
            )
        self.stdout.write(self.style.SUCCESS(f"已初始化 {len(SITES)} 个商城"))
