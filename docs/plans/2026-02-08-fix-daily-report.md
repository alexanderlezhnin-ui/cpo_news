# Fix Daily Report (45/100 → 90/100) — План реализации

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Цель:** Превратить daily report из "сырого дампа данных" в actionable intelligence для CPO с TL-центричным фокусом, sentiment-классификацией и обязательными ссылками на источники.

**Архитектура:** Рефакторинг `generate_daily_reports.py` — добавление аналитических функций для классификации, фильтрации и интерпретации. Новый HTML-шаблон с 3 секциями (🔴/🟡/🟢) вместо 2 текущих. Каждый сигнал содержит ссылку на источник.

**Tech Stack:** Python 3, JSON, HTML/CSS (статика)

---

## Целевой формат отчёта

```
📊 7 февраля — ТИХИЙ ДЕНЬ (−80% vs вчера)

🔴 ТРЕБУЕТ ВНИМАНИЯ (2):
   • Жалоба на sales в Беседке → [Открыть](t.me/c/...)
   • Клиент просит помощь с API → [Открыть](t.me/...)

🟡 МОНИТОРИТЬ (3):
   • Тарбаев про госагрегатор 🤡45 → [Читать](t.me/...)
   • НДС 0% в Крыму → возможность для маркетинга? → [Читать](t.me/...)

🟢 ПОЗИТИВ (1):
   • Похвала TravelLine от клиента → [Открыть](t.me/...)

📈 Статистика дня:
   • TravelLine упоминаний: 3 (↓ vs вчера 12)
   • Конкурентов: bnovo (5), островок (2)
   • Источник: анализ 79 сообщений из 21 канала
```

---

### Задача 1: Добавить TL-центричную классификацию сообщений

**Файлы:**
- Изменить: `generate_daily_reports.py:135-172` (функция `get_chat_discussions`)
- Создать: новая функция `classify_message(msg) → dict`

**Step 1: Написать функцию классификации**

```python
def classify_message(msg):
    """
    Classify message by relevance and sentiment for TravelLine CPO.

    Returns:
        dict with keys:
        - relevance: 'high' | 'medium' | 'low' | 'irrelevant'
        - sentiment: 'negative' | 'neutral' | 'positive'
        - category: 'complaint' | 'competitor_mention' | 'tl_mention' | 'market_signal' | 'other'
        - tl_related: bool
        - competitors_mentioned: list[str]
    """
    text = msg.get('text', '').lower()
    result = {
        'relevance': 'low',
        'sentiment': 'neutral',
        'category': 'other',
        'tl_related': False,
        'competitors_mentioned': []
    }

    # TravelLine mentions (high priority)
    tl_keywords = ['travelline', 'тревеллайн', 'тревелайн', 'tl ', ' tl']
    for kw in tl_keywords:
        if kw in text:
            result['tl_related'] = True
            result['relevance'] = 'high'
            result['category'] = 'tl_mention'
            break

    # Competitor mentions
    competitors = {
        'bnovo': ['bnovo', 'бново', 'би-ново'],
        'hotellab': ['hotellab', 'хотеллаб'],
        'контур': ['контур.отель', 'контур отель', 'otelkontur'],
        'островок': ['островок', 'ostrovok'],
        'яндекс': ['яндекс путешеств', 'yandex travel', 'яндекс.путешеств'],
        'bronevik': ['bronevik', 'броневик'],
        'авито': ['авито', 'avito']
    }

    for comp, keywords in competitors.items():
        for kw in keywords:
            if kw in text:
                result['competitors_mentioned'].append(comp)
                if result['relevance'] != 'high':
                    result['relevance'] = 'medium'
                break

    # Negative sentiment (complaints, problems)
    negative_keywords = ['проблем', 'не работает', 'баг', 'ошибк', 'жалоб', 'ужас',
                        'кошмар', 'отключ', 'помогите', 'срочно', 'не могу', 'сломал']
    for kw in negative_keywords:
        if kw in text:
            result['sentiment'] = 'negative'
            if result['tl_related']:
                result['category'] = 'complaint'
                result['relevance'] = 'high'
            break

    # Positive sentiment
    positive_keywords = ['спасибо', 'отлично', 'супер', 'рекомендую', 'лучший',
                        'молодцы', 'круто', 'нравится', 'доволен', 'помогли']
    for kw in positive_keywords:
        if kw in text:
            result['sentiment'] = 'positive'
            break

    # Market signals (regulatory, trends)
    market_keywords = ['ндс', 'налог', 'закон', 'регулир', 'госагрегатор',
                      'минцифры', 'ростуризм', 'тренд', 'рынок']
    for kw in market_keywords:
        if kw in text:
            if result['relevance'] == 'low':
                result['relevance'] = 'medium'
            result['category'] = 'market_signal'
            break

    # Filter out irrelevant (foreign topics, off-topic)
    irrelevant_keywords = ['новая зеландия', 'new zealand', 'nz farms',
                          'погода в', 'курс доллар', 'футбол', 'хоккей']
    for kw in irrelevant_keywords:
        if kw in text:
            result['relevance'] = 'irrelevant'
            break

    return result
```

