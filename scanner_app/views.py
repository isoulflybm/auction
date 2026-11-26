import sys
import pprint
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.apps import apps
from django.db.models import Q
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import re
from django.db.models import F
#from django.utils import timezone
from datetime import datetime, timezone, timedelta
import json
from django.template.loader import render_to_string # Импортируем рендер в строку
from django.http import JsonResponse # Импортируем JsonResponse
from urllib.parse import quote_plus, unquote_plus

# Настройка логирования (если нет глобальной настройки в settings.py)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

from scanner_app.models import Lot, Category, Status, AvailableActions, Images, Data, Rates, Region, City, District
    
def parse_area_with_units(area_str):
    """
    Продвинутый парсер площади. Ищет число и единицы измерения (га, сотка).
    Возвращает площадь в квадратных метрах (Decimal) или None.
    """
    if not area_str:
        return None
    cleaned_str = str(area_str).replace(',', '.').strip()
    match = re.search(r'(\d+\.?\d*)', cleaned_str)
    if not match:
        return None
    try:
        value = Decimal(match.group(1))
    except InvalidOperation:
        return None
    lower_str = cleaned_str.lower()
    if 'га' in lower_str or 'гектар' in lower_str:
        return value * 10000
    elif 'сот' in lower_str:
        return value * 100
    return value
    
def get_filtered_lots(request_params, app_config):
    """
    Универсальная функция фильтрации, которая работает и с QueryDict (от request.GET),
    и с обычным dict (от current_filters).
    """
    lots = Lot.objects.select_related(
        'category', 'status', 'region', 'city', 'district'
    ).prefetch_related('images', 'data_items').all()
    
    # --- Извлекаем параметры универсальным способом ---
    title = request_params.get('title', '').strip()
    category_id = request_params.get('category', '0')
    status_id = request_params.get('status', '0')
    date_from_str = request_params.get('date_from', '')
    date_to_str = request_params.get('date_to', '')
    price_from_str = request_params.get('price_from', '')
    price_to_str = request_params.get('price_to', '')
    sort_by = request_params.get('sort_by', 'announcement_date')
    sort_direction = request_params.get('sort_direction', 'desc')
    current_currency = request_params.get('currency', app_config.default_currency)
    repeat_auction_status = request_params.get('repeat_auction', 'all')

    # ✅ ГЛАВНОЕ ИСПРАВЛЕНИЕ: Проверяем, есть ли у объекта метод .getlist()
    if hasattr(request_params, 'getlist'):
        # Если это QueryDict, используем .getlist()
        selected_regions = request_params.getlist('region')
        selected_cities = request_params.getlist('city')
        selected_districts = request_params.getlist('district')
    else:
        # Если это обычный словарь, используем .get()
        selected_regions = request_params.get('region', [])
        selected_cities = request_params.get('city', [])
        selected_districts = request_params.get('district', [])
    
    # --- Применяем фильтры ---
    if repeat_auction_status == 'yes':
        lots = lots.filter(title__icontains='повторный')
    elif repeat_auction_status == 'no':
        lots = lots.exclude(title__icontains='повторный')

    if title:
        lots = lots.filter(Q(title__icontains=title) | Q(data_items__value__icontains=title)).distinct()

    if category_id and category_id != '0':
        try:
            lots = lots.filter(category__id=int(category_id))
        except (ValueError, TypeError):
            pass

    if status_id and status_id != '0':
        try:
            lots = lots.filter(status__id=int(status_id))
        except (ValueError, TypeError):
            pass
            
    if selected_regions:
        region_ids = [r_id for r_id in selected_regions if r_id and r_id.isdigit()]
        if region_ids:
            lots = lots.filter(region__id__in=region_ids)
            
    if selected_cities:
        city_ids = [c_id for c_id in selected_cities if c_id and c_id.isdigit()]
        if city_ids:
            lots = lots.filter(city__id__in=city_ids)

    if selected_districts:
        district_ids = [d_id for d_id in selected_districts if d_id and d_id.isdigit()]
        if district_ids:
            lots = lots.filter(district__id__in=district_ids)

    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            lots = lots.filter(announcement_date__gte=date_from)
        except ValueError:
            pass

    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            lots = lots.filter(announcement_date__lte=date_to)
        except ValueError:
            pass

    base_currency_rate = Decimal('1.0')
    try:
        if current_currency and current_currency != app_config.default_currency:
            rate_obj = Rates.objects.get(currency=current_currency)
            base_currency_rate = rate_obj.value
    except Rates.DoesNotExist:
        pass # Используем 1.0, если курс не найден

    if price_from_str:
        try:
            price_from = Decimal(price_from_str)
            lots = lots.filter(base_price__gte=price_from * base_currency_rate)
        except InvalidOperation: pass

    if price_to_str:
        try:
            price_to = Decimal(price_to_str)
            lots = lots.filter(base_price__lte=price_to * base_currency_rate)
        except InvalidOperation: pass
    
    sort_by_map = {'price': 'base_price', 'date': 'announcement_date', 'title': 'title'}
    actual_sort_by_field = sort_by_map.get(sort_by, 'announcement_date')

    if sort_direction == 'desc':
        lots = lots.order_by(F(actual_sort_by_field).desc(nulls_last=True))
    else:
        lots = lots.order_by(F(actual_sort_by_field).asc(nulls_first=True))

    return lots, current_currency
    

