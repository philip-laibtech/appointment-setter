FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.lock.txt

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /venv /venv
COPY . .

ENV PATH=/venv/bin:$PATH

# No real secrets needed here — core/settings.py falls back to a dev-only
# SECRET_KEY and DEBUG=true when unset, and collectstatic never touches the DB.
RUN python manage.py collectstatic --noinput

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "core.wsgi:application", "--bind", "127.0.0.1:8000", "--workers", "1", "--threads", "4"]
