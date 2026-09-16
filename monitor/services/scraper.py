import json
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from monitor.models import StockStatus

from .http import fetch_html, fetch_html_bright_data
from .browser import fetch_html_browser


@dataclass
class VariantObservation:
    external_id: str = "default"
    name: str = "单规格"
    status: str = StockStatus.UNKNOWN
    price: Decimal | None = None
    currency: str = ""
    hint: str = ""

    @property
    def status_label(self):
        return dict(StockStatus.choices).get(self.status, self.status)


@dataclass
class ProductObservation:
    name: str
    canonical_url: str
    image_url: str = ""
    variants: list[VariantObservation] = field(default_factory=list)


def _decimal(value):
    if value in (None, ""):
        return None
    match = re.search(r"\d[\d,.]*", str(value))
    if not match:
        return None
    normalized = match.group(0).replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _status(value):
    text = str(value or "").lower()
    if any(word in text for word in ("outofstock", "soldout", "out_of_stock", "out of stock", "sold out", "缺货", "售罄")):
        return StockStatus.OUT_OF_STOCK
    if any(word in text for word in ("discontinued", "discontinuedby", "下架", "停产")):
        return StockStatus.DISCONTINUED
    if any(word in text for word in ("instock", "limitedavailability", "preorder", "in_stock", "in stock", "add to cart", "加入购物车", "有货")):
        return StockStatus.IN_STOCK
    return StockStatus.UNKNOWN


def _variant_name(product_name="", explicit_name="", sku=""):
    explicit = str(explicit_name or "").strip()
    if explicit.lower() not in {"", "default", "default title", "默认规格"}:
        return explicit[:200]

    text = str(product_name or "")
    chinese_units = {
        "千克": "kg",
        "公斤": "kg",
        "克": "g",
        "盎司": "oz",
        "磅": "lbs",
    }
    for source, target in chinese_units.items():
        text = re.sub(rf"(\d+(?:[.,]\d+)?)\s*{source}", rf"\1{target}", text, flags=re.I)

    english_units = {
        r"kilograms?": "kg",
        r"grams?": "g",
        r"ounces?": "oz",
        r"pounds?": "lbs",
    }
    for source, target in english_units.items():
        text = re.sub(
            rf"(\d+(?:[.,]\d+)?)\s*{source}\b",
            rf"\1{target}",
            text,
            flags=re.I,
        )

    units = r"kg|g|oz|lbs?"
    patterns = (
        rf"(?<![\d.,])(\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:{units}))(?![A-Za-z])",
        rf"(?<![\d.,])(\d+(?:[.,]\d+)?\s*(?:{units}))(?![A-Za-z])",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return re.sub(r"\s+", "", match.group(1))[:200]

    sku_text = str(sku or "").strip()
    return sku_text[:200] if sku_text else "单规格"


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


class GenericAdapter:
    def __init__(self, site):
        self.site = site
        self.config = site.parser_config or {}

    def fetch(self, url):
        html, final_url = fetch_html(url, self.site.domain)
        return self.parse(html, final_url)

    def parse(self, html, final_url):
        soup = BeautifulSoup(html, "lxml")
        canonical = soup.select_one('link[rel="canonical"]')
        canonical_url = canonical.get("href", final_url) if canonical else final_url
        product_nodes = []
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or script.get_text())
                product_nodes.extend(
                    node for node in _walk_json(data)
                    if str(node.get("@type", "")).lower() == "product"
                )
            except (json.JSONDecodeError, TypeError):
                continue

        if product_nodes:
            parsed = self._from_jsonld(product_nodes[0], canonical_url)
            if parsed.variants and any(v.status != StockStatus.UNKNOWN for v in parsed.variants):
                return parsed

        return self._from_selectors(soup, canonical_url, product_nodes[0] if product_nodes else {})

    def _from_jsonld(self, product, canonical_url):
        name = str(product.get("name") or "").strip()
        image = product.get("image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""
        if isinstance(image, dict):
            image = image.get("url", "")
        offers = product.get("offers") or []
        if isinstance(offers, dict) and isinstance(offers.get("offers"), list):
            offers = offers["offers"]
        elif isinstance(offers, dict):
            offers = [offers]
        variants = []
        for index, offer in enumerate(offers):
            if not isinstance(offer, dict):
                continue
            availability = offer.get("availability", "")
            external_id = str(offer.get("sku") or offer.get("mpn") or f"offer-{index}")
            variants.append(VariantObservation(
                external_id=external_id[:200],
                name=_variant_name(name, offer.get("name"), offer.get("sku")),
                status=_status(availability),
                price=_decimal(offer.get("price") or offer.get("lowPrice")),
                currency=str(offer.get("priceCurrency") or "")[:8],
                hint=f"JSON-LD availability={availability}"[:500],
            ))
        return ProductObservation(name=name, canonical_url=canonical_url, image_url=str(image), variants=variants)

    def _from_selectors(self, soup, canonical_url, product):
        def text_for(key, default_selector=""):
            selector = self.config.get(key) or default_selector
            node = soup.select_one(selector) if selector else None
            return node.get_text(" ", strip=True) if node else ""

        title = text_for("name_selector", "h1") or str(product.get("name") or "")
        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)
        image = ""
        image_node = soup.select_one(self.config.get("image_selector", 'meta[property="og:image"]'))
        if image_node:
            image = image_node.get("content") or image_node.get("src") or ""
        price_text = text_for("price_selector", '[itemprop="price"], .price, .product-price')
        stock_selector = self.config.get("stock_selector", '[itemprop="availability"], .availability, .stock, button[name*="cart" i], input[value*="cart" i]')
        stock_nodes = soup.select(stock_selector)
        evidence = []
        enabled_evidence = []
        for node in stock_nodes:
            node_text = node.get("content") or node.get("value") or node.get_text(" ", strip=True)
            is_disabled = node.has_attr("disabled") or str(node.get("aria-disabled", "")).lower() == "true"
            evidence.append(f"{node_text}{' [disabled]' if is_disabled else ''}")
            if not is_disabled:
                enabled_evidence.append(node_text)
        stock_text = " ".join(evidence)
        enabled_text = " ".join(enabled_evidence).lower()
        lowered = stock_text.lower()
        out_patterns = self.config.get("out_of_stock_patterns", ["out of stock", "sold out", "currently unavailable", "缺货", "售罄"])
        in_patterns = self.config.get("in_stock_patterns", ["in stock", "add to cart", "add to bag", "加入购物车", "有货"])
        if any(str(p).lower() in lowered for p in out_patterns):
            status = StockStatus.OUT_OF_STOCK
        elif any(str(p).lower() in enabled_text for p in in_patterns):
            status = StockStatus.IN_STOCK
        else:
            status = StockStatus.UNKNOWN
        return ProductObservation(
            name=title[:300], canonical_url=canonical_url, image_url=image,
            variants=[VariantObservation(
                name=_variant_name(title),
                status=status,
                price=_decimal(price_text),
                hint=stock_text[:500],
            )],
        )


