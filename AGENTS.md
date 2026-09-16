# Agent 项目指南

## 项目概述

本项目是一个供单人运营使用的海淘商城补货监控工具。运营人员只需在中文 Ant Design Pro 控制台中粘贴商品详情页 URL，后端就会识别商城、解析商品及规格库存、定时检查库存变化，并在确认某个规格从缺货变为有货后发送飞书通知。

系统目前配置了 15 个商城，覆盖美站、德站、港站、新加坡站和英站。商城定义及解析器分配统一维护在 `monitor/management/commands/seed_sites.py`。

这是一个小型个人运营工具。优先采用简单、可靠、容易维护的实现，不要引入企业级基础设施、复杂配置或不必要的抽象。

## 核心流程

```text
运营人员粘贴商品 URL
  -> 根据域名匹配已启用的 Site
  -> 抓取并解析商品名、图片、规格、价格和库存
  -> 第一次结果只作为库存基线，不发送通知
  -> Celery Beat 每分钟分发到期的商品检查任务
  -> Worker 独立检查每个规格
  -> 确认规格从缺货变为有货后创建 StockEvent
  -> 推送到对应站点飞书群和综合群
```

日常运营操作应当只需要一个商品 URL。解析规则、商城选择、检查间隔和通知路由都应提供合理默认值。

## 产品定位

- 日常运营入口是 `/console/`，`/admin/` 仅用于技术维护。
- 控制台使用 React、TypeScript、Ant Design 和 Ant Design Pro Components，界面语言为中文。
- 界面应简洁、紧凑并符合标准后台管理系统习惯。这是运营工具，不是营销网站。
- 核心操作是“添加监控商品”：粘贴一个 URL 并提交。
- 不要向运营人员暴露 CSS 选择器、解析规则等底层抓取配置。
- 当前部署不引入 Nginx，也不要求域名。服务器入口为 `http://<公网IP>:8000/console/`。

## 技术与服务

- 后端：Django
- API：`/api/console/v1/` 下的 Django JSON 接口
- 前端：React 19、TypeScript、Vite、Ant Design Pro
- 任务队列与调度：Celery Worker、Celery Beat
- 消息代理与缓存：Redis
- 生产数据库：PostgreSQL
- 非 Docker 本地数据库：未设置 `POSTGRES_HOST` 时使用 SQLite
- 页面解析：HTTPX、BeautifulSoup、JSON-LD 和商城专用解析器
- 浏览器回退：受 Cloudflare 保护的部分商城使用 Playwright 和系统 Chromium
- 静态文件：Vite 构建产物复制到 Django 镜像，并由 WhiteNoise 提供服务
- 通知：运营台使用支持加签的飞书自定义机器人 Webhook；每个群可多选接收站点，`ALL` 表示全部站点；底层通知渠道模型兼容钉钉

Docker Compose 包含 `db`、`redis`、`web`、`worker`、`worker_bright_data` 和 `beat` 六个服务。默认 Worker 处理普通抓取、Chromium 和通知；Bright Data Worker 独立处理 Havana House 和 Smokingpipes，避免受保护站点的请求阻塞其他商城。

## 重要文件

- `monitor/models.py`：商城、商品、规格、快照、补货事件、通知渠道、异常及商品汇总库存状态
- `monitor/services/scraper.py`：公共解析工具和所有商城解析器
- `monitor/services/browser.py`：复用浏览器资料目录的 Chromium 回退通道
- `monitor/services/http.py`：限制大小的 HTTP 抓取、跳转校验、IPv4 传输及 SSRF 防护
- `monitor/services/catalog.py`：URL 校验和首次库存基线创建
- `monitor/services/checker.py`：定时检查、连续确认及补货事件创建
- `monitor/services/notifier.py`：飞书与钉钉消息组装及发送
- `monitor/tasks.py`：Celery 任务分发、库存检查、通知和历史数据清理
- `monitor/console/`：运营控制台 JSON API 和序列化逻辑
- `monitor/management/commands/seed_sites.py`：支持商城的权威配置清单
- `docs/ADAPTER_PROGRESS.md`：商城解析器验证进度、真实样本、已知限制和下一步样本需求
- `console/src/`：React 运营控制台
- `restock/settings.py`：Django、Celery、数据库、缓存及部署配置
- `deploy/manage.sh`：简化的 Docker 生命周期管理脚本
- `deploy/entrypoint.sh`：容器启动及初始化逻辑
- `tests/test_scraper.py`：解析器定向测试

## 库存语义

库存以规格为最小单位。解析多规格商品时，绝不能提前合并成一个布尔库存值。

所有单规格解析器统一使用平台规格名或从商品标题提取包装重量；无法提取时显示“单规格”，不要向运营界面输出“默认规格”。标题重量兜底支持 `g/kg/oz/lbs` 和克/千克/公斤/盎司/磅，多规格页面仍优先采用平台返回的规格标签。

