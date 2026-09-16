from decimal import Decimal

from monitor.models import StockStatus
from monitor.services.catalog import UnreadableStock
from monitor.services.scraper import ProductObservation, VariantObservation


def observe_product(site, url):
    if url != "https://smokingpipes.com/product/test":
        raise UnreadableStock("暂时无法识别该商品库存")
    return ProductObservation(
        name="Test Flake",
        canonical_url=url,
        variants=[VariantObservation(
            external_id="50g", name="50g", status=StockStatus.OUT_OF_STOCK,
            price=Decimal("12.50"), currency="USD",
        )],
    )


def send_channel(channel, payload):
    return {"errcode": 0, "errmsg": "ok"}
