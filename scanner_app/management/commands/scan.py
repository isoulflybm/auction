import json
import logging
import requests
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.db import transaction
import xml.etree.ElementTree as ET

# Импорт моделей
from scanner_app.models import (
    Lot, Category, Status, Region, City, District, 
    Images, Data, Rates
)

# Импорт наших помощников
from .locations import KYRGYZSTAN_GEO
from .ai_helper import get_clean_location

class Command(BaseCommand):
    help = 'Универсальный сканер: файлы, тест или полный проход по сайту'

    def add_arguments(self, parser):
        # Флаг для загрузки из JSON файла
        parser.add_argument(
            '--json', 
            type=str, 
            nargs='?', 
            const='sot_kg_data.json', 
            help='Путь к JSON файлу (по умолчанию sot_kg_data.json)'
        )
        
        # Флаг для быстрого теста (1 страница)
        parser.add_argument(
            '--scan', 
            action='store_true', 
            help='Тестовый прогон: сканирует только первую страницу сайта'
        )

        # Флаг для полного сканирования
        parser.add_argument(
            '--full-scan', 
            action='store_true', 
            help='Полное сканирование: проходит по всем страницам сайта'
        )

        # НОВЫЙ ФЛАГ: ОЧИСТКА
        parser.add_argument(
            '--clean', 
            action='store_true', 
            help='!!! ОПАСНО: Удаляет ВСЕ лоты и географию перед запуском !!!'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- ЗАПУСК СИСТЕМЫ ---'))
        
        # 1. Если есть флаг --clean, чистим базу
        if options['clean']:
            self.wipe_database()

        # 2. Восстанавливаем эталонную географию (даже если почистили)
        self.init_geo_db()
        
        # 3. Выбираем режим работы
        if options['full_scan']:
            self.stdout.write(self.style.WARNING('>>> РЕЖИМ: FULL SCAN (ВЕСЬ САЙТ)'))
            self.scan_web(full=True)
            
        elif options['scan']:
            self.stdout.write(self.style.WARNING('>>> РЕЖИМ: TEST SCAN (1 СТРАНИЦА)'))
            self.scan_web(full=False)
            
        elif options['json']:
            filename = options['json']
            self.stdout.write(self.style.WARNING(f'>>> РЕЖИМ: ИМПОРТ ИЗ ФАЙЛА ({filename})'))
            self.import_from_json(filename)
            
        else:
            self.stdout.write(self.style.WARNING('>>> Аргументы не указаны. Пробую найти sot_kg_data.json...'))
            self.import_from_json('sot_kg_data.json')

        # 4. Финализация (валюты)
        self.update_rates()
        self.stdout.write(self.style.SUCCESS('--- РАБОТА ЗАВЕРШЕНА ---'))

    def wipe_database(self):
        """Полная очистка оперативных данных."""
        self.stdout.write(self.style.ERROR("!!! ЗАПУЩЕНА ОЧИСТКА БАЗЫ ДАННЫХ !!!"))
        
        with transaction.atomic():
            # Удаляем Лоты (каскадно удалятся Images, Data, AvailableActions)
            count_lots, _ = Lot.objects.all().delete()
            self.stdout.write(f"  -> Удалено лотов: {count_lots}")
            
            # Удаляем Географию (чтобы убрать дубликаты типа 'г.Бишкек')
            # Порядок важен: сначала Районы, потом Города, потом Регионы
            District.objects.all().delete()
            City.objects.all().delete()
            Region.objects.all().delete()
            self.stdout.write("  -> География полностью очищена.")
            
            # Категории и Статусы можно оставить, они не мешают, или раскомментируй:
            # Category.objects.all().delete()
            # Status.objects.all().delete()
            
        self.stdout.write(self.style.SUCCESS("--- База данных девственно чиста ---"))

    def init_geo_db(self):
        """Создает эталонную структуру регионов."""
        self.stdout.write("Инициализация эталонной географии...")
        with transaction.atomic():
            for region_name, data in KYRGYZSTAN_GEO.items():
                region_obj, _ = Region.objects.get_or_create(name=region_name)
                
                if data.get('is_capital'):
                    city_obj, _ = City.objects.get_or_create(name=region_name, region=region_obj)
                    for dist_name in data.get('districts', []):
                        District.objects.get_or_create(name=dist_name, city=city_obj)
                else:
                    for city_name in data.get('cities', []):
                        City.objects.get_or_create(name=city_name, region=region_obj)
                    for dist_name in data.get('districts', []):
                        District.objects.get_or_create(name=dist_name, region=region_obj)

    def import_from_json(self, filename):
        """Логика для файла."""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                items = data.get('items', []) if isinstance(data, dict) else data
                self.process_batch(items)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Файл {filename} не найден!"))

    def scan_web(self, full=False):
        """Логика для сайта."""
        base_url = 'https://portal.sot.kg/api/v1/lot/'
        page = 1
        address_cache = {}

        while True:
            url = f"{base_url}?page={page}&limit=20"
            self.stdout.write(f"Скачивание страницы {page}...")
            
            try:
                response = requests.get(url, timeout=30)
                if response.status_code != 200:
                    self.stdout.write(self.style.ERROR(f"Ошибка сервера: {response.status_code}"))
                    break
                
                data = response.json()
                items = data.get('items', [])
                
                if not items:
                    self.stdout.write("Лоты закончились.")
                    break

                self.process_batch(items, address_cache)

                if not full:
                    break
                
                page += 1
                time.sleep(1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Сетевая ошибка: {e}"))
                break

    def process_batch(self, lots_list, address_cache=None):
        if address_cache is None: address_cache = {}

        for item in lots_list:
            lot_id = item.get('id')
            if not lot_id: continue
            
            try:
                cat_data = item.get('category') or {}
                category, _ = Category.objects.get_or_create(
                    id=cat_data.get('id'),
                    defaults={'name_ru': cat_data.get('name_ru', 'N/A'), 'name_kg': cat_data.get('name_kg', 'N/A')}
                )
                stat_data = item.get('status') or {}
                status, _ = Status.objects.get_or_create(
                    id=stat_data.get('id'),
                    defaults={'name_ru': stat_data.get('name_ru', 'N/A'), 'name_kg': stat_data.get('name_kg', 'N/A')}
                )

                lot, created = Lot.objects.update_or_create(
                    lot_id=lot_id,
                    defaults={
                        'title': item.get('title', '')[:1000],
                        'description': item.get('description', '')[:4000] if item.get('description') else None,
                        'base_price': item.get('base_price', 0),
                        'start_date': parse_datetime(item.get('start_date')),
                        'end_date': parse_datetime(item.get('end_date')),
                        'announcement_date': parse_datetime(item.get('announcement_date')),
                        'category': category,
                        'status': status,
                        'court_name': item.get('court_name'),
                        'trade_type': item.get('trade_type'),
                        'app_status': item.get('app_status'),
                        'is_favorite': item.get('is_favorite', False)
                    }
                )

                if 'images' in item:
                    lot.images.all().delete()
                    for img in item.get('images', []):
                        Images.objects.create(lot=lot, src=img.get('src', ''), thumbnail=img.get('thumbnail', ''))

                lot.data_items.all().delete()
                raw_data = item.get('data', {})
                address_to_check = None

                for key, val in raw_data.items():
                    if isinstance(val, dict):
                        Data.objects.create(
                            lot=lot, item=key,
                            name_ru=val.get('name_ru', ''),
                            name_kg=val.get('name_kg', ''),
                            value=str(val.get('value', ''))[:4000]
                        )
                        if key == 'obj_address':
                            address_to_check = val.get('value', '')

                if address_to_check:
                    self.resolve_location(lot, address_to_check, address_cache)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Ошибка лота {lot_id}: {e}"))

    def resolve_location(self, lot, raw_address, cache):
        if raw_address in cache:
            geo = cache[raw_address]
        else:
            self.stdout.write(f"    [AI] Анализ: {raw_address[:30]}...")
            geo = get_clean_location(raw_address, KYRGYZSTAN_GEO.keys())
            cache[raw_address] = geo
            time.sleep(0.1) 

        if not geo: return

        try:
            if geo.get('region'):
                lot.region = Region.objects.filter(name__icontains=geo['region']).first()
            
            if geo.get('city') and lot.region:
                lot.city = City.objects.filter(name__icontains=geo['city'], region=lot.region).first()
            
            if geo.get('district'):
                d_name = geo['district']
                dist = None
                if lot.city:
                    dist = District.objects.filter(name__icontains=d_name, city=lot.city).first()
                if not dist and lot.region:
                    dist = District.objects.filter(name__icontains=d_name, region=lot.region).first()
                lot.district = dist
            
            lot.save()
        except Exception as e:
            print(f"DB Error: {e}")

    def update_rates(self):
        """Загружает курсы валют с НБКР."""
        self.stdout.write("--- Обновление курсов валют (НБКР) ---")
        url = "https://www.nbkr.kg/XML/daily.xml"
        
        # Гарантируем, что родной Сом всегда есть
        Rates.objects.update_or_create(currency='KGS', defaults={'value': Decimal('1.00000')})

        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            target_currencies = ['USD', 'EUR', 'RUB', 'KZT', 'CNY']
            
            for currency in root.findall('Currency'):
                iso_code = currency.get('ISOCode')
                if iso_code in target_currencies:
                    try:
                        val_str = currency.find('Value').text.replace(',', '.')
                        nominal_str = currency.find('Nominal').text
                        final_rate = Decimal(val_str) / Decimal(nominal_str)
                        
                        Rates.objects.update_or_create(currency=iso_code, defaults={'value': final_rate})
                        self.stdout.write(f"  -> {iso_code}: {final_rate}")
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"Ошибка парсинга {iso_code}: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Не удалось обновить курсы: {e}"))