class SmokingPipesAdapter(GenericAdapter):
    def fetch(self, url):
        try:
            html, final_url = fetch_html(url, self.site.domain)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            if os.getenv("BRIGHT_DATA_API_KEY", "").strip():
                html, final_url = fetch_html_bright_data(url, self.site.domain)
            else:
                html, final_url = fetch_html_browser(url, self.site.domain)
        return self.parse(html, final_url)

    def parse(self, html, final_url):
        observation = super().parse(html, final_url)
        if not observation.variants:
            return observation

        soup = BeautifulSoup(html, "lxml")
        product_number = ""
        for heading in soup.select("h3"):
            match = re.search(r"Product Number:\s*([\w-]+)", heading.get_text(" ", strip=True), re.I)
            if match:
                product_number = match.group(1)
                break

        variant = observation.variants[0]
        if product_number:
            variant.external_id = product_number
        page_text = soup.get_text(" ", strip=True).lower()
        if "we apologize, but this item is temporarily out of stock" in page_text:
            has_product_json = False
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    data = json.loads(script.string or script.get_text())
                    if any(str(node.get("@type", "")).lower() == "product" for node in _walk_json(data)):
                        has_product_json = True
                        break
                except (json.JSONDecodeError, TypeError):
                    continue
            variant.status = StockStatus.OUT_OF_STOCK
            if not has_product_json:
                variant.price = None
            if not variant.currency:
                variant.currency = "USD"
            variant.hint = f"Smokingpipes legacy product={product_number} temporarily out of stock"[:500]
        variant.name = _variant_name(observation.name)
        return observation


