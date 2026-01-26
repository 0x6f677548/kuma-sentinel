FROM python:3.12-slim

# Links Docker image with repository
LABEL org.opencontainers.image.source=https://go.hugobatista.com/gh/kuma-sentinel
LABEL security.scan="true"
LABEL maintainer="Hugo Batista <mail@hugobatista.com>"

# Install nmap (required for port scanning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_ROOT_USER_ACTION=ignore

WORKDIR /app
COPY . /app

RUN pip install --no-cache --upgrade pip \
 && pip install --no-cache /app \
 && addgroup --system app && adduser --system --group app \
 && mkdir -p /var/log/kuma-sentinel \
 && mkdir -p /data \
 && chown -R app:app /var/log/kuma-sentinel \
 && chown -R app:app /data

USER app

VOLUME /var/log/kuma-sentinel
VOLUME /data

HEALTHCHECK --interval=300s --timeout=10s --start-period=5s --retries=3 \
    CMD kuma-sentinel --version || exit 1

ENTRYPOINT ["kuma-sentinel"]