规格持久化状态如下：

- `unknown`：没有足够证据可靠判断
- `out_of_stock`：缺货
- `in_stock`：有货
- `discontinued`：已下架或已移除

商品级状态只用于汇总展示：

- `in_stock`：所有当前规格都有货
- `partial_stock`：至少一个规格有货，但不是全部规格有货
- `out_of_stock`：所有规格均缺货或已下架
- `unknown`：没有足够信息可靠判断

混合库存应显示类似“部分有货 1/6”的数量，并在控制台中展示每个规格的独立状态，让运营人员可以直接看到具体哪个规格有货。

通知规则比一般的状态变化更严格：

- 首次成功解析只创建库存基线，不发送通知。
- 规格从 `out_of_stock` 或 `discontinued` 变为 `in_stock` 时创建补货事件。
- 有货结果必须连续检测到两次才正式确认。
- 变为缺货只需检测一次，不发送通知。
- `unknown` 结果不会覆盖已经确认的库存状态。
- 多规格商品中的每个规格独立判断和发送通知。

修改商品汇总标签、筛选条件或界面展示时，不要意外改变这些通知规则。

## 商城解析器开发流程

当前阶段由运营人员逐个提供真实商品详情页 URL，用于验证每个商城并实现可靠的解析器。

除非运营人员明确说“加入监控”，否则收到的商城 URL 默认是解析器开发样本，不要在数据库中创建 Product 记录。

处理每个新商城样本时：

1. 清理 URL 中误带的中文标点或转义后的查询参数分隔符。
2. 抓取真实页面，记录普通 HTTP 是否可用，或者是否出现 Cloudflare 等访问限制。
3. 优先使用可靠的服务端数据，不要首先依赖可见按钮文字。优先级通常为 JSON-LD、平台内嵌 JSON、规格数据载荷、商品区域内的明确 DOM 标记。
4. 确认 URL 是固定单规格商品，还是包含多个可选择规格的商品。
5. 使用平台规格 ID、商品 ID 或 SKU 保持规格标识稳定。
6. 正确解析本地化价格，包括欧洲小数逗号。
7. 证据不充分时返回 `unknown`，不要猜测库存。
8. 在 `monitor/services/scraper.py` 中新增商城或电商平台解析器，并在 `ADAPTERS` 中注册。
9. 在 `seed_sites.py` 中更新对应商城的解析器配置。
10. 为有货和缺货状态补充小型静态 HTML 测试；涉及多规格时必须增加多规格测试。
11. 只运行新增的定向测试，并执行一次真实页面解析验证。

如果样本是单规格商品，但商城平台可能存在可选择规格，应明确说明当前限制，并在获得真实多规格 URL 后再宣称支持规格级解析。

不要仅因页面中出现 `cart`、`available` 等通用文字，或者推荐商品存在购买按钮，就将当前商品判断为有货。库存证据必须限定在当前商品容器或当前商品的结构化数据内。明确的缺货证据必须优先，例如德文 `nicht bestellbar` 包含 `bestellbar`，不能因此误判成有货。

## 当前解析器覆盖情况

- `generic`：优先解析 JSON-LD，失败后使用配置的 CSS 选择器。它只是兜底方案，商城被分配到 `generic` 并不代表已经完成生产级验证。
- `smokingpipes`：使用通用结构化数据解析；普通 HTTP 返回 403 时优先使用 Bright Data Web Unlocker，未配置 Bright Data 时才使用 Chromium 回退。
- `woocommerce`：解析所有 WooCommerce 内嵌规格，包括规格 ID、名称、价格和独立库存状态。当前用于 Dreaming Pipes。
- `tecon`：解析 Tecon 的德文库存标记、使用小数逗号的欧元价格、相对图片地址和固定商品 ID。
- `bigcommerce`：解析内嵌 `BCData`，并优先读取 GraphQL 规格级库存和价格。当前用于 GQ Tobaccos，已验证单规格和多规格商品。
- `nova`：在 BigCommerce 解析基础上读取 Nova 商品页展示的净重，避免固定规格显示为“单规格”。
- `shopify`：读取 Shopify 商品 JSON，按 variant ID 独立解析规格名、价格和库存。当前用于 Hava Havana、70 Cigars 和 Tobacco Lifestyle；地区与币种由商城默认配置提供。
- `jamesbarber`：解析 James Barber 的 WooCommerce 固定规格页面，库存只读取当前商品容器，避免推荐商品干扰。
- `cgars`：使用通用 JSON-LD 解析；普通 HTTP 返回 403 时使用 Chromium 回退。支持固定包装，并将共享库存的散装重量价格阶梯建模为一个库存单元，避免补货时重复通知。