class CgarsAdapter(GenericAdapter):
    def fetch(self, url):
        try:
            html, final_url = fetch_html(url, self.site.domain)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            html, final_url = fetch_html_browser(url, self.site.domain)
        return self.parse(html, final_url)

    def parse(self, html, final_url):
        observation = super().parse(html, final_url)
        if not observation.variants:
            return observation

        soup = BeautifulSoup(html, "lxml")
        product_id_match = re.search(r"-p-(\d+)\.html", urlparse(final_url).path)
        variant = observation.variants[0]
        if product_id_match:
            variant.external_id = product_id_match.group(1)

        weight_options = []
        if soup.select_one("#grams-slider"):
            option_pattern = re.compile(
                r"gValue\s*===\s*(\d+)\).*?result\s*=\s*[\"']([^\"']+)[\"']"
                r".*?options_values_id\s*=\s*[\"'](\d+)[\"']"
            )
            for script in soup.select("script"):
                weight_options.extend(option_pattern.findall(script.string or script.get_text()))

        if weight_options:
            minimum = weight_options[0][0]
            maximum = weight_options[-1][0]
            variant.name = f"散装（{minimum}g-{maximum}g）"
            prices = ", ".join(f"{grams}g={price}" for grams, price, _option_id in weight_options)
            variant.hint = f"{variant.hint}; shared-stock weights: {prices}"[:500]
        else:
            weight_match = re.search(r"\b(\d+(?:\.\d+)?\s*(?:kg|g|oz|lbs?))\b", observation.name, re.I)
            if weight_match:
                variant.name = re.sub(r"\s+", "", weight_match.group(1))
        return observation


class WooCommerceAdapter(GenericAdapter):
    currency_symbols = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}

    def parse(self, html, final_url):
        soup = BeautifulSoup(html, "lxml")
        form = soup.select_one("form.variations_form[data-product_variations]")
        if not form:
            observation = super().parse(html, final_url)
            current_product = soup.select_one("body.single-product div.product, body.single-product article.product")
            if observation.variants and current_product is not None:
                variant = observation.variants[0]
                product_id = next(
                    (
                        match.group(1)
                        for class_name in current_product.get("class") or []
                        if (match := re.fullmatch(r"post-(\d+)", class_name))
                    ),
                    "",
                )
                if product_id:
                    variant.external_id = product_id
                classes = set(current_product.get("class") or [])
                if "outofstock" in classes:
                    variant.status = StockStatus.OUT_OF_STOCK
                elif "instock" in classes:
                    variant.status = StockStatus.IN_STOCK
                if not variant.currency:
                    variant.currency = str(self.config.get("currency") or "")[:8]
                variant.hint = f"WooCommerce product_id={product_id} {variant.hint}"[:500]
            return observation

        title_node = soup.select_one("h1.product_title, h1")
        title = title_node.get_text(" ", strip=True) if title_node else ""

        try:
            variations = json.loads(form.get("data-product_variations") or "[]")
        except (json.JSONDecodeError, TypeError):
            return super().parse(html, final_url)
        if not isinstance(variations, list):
            return super().parse(html, final_url)

        query = parse_qs(urlparse(final_url).query)
        selected_id = (query.get("variation_id") or [None])[0]
        selected_attributes = {
            key: values
            for key, values in query.items()
            if key.startswith("attribute_") and values
        }

        option_labels = {}
        for select in form.select("select[name]"):
            option_labels[select.get("name")] = {
                option.get("value"): option.get_text(" ", strip=True)
                for option in select.select("option[value]")
                if option.get("value")
            }

        parsed_variants = []
        image_url = ""
        for variation in variations:
            if not isinstance(variation, dict):
                continue
            variation_id = str(variation.get("variation_id") or "")
            attributes = variation.get("attributes") or {}
            if selected_id and variation_id != str(selected_id):
                continue
            if any(str(attributes.get(key, "")) not in values for key, values in selected_attributes.items()):
                continue

            names = [
                option_labels.get(key, {}).get(str(value), str(value))
                for key, value in attributes.items()
                if value not in (None, "")
            ]
            stock = variation.get("is_in_stock")
            status = (
                StockStatus.IN_STOCK if stock is True
                else StockStatus.OUT_OF_STOCK if stock is False
                else StockStatus.UNKNOWN
            )
            price_html = str(variation.get("price_html") or "")
            price_text = BeautifulSoup(price_html, "lxml").get_text(" ", strip=True)
            currency = str(self.config.get("currency") or "")[:8]
            if not currency:
                currency = next(
                    (code for symbol, code in self.currency_symbols.items() if symbol in price_text),
                    "",
                )
            sku = str(variation.get("sku") or "")
            parsed_variants.append(VariantObservation(
                external_id=(variation_id or sku or f"variation-{len(parsed_variants)}")[:200],
                name=_variant_name(title, " / ".join(names), sku),
                status=status,
                price=_decimal(variation.get("display_price")),
                currency=currency,
                hint=f"WooCommerce variation_id={variation_id} sku={sku} is_in_stock={stock}"[:500],
            ))
            if not image_url and isinstance(variation.get("image"), dict):
                image_url = str(variation["image"].get("full_src") or variation["image"].get("src") or "")

        canonical = soup.select_one('link[rel="canonical"]')
        canonical_url = canonical.get("href", final_url) if canonical else final_url
        if not image_url:
            image_node = soup.select_one('meta[property="og:image"]')
            image_url = str(image_node.get("content") or "") if image_node else ""
        return ProductObservation(
            name=title[:300],
            canonical_url=canonical_url,
            image_url=image_url,
            variants=parsed_variants,
        )


