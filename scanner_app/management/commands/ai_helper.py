# ai_helper.py
import requests
import json
import re
import urllib3
from requests.auth import HTTPBasicAuth

# Отключаем предупреждения SSL (так как сертификат самоподписанный/невалидный)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- НАСТРОЙКИ ---
# Точно как в твоем curl запросе
#OLLAMA_BASE_URL = "https://ollama.i7.kg/ollama"
OLLAMA_BASE_URL = "http://192.168.11.12:11434"
#AUTH = HTTPBasicAuth('admin', 'Test123456')
#AUTH_KEY = "fw_8yzj5DWktu3URZfZxRmkbm"
#MODEL = "phi3:mini"
MODEL = "qwen3:8b"

def get_clean_location(raw_address, valid_geo_keys):
    """
    Отправляет адрес в AI и просит вернуть JSON.
    Адаптировано под твой рабочий main.py.
    """
    if not raw_address or len(raw_address) < 3:
        return None

    # Промпт (Инструкция)
    system_prompt = f"""
    Ты парсер адресов JSON.
    Допустимые регионы (Region): {', '.join(valid_geo_keys)}.
    
    Твоя задача: извлечь "region", "city", "district" из текста.
    
    Правила:
    1. Верни ТОЛЬКО валидный JSON объект.
    2. Никакого текста до или после JSON.
    3. Поля: region, city, district.
    4. Если город Бишкек или Ош -> это region.
    5. Если данных нет -> null.
    """

    user_prompt = f"Адрес для разбора: {raw_address}"

    # Полный URL
    url = f"{OLLAMA_BASE_URL}/api/chat"
    
    # Payload (убрал format="json", так как в твоем main.py его нет)
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False, # Нам нужен весь ответ сразу
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096 
        }
    }

    # Заголовки как у браузера/curl
    headers = {
        "User-Agent": "ScannerBot/1.0",
        "Content-Type": "application/json",
#	"Authorization": f"Bearer {AUTH_KEY}"
    }

    try:
        # verify=False отключает проверку сертификата (как ключ -k в curl)
        response = requests.post(
            url, 
            json=payload, 
            headers=headers, 
            #auth=AUTH, 
            timeout=600, 
            verify=False
        )
        
        # --- ОТЛАДКА ПРИ ОШИБКЕ ---
        if response.status_code != 200:
            print(f"\n[AI DEBUG] ОШИБКА URL: {url}")
            print(f"[AI DEBUG] Код ответа: {response.status_code}")
            print(f"[AI DEBUG] Текст ошибки: {response.text[:500]}") # Читаем, что ответил сервер
            return None
        # ---------------------------

        result = response.json()
        content = result.get('message', {}).get('content', '{}')
        
        # Чистим ответ, если модель решила добавить Markdown (```json ... ```)
        content = clean_json_string(content)
        
        return json.loads(content)

    except Exception as e:
        print(f"[AI ERROR] Сбой запроса: {e}")
        return None

def clean_json_string(text):
    """
    Вырезает JSON объект из текста, если модель добавила лишние слова.
    Ищет текст между первой { и последней }.
    """
    try:
        # Сначала пробуем найти блок кода ```json ... ```
        match_code = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match_code:
            return match_code.group(1)
            
        # Если нет, ищем просто фигурные скобки
        match_simple = re.search(r'\{.*\}', text, re.DOTALL)
        if match_simple:
            return match_simple.group(0)
            
        return text
    except:
        return text
