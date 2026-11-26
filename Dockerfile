FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Системные пакеты для сборки psycopg2 и работы cron
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Установка Python-зависимостей отдельным слоем для кэширования при пересборках
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода проекта внутрь образа
COPY . /app/

# Подготовка каталога статики и прав на скрипт cron
RUN mkdir -p /app/staticfiles && \
    if [ -f /app/entrypoint.cron.sh ]; then chmod +x /app/entrypoint.cron.sh; fi

EXPOSE 8000

CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]
