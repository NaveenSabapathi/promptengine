FROM python:3.12-slim-bookworm AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY apps/api/requirements.lock.txt ./requirements.lock.txt
RUN python -m venv /opt/venv \
    && sed '/^pytest==/d; /^ruff==/d' requirements.lock.txt > requirements.production.txt \
    && /opt/venv/bin/pip install --only-binary=:all: -r requirements.production.txt
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN /opt/venv/bin/python -c "import tiktoken; tiktoken.encoding_for_model('gpt-4o-mini')"

FROM python:3.12-slim-bookworm AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/tiktoken /opt/tiktoken
WORKDIR /app
COPY apps/api/promptengine ./promptengine
COPY apps/api/migrations ./migrations
COPY apps/api/wsgi.py apps/api/gunicorn.conf.py ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=3)"
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
