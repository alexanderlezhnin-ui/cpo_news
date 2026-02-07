# CPO News — TravelLine Competitive Monitor

## What is this?
A Telegram-based competitive intelligence tool for TravelLine's CPO (Юрий Костин).
Collects messages from 21 Telegram channels/groups across 5 categories, analyzes them, and generates interactive HTML reports.

**Live site**: https://cpo-news.vercel.app
**GitHub**: https://github.com/ilasuvorov/cpo_news

## Current state (as of 2026-02-07)

### What works
1. `collect_channels.py` — collects messages from 21 Telegram channels via Telethon
2. `generate_daily_reports.py` — generates daily HTML reports from collected data
3. `list_hotel_channels.py` — utility to scan user's TG subscriptions for hotel channels
4. `public/index.html` — weekly report (dark theme, 6 tabs, mobile-responsive)
5. `public/2026-02-02.html` ... `2026-02-07.html` — daily reports
6. Яндекс Метрика connected (counter `106707351`)
7. Deployed on Vercel as static site
8. Pushed to GitHub (`ilasuvorov/cpo_news`, private repo)

### What's manual (needs automation)
- Weekly report analysis & generation is done manually by AI agent
- Daily reports use auto-generated content (top posts by engagement)
- No cron/scheduled pipeline yet

## Project structure
```
collect_channels.py       — main data collection script (Telethon)
generate_daily_reports.py — generates 6 daily HTML reports from data
list_hotel_channels.py    — utility to scan user's TG subscriptions
public/
  index.html              — weekly report (Vercel serves this as main page)
  2026-02-02.html         — daily reports (02-07 Feb)
  2026-02-03.html
  2026-02-04.html
  2026-02-05.html
  2026-02-06.html
  2026-02-07.html
data/                     — collected JSON data (gitignored)
examples/                 — example generated reports
vercel.json               — Vercel config (outputDirectory: public)
.env.example              — template for Telegram credentials
requirements.txt          — Python deps: telethon, python-dotenv
```

## Channel configuration (21 channels, 5 categories)

### OTA competitors (3)
- `yandex_travel_pro` — Яндекс Путешествия для отелей
- `extranetetg` — Островок (экстранет)
- `bronevik_com` — Bronevik.com (B2B/корп тревел)

### B2B SaaS competitors (5)
- `bnovonews` — Bnovo (PMS конкурент)
- `hotellab_io` — Hotellab (revenue management)
- `otelkontur` — Контур.Отель
- `bronirui_online` — Бронируй Онлайн
- `uhotelsapp` — TravelLine (свой канал в B2B контексте)

### Industry news (8)
- `wrkhotel`, `hotel_geek`, `russianhospitalityawards`, `portierdenuit`
- `AZO_channel`, `Hoteliernews`, `HotelierPRO`, `frontdesk_ru`

### TravelLine (1)
- `travelline_news` — официальный канал TL

### Hotelier chats (4)
- `chat_hotel` (4662 участника)
- `hotel_advisors`
- `HRSRussia` — чат про гостиничные системы
- `-1001264671967` — TL: Беседка (приватная группа, 7516 участников, нужен numeric ID)

## Technical notes

### Telegram collection
- Uses Telethon with StringSession auth
- Credentials loaded from `.env` (local) or fallback to `~/Projects/Personal/iamsu_mcp_tg/.env`
- Private groups need numeric IDs with -100 prefix
- `collect_channel()` accepts both str usernames and int IDs
- Collects: text, date, views, forwards, reactions (emoji+count), replies_count, sender
- Output: JSON per channel in `data/YYYY-MM-DD/`

### Daily report generation
- `generate_daily_reports.py` reads `data/2026-02-07/all_channels.json`
- Filters messages by date, finds top posts by engagement score
- Engagement score: views + forwards*10 + reactions*5
- Picks diverse posts (max 1 per channel)
- Includes chat discussions with keyword filtering
- Keywords: яндекс, комисси, отключ, travelline, bnovo, островок, авито, проблем, помогите, подскажите