class TeconAdapter(GenericAdapter):
    def parse(self, html, final_url):
        soup = BeautifulSoup(html, "lxml")
        title_node = soup.select_one(".product_details_wrapper h1, h1")
        title = title_node.get_text(" ", strip=True) if title_node else ""

        image_node = soup.select_one(".center_product_wrapper img, #zoom_01")
        image_url = urljoin(final_url, image_node.get("src", "")) if image_node else ""

        price_node = soup.select_one("#cart_price")
        if price_node is None:
            price_node = soup.select_one(".product_price")
        price_text = ""
        if price_node is not None:
            price_text = price_node.get("value") or price_node.get_text(" ", strip=True)
        price_match = re.search(r"(\d[\d.]*(?:,\d+)?)", price_text)
        price = None
        if price_match:
            normalized = price_match.group(1).replace(".", "").replace(",", ".")
            try:
                price = Decimal(normalized)
            except InvalidOperation:
                pass
        if price is not None and price <= 0:
            price = None

        details = soup.select_one(".product_details_wrapper")
        stock_text = details.get_text(" ", strip=True) if details else ""
        stock_lower = stock_text.lower()
        stock_images = " ".join(
            str(node.get("src") or "").lower()
            for node in soup.select(".product_details_wrapper img[src]")
        )
        out_of_stock_text = ("nicht bestellbar", "nicht verfügbar", "ausverkauft", "vergriffen")
        out_of_stock_images = ("outofstock", "soldout", "notinstock", "nostock")
        if any(marker in stock_lower for marker in out_of_stock_text):
            status = StockStatus.OUT_OF_STOCK
        elif any(marker in stock_images for marker in out_of_stock_images):
            status = StockStatus.OUT_OF_STOCK
        elif "instock.png" in stock_images or "bestellbar" in stock_lower:
            status = StockStatus.IN_STOCK
        else:
            status = StockStatus.UNKNOWN

        query = parse_qs(urlparse(final_url).query)
        product_id = (query.get("products_id") or ["default"])[0]
        return ProductObservation(
            name=title[:300],
            canonical_url=final_url,
            image_url=image_url,
            variants=[VariantObservation(
                external_id=str(product_id)[:200],
                name=_variant_name(title),
                status=status,
                price=price,
                currency="EUR",
                hint=f"Tecon stock={stock_text}"[:500],
            )],
        )