**Step 2: Запустить и проверить классификацию**

Добавить тестовый вывод в `main()`:
```python
# Test classification
test_msgs = filter_by_date(data, "2026-02-07")[:10]
for msg in test_msgs:
    cls = classify_message(msg)
    print(f"{msg.get('channel')}: {cls['relevance']}, {cls['sentiment']}, {cls['category']}")
```

Run: `python generate_daily_reports.py`
Expected: Видим классификацию первых 10 сообщений

**Step 3: Commit**

```bash
git add generate_daily_reports.py
git commit -m "feat(daily): add TL-centric message classification"
```

---

### Задача 2: Добавить вычисление дельты vs предыдущий день

**Файлы:**
- Изменить: `generate_daily_reports.py`
- Добавить: функция `get_day_delta(data, current_date, prev_date) → dict`

**Step 1: Написать функцию дельты**

```python
def get_day_delta(data, current_date, prev_date):
    """
    Calculate activity delta between two days.

    Returns:
        dict with keys:
        - total_delta: int (difference in message count)
        - total_delta_pct: float (percentage change)
        - tl_mentions_today: int
        - tl_mentions_yesterday: int
        - trend: 'up' | 'down' | 'stable'
        - label: str (e.g., "ТИХИЙ ДЕНЬ", "АКТИВНЫЙ ДЕНЬ")
    """
    current_msgs = filter_by_date(data, current_date)
    prev_msgs = filter_by_date(data, prev_date) if prev_date else []

    current_count = len(current_msgs)
    prev_count = len(prev_msgs) if prev_msgs else current_count

    delta = current_count - prev_count
    delta_pct = ((current_count - prev_count) / prev_count * 100) if prev_count > 0 else 0

    # Count TL mentions
    tl_today = sum(1 for m in current_msgs if classify_message(m)['tl_related'])
    tl_yesterday = sum(1 for m in prev_msgs if classify_message(m)['tl_related'])

    # Determine trend
    if delta_pct < -50:
        trend = 'down'
        label = 'ТИХИЙ ДЕНЬ'
    elif delta_pct > 50:
        trend = 'up'
        label = 'АКТИВНЫЙ ДЕНЬ'
    else:
        trend = 'stable'
        label = 'ОБЫЧНЫЙ ДЕНЬ'

    return {
        'total_today': current_count,
        'total_yesterday': prev_count,
        'total_delta': delta,
        'total_delta_pct': round(delta_pct),
        'tl_mentions_today': tl_today,
        'tl_mentions_yesterday': tl_yesterday,
        'trend': trend,
        'label': label
    }
```

**Step 2: Интегрировать в generate_html**

Изменить вызов в `generate_html()`:
```python
def generate_html(date_str, messages, data):
    # Get previous date
    idx = DATES.index(date_str)
    prev_date = DATES[idx-1] if idx > 0 else None

    # Calculate delta
    delta = get_day_delta(data, date_str, prev_date)
```

**Step 3: Commit**

```bash
git add generate_daily_reports.py
git commit -m "feat(daily): add day-over-day activity delta"
```

---

### Задача 3: Создать группировку по приоритету (🔴/🟡/🟢)

**Файлы:**
- Изменить: `generate_daily_reports.py`
- Добавить: функция `group_by_priority(messages) → dict`

**Step 1: Написать функцию группировки**

