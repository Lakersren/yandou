# 商城解析器适配进度

最后更新：2026-09-15

本文档是商城解析进度的权威记录。每完成一个真实商品页面验证，都应更新对应商城的覆盖类型、样本 URL、解析依据、已知限制和下一步工作。

## 状态说明

- `已验证`：已有专用或平台级解析器，并通过真实页面和定向测试验证。
- `部分验证`：部分页面类型可用，但仍缺少关键样本或存在已知限制。
- `待验证`：仍使用 `generic` 通用解析器，尚未用真实页面证明稳定性。

“已验证”只代表文档中列出的页面类型，不代表商城未来新增的所有页面模板都自动兼容。

单规格命名采用全局统一规则：优先使用平台提供的规格名称，其次从商品标题提取 `50g`、`1kg`、`2oz`、`2lbs` 或对应中文单位等包装重量，仍无法识别时显示“单规格”，不再显示“默认规格”。

## 总体进度

| 站点 | 商城 | 代码 | 当前解析器 | 状态 | 已验证类型 |
|---|---|---:|---|---|---|
| 美站 | Smokingpipes | `sp` | `smokingpipes` | 已验证 | 固定单规格、Cloudflare 403 后使用 Bright Data |
| 美站 | Dreaming Pipes | `dp` | `woocommerce` | 已验证 | WooCommerce 多规格、混合库存 |
| 美站 | 4Noggins | `4n` | `generic` | 待验证 | 无 |
| 美站 | Nova Pipes & Tobacco | `np` | `nova` | 已验证 | BigCommerce 固定规格、页面净重、缺货状态 |
| 美站 | 70 Cigars | `70` | `shopify` | 已验证 | Shopify 独立库存多规格 |
| 德站 | Tecon | `tecon` | `tecon` | 部分验证 | 固定包装、德文库存、欧式价格 |
| 德站 | Peter Heinrichs | `ph` | `generic` | 待验证 | 无 |
| 港站 | Pipe Uncle | `pipeuncle` | `generic` | 待验证 | 无 |
| 港站 | Tobacco Lifestyle | `lifestyle` | `shopify` | 部分验证 | Shopify 固定规格缺货页面 |
| 新加坡站 | Pipes Space | `ps` | `generic` | 待验证 | 无 |
| 英站 | C.Gars | `cg` | `cgars` | 已验证 | 固定包装、共享库存散装重量阶梯、Cloudflare 403 回退 |
| 英站 | GQ Tobaccos | `gq` | `bigcommerce` | 已验证 | BigCommerce 单规格和独立库存多规格 |
| 英站 | Hava Havana | `hh` | `shopify` | 已验证 | Shopify 独立库存多规格 |
| 英站 | Havana House | `havanahouse` | `havanahouse` | 已验证 | Bright Data Web Unlocker + WooCommerce，11 条固定规格样本；默认 15 分钟检查 |
| 英站 | James Barber | `jb` | `jamesbarber` | 部分验证 | WooCommerce 固定规格缺货页面 |

当前统计：

- 已验证：6 个商城
- 部分验证：4 个商城
- 待验证：5 个商城
- 已通过真实 URL 进行过分析：9 个商城

## 已完成或部分完成的商城

### Smokingpipes

当前解析器：`smokingpipes`

实现方式：优先使用普通 HTTP 和 JSON-LD；遇到 Cloudflare `403 Forbidden` 时切换到持久化 Chromium，并等待 Product 或 ProductGroup JSON-LD 出现。

已验证样本：

