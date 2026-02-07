"""
Получить список всех каналов/чатов пользователя в Telegram,
отфильтровать по отельной/гостиничной тематике.
"""
import asyncio
import os
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

if not os.getenv("TELEGRAM_API_ID"):
    MCP_DIR = Path.home() / "Projects" / "Personal" / "iamsu_mcp_tg"
    if (MCP_DIR / ".env").exists():
        load_dotenv(MCP_DIR / ".env")

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION")

# Ключевые слова для фильтрации отельных каналов
HOTEL_KEYWORDS = [
    "hotel", "отел", "гостин", "hostel", "хостел", "travel", "путешеств",
    "туризм", "tourism", "booking", "бронир", "hospitality", "resort",
    "курорт", "apartament", "апартамент", "bnovo", "travelline",
    "extranet", "островок", "яндекс путеш", "ota", "pms", "ревпар",
    "revpar", "adr", "загрузк", "номерн", "санатор", "глэмпинг",
    "glamping", "средств размещ", "гостеприимств", "hotelier",
    "портье", "ресторан", "horeca", "хорека", "общепит",
    "azimut", "cosmos", "marriott", "hilton", "accor",
    "wyndham", "radisson", "holiday inn", "novotel",
    "geek", "wrk", "azo", "portier", "advisor",
]


async def main():
    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована!")
        sys.exit(1)

    print("✅ Подключено к Telegram\n")

    # Собираем все диалоги (каналы и группы)
    all_channels = []
    all_groups = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        if isinstance(entity, Channel):
            info = {
                "title": dialog.title or "",
                "username": getattr(entity, 'username', None) or "",
                "id": entity.id,
                "participants_count": getattr(entity, 'participants_count', None),
                "is_megagroup": getattr(entity, 'megagroup', False),
                "is_broadcast": getattr(entity, 'broadcast', False),
            }

            if info["is_megagroup"] or not info["is_broadcast"]:
                all_groups.append(info)
            else:
                all_channels.append(info)
        elif isinstance(entity, Chat):
            all_groups.append({
                "title": dialog.title or "",
                "username": "",
                "id": entity.id,
                "participants_count": getattr(entity, 'participants_count', None),
                "is_megagroup": False,
                "is_broadcast": False,
            })

    def matches_hotel(item):
        text = (item["title"] + " " + item["username"]).lower()
        return any(kw in text for kw in HOTEL_KEYWORDS)

    hotel_channels = [c for c in all_channels if matches_hotel(c)]
    hotel_groups = [g for g in all_groups if matches_hotel(g)]

    # Наши текущие каналы
    CURRENT = {
        "yandex_travel_pro", "extranetetg", "bnovonews", "uhotelsapp",
        "wrkhotel", "hotel_geek", "russianhospitalityawards",
        "portierdenuit", "AZO_channel", "chat_hotel", "hotel_advisors",
    }
    current_lower = {c.lower() for c in CURRENT}

    print("=" * 70)
    print("📡 ОТЕЛЬНЫЕ КАНАЛЫ (broadcasts)")
    print("=" * 70)
    for c in sorted(hotel_channels, key=lambda x: x["participants_count"] or 0, reverse=True):
        username = c["username"]
        marker = "✅" if username.lower() in current_lower else "🆕"
        subs = c["participants_count"] or "?"
        print(f"  {marker} @{username:<35} {c['title']:<40} ({subs} подписчиков)")

    print(f"\n{'=' * 70}")
    print("💬 ОТЕЛЬНЫЕ ГРУППЫ/ЧАТЫ (megagroups + chats)")
    print("=" * 70)
    for g in sorted(hotel_groups, key=lambda x: x["participants_count"] or 0, reverse=True):
        username = g["username"] or f"[id:{g['id']}]"
        marker = "✅" if (g["username"] or "").lower() in current_lower else "🆕"
        members = g["participants_count"] or "?"
        print(f"  {marker} @{username:<35} {g['title']:<40} ({members} участников)")

    # Итого
    new_channels = [c for c in hotel_channels if c["username"].lower() not in current_lower]
    new_groups = [g for g in hotel_groups if (g["username"] or "").lower() not in current_lower]

    print(f"\n{'=' * 70}")
    print(f"📊 ИТОГО:")
    print(f"  Отельных каналов найдено: {len(hotel_channels)} (из них новых: {len(new_channels)})")
    print(f"  Отельных групп найдено:   {len(hotel_groups)} (из них новых: {len(new_groups)})")
    print(f"  Уже мониторим:            {len(CURRENT)} каналов/групп")
    print(f"  Всего каналов у тебя:     {len(all_channels)}")
    print(f"  Всего групп у тебя:       {len(all_groups)}")
    print("=" * 70)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