```python
def group_by_priority(messages):
    """
    Group messages into priority buckets for CPO.

    Returns:
        dict with keys:
        - red: list[msg] — ТРЕБУЕТ ВНИМАНИЯ (complaints about TL, urgent issues)
        - yellow: list[msg] — МОНИТОРИТЬ (competitor signals, market news)
        - green: list[msg] — ПОЗИТИВ (positive mentions, wins)
        - stats: dict with counts and competitor breakdown
    """
    red = []
    yellow = []
    green = []

    competitor_counts = {}
    tl_mentions = 0

    for msg in messages:
        cls = classify_message(msg)

        # Skip irrelevant
        if cls['relevance'] == 'irrelevant':
            continue

        # Track stats
        if cls['tl_related']:
            tl_mentions += 1
        for comp in cls['competitors_mentioned']:
            competitor_counts[comp] = competitor_counts.get(comp, 0) + 1

        # Assign to bucket
        if cls['tl_related'] and cls['sentiment'] == 'negative':
            # RED: TL complaint or problem
            red.append({**msg, '_classification': cls})
        elif cls['sentiment'] == 'positive' and cls['tl_related']:
            # GREEN: Positive TL mention
            green.append({**msg, '_classification': cls})
        elif cls['relevance'] in ['high', 'medium']:
            # YELLOW: Monitor (competitors, market signals)
            yellow.append({**msg, '_classification': cls})

    # Sort by engagement within each bucket
    red.sort(key=lambda m: get_engagement_score(m), reverse=True)
    yellow.sort(key=lambda m: get_engagement_score(m), reverse=True)
    green.sort(key=lambda m: get_engagement_score(m), reverse=True)

    # Limit to top items per bucket
    return {
        'red': red[:5],
        'yellow': yellow[:7],
        'green': green[:3],
        'stats': {
            'tl_mentions': tl_mentions,
            'competitors': competitor_counts,
            'total_analyzed': len(messages)
        }
    }
```

**Step 2: Commit**

```bash
git add generate_daily_reports.py
git commit -m "feat(daily): add priority grouping (red/yellow/green)"
```

---

### Задача 4: Добавить дедупликацию сообщений

**Файлы:**
- Изменить: `generate_daily_reports.py`
- Добавить: функция `deduplicate_messages(messages) → list`

**Step 1: Написать функцию дедупликации**

```python
def deduplicate_messages(messages):
    """
    Remove duplicate/cross-posted messages.
    Uses text similarity to detect reposts.
    """
    seen_texts = {}
    unique = []

    for msg in messages:
        text = msg.get('text', '')[:200].lower().strip()  # First 200 chars

        # Skip if too similar to already seen
        is_duplicate = False
        for seen_text in seen_texts:
            # Simple similarity: check if 80% of words match
            words1 = set(text.split())
            words2 = set(seen_text.split())
            if len(words1) > 3 and len(words2) > 3:
                overlap = len(words1 & words2) / max(len(words1), len(words2))
                if overlap > 0.8:
                    is_duplicate = True
                    # Keep the one with more engagement
                    if get_engagement_score(msg) > seen_texts[seen_text]['score']:
                        unique.remove(seen_texts[seen_text]['msg'])
                        unique.append(msg)
                        seen_texts[text] = {'msg': msg, 'score': get_engagement_score(msg)}
                    break

        if not is_duplicate:
            unique.append(msg)
            seen_texts[text] = {'msg': msg, 'score': get_engagement_score(msg)}

    return unique
```

**Step 2: Интегрировать в pipeline**

В `generate_html()`:
```python
# Deduplicate before processing
messages = deduplicate_messages(messages)
```

**Step 3: Commit**

```bash
git add generate_daily_reports.py
git commit -m "feat(daily): add message deduplication"
```

---

### Задача 5: Обновить HTML-шаблон с новой структурой

**Файлы:**
- Изменить: `generate_daily_reports.py:174-556` (функция `generate_html`)

**Step 1: Добавить CSS для новых компонентов**

Добавить в `<style>` секцию:
```css
/* Priority sections */
.priority-section {
  margin-bottom: 24px;
}
.priority-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}
.priority-header.red { color: var(--red); }
.priority-header.yellow { color: var(--orange); }
.priority-header.green { color: var(--green); }
.priority-count {
  background: var(--surface2);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

/* Signal card */
.signal-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.signal-card.red { border-left: 3px solid var(--red); }
.signal-card.yellow { border-left: 3px solid var(--orange); }
.signal-card.green { border-left: 3px solid var(--green); }

.signal-content {
  flex: 1;
}
.signal-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.signal-meta {
  font-size: 12px;
  color: var(--text2);
}
.signal-source {
  flex-shrink: 0;
}
.signal-source a {
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
  padding: 6px 12px;
  border: 1px solid var(--accent);
  border-radius: 16px;
  transition: all 0.2s;
}
.signal-source a:hover {
  background: var(--accent);
  color: #fff;
}

/* Day summary header */
.day-summary {
  background: linear-gradient(135deg, #1e2a4a 0%, #2a1e4a 100%);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 20px;
  border: 1px solid var(--border);
}
.day-summary h1 {
  font-size: 20px;
  margin-bottom: 8px;
}
.day-label {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  margin-left: 8px;
}
.day-label.down { background: rgba(255,107,107,0.2); color: var(--red); }
.day-label.up { background: rgba(81,207,102,0.2); color: var(--green); }
.day-label.stable { background: rgba(108,140,255,0.2); color: var(--accent); }

.day-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--text2);
}
.day-stats span {
  display: flex;
  align-items: center;
  gap: 4px;
}
```

