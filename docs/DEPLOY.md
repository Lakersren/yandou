# 腾讯云部署与数据迁移

这套方案面向单人使用：一台腾讯云 Linux 服务器、Docker Compose、公网 IP 直接访问 `8000` 端口，不使用域名和 Nginx。

## 服务器要求

- Ubuntu 22.04 或 24.04
- 建议 2 核 4GB 内存
- 系统盘至少保留 15GB 可用空间
- 腾讯云安全组只向你的公网 IP 开放 TCP `8000`

## 一、本机导出当前数据库

确保本机 Docker 服务正在运行，然后在项目目录执行：

```bash
./deploy/manage.sh export-db
```

命令会生成 `deploy/backups/restock-日期时间.dump`。这个文件包含当前账号、商城、监控商品、规格库存、飞书群配置和历史记录，不会被 Git 提交。

迁移飞书群配置时，服务器必须沿用本机 `.env` 中原来的 `APP_ENCRYPTION_KEY`。重新生成该值会导致数据库内加密保存的 Webhook 和签名密钥无法读取。

## 二、准备腾讯云服务器

在腾讯云控制台把 TCP `8000` 入站规则的来源限制为你当前电脑的公网 IP。登录服务器后安装 Docker：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

退出 SSH 并重新登录，然后确认：

```bash
docker version
docker compose version
```

## 三、上传项目、配置和数据库

在服务器创建目录：

```bash
sudo mkdir -p /opt/yandou
sudo chown "$USER":"$USER" /opt/yandou
```

在 Mac 项目目录执行，替换服务器用户名、IP 和备份文件名：

```bash
rsync -av --exclude '.git' --exclude '.venv' --exclude 'console/node_modules' \
  --exclude 'deploy/backups' \
  ./ 服务器用户名@服务器IP:/opt/yandou/
ssh 服务器用户名@服务器IP 'mkdir -p /opt/yandou/deploy/backups'
scp deploy/backups/restock-日期时间.dump \
  服务器用户名@服务器IP:/opt/yandou/deploy/backups/current.dump
```

`.env` 默认不会被 Git 管理，但上面的 `rsync` 会将它一并复制到服务器。它包含敏感信息，禁止发送给其他人或提交到代码仓库。

## 四、修改服务器配置

登录服务器：

```bash
cd /opt/yandou
nano .env
```

保留原来的 `APP_ENCRYPTION_KEY` 和 `BRIGHT_DATA_API_KEY`，修改以下项目：

```dotenv
DJANGO_ALLOWED_HOSTS=服务器公网IP,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://服务器公网IP:8000
POSTGRES_PASSWORD=服务器数据库强密码
COOKIE_SECURE=0
SECURE_SSL_REDIRECT=0
WEB_PORT=8000
PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
```

数据库备份不依赖原来的 PostgreSQL 密码，所以服务器可以设置新密码。当前账号已经包含在数据库中，`ADMIN_PASSWORD` 仅在数据库里不存在管理员时使用。

## 五、导入并启动

在服务器项目目录执行：

```bash
chmod +x deploy/manage.sh
./deploy/manage.sh import-db deploy/backups/current.dump
./deploy/manage.sh status
```

`import-db` 会启动 PostgreSQL 和 Redis、覆盖目标数据库、构建应用镜像，然后启动 Web、普通 Worker、Bright Data Worker 和定时调度器。它适合首次部署或明确的数据迁移，不要在含有新数据的服务器上随意重复执行。

访问：

- 运营台：`http://服务器公网IP:8000/console/`
- 技术后台：`http://服务器公网IP:8000/admin/`

## 六、部署后检查

```bash
./deploy/manage.sh status
./deploy/manage.sh logs
```

确认六个容器均为运行状态，在运营台检查商品数量和飞书群配置，然后对一条普通商品和一条 Smokingpipes 商品执行“重新检查”。

以后更新代码只需重新上传变更并执行：

```bash
./deploy/manage.sh start
```

数据库保存在 Docker 数据卷中，`stop` 和重新构建镜像不会删除数据。禁止执行 `docker compose down -v`。
