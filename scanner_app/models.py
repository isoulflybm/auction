from django.db import models
from decimal import Decimal
from django.utils import timezone
import datetime

# --- New models for location ---

class Region(models.Model):
    """Модель для областей (регионов), например, Ошская область, Чуйская область."""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название области/региона")

    class Meta:
        verbose_name = "Область/Регион"
        verbose_name_plural = "Области/Регионы"
        ordering = ['name']

    def __str__(self):
        return self.name

class City(models.Model):
    """Модель для городов, например, Бишкек, Ош."""
    name = models.CharField(max_length=255, verbose_name="Название города")
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='cities',
        verbose_name="Область/Регион"
    )

    class Meta:
        unique_together = ('name', 'region')
        verbose_name = "Город"
        verbose_name_plural = "Города"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.region.name})"

class District(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название района")
    # Город, к которому принадлежит район (опционально, т.к. может быть район области)
    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        related_name='districts',
        verbose_name="Город",
        null=True, blank=True # Вот это важно!
    )
    # Область, к которой принадлежит район (нужно для районов области)
    region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        related_name='districts',
        verbose_name="Область/Регион",
        null=True, blank=True
    )

    class Meta:
        unique_together = ('name', 'city')
        verbose_name = "Район"
        verbose_name_plural = "Районы"
        ordering = ['name']

    def __str__(self):
        # 1. Сначала проверяем город (для районов внутри городов, например, Бишкек)
        if self.city:
            return f"{self.name} (г. {self.city.name})"
        
        # 2. Если города нет, проверяем область (для сельских районов)
        elif self.region:
            return f"{self.name} ({self.region.name})"
            
        # 3. На случай, если (вдруг) нет ни того, ни другого
        return self.name

class Category(models.Model):
    name_ru = models.CharField(max_length=255, unique=True, verbose_name="Название категории (RU)")
    name_kg = models.CharField(max_length=255, unique=True, verbose_name="Название категории (KG)")

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name_ru

class Status(models.Model):
    name_ru = models.CharField(max_length=255, unique=True, verbose_name="Название статуса (RU)")
    name_kg = models.CharField(max_length=255, unique=True, verbose_name="Название статуса (KG)")

    class Meta:
        verbose_name = "Статус"
        verbose_name_plural = "Статусы"

    def __str__(self):
        return self.name_ru

# --- Lot Model ---
class Lot(models.Model):
    lot_id = models.IntegerField(unique=True, db_index=True, verbose_name="ID лота на источнике", primary_key=True)
    title = models.CharField(max_length=1023, verbose_name="Заголовок")
    description = models.TextField(max_length=4095, verbose_name="Описание", blank=True, null=True)
    base_price = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Стартовая цена")
    start_date = models.DateTimeField(verbose_name="Дата начала торгов", null=True, blank=True)
    end_date = models.DateTimeField(verbose_name="Дата окончания торгов", null=True, blank=True)
    announcement_date = models.DateTimeField(verbose_name="Дата публикации", null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='lots')
    status = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True, related_name='lots')
    court_name = models.CharField(max_length=1023, verbose_name="Название суда/исполнительного органа", blank=True, null=True)
    trade_type = models.CharField(max_length=255, verbose_name="Тип торгов", blank=True, null=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name='lots')
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='lots')
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name='lots')
    is_favorite = models.BooleanField(default=False)
    app_status = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def _get_area_data(self):
        """Внутренний метод для поиска и парсинга площади из связанных данных."""
        
        # Категории, для которых имеет смысл показывать площадь
        AREA_CATEGORIES = (43, 58, 64, 65, 66)
        if not self.category or self.category.id not in AREA_CATEGORIES:
            return None, None, None

        # Ищем площадь в разных полях
        area_keys = ['total_area', 'land_plot', 'square', 'living_area']
        area_data_item = self.data_items.filter(item__in=area_keys).first()

        if not area_data_item or not area_data_item.value:
            return None, None, None

        area_string = area_data_item.value.lower()
        
        # Ищем число и единицу измерения (кв.м, га, соток)
        match = re.search(r'([\d\.,\s]+)\s*(кв\.м|м2|га|гектар|соток)', area_string)
        if not match:
            return None, None, None

        try:
            value_str = match.group(1).replace(',', '.').replace(' ', '')
            value = Decimal(value_str)
            unit = match.group(2)
            return value, unit, area_data_item.name_ru
        except (ValueError, TypeError):
            return None, None, None

    @property
    def display_area(self):
        """Возвращает отформатированную строку с площадью, если это применимо."""
        value, unit, name_ru = self._get_area_data()
        if value and unit:
            return f"{name_ru}: {value} {unit}"
        return ""

    @property
    def unit_price(self):
        """Рассчитывает и возвращает удельную стоимость за кв.м. или гектар."""
        value, unit, _ = self._get_area_data()
        if not value or not self.base_price or value == 0:
            return ""

        price = self.base_price
        area_in_sq_meters = value

        if unit in ['га', 'гектар']:
            area_in_sq_meters = value * 10000
        elif unit == 'соток':
            area_in_sq_meters = value * 100

        if area_in_sq_meters == 0:
            return ""

        price_per_sq_meter = round(price / area_in_sq_meters, 2)

        # Если площадь большая, покажем цену за гектар
        if area_in_sq_meters >= 10000:
            price_per_hectare = round(price / (area_in_sq_meters / 10000), 2)
            return f"{price_per_hectare:,.2f} сом/га".replace(',', ' ')
        else:
            return f"{price_per_sq_meter:,.2f} сом/м²".replace(',', ' ')


    class Meta:
        verbose_name = "Лот"
        verbose_name_plural = "Лоты"
        ordering = ['-announcement_date']

    def __str__(self):
        return f"Лот #{self.lot_id} - {self.title}"

# --- Dependent Models ---
class Images(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='images', to_field='lot_id')
    src = models.CharField(max_length=255, default='')
    thumbnail = models.CharField(max_length=255, default='')

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"

    def __str__(self):
        return f"Изображение для лота {self.lot.lot_id}"

class Data(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='data_items', to_field='lot_id')
    item = models.CharField(max_length=255, default='')
    name_ru = models.CharField(max_length=255, default='')
    name_kg = models.CharField(max_length=255, default='')
    value = models.TextField(max_length=4095, default='')

    class Meta:
        verbose_name = "Дополнительные данные"
        verbose_name_plural = "Дополнительные данные"
        unique_together = ('lot', 'item')

    def __str__(self):
        return f"{self.name_ru}: {self.value}"

class Rates(models.Model):
    currency = models.CharField(max_length=10, unique=True, default='')
    value = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('1.00000'))
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Курс валюты"
        verbose_name_plural = "Курсы валют"

    def __str__(self):
        return f"{self.currency}: {self.value}"

class AvailableActions(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='available_actions', to_field='lot_id', null=True, blank=True)
    name_ru = models.CharField(max_length=255, verbose_name="Название действия (RU)")
    name_kg = models.CharField(max_length=255, verbose_name="Название действия (KG)")
    action_type = models.CharField(max_length=255, verbose_name="Тип действия", default='')
    url = models.CharField(max_length=1023, verbose_name="Ссылка действия", default='')

    class Meta:
        verbose_name = "Доступное действие"
        verbose_name_plural = "Доступные действия"

    def __str__(self):
        return f"{self.name_ru} для лота {self.lot.lot_id if self.lot else 'N/A'}"
