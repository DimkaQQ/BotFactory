# Shared image for the "api" and "bot" (meta-bot) services — same codebase,
# different CMD per docker-compose.
FROM python:3.12-slim

WORKDIR /srv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY meta_bot ./meta_bot
COPY migrations ./migrations
COPY alembic.ini .

# Не root: если в приложении найдут дыру, у атакующего не будет прав на
# всю систему контейнера. Каталог загрузок создаётся здесь, чтобы именованный
# том при первом создании унаследовал владельца (на томе, созданном раньше
# под root, нужен разовый chown — см. deploy/ops.md).
RUN useradd --system --uid 10001 --home-dir /srv --shell /usr/sbin/nologin app \
    && mkdir -p /srv/media_uploads \
    && chown -R app:app /srv/media_uploads
USER app

# Только для сервиса api: у мета-бота и migrate порта нет, там проверка
# отключена в docker-compose.yml.
HEALTHCHECK --interval=30s --timeout=6s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
