# Используем официальный легковесный образ Python
FROM python:3.10-slim

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Устанавливаем системные зависимости для psycopg2 и cron
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    cron \
    && apt-get clean

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта в рабочую директорию
COPY . .

# Собираем статические файлы. Nginx будет их раздавать.
RUN python manage.py collectstatic --noinput

