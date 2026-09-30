FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-calc libreoffice-impress pandoc imagemagick \
    poppler-utils fonts-liberation fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY main.py jobs.py observability.py run.sh ./
COPY scripts ./scripts
COPY deploy/start-tunnel.sh ./deploy/start-tunnel.sh
COPY static ./static
RUN chmod -R a+rX /app && chmod 755 ./run.sh ./deploy/start-tunnel.sh && useradd --create-home --uid 10001 appuser && mkdir /data /logs && chown appuser /data /logs
USER appuser
ENV DATA_DIR=/data LOG_DIR=/logs
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
EXPOSE 8000
CMD ["python", "scripts/runtime.py"]