### Report format
- Dark theme (#0f1117 bg), CSS custom properties for theming
- Weekly: 6 tabbed sections (Война комиссий, Конкуренты, Рынок, Голос TL, Голос клиента, Выводы)
- Daily: 2 sections (Топ публикации, Обсуждения в чатах)
- Components: timeline, competitor grid cards, data tables, quote blocks, engagement badges
- All Telegram citations have clickable links: `https://t.me/{channel}/{msg_id}`
- Mobile-responsive (CSS Grid, media queries @600px)

### Яндекс Метрика
- Counter ID: `106707351`
- Enabled: webvisor, clickmap, accurateTrackBounce, trackLinks
- Added to all HTML files (weekly + 6 daily)
- Dashboard: https://metrika.yandex.ru

### Vercel
- Project name: `cpo-news`
- Static deploy from `public/` directory
- Linked to Vercel account `ilyas-projects-dfd92f00`
- `vercel.json` sets outputDirectory and security headers
- Deploy: `npx vercel --yes --prod` or auto-deploy via Git integration

### GitHub
- Repo: `ilasuvorov/cpo_news` (private)
- gh CLI installed (`/c/Program Files/GitHub CLI/gh.exe`), authenticated as `ilasuvorov`
- `.gitignore` excludes: `data/`, `.env`, `*.session`, `.mcp.json`, `.vercel/`, `.claude/settings.local.json`

### Python environment
- Using venv from: `C:\Users\ilya.suvorov\Projects\Personal\iamsu_mcp_tg\venv\Scripts\python.exe`
- Windows: need `PYTHONIOENCODING=utf-8` for correct output
- Need `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')` in scripts

## Roadmap

### ✅ DONE: Яндекс Метрика
- Counter 106707351 added to all pages
- Tracks: visits, depth, time on page, click map, webvisor

### ✅ DONE: Daily reports
- 6 daily reports (02-07 Feb 2026)
- Navigation between days and weekly report
- Auto-generated from data (top posts by engagement)

### NEXT: Automated pipeline
**Goal**: Run collection + analysis + HTML generation without human intervention.
- Pipeline: `collect_channels.py` → filter (Haiku) → analyze + cluster topics (Sonnet) → generate HTML (Sonnet)
- Weekly report: still needs manual curation for quality
- Daily reports: can be fully automated with `generate_daily_reports.py`
- Cron via GitHub Actions

### FUTURE: Claude API integration
- Use Claude API (Anthropic) for analysis step
- Pipeline: Haiku for chat filtering → Sonnet for analysis + HTML generation
- Estimated cost: **~$17/month** (4 weekly + 30 daily reports)
  - Weekly: ~$1.60/report (750K input tokens raw, filtered down)
  - Daily: ~$0.35/report
- Can optimize with prompt caching (up to 50% savings)

## Known issues / gotchas
- Background Task agents in Claude Code have a bug where output files are empty — use Python scripts via Bash directly instead
- Write tool requires Read first before overwriting a file
- Large chat channels (chat_hotel: 1479 msgs, Беседка: 1490 msgs) dominate data volume
- Private group TL: Беседка needs numeric ID `-1001264671967`
- Channel `portierdenuit` is very active (137 msgs/week) — may need filtering

## Data from last collection (2026-02-07)
- Total: 3,732 messages from 21 channels
- By date: 02.02 (364) | 03.02 (199) | 04.02 (262) | 05.02 (410) | 06.02 (427) | 07.02 (79)
- Biggest: chat_hotel (1,479), Беседка (1,490), portierdenuit (137), Hoteliernews (134)
- Key topics discovered: Яндекс commission war (7 hotel chains left), Bnovo API launch, Авито integration, Контур in Mintsifry whitelist
- Hottest post: wrkhotel/5153 (mass disconnection from YP) — 4,633 views, 265 forwards
