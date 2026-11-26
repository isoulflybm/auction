from django.apps import AppConfig

class ScannerAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scanner_app'
    scan_url = 'https://portal.sot.kg/api/v1/lot/'
    auction_url = 'https://portal.sot.kg/auction/'
    bank_url = 'https://www.nbkr.kg/XML/daily.xml'
    default_currency = 'USD'
    areas_category_ids = (64, 65, 66)
    houses_category_ids = (43, 58)
    sqm_to_ha_threshold = 1000 # Пороговое значение в м2, ниже которого предполагаем м2 для конвертации в га
    data_items = ('total_area', 'living_area', 'land_plot', 'square') # Это именно то, что нужно!
    rates_flags = {
        'USD': 'US',
        'EUR': 'FM',
        'CNY': 'CN',
        'KZT': 'KZ',
        'RUB': 'RU',
        'KGS': 'KG',
    }
    # Валюта по умолчанию (если у вас есть такая настройка)
    default_currency = 'KGS' # Должен быть в rates_flags
    # --- ВОТ ЭТОТ АТРИБУТ НУЖНО ДОБАВИТЬ (ИЛИ ПРОВЕРИТЬ, ЧТО ОН ЕСТЬ) ---
    available_currencies = list(rates_flags.keys()) # ['KGS', 'USD', 'EUR', 'RUB', 'KZT']
    initial_visible_data_fields = [
        'vehicle_brand',      # Марка автомобиля (видимо сразу)
        'vehicle_model',      # Модель автомобиля (видимо сразу)
        'year_of_issue',      # Год выпуска (видимо сразу)
        # Добавьте сюда другие поля, которые вы хотите ВСЕГДА отображать СРАЗУ, независимо от типа лота.
    ]
    hidden_data_fields_toggle_button = [
        'obj_address',            # Адрес объекта (для недвижимости)
        'total_area',             # Общая площадь (для недвижимости)
        'land_plot',              # Площадь участка (для недвижимости)
        'living_area',            # Жилая площадь (для недвижимости)
        'document_number',        # Номер документа (для недвижимости/транспорта)
        'intended_purpose',       # Целевое назначение (для недвижимости)
        'dateRegistration_estate',# Дата регистрации (для недвижимости)
        'eni_code',               # Код ЕНИ
        'color',                  # Цвет автомобиля
        'vin_code',               # VIN-код автомобиля
        'fuel_type',              # Тип топлива автомобиля
        'state_number',           # Государственный номер автомобиля
        'engine_capacity',        # Объем двигателя автомобиля
        # Добавьте сюда другие поля, которые должны быть СКРЫТЫ и отображаться ТОЛЬКО при нажатии кнопки "Показать все".
    ]