def prepare_lots_for_display(lots_page, current_currency, app_config):
    """
    Новая функция, которая подготавливает лоты к отображению (цены, площади и т.д.).
    """
    base_currency_rate = Decimal('1.0')
    try:
        if current_currency and current_currency != app_config.default_currency:
            base_currency_rate_obj = Rates.objects.get(currency=current_currency)
            base_currency_rate = base_currency_rate_obj.value
    except Rates.DoesNotExist:
        pass

    for lot in lots_page:
        # 1. Инициализируем новые поля по умолчанию
        lot.price_per_unit = None
        lot.price_per_unit_measure = ''
        lot.is_repeat_auction = False

        # 2. Проверяем заголовок на слово "повторный"
        if 'повторный' in lot.title.lower():
            lot.is_repeat_auction = True
        
        if lot.base_price is not None:
            lot.display_price = (lot.base_price / base_currency_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            #lot.final_display_price = lot.display_price
            lot.final_display_price = "{:,.2f}".format(float(lot.display_price)).replace(",", " ")
        else:
            lot.display_price = Decimal('0.00')
            lot.final_display_price = Decimal('0.00')

        lot.current_currency_code = current_currency
        
        auction_base_url = app_config.auction_url
        if auction_base_url and hasattr(lot, 'lot_id') and lot.lot_id:
            if not auction_base_url.endswith('/'):
                auction_base_url += '/'
            lot.participate_action_url = f"{auction_base_url}{lot.lot_id}"
        else:
            lot.participate_action_url = None

        lot.display_data_initial = []
        lot.display_data_hidden = []
        lot.address_display = "Не указан"
        lot.square_value_display = "Не указана"

        address_data = lot.data_items.filter(item='obj_address').first()
        if address_data and address_data.value:
            lot.address_display = address_data.value

        # --- Продвинутый расчет площади и удельной стоимости ---
        square_data = None
        # Ищем данные о площади в полях, указанных в конфиге
        for item_name in getattr(app_config, 'data_items', []):
            current_square_data = lot.data_items.filter(item=item_name).first()
            if current_square_data and current_square_data.value:
                square_data = current_square_data
                break # Нашли первое непустое значение, выходим

        # Расчет площади и удельной стоимости
        square_data = None
        for item_name in getattr(app_config, 'data_items', []):
            current_square_data = lot.data_items.filter(item=item_name).first()
            if current_square_data and current_square_data.value:
                square_data = current_square_data
                break

        if square_data:
            area_in_sqm = parse_area_with_units(square_data.value)

            if area_in_sqm is not None and area_in_sqm > 0 and lot.display_price > 0:
                try:
                    original_unit_str = square_data.value.lower()

                    # Вариант 1: Если в строке есть ГЕКТАРЫ
                    if 'га' in original_unit_str or 'гектар' in original_unit_str:
                        area_in_ha = area_in_sqm / Decimal('10000')
                        lot.square_value_display = f"{area_in_ha.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)} га"
                        lot.price_per_unit_data = (lot.display_price / area_in_ha).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        lot.price_per_unit = "{:,.2f}".format(float(lot.price_per_unit_data)).replace(",", " ")
                        lot.price_per_unit_measure = '/ га'
                    
                    # Вариант 2: Если в строке есть СОТКИ
                    elif 'сот' in original_unit_str:
                        area_in_sotka = area_in_sqm / Decimal('100')
                        lot.square_value_display = f"{area_in_sotka.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} сот."
                        lot.price_per_unit_data = (lot.display_price / area_in_sotka).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        lot.price_per_unit = "{:,.2f}".format(float(lot.price_per_unit_data)).replace(",", " ")
                        lot.price_per_unit_measure = '/ сот.'

                    # Вариант 3: Все остальное считаем КВАДРАТНЫМИ МЕТРАМИ
                    else:
                        lot.square_value_display = f"{area_in_sqm.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} м²"
                        lot.price_per_unit_data = (lot.display_price / area_in_sqm).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        lot.price_per_unit = "{:,.2f}".format(float(lot.price_per_unit_data)).replace(",", " ")
                        lot.price_per_unit_measure = '/ м²'

                except (InvalidOperation, ZeroDivisionError) as e:
                    logging.error(f"Ошибка при расчете удельной цены для лота {lot.lot_id}: {e}")
                    lot.square_value_display = square_data.value
            
            elif area_in_sqm is not None:
                lot.square_value_display = f"{area_in_sqm.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} м²"

            else:
                lot.square_value_display = square_data.value

        # --- Конец блока расчета площади ---

        for data_item in lot.data_items.all():
            # Пропускаем дублирование информации о площади, если она уже обработана
            if square_data and data_item.item == square_data.item:
                continue

            initial_visible_data_fields = getattr(app_config, 'initial_visible_data_fields', [])
            hidden_data_fields_toggle_button = getattr(app_config, 'hidden_data_fields_toggle_button', [])

            if data_item.item in initial_visible_data_fields:
                lot.display_data_initial.append(data_item)
            elif data_item.item in hidden_data_fields_toggle_button:
                lot.display_data_hidden.append(data_item)
            else:
                lot.display_data_initial.append(data_item)

        def sort_key_initial(data_obj):
            initial_visible_data_fields = getattr(app_config, 'initial_visible_data_fields', [])
            if data_obj.item in initial_visible_data_fields:
                return initial_visible_data_fields.index(data_obj.item)
            return len(initial_visible_data_fields)

        def sort_key_hidden(data_obj):
            hidden_data_fields_toggle_button = getattr(app_config, 'hidden_data_fields_toggle_button', [])
            if data_obj.item in hidden_data_fields_toggle_button:
                return hidden_data_fields_toggle_button.index(data_obj.item)
            return len(hidden_data_fields_toggle_button)

        lot.display_data_initial.sort(key=sort_key_initial)
        lot.display_data_hidden.sort(key=sort_key_hidden)
    
    return lots_page


# Главная функция представления
def index(request):
    app_config = apps.get_app_config('scanner_app')

    list_params = ['region', 'city', 'district']
    filter_params_defaults = {
        'title': '', 'category': '0', 'status': '0', 'date_from': '', 'date_to': '',
        'price_from': '', 'price_to': '', 'sort_by': 'announcement_date',
        'sort_direction': 'desc', 'currency': app_config.default_currency,
        'page': '1', 'region': [], 'city': [], 'district': [], 'repeat_auction': 'all',
    }

    current_filters = {}
    # Определяем ключи, которые означают применение фильтра
    filter_keys = {
        'title', 'category', 'status', 'date_from', 'date_to', 'price_from', 
        'price_to', 'region', 'city', 'district', 'repeat_auction', 
        'sort_by', 'sort_direction', 'currency', 'page'
    }
    # Считаем отправкой формы, если в URL есть хотя бы один из этих ключей
    is_form_submission = any(key in request.GET for key in filter_keys)

    # Шаг 1: Формируем фильтры из URL или Cookie
    for param, default_value in filter_params_defaults.items():
        if param in request.GET:
            if param in list_params:
                current_filters[param] = request.GET.getlist(param)
            else:
                current_filters[param] = request.GET.get(param)
        else:
            cookie_name = f'filter_{param}'
            cookie_val = request.COOKIES.get(cookie_name)
            if cookie_val:
                if param in list_params:
                    try: current_filters[param] = json.loads(cookie_val)
                    except json.JSONDecodeError: current_filters[param] = default_value
                else:
                    current_filters[param] = unquote_plus(cookie_val)
            else:
                current_filters[param] = default_value

    # Шаг 2: Получаем отфильтрованные данные (эта часть у вас работает)
    lots, current_currency = get_filtered_lots(current_filters, app_config)

    # Шаг 3: Получаем данные для сайдбара
    categories = Category.objects.all()
    statuses = Status.objects.all()
    rates = Rates.objects.all()
    regions = Region.objects.all()
    cities = City.objects.all()
    districts = District.objects.all()

    # Шаг 4: Пагинация
    paginator = Paginator(lots, 9)
    page_number = current_filters.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Шаг 5: Подготовка лотов к отображению
    prepared_lots = prepare_lots_for_display(page_obj.object_list, current_currency, app_config)
    page_obj.object_list = prepared_lots

    # ✅ КЛЮЧЕВОЙ МОМЕНТ: Готовим переменные для контекста
    try:
        category_id = int(current_filters.get('category', 0))
    except (ValueError, TypeError):
        category_id = 0
    try:
        status_id = int(current_filters.get('status', 0))
    except (ValueError, TypeError):
        status_id = 0
    if not status_id and len(statuses):
        status_id = statuses[0].id

    # ✅ УБЕДИТЕСЬ, ЧТО ВАШ СЛОВАРЬ `data` ВЫГЛЯДИТ ИМЕННО ТАК
    data = {
        'page_obj': page_obj, 'categories': categories, 'statuses': statuses, 'rates': rates,
        'regions': regions, 'cities': cities, 'districts': districts,
        
        # Передаем все значения из `current_filters` в шаблон под нужными именами
        'title': current_filters.get('title', ''),
        'category_id': category_id,
        'status_id': status_id,
        'date_from': current_filters.get('date_from', ''),
        'date_to': current_filters.get('date_to', ''),
        'price_from': current_filters.get('price_from', ''),
        'price_to': current_filters.get('price_to', ''),
        'sort_by': current_filters.get('sort_by', 'announcement_date'),
        'sort_direction': current_filters.get('sort_direction', 'desc'),
        'repeat_auction': current_filters.get('repeat_auction', 'all'),
        'current_currency': current_currency,
        
        'selected_regions': current_filters.get('region', []),
        'selected_cities': current_filters.get('city', []),
        'selected_districts': current_filters.get('district', []),
    }
    
    print("--- START DATA DUMP ---", file=sys.stderr)
    pprint.pprint(data, stream=sys.stderr)
    print("--- END DATA DUMP ---", file=sys.stderr)

    # Шаг 7: Рендерим ответ и устанавливаем cookie
    response = render(request, 'html/front-pages/online-auction.html', data)
    
# Шаг 8: Если пользователь отправил форму, прикрепляем cookie к готовому ответу
    if is_form_submission:
        for param, value in current_filters.items():
            cookie_name = f'filter_{param}'
            # The "if param == 'page':" block has been removed.
            
            if isinstance(value, list):
                cleaned_value = [item for item in value if item]
                response.set_cookie(
                    cookie_name,
                    json.dumps(cleaned_value),
                    max_age=30*24*60*60,
                    samesite='Lax',
                    secure=True
                )
            else:
                encoded_value = quote_plus(str(value))
                response.set_cookie(
                    cookie_name,
                    encoded_value,
                    max_age=30*24*60*60,
                    samesite='Lax',
                    secure=True
                )
                
    return response


def load_lots_api(request):
    """
    API для динамической подгрузки.
    Возвращает HTML для лотов и для пагинации.
    """
    app_config = apps.get_app_config('scanner_app')
    lots, current_currency = get_filtered_lots(request.GET, app_config)
    
    paginator = Paginator(lots, 9)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    prepared_lots = prepare_lots_for_display(page_obj.object_list, current_currency, app_config)

    # 1. Рендерим в строку список лотов (это у вас уже есть)
    lots_html = render_to_string(
        'html/partials/_lot_list_partial.html',
        {'page_obj': prepared_lots}
    )

    # 2. ✅ НОВОЕ: Рендерим в строку обновленный блок пагинации
    pagination_html = render_to_string(
        'html/includes/pagination.html',
        {'page_obj': page_obj} # Передаем весь page_obj, чтобы пагинация знала о страницах
    )

    # 3. ✅ НОВОЕ: Возвращаем оба HTML-фрагмента в JSON-ответе
    return JsonResponse({
        'html': lots_html,
        'pagination_html': pagination_html, # Добавляем новый ключ
        'has_next': page_obj.has_next()
    })
