FROM ghcr.io/astral-sh/uv:0.11.18@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 AS uv-dist

FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS builder

WORKDIR /tmp

COPY --from=uv-dist /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock README.md ./
COPY src src/

RUN uv export --no-dev --no-emit-project -o requirements.txt \
 && uv build

FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

ARG UID=1000
ARG GID=1000
ARG APP_USER=appuser

LABEL org.opencontainers.image.source=https://go.hugobatista.com/gh/kuma-scout
LABEL security.scan="true"
LABEL maintainer="Hugo Batista <code at hugobatista.com>"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
 && rm -rf /var/lib/apt/lists/* \
 && addgroup --system --gid ${GID} ${APP_USER} \
 && adduser --system --uid ${UID} --gid ${GID} --home /app --shell /sbin/nologin ${APP_USER} \
 && mkdir -p /app /var/log/kuma-scout /data \
 && chown -R ${APP_USER}:${APP_USER} /app /var/log/kuma-scout /data

WORKDIR /app

COPY --chown=${UID}:${GID} --from=builder /tmp/requirements.txt ./
RUN pip install --no-cache --upgrade pip \
 && pip install --no-cache --require-hashes -r ./requirements.txt

COPY --chown=${UID}:${GID} --from=builder /tmp/dist/*.whl /tmp/
RUN pip install --no-cache /tmp/*.whl && rm /tmp/*.whl

USER ${APP_USER}

VOLUME /var/log/kuma-scout
VOLUME /data

HEALTHCHECK --interval=300s --timeout=10s --start-period=5s --retries=3 \
    CMD kuma-scout --version || exit 1

ENTRYPOINT ["kuma-scout"]
