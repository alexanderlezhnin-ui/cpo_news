# CPO News — TravelLine Competitive Monitor

## What is this?
A Telegram-based competitive intelligence tool for TravelLine's CPO.
Collects messages from 21 Telegram channels/groups across 5 categories and generates weekly reports.

## Project structure
```
collect_channels.py   — main data collection script (Telethon)
list_hotel_channels.py — utility to scan user's TG subscriptions for hotel channels
data/                  — collected JSON data (gitignored)
examples/              — example generated reports
```

## Categories monitored
- **OTA competitors** (Yandex Travel, Ostrovok, Bronevik)
- **B2B SaaS competitors** (Bnovo, Hotellab, Kontur, Bronirui Online)
- **Industry news** (8 channels)
- **TravelLine** (own channel — market perception)
- **Hotelier chats** (4 groups including private TL: Besedka)

## Running
```bash
pip install -r requirements.txt
cp .env.example .env  # fill in your Telegram credentials
python collect_channels.py
```

## Output
- JSON files per channel in `data/YYYY-MM-DD/`
- Combined `all_channels.json`
- Reports generated manually (to be automated)