仍然使用 `generic` 的商城必须通过真实商品 URL 验证后，才能视为适配完成。特别是包含可选尺寸或重量的商城，即使通用 JSON-LD 返回总体 Offer，也必须实现明确的规格级解析。

## 浏览器回退规则

只有普通 HTTP 抓取被拦截，并且无法通过其他方式获得结构化 HTML 时才使用浏览器。浏览器抓取速度更慢，内存占用也更高。

`monitor/services/browser.py` 使用持久化资料目录，并拦截图片、媒体和字体请求。Docker 中 Web 与 Worker 使用各自独立的浏览器资料卷。镜像内安装 Chromium，并通过以下变量配置：

浏览器运行时固定隔离在专用线程中，避免 Playwright 的同步事件循环使 Django ORM 误判为异步上下文。不要把浏览器上下文重新移回执行 ORM 的主线程。

```text
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
RESTOCK_BROWSER_PROFILE_DIR=/browser-profile
```

当前浏览器抓取会等待页面出现 Product 或 ProductGroup JSON-LD。若受保护商城没有这些数据，应增加对应商城的明确页面就绪条件，不要使用任意时长的 `sleep`。

## 本地开发

启动后端：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_sites
python manage.py runserver
```

在另一个终端启动前端：

```bash
cd console
npm ci
npm run dev
```

使用 `http://127.0.0.1:5173/console/` 访问 Vite 开发环境。Vite 会代理 Django 登录、Admin 和 API 路由。由 Django 提供的 `/console/` 使用上一次生产构建的前端资源，不会直接反映当前前端源码。

## Docker 操作

```bash
./deploy/manage.sh start
./deploy/manage.sh restart
./deploy/manage.sh status
./deploy/manage.sh logs
./deploy/manage.sh stop
./deploy/manage.sh export-db
./deploy/manage.sh import-db deploy/backups/current.dump
```

`start` 会重新构建镜像，`restart` 只重启已有容器。Python 解析器代码会被打包到镜像中，因此正式生效通常需要重新构建。在本地快速开发解析器时，不要每次小改动都重建 Docker；应先在本地完成定向验证，积累一批有效改动后再统一构建。

跨机器迁移使用 `export-db` 和 `import-db`。导入会覆盖目标数据库；迁移已有飞书配置时必须保留原 `APP_ENCRYPTION_KEY`，否则加密字段无法解密。数据库备份保存在已忽略的 `deploy/backups/`，禁止提交到 Git。

Compose 默认使用 DaoCloud 镜像地址和腾讯 Debian 软件源。它们是镜像源，不要求本机运行代理。如果 Docker 报错 `proxyconnect ... 127.0.0.1:<端口>`，应检查并清理 macOS 或 Docker Desktop 中残留的代理设置。

日常操作禁止执行 `docker compose down -v`，因为该命令会删除 PostgreSQL、Redis 和浏览器资料数据卷。

## 测试要求

项目当前处于本地快速开发阶段，验证范围应与改动风险匹配：

- 修改解析器：只运行 `tests.test_scraper` 中对应的测试方法；涉及网络行为时再执行一次真实页面解析。
- 修改后端模型或检查逻辑：只运行直接相关的 Django 测试模块。
- 修改前端：仅在必要时运行相关 Vitest 文件或 TypeScript 构建。
- 不要在每次编辑后运行完整 Django、Vitest 和 Playwright 测试套件。
- 不要在每次解析器编辑后重建 Docker。
- 到达部署节点，或者修改共享库存与事件语义时，再运行更广泛的检查。
- 日常修改不需要执行响应式截图检查。

定向测试示例：

```bash
.venv/bin/python manage.py test tests.test_scraper.GenericAdapterTests.<测试方法> -v 1
```

## 安全与数据处理

- 保留 `Site.accepts_url` 的域名校验和 `_assert_public_host` 的 SSRF 防护。
- 禁止带账号密码的 URL、任意端口、私有 IP 目标和跨商城域名跳转。
- 飞书和钉钉 Webhook 地址及密钥使用加密字段存储，禁止打印或提交其真实值。
- 不要输出 `.env` 内容；配置说明只能参考 `.env.example`。
- 保留现有 PostgreSQL、Redis 和浏览器资料数据卷。
- 当前工作区中已有的未提交改动属于用户，禁止还原无关文件。

## 修改原则

- 改动范围应限定在用户提供的商城或明确提出的工作流内。
- 优先复用现有解析器或实现平台级通用解析器，不要复制重复的选择器逻辑。
- 避免误发补货通知；证据不足时返回 `unknown` 比猜测更安全。
- 保持运营配置最少，并提供合理默认值。
- 除非用户明确要求，否则不要添加企业级备份、监控平台、代理、Nginx 或编排复杂度。
- 保持控制台中文文案与现有界面一致。
- 解析器覆盖范围或核心库存语义发生实质变化时，应同步更新本文档。
