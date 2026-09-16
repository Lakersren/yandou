# 海淘补货机器人

面向运营人员的商品 URL 库存监控服务。系统定时检查商品页，在确认发生“缺货 → 有货”后，推送到对应站点飞书群和综合群。

## 已实现

- Ant Design Pro 中文运营控制台和账号权限
- 粘贴一个商品 URL 即可开启监控
- 已知商城域名限制及内网地址防护
- 商品、规格、价格和库存统一模型
- 首次检查只建基线；有货连续确认两次再通知
- 失败不覆盖库存，保留异常记录
- 飞书通知群可多选接收站点，“全部站点”覆盖所有商城；支持加签 Webhook 并加密保存密钥
- Celery 定时调度、失败重试和通知去重
- Havana House 和 Smokingpipes 使用独立 Bright Data Worker，受保护站点的请求不阻塞普通商城抓取
- 运营、只读两类后台角色和操作审计
- 30 天库存快照、90 天异常记录自动清理
- PostgreSQL、Redis、Docker Compose 部署

## 本地验证

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_sites
python manage.py createsuperuser
python manage.py runserver
```

Console 前端在另一个终端运行：

```bash
cd console
npm ci
npm run dev
```

Django 仍在项目根目录通过 `python manage.py runserver` 运行。打开 `http://127.0.0.1:5173/console/` 使用开发控制台，未登录时会进入同一地址下的 Django 登录页，登录后返回原页面。Vite 直接提供 `/console/` 及其子路由的前端源码；`/api/`、`/admin/` 和登录页使用的 `/static/admin/` 转发给 Django，以保留同域 Session 和 CSRF Cookie。不要通过 Django 的 `/console/` 地址访问开发源码。

`npm run test:dev` 可验证开发入口、子路由和登录/API 代理。生产构建仍将资源放在 `/static/console/`，由 Django 的 `/console/` 页面加载。

Daily URL: http://<server-public-ip>:8000/console/

Technical maintenance: http://<server-public-ip>:8000/admin/

Daily operation: click Add Monitored Product, paste one product URL, and submit.

One-time setup: configure Feishu site groups and the all-sites group.

## 浏览器验收测试

Playwright 使用独立的 `.e2e.sqlite3` 数据库、固定商品观察结果和无网络的通知发送器。它不会访问真实商城或飞书。运行后数据库会自动删除：

```bash
cd console
npm run build
npx playwright test
```

## 腾讯云部署（公网 IP）

这套简化部署适合单人使用，推荐腾讯云 Ubuntu 22.04/24.04、2 核 4GB。服务直接监听公网 IP 的 `8000` 端口，不需要域名和 Nginx。

从当前开发机迁移数据库的完整步骤见 [腾讯云部署与数据迁移](docs/DEPLOY.md)。

### 1. 配置安全组

在腾讯云控制台为服务器添加入站规则：协议 `TCP`，端口 `8000`，来源填写你自己电脑当前的公网 IP。不要将来源设置为 `0.0.0.0/0`，否则登录页和管理后台会暴露在整个公网。

### 2. 安装 Docker

登录服务器后执行：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

退出 SSH 并重新登录，让 Docker 用户组生效。然后确认：

```bash
docker version
docker compose version
```

### 3. 配置项目

将项目放到服务器，进入项目目录：

```bash
cp .env.example .env
nano .env
```

至少替换以下内容：

```dotenv
DJANGO_SECRET_KEY=一段足够长的随机字符串
APP_ENCRYPTION_KEY=另一段足够长的随机字符串
DJANGO_ALLOWED_HOSTS=服务器公网IP
DJANGO_CSRF_TRUSTED_ORIGINS=http://服务器公网IP:8000
POSTGRES_PASSWORD=数据库强密码
ADMIN_USERNAME=admin
ADMIN_PASSWORD=后台登录强密码
```

公网 IP 直连使用 HTTP，因此保持 `COOKIE_SECURE=0`、`SECURE_SSL_REDIRECT=0`。可以用 `openssl rand -hex 32` 生成随机字符串。

### 4. 后台启动

```bash
./deploy/manage.sh start
./deploy/manage.sh status
```

首次启动会自动构建镜像、创建数据库表、初始化商城和后台角色，并根据 `.env` 创建管理员。以后服务器重启时，Docker 和容器会自动恢复运行。

访问地址：

- 运营台：`http://服务器公网IP:8000/console/`
- 技术后台：`http://服务器公网IP:8000/admin/`

### 日常命令

```bash
./deploy/manage.sh start    # 构建并后台启动
./deploy/manage.sh stop     # 停止全部服务
./deploy/manage.sh restart  # 重启全部服务
./deploy/manage.sh status   # 查看运行状态
./deploy/manage.sh logs     # 持续查看主要日志，按 Ctrl+C 退出
./deploy/manage.sh export-db # 导出当前 PostgreSQL 数据
./deploy/manage.sh import-db deploy/backups/current.dump # 覆盖导入并启动
```

## 运营流程

1. 进入“飞书群”，录入自定义机器人 Webhook 并选择接收范围；可多选站点，选择“全部站点”即接收所有商城补货。机器人启用签名校验时再填写加签密钥。
2. 打开 `/console/`，进入“商品监控”，点击“添加监控商品”。
3. 粘贴一个商品 URL，点击“开始监控”。系统自动识别商城并建立库存基线，不会误发补货。
4. 在“补货记录”和“异常记录”中查看运行情况。Django Admin `/admin/` 仅用于技术维护。

## 商城适配

各商城的真实 URL、已验证页面类型、解析依据和待办事项统一记录在 [商城解析器适配进度](docs/ADAPTER_PROGRESS.md)。

系统会按域名匹配商城。通用解析器优先读取 JSON-LD，再使用后台商城记录中的 `parser_config`：

```json
{
  "name_selector": "h1.product-title",
  "price_selector": ".product-price",
  "stock_selector": ".availability, button.add-to-cart",
  "in_stock_patterns": ["in stock", "add to cart"],
  "out_of_stock_patterns": ["out of stock", "sold out"]
}
```

若添加商品时提示“暂时无法识别该商品库存”，系统不会创建监控商品。请由技术维护人员根据具体商品 URL 校准对应商城规则，或新增专用适配器。页面要求登录、出现验证码或明确禁止自动访问时应暂停该站点。

目前初始化的是需求清单里实际列出的 15 个商城（美 5、德 2、港 2、新加坡 1、英 5）；虽然原描述写了 14 个，但列表合计为 15 个，系统全部保留。

数据库和 Redis 使用 Docker 数据卷保存；执行 `stop` 不会删除商品和配置数据。
