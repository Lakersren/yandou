ARG NODE_IMAGE=docker.m.daocloud.io/library/node:22-alpine
ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.13-slim

FROM ${NODE_IMAGE} AS console-build

WORKDIR /console
COPY console/package.json console/package-lock.json ./
RUN npm ci
COPY console/ ./
RUN npm run build

FROM ${PYTHON_IMAGE}

ARG DEBIAN_MIRROR=https://mirrors.cloud.tencent.com
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN sed -i \
      -e "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" \
      -e "s|https://deb.debian.org|${DEBIAN_MIRROR}|g" \
      -e "s|http://security.debian.org|${DEBIAN_MIRROR}|g" \
      -e "s|https://security.debian.org|${DEBIAN_MIRROR}|g" \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates chromium \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt
COPY . .
COPY --from=console-build /monitor/static/console /app/monitor/static/console
RUN chmod +x /app/deploy/entrypoint.sh

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["web"]