- [Limited Edition 2026 Heritage Collection 100g](https://www.smokingpipes.com/pipe-tobacco/erik-stokkebye/limited-edition-2026-heritage-collection-100g/product_id/737541)

真实解析结果：

- 商品名：Limited Edition 2026 Heritage Collection 100g
- SKU：`003-553-0043`
- 价格：`USD 27.00`
- 库存：有货
- 类型：固定单规格

已知限制：尚未提供 Smokingpipes 真正的多规格商品页面，不能确认同站点其他模板是否一致。

下一步样本：固定单规格缺货页面、多规格页面（如果存在）。

### Dreaming Pipes

当前解析器：`woocommerce`

实现方式：读取 WooCommerce `form.variations_form` 中的 `data-product_variations`，按 `variation_id` 保存每个规格的名称、价格和独立库存。

已验证样本：

- [4th Generation Afternoon Melange](https://dreamingpipes.com/product/4th-generation-afternoon-melange/)

真实解析结果：

| 规格 | 价格 | 库存 |
|---|---:|---|
| 1oz | USD 5.08 | 缺货 |
| 2oz | USD 9.55 | 缺货 |
| 4oz | USD 18.04 | 缺货 |
| 8oz | USD 33.66 | 缺货 |
| 16oz | USD 64.45 | 缺货 |
| 2lbs | USD 123.60 | 有货 |

商品汇总状态应显示为“部分有货 1/6”，不能显示为总体“有货”。

URL 带 `variation_id` 或 `attribute_*` 参数时，解析器会限定到 URL 明确选择的规格；未指定时解析全部规格。

### 70 Cigars

当前解析器：`generic`，尚未完成 Shopify 专用适配。

问题样本：

- [Rattray's Marlin Flake](https://70cigars.com/zh-cn/products/rattrays-marlin-flake?variant=44197838717160)

已确认问题：URL 指向一个具体 Shopify `variant`，但通用解析器读取到了商品整体或其他规格的库存，出现“粘贴的 500g 缺货，但结果显示 50g 有货”的误判。

风险：当前不应将 70 Cigars 视为稳定可用，也不应根据商品总体 Offer 推断 URL 指定规格的库存。

下一步：实现 Shopify variants 解析，覆盖以下情况：

- 无 `variant` 参数时解析全部规格。
- 有 `variant` 参数时只监控指定规格。
- 至少提供一个多规格部分有货样本和一个全部缺货样本。

### Tecon

当前解析器：`tecon`

实现方式：读取 Tecon 商品区域中的德文库存标记；识别 `Bestellbar` 和 `instock.png`；让 `nicht bestellbar`、`nicht verfügbar`、`ausverkauft`、`vergriffen` 等明确缺货标记优先。支持 `27,80 €` 形式的欧式价格和相对图片地址。

已验证样本：

- [Esterval's Pipe House No. 1 Pfeifentabak 100g Dose](https://www.tecon-gmbh.de/product_info.php?cPath=667_2393&products_id=15504&language=de&lgcode=1)

真实解析结果：

- 商品 ID：`15504`
- 规格：100g
- 价格：`EUR 27.80`
- 库存：有货
- 类型：固定包装

已知限制：尚未获得 Tecon 缺货真实页面和多规格真实页面。缺货规则已有静态测试，但仍需要真实页面确认。

### GQ Tobaccos

当前解析器：`bigcommerce`

实现方式：

- 单规格页面读取内嵌 `BCData.product_attributes`。
- 多规格页面优先读取 `stencilBootstrap` 中的 GraphQL variant 数据。
- 逐个保存 BigCommerce variant `entityId`、规格名称、含税价格和独立库存。
- 不使用页面初始 DOM 中可能存在的 `Sold Out` 占位文字。

已验证单规格样本：

- [Chieftain Shipwrights Mixture 50g Tin](https://www.gqtobaccos.com/pipe-tobacco/cheiftain-shipwrights-mixture-pipe-tobacco-50g-tin/)

解析结果：商品 ID `23821`，`GBP 24.99`，有货。

已验证多规格样本：

- [Gawith Hoggarth Rich Dark Spring Dew](https://www.gqtobaccos.com/gawith-hoggarth-rich-dark-honeydew-pipe-tobaccoloose/)

| Variant ID | 规格 | 价格 | 库存 |
|---:|---|---:|---|
| 23355 | 10g Loose Pouch | GBP 4.99 | 有货 |
| 23356 | 25g Loose Pouch | GBP 10.49 | 有货 |
| 23357 | 50g Loose Pouch | GBP 20.69 | 有货 |
| 23358 | 200g Loose Pouch | GBP 80.99 | 有货 |
| 23359 | 500g Factory Bag | GBP 203.99 | 有货 |

关键结论：该多规格页面的初始 HTML 为各规格渲染了 `Sold Out` 占位元素，但 GraphQL 数据显示五个规格均有货。必须以 GraphQL 规格数据为准。

下一步样本：多规格部分有货或全部缺货页面，用于继续验证 GraphQL 缺货状态。

### Hava Havana

当前解析器：`shopify`

实现方式：读取 Shopify 商品 `.js` 数据，使用稳定的 variant ID，逐个保存规格名称、英国含税价格和独立库存。请求固定 `country=GB`，避免 Shopify 返回未含 VAT 的地区价格。

已验证 8 个 Germain's 商品页面，共 17 个规格。页面包含 `50g Tin`、`500g Bag`，以及 Eighteen Twenty 的 Mixture/Flake 两种 500g 包装；验证时所有规格均为缺货，价格分别为 GBP 30.00 和 GBP 300.00。

下一步样本：至少一个真实有货或部分有货页面，用于补充线上状态验证。

### C.Gars

当前解析器：`cgars`

实现方式：普通 HTTP 返回 Cloudflare 403 时切换 Chromium。固定包装读取 JSON-LD；散装页面读取重量滑块脚本中的克数和价格阶梯，但把共享库存的重量档位保留为一个库存单元。

已验证固定包装样本：

- [Germains Rich Dark Flake 500g Bag](https://www.cgarsltd.co.uk/germains-rich-dark-flake-pipe-tobacco-500g-bag-p-23795.html)
  - 规格：500g
  - 价格：GBP 450.00
  - 库存：缺货
- [Germains Rich Dark Flake 50g Tin](https://www.cgarsltd.co.uk/germains-rich-dark-flake-pipe-tobacco-50g-tin-p-40128.html)
  - 商品 ID：`40128`
  - 规格：50g
  - 价格：GBP 55.00
  - 库存：缺货

已验证散装样本：

- [Kendal Bobs C Medium Flake Loose](https://www.cgarsltd.co.uk/kendal-bobs-medium-flake-pipe-tobacco-loose-p-21171.html)
  - 商品 ID：`21171`
  - 规格展示：散装（10g-1000g）
  - 起售价：GBP 4.99
  - 库存：有货

页面提供 10g、30g、50g、75g、100g、200g、300g、500g、1000g 九个价格档位。这些档位来自同一份散装库存，不具备独立库存状态，因此不能创建九个独立补货事件，否则一次补货会重复发送九条通知。

下一步样本：固定包装有货页面、散装缺货页面。

## 待验证商城与所需样本

以下商城目前仍使用 `generic`，每个商城优先收集 2 至 4 条真实商品详情页：

| 商城 | 优先需要的样本 |
|---|---|
| 4Noggins | 单规格有货、单规格缺货、多规格页面（如存在） |
| Nova Pipes & Tobacco | 单规格有货、单规格缺货、多规格页面（如存在） |
| Peter Heinrichs | 固定包装有货、固定包装缺货、多规格页面（如存在） |
| Pipe Uncle | 有货、缺货、多规格或可选包装页面 |
| Tobacco Lifestyle | 有货、缺货、多规格或可选包装页面 |
| Pipes Space | 有货、缺货、多规格或可选包装页面 |
| Havana House | 有货、缺货、多规格或可选包装页面 |
| James Barber | 有货、缺货、多规格或可选包装页面 |

## 样本提交格式

提供新 URL 时，最好同时标注人工看到的真实状态：

```text
商城：示例商城
URL：https://example.com/product/example
页面类型：单规格 / 多规格 / 不确定
人工观察：50g 缺货，500g 有货
其他信息：URL 中已经选择 500g
```

如果无法确认页面类型或库存，也可以只提供 URL，开发时再进行判断。

## 更新规则

每次新增或修改商城解析器时，应同步完成以下记录：

1. 更新“总体进度”表中的解析器、状态和覆盖类型。
2. 在商城详情中加入真实样本 URL 和当时的解析结果。
3. 记录最终采用的库存证据及被排除的不可靠证据。
4. 记录单规格、多规格、URL 指定规格或共享库存价格阶梯的语义。
5. 写明仍缺少的页面类型和下一步样本。
6. 更新 `AGENTS.md` 中的“当前解析器覆盖情况”。
7. 只运行对应解析器的定向测试；部署节点再运行更广泛检查。

商城配置的代码权威来源仍是 `monitor/management/commands/seed_sites.py`，本文档负责记录验证证据和开发进度，两者应保持一致。
