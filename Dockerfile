FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt

COPY app ./app
COPY prototype ./prototype
COPY config.py ./config.py
COPY scripts/serve.py ./scripts/serve.py

RUN groupadd --system boardtrace \
    && useradd --system --gid boardtrace boardtrace \
    && mkdir -p /app/data/backups \
    && chown -R boardtrace:boardtrace /app/data

USER boardtrace
EXPOSE 5000
CMD ["python", "scripts/serve.py"]
