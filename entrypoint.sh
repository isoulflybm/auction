#!/bin/sh
set -e

# Заменяем переменные в шаблоне на реальные значения из .env
envsubst < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Ждем, пока Django-контейнер запустится
until nc -z web 8000; do
    echo "Waiting for Django web server..."
    sleep 2s
done

# Проверяем, существует ли сертификат
if [ ! -f "/etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem" ]; then
    echo "SSL certificate not found. Obtaining one..."

    # Запрашиваем сертификат в тестовом режиме (можно убрать --staging для продакшена)
    certbot certonly --nginx -d $DOMAIN_NAME --email $EMAIL --agree-tos --no-eff-email --non-interactive
fi

# Запускаем Nginx в фоновом режиме
nginx -g 'daemon off;' &

# Запускаем цикл обновления сертификатов
while :; do
    sleep 12h
    echo "Renewing SSL certificate..."
    certbot renew --quiet
    # Перезагружаем Nginx, чтобы он подхватил новые сертификаты
    nginx -s reload
done