**Step 2: Обновить HTML-генерацию**

Заменить текущую генерацию на новую структуру с priority sections:
```python
def generate_signal_html(msg, priority):
    """Generate HTML for a single signal card."""
    cls = msg.get('_classification', {})
    text = msg.get('text', '')[:150]
    if len(msg.get('text', '')) > 150:
        text += '...'
    text = escape_html(text)

    channel = msg.get('channel', '')
    channel_name = msg.get('channel_name', channel)
    msg_id = msg.get('id', '')

    # Build link
    if str(channel).startswith('-100'):
        # Private group
        chat_id = str(channel)[4:]  # Remove -100 prefix
        link = f"https://t.me/c/{chat_id}/{msg_id}"
    else:
        link = f"https://t.me/{channel}/{msg_id}"

    sender = msg.get('sender', '')
    reactions = format_reactions(msg.get('reactions', []))

    return f'''
    <div class="signal-card {priority}">
      <div class="signal-content">
        <div class="signal-title">{text}</div>
        <div class="signal-meta">
          {sender} в {channel_name}
          {' · ' + reactions if reactions else ''}
        </div>
      </div>
      <div class="signal-source">
        <a href="{link}" target="_blank">Открыть →</a>
      </div>
    </div>'''
```

**Step 3: Обновить header с дельтой**

```python
# In generate_html():
delta_sign = '+' if delta['total_delta'] >= 0 else ''
delta_class = delta['trend']

header_html = f'''
<div class="day-summary">
  <h1>📊 {date_ru}
    <span class="day-label {delta_class}">{delta['label']} ({delta_sign}{delta['total_delta_pct']}%)</span>
  </h1>
  <div class="day-stats">
    <span>💬 {delta['total_today']} сообщений (вчера: {delta['total_yesterday']})</span>
    <span>📍 TravelLine: {delta['tl_mentions_today']} упоминаний
      {'↓' if delta['tl_mentions_today'] < delta['tl_mentions_yesterday'] else '↑'}
      vs {delta['tl_mentions_yesterday']}</span>
  </div>
</div>'''
```

**Step 4: Собрать priority секции**

```python
# Generate priority sections
priority_sections = ''

if priority_groups['red']:
    priority_sections += f'''
    <div class="priority-section">
      <div class="priority-header red">
        🔴 ТРЕБУЕТ ВНИМАНИЯ <span class="priority-count">{len(priority_groups['red'])}</span>
      </div>
      {''.join(generate_signal_html(m, 'red') for m in priority_groups['red'])}
    </div>'''

if priority_groups['yellow']:
    priority_sections += f'''
    <div class="priority-section">
      <div class="priority-header yellow">
        🟡 МОНИТОРИТЬ <span class="priority-count">{len(priority_groups['yellow'])}</span>
      </div>
      {''.join(generate_signal_html(m, 'yellow') for m in priority_groups['yellow'])}
    </div>'''

if priority_groups['green']:
    priority_sections += f'''
    <div class="priority-section">
      <div class="priority-header green">
        🟢 ПОЗИТИВ <span class="priority-count">{len(priority_groups['green'])}</span>
      </div>
      {''.join(generate_signal_html(m, 'green') for m in priority_groups['green'])}
    </div>'''
```

**Step 5: Добавить статистику с источниками**

```python
stats_html = f'''
<div class="stats-summary">
  <div class="section-title">📈 Статистика дня</div>
  <div class="stats-grid">
    <div class="stat-item">
      <span class="stat-value">{priority_groups['stats']['tl_mentions']}</span>
      <span class="stat-label">упоминаний TL</span>
    </div>
    {''.join(f'<div class="stat-item"><span class="stat-value">{count}</span><span class="stat-label">{comp}</span></div>'
             for comp, count in sorted(priority_groups['stats']['competitors'].items(), key=lambda x: -x[1])[:4])}
  </div>
  <div class="source-note">
    Источник: анализ {priority_groups['stats']['total_analyzed']} сообщений из 21 канала
  </div>
</div>'''
```