class BigCommerceAdapter(GenericAdapter):
    currency_symbols = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}

    def parse(self, html, final_url):
        soup = BeautifulSoup(html, "lxml")
        title_node = soup.select_one("h1.productView-name, h1")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        image_node = soup.select_one('meta[property="og:image"]')
        image_url = str(image_node.get("content") or "") if image_node else ""
        canonical = soup.select_one('link[rel="canonical"]')
        canonical_url = canonical.get("href", final_url) if canonical else final_url

        stencil_context = self._stencil_product_context(soup)
        gql_variants = (
            (stencil_context.get("gqlProductResults") or {})
            .get("variants", {})
            .get("edges", [])
        )
        context_title = str((stencil_context.get("product") or {}).get("title") or "")
        product_name = context_title or title
        parsed_variants = self._gql_variants(gql_variants, product_name)
        if parsed_variants:
            return ProductObservation(
                name=product_name[:300],
                canonical_url=canonical_url,
                image_url=image_url,
                variants=parsed_variants,
            )

        product_data = None
        decoder = json.JSONDecoder()
        for script in soup.select("script"):
            script_text = script.string or script.get_text()
            match = re.search(r"\b(?:var\s+)?BCData\s*=\s*", script_text or "")
            if not match:
                continue
            try:
                product_data, _end = decoder.raw_decode(script_text[match.end():].lstrip())
            except (json.JSONDecodeError, TypeError):
                continue
            break

        attributes = (product_data or {}).get("product_attributes") or {}
        if not attributes:
            return super().parse(html, final_url)

        in_stock = attributes.get("instock")
        purchasable = attributes.get("purchasable")
        if in_stock is True and purchasable is not False:
            status = StockStatus.IN_STOCK
        elif in_stock is False or purchasable is False:
            status = StockStatus.OUT_OF_STOCK
        else:
            status = StockStatus.UNKNOWN

        price_data = attributes.get("price") or {}
        price_offer = price_data.get("with_tax") or price_data.get("without_tax") or {}
        price = _decimal(price_offer.get("value"))
        currency = str(price_offer.get("currency") or "")[:8]
        if not currency:
            formatted = str(price_offer.get("formatted") or "")
            currency = next(
                (code for symbol, code in self.currency_symbols.items() if symbol in formatted),
                "",
            )

        product_node = soup.select_one(".productView[data-entity-id]")
        product_id = str(product_node.get("data-entity-id") or "") if product_node else ""
        if not product_id:
            id_node = soup.select_one('input[name="product_id"]')
            product_id = str(id_node.get("value") or "") if id_node else "default"

        return ProductObservation(
            name=title[:300],
            canonical_url=canonical_url,
            image_url=image_url,
            variants=[VariantObservation(
                external_id=product_id[:200],
                name=_variant_name(title),
                status=status,
                price=price,
                currency=currency,
                hint=(
                    f"BigCommerce product_id={product_id} instock={in_stock} "
                    f"stock={attributes.get('stock')} purchasable={purchasable}"
                )[:500],
            )],
        )

    @staticmethod
    def _stencil_product_context(soup):
        decoder = json.JSONDecoder()
        pattern = re.compile(r"\bstencilBootstrap\(\s*[\"']product[\"']\s*,\s*")
        for script in soup.select("script"):
            script_text = script.string or script.get_text()
            match = pattern.search(script_text or "")
            if not match:
                continue
            try:
                encoded_context, _end = decoder.raw_decode(script_text[match.end():].lstrip())
                if isinstance(encoded_context, str):
                    context = json.loads(encoded_context)
                    return context if isinstance(context, dict) else {}
            except (json.JSONDecodeError, TypeError):
                continue
        return {}

    @staticmethod
    def _gql_variants(edges, product_name=""):
        variants = []
        for edge in edges:
            node = (edge or {}).get("node") or {}
            inventory = node.get("inventory") or {}
            in_stock = inventory.get("isInStock")
            status = (
                StockStatus.IN_STOCK if in_stock is True
                else StockStatus.OUT_OF_STOCK if in_stock is False
                else StockStatus.UNKNOWN
            )

            labels = []
            for option_edge in (node.get("options") or {}).get("edges", []):
                option = (option_edge or {}).get("node") or {}
                for value_edge in (option.get("values") or {}).get("edges", []):
                    label = str(((value_edge or {}).get("node") or {}).get("label") or "").strip()
                    if label:
                        labels.append(label)

            price_data = (node.get("incVatPrices") or {}).get("price") or {}
            if not price_data:
                price_data = (node.get("exVatPrices") or {}).get("price") or {}
            external_id = str(node.get("entityId") or node.get("sku") or f"variant-{len(variants)}")
            variants.append(VariantObservation(
                external_id=external_id[:200],
                name=_variant_name(product_name, " / ".join(labels), node.get("sku")),
                status=status,
                price=_decimal(price_data.get("value")),
                currency=str(price_data.get("currencyCode") or "")[:8],
                hint=(
                    f"BigCommerce variant_id={external_id} sku={node.get('sku') or ''} "
                    f"is_in_stock={in_stock}"
                )[:500],
            ))
        return variants


