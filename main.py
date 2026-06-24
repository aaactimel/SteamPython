import requests
import time
import schedule
import threading
import json
import os
import html
import random

# ==========================================
# НАСТРОЙКИ (CONFIG)
# ==========================================
TELEGRAM_BOT_TOKEN = '8306504258:AAGrO_wU4s870QdSoQ9l_-fGaiwSZyQXrlM'
TELEGRAM_CHAT_ID = '-1004417015680' # Или числовой ID, например -100123456789
CHEAPSHARK_API_URL = 'https://www.cheapshark.com/api/1.0/deals?storeID=1&onSale=1'

# Файл, куда будем сохранять ID уже опубликованных скидок,
# чтобы при перезапуске скрипта бот не спамил старыми играми.
SEEN_DEALS_FILE = 'seen_deals.json'

# ==========================================
# БАЗА ДАННЫХ (КЭШ)
# ==========================================
def load_seen_deals():
    """Загружает список уже отправленных игр из файла."""
    if os.path.exists(SEEN_DEALS_FILE):
        with open(SEEN_DEALS_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_seen_deals(seen_set):
    """Сохраняет список отправленных игр в файл."""
    with open(SEEN_DEALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(seen_set), f)

# Инициализируем наш кэш при старте
seen_deals = load_seen_deals()

# ==========================================
# ЛОГИКА ФОРМАТИРОВАНИЯ И ОТПРАВКИ
# ==========================================
def get_rating_emoji(rating_text):
    """Подбирает эмодзи в зависимости от текста отзывов."""
    if not rating_text:
        return "🤍" # Если отзывов нет
    
    text_lower = rating_text.lower()
    if "overwhelmingly positive" in text_lower or "very positive" in text_lower:
        return "💙"
    elif "mostly positive" in text_lower:
        return "💚"
    elif "mixed" in text_lower:
        return "💛"
    elif "mostly negative" in text_lower:
        return "🧡"
    elif "very negative" in text_lower or "overwhelmingly negative" in text_lower:
        return "💔"
    return "🤍" # Фолбэк для нестандартных значений

def send_telegram_message(text):
    """Отправляет отформатированное сообщение в Телеграм."""
    # Защитная проверка: если текста нет, даже не шлем запрос
    if not text or not text.strip():
        print("[WARN] Попытка отправить пустое сообщение заблокирована.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        # Выводим подробности ответа Телеграма, чтобы понять, что не так с текстом
        print(f"[ERROR] Ошибка API Телеграма: {http_err}")
        print(f"[DEBUG] Сервер вернул: {response.text}")
    except Exception as e:
        print(f"[ERROR] Ошибка отправки в Телеграм: {e}")

def check_deals():
    """Стучится в CheapShark, парсит JSON и рассылает новые скидки."""
    print("[INFO] Проверяю новые скидки...")
    try:
        response = requests.get(CHEAPSHARK_API_URL, timeout=10)
        response.raise_for_status()
        deals = response.json()
    except Exception as e:
        print(f"[ERROR] Не удалось достучаться до API: {e}")
        return

    new_deals_count = 0

    for deal in deals:
        deal_id = deal.get("dealID")
        
        if deal_id in seen_deals:
            continue
            
        # Безопасно вытаскиваем строки и сразу экранируем их от злых спецсимволов HTML
        title = html.escape(deal.get("title", "Неизвестная игра"))
        rating_text = html.escape(deal.get("steamRatingText", "Нет отзывов"))
        
        normal_price = deal.get("normalPrice", "0")
        sale_price = deal.get("salePrice", "0")
        
        try:
            savings = int(float(deal.get("savings", 0)))
        except (ValueError, TypeError):
            savings = 0
        
        rating_percent = deal.get("steamRatingPercent", "0")
        rating_count = deal.get("steamRatingCount", "0")
        app_id = deal.get("steamAppID")

        if not app_id:
            continue

        emoji = get_rating_emoji(rating_text)
        
        # Собираем строку
        msg = (
            f"💎 <b>{title}</b> <s>${normal_price}</s> -> ${sale_price} ({savings}%)\n"
            f"{emoji} {rating_text} ({rating_percent}% / {rating_count} оценок)\n\n"
            f"🧩 <a href='https://store.steampowered.com/app/{app_id}/'>Steam</a> 🔑 <a href='https://www.cheapshark.com/'>Источник</a>"
        )
        
        # Дополнительный предохранитель перед отправкой
        if msg.strip():
            send_telegram_message(msg)
            seen_deals.add(deal_id)
            new_deals_count += 1
            time.sleep(random.randint(23,30))
        else:
            print(f"[WARN] Сгенерирован пустой шаблон для deal_id: {deal_id}")

    if new_deals_count > 0:
        print(f"[SUCCESS] Отправлено новых скидок: {new_deals_count}")
        save_seen_deals(seen_deals)
    else:
        print("[INFO] Новых скидок не обнаружено.")

# ==========================================
# ПОТОКИ (THREADS) И ЗАПУСК
# ==========================================
def console_listener():
    """Слушает ввод в консоль для ручного запуска."""
    while True:
        cmd = input().strip().lower()
        if cmd == "check":
            check_deals()
        elif cmd == "exit":
            print("[INFO] Выключаюсь...")
            os._exit(0) # Жесткий выход, чтобы убить все потоки разом
        else:
            print("[INFO] Неизвестная команда. Доступны: 'check', 'exit'")

def main():
    print("[INFO] Бот запущен! Инициализирую первую проверку...")
    
    # 1. Проверяем скидки прямо при запуске
    check_deals()
    
    # 2. Настраиваем проверку каждый ровный час (:00 минут)
    schedule.every().hour.at(":00").do(check_deals)
    
    # 3. Запускаем отдельный поток для прослушивания консоли (чтобы input() не блокировал таймер)
    listener_thread = threading.Thread(target=console_listener, daemon=True)
    listener_thread.start()
    
    print("[INFO] Ожидание по расписанию... (Введи 'check' для ручного запуска)")
    
    # Бесконечный цикл, в котором крутится планировщик
    while True:
        schedule.run_pending()
        time.sleep(1) # Спим 1 секунду, чтобы не грузить процессор

if __name__ == "__main__":
    main()