**Step 6: Commit**

```bash
git add generate_daily_reports.py
git commit -m "feat(daily): new HTML template with priority sections"
```

---

### Задача 6: Добавить обязательные ссылки на источники

**Файлы:**
- Изменить: `generate_daily_reports.py`

**Step 1: Убедиться что все карточки содержат ссылки**

Проверить функцию `generate_signal_html()` — ссылка уже добавлена.

Добавить ссылки в статистику:
```python
def get_source_link(msg):
    """Generate Telegram link for a message."""
    channel = msg.get('channel', '')
    msg_id = msg.get('id', '')

    if not channel or not msg_id:
        return '#'

    if str(channel).startswith('-100'):
        chat_id = str(channel)[4:]
        return f"https://t.me/c/{chat_id}/{msg_id}"
    else:
        return f"https://t.me/{channel}/{msg_id}"
```

**Step 2: Обновить footer с источниками**

```python
footer_html = f'''
<div class="footer">
  <div class="footer-sources">
    Данные собраны из 21 Telegram-канала ·
    <a href="https://t.me/travelline_news">TravelLine</a> ·
    <a href="https://t.me/yandex_travel_pro">Яндекс</a> ·
    <a href="https://t.me/bnovonews">Bnovo</a> ·
    <a href="https://t.me/chat_hotel">Чат отельеров</a>
  </div>
  <a href="index.html">← Недельный обзор</a>
</div>'''
```

**Step 3: Commit**

```bash
git add generate_daily_reports.py
git commit -m "feat(daily): ensure all data points link to sources"
```

---

### Задача 7: Регенерировать все daily reports

**Файлы:**
- Изменить: `public/2026-02-02.html` ... `public/2026-02-07.html`

**Step 1: Запустить генерацию**

```bash
cd "c:\Users\ilya.suvorov\Projects\Work\TravelLine\Product instruments"
python generate_daily_reports.py
```

Expected:
```
Loading data...
Generating 2026-02-02...
  Found X messages
  Saved to public/2026-02-02.html
...
Done! Generated 6 daily reports.
```

**Step 2: Проверить результат локально**

Открыть `public/2026-02-07.html` в браузере и убедиться:
- [ ] Есть header с дельтой (ТИХИЙ ДЕНЬ −80%)
- [ ] Есть секция 🔴 ТРЕБУЕТ ВНИМАНИЯ
- [ ] Есть секция 🟡 МОНИТОРИТЬ
- [ ] Есть секция 🟢 ПОЗИТИВ (или пусто)
- [ ] Каждая карточка имеет кнопку "Открыть →" со ссылкой
- [ ] Есть статистика с источниками

**Step 3: Commit**

```bash
git add public/*.html
git commit -m "feat(daily): regenerate all reports with new format"
```

---

### Задача 8: Deploy и финальная проверка

**Файлы:**
- Нет изменений

**Step 1: Deploy на Vercel**

```bash
npx vercel --yes --prod
```

Expected: Deploy successful, URL: https://cpo-news.vercel.app

**Step 2: Проверить live**

Открыть https://cpo-news.vercel.app/2026-02-07.html

**Step 3: Commit документацию**

Обновить CLAUDE.md — заменить "🔴 NEXT: Fix Daily Report (45/100)" на "✅ DONE":

```bash
git add CLAUDE.md
git commit -m "docs: mark daily report fix as done (45→90)"
```

---

## Критерии успеха (Definition of Done)

| Критерий | Проверка |
|----------|----------|
| TL-центричность | Жалобы на TL в секции 🔴 |
| Sentiment | Три секции по приоритету |
| Дельта | Header показывает "−80% vs вчера" |
| Релевантность | Нет постов про фермы NZ |
| Дедупликация | Один пост не показан дважды |
| "So what?" | Секции интерпретируют контекст |
| **Источники** | Каждый сигнал имеет ссылку |

---

**Plan complete and saved to `docs/plans/2026-02-08-fix-daily-report.md`.**

**Два варианта выполнения:**

1. **Subagent-Driven (в этой сессии)** — запускаю subagent на каждую задачу, ревью между задачами, быстрая итерация

2. **Пакетное выполнение** — `/execute-plan` с чекпоинтами после каждых 2-3 задач

**Какой подход?**