class NovaAdapter(BigCommerceAdapter):
    def parse(self, html, final_url):
        observation = super().parse(html, final_url)
        if not observation.variants:
            return observation
        soup = BeautifulSoup(html, "lxml")
        weight_node = soup.select_one(".nova-net-weight-row .productView-info-value")
        if weight_node:
            weight = weight_node.get_text(" ", strip=True)
            if weight:
                observation.variants[0].name = weight[:200]
        return observation


class ShopifyAdapter(GenericAdapter):
    def fetch(self, url):
        parsed_url = urlparse(url)
        product_path = parsed_url.path.rstrip("/")
        json_path = product_path if product_path.endswith(".js") else f"{product_path}.js"
        country = str(self.config.get("country") or "GB")
        json_url = urlunparse(parsed_url._replace(
            path=json_path,
            query=urlencode({"country": country}),
            fragment="",
        ))
        payload, _final_url = fetch_html(json_url, self.site.domain)
        return self.parse(payload, url)

    def parse(self, payload, canonical_url):
        try:
            product = json.loads(payload)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Shopify 商品数据格式无效") from exc
        if not isinstance(product, dict):
            raise ValueError("Shopify 商品数据格式无效")

        name = str(product.get("title") or "").strip()
        currency = str(self.config.get("currency") or "GBP")[:8]
        image = product.get("featured_image") or ""
        if isinstance(image, dict):
            image = image.get("src") or image.get("url") or ""
        image_url = urljoin(canonical_url, str(image)) if image else ""

        variants = []
        for index, variant in enumerate(product.get("variants") or []):
            if not isinstance(variant, dict):
                continue
            available = variant.get("available")
            status = (
                StockStatus.IN_STOCK if available is True
                else StockStatus.OUT_OF_STOCK if available is False
                else StockStatus.UNKNOWN
            )
            external_id = str(variant.get("id") or variant.get("sku") or f"variant-{index}")
            price = _decimal(variant.get("price"))
            if price is not None:
                price /= Decimal("100")
            variants.append(VariantObservation(
                external_id=external_id[:200],
                name=_variant_name(
                    name,
                    variant.get("public_title") or variant.get("title"),
                    variant.get("sku"),
                ),
                status=status,
                price=price,
                currency=currency,
                hint=f"Shopify variant_id={external_id} available={available}"[:500],
            ))

        return ProductObservation(
            name=name[:300],
            canonical_url=canonical_url,
            image_url=image_url,
            variants=variants,
        )


class JamesBarberAdapter(GenericAdapter):
    def parse(self, html, final_url):
        observation = super().parse(html, final_url)
        if not observation.variants:
            return observation

        soup = BeautifulSoup(html, "lxml")
        product_node = soup.select_one('div.product[id^="product-"]')
        variant = observation.variants[0]
        if product_node is not None:
            product_id = re.search(r"^product-(\d+)$", str(product_node.get("id") or ""))
            if product_id:
                variant.external_id = product_id.group(1)

            classes = set(product_node.get("class") or [])
            stock_node = product_node.select_one(".summary p.stock, p.stock")
            stock_classes = set(stock_node.get("class") or []) if stock_node else set()
            if "outofstock" in classes or "out-of-stock" in stock_classes:
                variant.status = StockStatus.OUT_OF_STOCK
            elif "instock" in classes or "in-stock" in stock_classes:
                variant.status = StockStatus.IN_STOCK

        variant.name = _variant_name(observation.name)
        if not variant.currency:
            variant.currency = "GBP"
        variant.hint = f"James Barber product_id={variant.external_id} {variant.hint}"[:500]
        return observation


class HavanaHouseAdapter(WooCommerceAdapter):
    def fetch(self, url):
        html, final_url = fetch_html_bright_data(url, self.site.domain)
        return self.parse(html, final_url)


ADAPTERS = {
    "generic": GenericAdapter,
    "smokingpipes": SmokingPipesAdapter,
    "cgars": CgarsAdapter,
    "woocommerce": WooCommerceAdapter,
    "tecon": TeconAdapter,
    "bigcommerce": BigCommerceAdapter,
    "nova": NovaAdapter,
    "shopify": ShopifyAdapter,
    "jamesbarber": JamesBarberAdapter,
    "havanahouse": HavanaHouseAdapter,
}


def get_adapter(site):
    adapter_class = ADAPTERS.get(site.adapter)
    if not adapter_class:
        raise ValueError(f"未知解析器：{site.adapter}")
    return adapter_class(site)
