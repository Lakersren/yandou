#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env"}
BACKUP_DIR=${BACKUP_DIR:-"$PROJECT_ROOT/deploy/backups"}

if [ ! -f "$ENV_FILE" ]; then
  echo "配置文件不存在：$ENV_FILE" >&2
  echo "请先执行：cp .env.example .env，然后修改其中的密码和服务器 IP。" >&2
  exit 1
fi

compose() {
  docker compose --project-directory "$PROJECT_ROOT" --env-file "$ENV_FILE" "$@"
}

case "${1:-}" in
  start)
    compose up -d --build --remove-orphans
    ;;
  stop)
    compose down
    ;;
  restart)
    compose restart
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs -f --tail 200 web worker worker_bright_data beat
    ;;
  export-db)
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE=${2:-"$BACKUP_DIR/restock-$(date +%Y%m%d-%H%M%S).dump"}
    compose exec -T db sh -c \
      'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      > "$BACKUP_FILE"
    echo "数据库已导出：$BACKUP_FILE"
    ;;
  import-db)
    BACKUP_FILE=${2:-}
    if [ -z "$BACKUP_FILE" ] || [ ! -s "$BACKUP_FILE" ]; then
      echo "请提供有效的数据库备份文件：$0 import-db <backup.dump>" >&2
      exit 2
    fi
    echo "即将用 $BACKUP_FILE 覆盖目标数据库。"
    compose stop web worker worker_bright_data beat
    compose up -d db redis
    compose exec -T db sh -c \
      'until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do sleep 1; done'
    # The official image briefly accepts connections through a temporary server
    # during first-time initialization, then restarts PostgreSQL.
    sleep 3
    compose exec -T db sh -c \
      'until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do sleep 1; done'
    compose exec -T db sh -c \
      'pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      < "$BACKUP_FILE"
    compose up -d --build --remove-orphans
    echo "数据库导入完成，服务已启动。"
    ;;
  *)
    echo "用法：$0 {start|stop|restart|status|logs|export-db [文件]|import-db <文件>}" >&2
    exit 2
    ;;
esac
