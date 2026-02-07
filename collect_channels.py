"""
Скрипт сбора данных из Telegram-каналов для еженедельной сводки CPO.
Использует credentials из iamsu_mcp_tg/.env
"""

import asyncio
import json
import os
import sys
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Fix Windows console encoding for emoji
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User, MessageReplies

# Загружаем credentials
# По умолчанию из .env в директории скрипта, или из MCP-проекта как fallback
SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

if not os.getenv("TELEGRAM_API_ID"):
    # Fallback: попробовать загрузить из MCP-проекта (для локальной разработки)
    MCP_DIR = Path.home() / "Projects" / "Personal" / "iamsu_mcp_tg"
    if (MCP_DIR / ".env").exists():
        load_dotenv(MCP_DIR / ".env")

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION")

# Каналы для мониторинга — сгруппированы по категориям
CHANNELS = {
    "ota_competitors": {
        "label": "OTA-конкуренты (за бронирования)",
        "channels": [
            "yandex_travel_pro",   # Яндекс Путешествия
            "extranetetg",         # Островок
            "bronevik_com",        # Bronevik.com
        ]
    },
    "b2b_saas": {
        "label": "B2B SaaS конкуренты (за клиентов)",
        "channels": [
            "bnovonews",           # Bnovo
            "hotellab_io",         # Hotellab (revenue management)
            "otelkontur",          # Контур для отельера
            "bronirui_online",     # Бронируй Онлайн
            "uhotelsapp",          # TravelLine (свой)
        ]
    },
    "industry_news": {
        "label": "Независимые отраслевые каналы",
        "channels": [
            "wrkhotel",
            "hotel_geek",
            "russianhospitalityawards",
            "portierdenuit",
            "AZO_channel",
            "Hoteliernews",        # Новости отелей (12k подписчиков)
            "HotelierPRO",         # Hotelier.PRO — аналитика
            "frontdesk_ru",        # Сообщество профессионалов
        ]
    },
    "travelline": {
        "label": "TravelLine (свой канал — как нас видит рынок)",
        "channels": [
            "travelline_news",     # TravelLine официальный
        ]
    },
    "hotelier_chats": {
        "label": "Чаты отельеров",
        "channels": [
            "chat_hotel",
            "hotel_advisors",
            "HRSRussia",           # HRS — чат про гостиничные системы
            -1001264671967,        # TL: Беседка (приватная группа, 7516 участников)
        ]
    },
}

# Период: последние 2 недели
DAYS_BACK = 14
OUTPUT_DIR = Path(__file__).parent / "data" / datetime.now().strftime("%Y-%m-%d")


def get_entity_name(entity) -> str:
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        return " ".join(p for p in parts if p) or entity.username or str(entity.id)
    return getattr(entity, "title", None) or str(entity.id)


def format_message(msg) -> dict:
    sender_name = "Unknown"
    if msg.sender:
        sender_name = get_entity_name(msg.sender)

    # Извлекаем реакции если есть
    reactions = []
    if hasattr(msg, 'reactions') and msg.reactions:
        for r in msg.reactions.results:
            emoji = getattr(r.reaction, 'emoticon', None) or str(r.reaction)
            reactions.append({"emoji": emoji, "count": r.count})

    # Извлекаем количество комментариев/ответов
    replies_count = 0
    if hasattr(msg, 'replies') and isinstance(msg.replies, MessageReplies):
        replies_count = msg.replies.replies or 0

    # Просмотры
    views = getattr(msg, 'views', None) or 0
    forwards = getattr(msg, 'forwards', None) or 0

    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "sender": sender_name,
        "sender_id": msg.sender_id,
        "text": msg.text or "",
        "has_media": msg.media is not None,
        "views": views,
        "forwards": forwards,
        "reactions": reactions,
        "replies_count": replies_count,
    }


async def collect_channel(client: TelegramClient, identifier, since: datetime) -> dict:
    """Собрать данные из одного канала. identifier может быть username (str) или ID (int)."""
    display_name = f"@{identifier}" if isinstance(identifier, str) else f"id:{identifier}"
    print(f"  📡 Собираю: {display_name}...", end=" ", flush=True)

    try:
        entity = await client.get_entity(identifier)
    except Exception as e:
        print(f"❌ Не найден: {e}")
        return {"error": str(e), "username": str(identifier), "messages": []}

    # Информация о канале
    resolved_username = getattr(entity, "username", None) or str(identifier)
    info = {
        "id": entity.id,
        "name": get_entity_name(entity),
        "username": resolved_username,
        "type": "channel" if isinstance(entity, Channel) else "group" if isinstance(entity, Chat) else "user",
        "participants_count": getattr(entity, "participants_count", None),
    }

    # Собираем сообщения за период
    messages = []
    async for msg in client.iter_messages(entity, offset_date=datetime.now(timezone.utc), limit=None):
        if msg.date and msg.date < since:
            break
        messages.append(format_message(msg))

    print(f"✅ {len(messages)} сообщений")

    return {
        "channel_info": info,
        "messages": messages,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "period": {
            "from": since.isoformat(),
            "to": datetime.now(timezone.utc).isoformat(),
        }
    }


async def main():
    print("=" * 60)
    print("🔍 Сбор данных из Telegram-каналов для сводки CPO")
    print(f"📅 Период: последние {DAYS_BACK} дней")
    print("=" * 60)

    # Создаём директорию для результатов
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    since = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

    # Подключаемся
    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована!")
        sys.exit(1)

    print("✅ Подключено к Telegram\n")

    all_data = {}

    for category_key, category in CHANNELS.items():
        print(f"\n{'─' * 40}")
        print(f"📂 {category['label']}")
        print(f"{'─' * 40}")

        category_data = {}
        for identifier in category["channels"]:
            data = await collect_channel(client, identifier, since)
            # Для имени файла: username или resolved name из channel_info
            file_key = identifier if isinstance(identifier, str) else data.get("channel_info", {}).get("username", str(identifier))
            category_data[file_key] = data

            # Сохраняем каждый канал отдельно
            channel_file = OUTPUT_DIR / f"{category_key}__{file_key}.json"
            with open(channel_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        all_data[category_key] = {
            "label": category["label"],
            "channels": category_data,
        }

    # Сохраняем сводный файл
    summary_file = OUTPUT_DIR / "all_channels.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    # Статистика
    print(f"\n{'=' * 60}")
    print("📊 СТАТИСТИКА СБОРА")
    print(f"{'=' * 60}")

    total_messages = 0
    for cat_key, cat_data in all_data.items():
        print(f"\n📂 {cat_data['label']}:")
        for ch_name, ch_data in cat_data["channels"].items():
            msg_count = len(ch_data.get("messages", []))
            total_messages += msg_count
            ch_info = ch_data.get("channel_info", {})
            subscribers = ch_info.get("participants_count", "?")
            status = "❌" if ch_data.get("error") else "✅"
            print(f"  {status} @{ch_name}: {msg_count} сообщений (подписчиков: {subscribers})")

    print(f"\n📦 Всего собрано: {total_messages} сообщений")
    print(f"💾 Сохранено в: {OUTPUT_DIR}")

    await client.disconnect()
    print("\n✅ Готово!")


if __name__ == "__main__":
    asyncio.run(main())
