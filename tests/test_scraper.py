import json

import httpx
from unittest.mock import patch

from django.test import SimpleTestCase

from monitor.models import StockStatus
from monitor.services.scraper import (
    BigCommerceAdapter,
    CgarsAdapter,
    GenericAdapter,
    HavanaHouseAdapter,
    JamesBarberAdapter,
    NovaAdapter,
    ShopifyAdapter,
    SmokingPipesAdapter,
    TeconAdapter,
    WooCommerceAdapter,
)


class FakeSite:
    domain = "example.com"
    parser_config = {}


class GenericAdapterTests(SimpleTestCase):
    def test_parses_json_ld_product(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"Test Flake","image":"https://example.com/a.jpg",
         "offers":{"@type":"Offer","sku":"50g","price":"19.50","priceCurrency":"USD",
         "availability":"https://schema.org/InStock"}}
        </script></head></html>
        """
        result = GenericAdapter(FakeSite()).parse(html, "https://example.com/p/1")
        self.assertEqual(result.name, "Test Flake")
        self.assertEqual(result.variants[0].external_id, "50g")
        self.assertEqual(result.variants[0].status, StockStatus.IN_STOCK)
        self.assertEqual(str(result.variants[0].price), "19.50")

    def test_out_of_stock_wins_over_cart_words(self):
        FakeSite.parser_config = {"stock_selector": ".availability"}
        html = "<h1>Test</h1><div class='availability'>Out of stock - add to cart unavailable</div>"
        result = GenericAdapter(FakeSite()).parse(html, "https://example.com/p/1")
        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)

    def test_disabled_cart_button_is_not_in_stock(self):
        FakeSite.parser_config = {"stock_selector": "button"}
        html = "<h1>Test</h1><button disabled>Add to cart</button>"
        result = GenericAdapter(FakeSite()).parse(html, "https://example.com/p/1")
        self.assertEqual(result.variants[0].status, StockStatus.UNKNOWN)

    def test_woocommerce_parses_all_embedded_variations(self):
        html = """
        <html><head>
          <link rel="canonical" href="https://example.com/product/blend/">
          <meta property="og:image" content="https://example.com/blend.jpg">
        </head><body>
          <h1 class="product_title">Afternoon Melange</h1>
          <form class="variations_form" data-product_variations='[
            {"variation_id":213952,"attributes":{"attribute_pa_weight":"1oz"},
             "sku":"1FGAM-1oz","display_price":5.08,"is_in_stock":false,
             "price_html":"$5.08"},
            {"variation_id":213965,"attributes":{"attribute_pa_weight":"2lbs"},
             "sku":"1FGAM-2lbs","display_price":123.60,"is_in_stock":true,
             "price_html":"$123.60"}
          ]'></form>
        </body></html>
        """

        result = WooCommerceAdapter(FakeSite()).parse(html, "https://example.com/product/blend/")

        self.assertEqual(result.name, "Afternoon Melange")
        self.assertEqual(result.image_url, "https://example.com/blend.jpg")
        self.assertEqual(
            [(item.external_id, item.name, item.status, str(item.price), item.currency) for item in result.variants],
            [
                ("213952", "1oz", StockStatus.OUT_OF_STOCK, "5.08", "USD"),
                ("213965", "2lbs", StockStatus.IN_STOCK, "123.6", "USD"),
            ],
        )
        self.assertIn("sku=1FGAM-2lbs", result.variants[1].hint)

    def test_woocommerce_filters_a_variation_selected_in_url(self):
        html = """
        <h1>Blend</h1>
        <form class="variations_form" data-product_variations='[
          {"variation_id":1,"attributes":{"attribute_pa_weight":"1oz"},"display_price":5,"is_in_stock":true},
          {"variation_id":2,"attributes":{"attribute_pa_weight":"2oz"},"display_price":9,"is_in_stock":false}
        ]'></form>
        """

        result = WooCommerceAdapter(FakeSite()).parse(
            html, "https://example.com/product/blend/?attribute_pa_weight=2oz"
        )

        self.assertEqual([(item.external_id, item.name) for item in result.variants], [("2", "2oz")])

    def test_woocommerce_simple_product_uses_stable_id_and_configured_currency(self):
        html = """
        <body class="single-product">
          <script type="application/ld+json">
          {"@type":"Product","name":"Germains Medium Flake 1.75oz",
           "offers":{"price":"19.99","availability":"https://schema.org/OutOfStock"}}
          </script>
          <div class="product post-109491 outofstock product-type-simple">
            <p class="stock out-of-stock">Out of stock</p>
          </div>
          <li class="product post-10 instock">Related product</li>
        </body>
        """
        site = FakeSite()
        site.parser_config = {"currency": "USD"}

        result = WooCommerceAdapter(site).parse(html, "https://example.com/product/tobacco/")

        self.assertEqual(result.variants[0].external_id, "109491")
        self.assertEqual(result.variants[0].name, "1.75oz")
        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)
        self.assertEqual(result.variants[0].currency, "USD")

    @patch("monitor.services.scraper.fetch_html_bright_data")
    def test_havana_house_fetches_with_bright_data_and_parses_woocommerce(self, fetch_html_bright_data):
        fetch_html_bright_data.return_value = ("""
        <body class="single-product">
          <script type="application/ld+json">
          {"@type":"Product","name":"Germains Eighteen Twenty Flake 500g",
           "offers":{"price":"124.99","priceCurrency":"GBP",
           "availability":"https://schema.org/OutOfStock"}}
          </script>
          <div class="product post-77123 outofstock product-type-simple">
            <p class="stock out-of-stock">Out of stock</p>
          </div>
        </body>
        """, "https://example.com/product/tobacco/")

        result = HavanaHouseAdapter(FakeSite()).fetch("https://example.com/product/tobacco/")

        fetch_html_bright_data.assert_called_once_with("https://example.com/product/tobacco/", "example.com")
        self.assertEqual(result.name, "Germains Eighteen Twenty Flake 500g")
        self.assertEqual(result.variants[0].external_id, "77123")
        self.assertEqual(result.variants[0].name, "500g")
        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)

    @patch.dict("os.environ", {}, clear=True)
    @patch("monitor.services.scraper.fetch_html_browser")
    @patch("monitor.services.scraper.fetch_html")
    def test_smokingpipes_uses_browser_after_cloudflare_403_without_bright_data(self, fetch_html, fetch_html_browser):
        request = httpx.Request("GET", "https://example.com/p/1")
        response = httpx.Response(403, request=request)
        fetch_html.side_effect = httpx.HTTPStatusError("Forbidden", request=request, response=response)
        fetch_html_browser.return_value = ("""
            <script type="application/ld+json">
            {"@type":"Product","name":"Heritage Collection 100g",
             "offers":{"sku":"003-553-0043","price":"27.00","priceCurrency":"USD",
             "availability":"https://schema.org/InStock"}}
            </script>
        """, "https://example.com/p/1")

        result = SmokingPipesAdapter(FakeSite()).fetch("https://example.com/p/1")

        fetch_html_browser.assert_called_once_with("https://example.com/p/1", "example.com")
        self.assertEqual(result.name, "Heritage Collection 100g")
        self.assertEqual(result.variants[0].status, StockStatus.IN_STOCK)

    @patch.dict("os.environ", {"BRIGHT_DATA_API_KEY": "test-key"}, clear=True)
    @patch("monitor.services.scraper.fetch_html_bright_data")
    @patch("monitor.services.scraper.fetch_html_browser")
    @patch("monitor.services.scraper.fetch_html")
    def test_smokingpipes_uses_bright_data_after_cloudflare_403(
        self, fetch_html, fetch_html_browser, fetch_html_bright_data
    ):
        request = httpx.Request("GET", "https://example.com/p/1")
        response = httpx.Response(403, request=request)
        fetch_html.side_effect = httpx.HTTPStatusError("Forbidden", request=request, response=response)
        fetch_html_bright_data.return_value = ("""
            <script type="application/ld+json">
            {"@type":"Product","name":"Heritage Collection 100g",
             "offers":{"sku":"003-553-0043","price":"27.00","priceCurrency":"USD",
             "availability":"https://schema.org/InStock"}}
            </script>
        """, "https://example.com/p/1")

        result = SmokingPipesAdapter(FakeSite()).fetch("https://example.com/p/1")

        fetch_html_bright_data.assert_called_once_with("https://example.com/p/1", "example.com")
        fetch_html_browser.assert_not_called()
        self.assertEqual(result.variants[0].status, StockStatus.IN_STOCK)

    @patch("monitor.services.scraper.fetch_html_browser")
    @patch("monitor.services.scraper.fetch_html")
    def test_smokingpipes_does_not_hide_non_403_errors(self, fetch_html, fetch_html_browser):
        request = httpx.Request("GET", "https://example.com/p/1")
        response = httpx.Response(500, request=request)
        fetch_html.side_effect = httpx.HTTPStatusError("Server error", request=request, response=response)

        with self.assertRaises(httpx.HTTPStatusError):
            SmokingPipesAdapter(FakeSite()).fetch("https://example.com/p/1")

        fetch_html_browser.assert_not_called()

    def test_smokingpipes_parses_legacy_page_without_product_json_ld(self):
        html = """
        <h1>Special Latakia Flake 50g Pipe Tobacco</h1>
        <h3>Product Number: 003-030-0007</h3>
        <div>We apologize, but this item is temporarily out of stock.</div>
        <section class="related"><button>Add to Cart</button><span class="price">$27.00</span></section>
        """

        result = SmokingPipesAdapter(FakeSite()).parse(html, "https://example.com/product_id/2013")

        self.assertEqual(result.variants[0].external_id, "003-030-0007")
        self.assertEqual(result.variants[0].name, "50g")
        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)
        self.assertIsNone(result.variants[0].price)
        self.assertEqual(result.variants[0].currency, "USD")

    def test_tecon_parses_localized_price_and_stock(self):
        html = """
        <div class="center_product_wrapper">
          <img src="images/product.jpg">
        </div>
        <div class="product_details_wrapper">
          <h1>Esterval's Pipe House No. 1 Pfeifentabak 100g Dose</h1>
          <div class="details_table">
            <b>Lieferzeit:</b>
            <img src="images/instock.png">
            <div>Bestellbar</div>
          </div>
          <div class="product_price">
            <input id="cart_price" value="27,80 &euro;">
          </div>
        </div>
        """

        result = TeconAdapter(FakeSite()).parse(
            html,
            "https://www.tecon-gmbh.de/product_info.php?products_id=15504",
        )

        self.assertEqual(result.name, "Esterval's Pipe House No. 1 Pfeifentabak 100g Dose")
        self.assertEqual(result.image_url, "https://www.tecon-gmbh.de/images/product.jpg")
        self.assertEqual(result.variants[0].external_id, "15504")
        self.assertEqual(result.variants[0].status, StockStatus.IN_STOCK)
        self.assertEqual(str(result.variants[0].price), "27.80")
        self.assertEqual(result.variants[0].currency, "EUR")

    def test_tecon_out_of_stock_wording_wins_over_bestellbar_substring(self):
        html = """
        <div class="product_details_wrapper">
          <h1>Unavailable tobacco</h1>
          <div class="details_table">Nicht bestellbar</div>
          <div class="product_price">19,50 &euro;</div>
        </div>
        """

        result = TeconAdapter(FakeSite()).parse(
            html,
            "https://www.tecon-gmbh.de/product_info.php?products_id=99",
        )

        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)

    def test_tecon_recognizes_archived_soldout_image_and_ignores_zero_price(self):
        html = """
        <div class="product_details_wrapper">
          <h1>Germain Medium Flake 50g Tin</h1>
          <div class="details_table"><img src="images/stock_soldout.png"><div>Ausverkauft</div></div>
          <input id="cart_price" value="0,00 €">
        </div>
        """

        result = TeconAdapter(FakeSite()).parse(
            html, "https://example.com/product_info.php?products_id=6251"
        )

        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)
        self.assertIsNone(result.variants[0].price)

    def test_bigcommerce_parses_embedded_inventory(self):
        html = """
        <html><head>
          <link rel="canonical" href="https://example.com/product/tobacco/">
          <meta property="og:image" content="https://cdn.example.com/product.jpg">
        </head><body>
          <script>
            var BCData = {"product_attributes": {
              "price": {"with_tax": {"formatted": "£24.99", "value": 24.99, "currency": "GBP"}},
              "stock": 1, "instock": true, "purchasable": true
            }};
          </script>
          <div class="productView" data-entity-id="23821">
            <h1 class="productView-name">Shipwrights Mixture 50g Tin</h1>
          </div>
        </body></html>
        """

        result = BigCommerceAdapter(FakeSite()).parse(html, "https://example.com/product/tobacco/")

        self.assertEqual(result.name, "Shipwrights Mixture 50g Tin")
        self.assertEqual(result.image_url, "https://cdn.example.com/product.jpg")
        self.assertEqual(result.variants[0].external_id, "23821")
        self.assertEqual(result.variants[0].name, "50g")
        self.assertEqual(result.variants[0].status, StockStatus.IN_STOCK)
        self.assertEqual(str(result.variants[0].price), "24.99")
        self.assertEqual(result.variants[0].currency, "GBP")

    def test_bigcommerce_parses_out_of_stock(self):
        html = """
        <script>var BCData = {"product_attributes": {
          "price": {"with_tax": {"value": 12.5, "currency": "GBP"}},
          "stock": 0, "instock": false, "purchasable": false
        }};</script>
        <div class="productView" data-entity-id="7"><h1>Unavailable tobacco</h1></div>
        """

        result = BigCommerceAdapter(FakeSite()).parse(html, "https://example.com/product/tobacco/")

        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)

    def test_nova_uses_displayed_net_weight_for_single_variant(self):
        html = """
        <script>var BCData = {"product_attributes": {
          "price": {"without_tax": {"value": 25, "currency": "USD"}},
          "instock": false, "purchasable": true
        }};</script>
        <div class="productView" data-entity-id="868">
          <h1>Special Latakia Flake</h1>
          <div class="nova-net-weight-row"><dd class="productView-info-value">1.75 Oz. (50g)</dd></div>
        </div>
        """

        result = NovaAdapter(FakeSite()).parse(html, "https://example.com/product/tobacco/")

        self.assertEqual(result.variants[0].external_id, "868")
        self.assertEqual(result.variants[0].name, "1.75 Oz. (50g)")
        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)

    def test_single_variant_uses_weight_from_product_name(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"JF Germains Mixture - 1kg in total",
         "offers":{"sku":"25322","price":"99.00","priceCurrency":"GBP",
         "availability":"https://schema.org/OutOfStock"}}
        </script>
        """

        result = GenericAdapter(FakeSite()).parse(html, "https://example.com/product")

        self.assertEqual(result.variants[0].name, "1kg")

    def test_single_variant_normalizes_chinese_weight_from_product_name(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"拉特雷 马林切片 - 50克罐装",
         "offers":{"price":"99.00","availability":"https://schema.org/InStock"}}
        </script>
        """

        result = GenericAdapter(FakeSite()).parse(html, "https://example.com/product")

        self.assertEqual(result.variants[0].name, "50g")

    def test_single_variant_normalizes_written_english_weight(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"Germains Special Latakia Flake 50 gram",
         "offers":{"price":"180.00","availability":"https://schema.org/OutOfStock"}}
        </script>
        """

        result = GenericAdapter(FakeSite()).parse(html, "https://example.com/product")

        self.assertEqual(result.variants[0].name, "50g")

    def test_bigcommerce_graphql_single_variant_uses_title_weight(self):
        context = {
            "product": {"title": "JF Germains - 1820 Mixture & 1820 Flake Tobacco - 1kg in total"},
            "gqlProductResults": {"variants": {"edges": [{"node": {
                "entityId": 25322,
                "inventory": {"isInStock": False},
                "options": {"edges": []},
                "incVatPrices": {"price": {"currencyCode": "GBP", "value": 499.99}},
            }}]}},
        }
        encoded_context = json.dumps(json.dumps(context))
        html = f"""
        <h1 class="productView-name">JF Germains Tobacco</h1>
        <script>window.stencilBootstrap("product", {encoded_context}).load();</script>
        """

        result = BigCommerceAdapter(FakeSite()).parse(html, "https://example.com/product/")

        self.assertEqual(result.variants[0].name, "1kg")

    def test_bigcommerce_parses_graphql_variants(self):
        context = {
            "product": {"title": "Rich Dark Honeydew"},
            "gqlProductResults": {
                "variants": {
                    "edges": [
                        {"node": {
                            "entityId": 23355,
                            "sku": "GH13-10g",
                            "inventory": {"isInStock": True},
                            "options": {"edges": [{"node": {
                                "displayName": "Size",
                                "values": {"edges": [{"node": {"entityId": 601, "label": "10g Loose Pouch"}}]},
                            }}]},
                            "incVatPrices": {"price": {"currencyCode": "GBP", "value": 4.99}},
                        }},
                        {"node": {
                            "entityId": 23359,
                            "sku": "GH13-500g",
                            "inventory": {"isInStock": False},
                            "options": {"edges": [{"node": {
                                "displayName": "Size",
                                "values": {"edges": [{"node": {"entityId": 605, "label": "500g Factory Bag"}}]},
                            }}]},
                            "incVatPrices": {"price": {"currencyCode": "GBP", "value": 203.99}},
                        }},
                    ]
                }
            },
        }
        encoded_context = json.dumps(json.dumps(context))
        html = f"""
        <html><head>
          <link rel="canonical" href="https://example.com/rich-dark/">
          <meta property="og:image" content="https://cdn.example.com/rich-dark.jpg">
        </head><body>
          <h1 class="productView-name">Rich Dark Honeydew</h1>
          <script>window.stencilBootstrap("product", {encoded_context}).load();</script>
          <div class="form-option">Sold Out</div>
        </body></html>
        """

        result = BigCommerceAdapter(FakeSite()).parse(html, "https://example.com/rich-dark/")

        self.assertEqual(
            [(item.external_id, item.name, item.status, str(item.price), item.currency) for item in result.variants],
            [
                ("23355", "10g Loose Pouch", StockStatus.IN_STOCK, "4.99", "GBP"),
                ("23359", "500g Factory Bag", StockStatus.OUT_OF_STOCK, "203.99", "GBP"),
            ],
        )

    @patch("monitor.services.scraper.fetch_html_browser")
    @patch("monitor.services.scraper.fetch_html")
    def test_cgars_uses_browser_after_cloudflare_403(self, fetch_html, fetch_html_browser):
        request = httpx.Request("GET", "https://example.com/product-p-23795.html")
        response = httpx.Response(403, request=request)
        fetch_html.side_effect = httpx.HTTPStatusError("Forbidden", request=request, response=response)
        fetch_html_browser.return_value = ("""
            <script type="application/ld+json">
            {"@type":"Product","name":"Germains Rich Dark Flake 500g Bag",
             "offers":{"price":"450.00","priceCurrency":"GBP",
             "availability":"https://schema.org/OutOfStock"}}
            </script>
        """, "https://example.com/product-p-23795.html")

        result = CgarsAdapter(FakeSite()).fetch("https://example.com/product-p-23795.html")

        fetch_html_browser.assert_called_once_with(
            "https://example.com/product-p-23795.html",
            "example.com",
        )
        self.assertEqual(result.name, "Germains Rich Dark Flake 500g Bag")
        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)
        self.assertEqual(str(result.variants[0].price), "450.00")
        self.assertEqual(result.variants[0].currency, "GBP")

    def test_cgars_treats_loose_weight_ladder_as_shared_stock(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"Kendal Bobs Medium Flake Pipe Tobacco (Loose)",
         "offers":{"price":"4.99","priceCurrency":"GBP",
         "availability":"https://schema.org/InStock"}}
        </script>
        <input type="hidden" name="id[70]" id="slider-input">
        <div id="grams-slider"></div>
        <script>
          if(gValue === 10) { result = "£4.99"; options_values_id = "1186"; }
          if(gValue === 500) { result = "£242.59"; options_values_id = "1202"; }
          if(gValue === 1000) { result = "£482.09"; options_values_id = "1207"; }
        </script>
        """

        result = CgarsAdapter(FakeSite()).parse(
            html,
            "https://example.com/kendal-bobs-loose-p-21171.html",
        )

        self.assertEqual(len(result.variants), 1)
        self.assertEqual(result.variants[0].external_id, "21171")
        self.assertEqual(result.variants[0].name, "散装（10g-1000g）")
        self.assertEqual(result.variants[0].status, StockStatus.IN_STOCK)
        self.assertEqual(str(result.variants[0].price), "4.99")
        self.assertIn("500g=£242.59", result.variants[0].hint)

    @patch("monitor.services.scraper.fetch_html")
    def test_shopify_fetches_product_json_and_parses_all_variants(self, fetch_html):
        fetch_html.return_value = (json.dumps({
            "id": 6556426240054,
            "title": "Germain's Eighteen Twenty Pipe Tobacco",
            "featured_image": "//cdn.shopify.com/product.jpg",
            "variants": [
                {"id": 47285956378944, "title": "50g Tin", "available": False, "price": 3000},
                {"id": 47285956411712, "title": "Mixture 500g Bag", "available": True, "price": 30000},
            ],
        }), "https://www.havahavana.com/products/eighteen-twenty-50g-tins.js")

        result = ShopifyAdapter(FakeSite()).fetch(
            "https://www.havahavana.com/products/eighteen-twenty-50g-tins"
        )

        fetch_html.assert_called_once_with(
            "https://www.havahavana.com/products/eighteen-twenty-50g-tins.js?country=GB",
            "example.com",
        )
        self.assertEqual(result.name, "Germain's Eighteen Twenty Pipe Tobacco")
        self.assertEqual(result.image_url, "https://cdn.shopify.com/product.jpg")
        self.assertEqual(
            [(item.external_id, item.name, item.status, str(item.price), item.currency) for item in result.variants],
            [
                ("47285956378944", "50g Tin", StockStatus.OUT_OF_STOCK, "30", "GBP"),
                ("47285956411712", "Mixture 500g Bag", StockStatus.IN_STOCK, "300", "GBP"),
            ],
        )

    def test_james_barber_uses_current_product_stock_not_related_products(self):
        html = """
        <script type="application/ld+json">
        {"@graph":[{"@type":"Product","name":"Germains King Charles Pipe Tobacco- 500g",
         "image":"https://example.com/product.jpg","sku":13501,
         "offers":{"price":"500.00","priceCurrency":"GBP",
         "availability":"https://schema.org/OutOfStock"}}]}
        </script>
        <h1 class="product_title">Germains King Charles Pipe Tobacco- 500g</h1>
        <div id="product-13501" class="product outofstock product-type-simple">
          <div class="summary"><p class="stock out-of-stock">Out of stock</p></div>
        </div>
        <section class="related products">
          <li class="product instock"><a class="add_to_cart_button">Add to basket</a></li>
        </section>
        """

        result = JamesBarberAdapter(FakeSite()).parse(html, "https://example.com/product/tobacco/")

        self.assertEqual(result.name, "Germains King Charles Pipe Tobacco- 500g")
        self.assertEqual(result.variants[0].external_id, "13501")
        self.assertEqual(result.variants[0].name, "500g")
        self.assertEqual(result.variants[0].status, StockStatus.OUT_OF_STOCK)
        self.assertEqual(str(result.variants[0].price), "500.00")
        self.assertEqual(result.variants[0].currency, "GBP")
