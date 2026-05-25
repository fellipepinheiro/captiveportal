FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Garante permissoes de execucao nos scripts
RUN chmod +x /app/scripts/migrate.sh && \
    mkdir -p /app/app/static/uploads && chmod 777 /app/app/static/uploads

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--timeout", "120", "--graceful-timeout", "30", "wsgi:app"]
