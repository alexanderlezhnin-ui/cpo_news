#!/usr/bin/env python3
"""
Generate daily HTML reports from Telegram channel data.
"""

import json
import sys
import io
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_FILE = Path("data/2026-02-07/all_channels.json")
OUTPUT_DIR = Path("public")

# Russian month names
MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

# Dates to generate
DATES = ["2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06", "2026-02-07"]


def load_data():
    """Load all channel messages."""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def filter_by_date(data, target_date):
    """Extract messages for a specific date."""
    messages = []

    for category_name, category in data.items():
        if 'channels' not in category:
            continue
        category_label = category.get('label', category_name)

        for channel_name, channel in category['channels'].items():
            channel_info = channel.get('channel_info', {})
            username = channel_info.get('username', channel_name)

            for msg in channel.get('messages', []):
                msg_date = msg.get('date', '')[:10]
                if msg_date == target_date:
                    messages.append({
                        'category': category_name,
                        'category_label': category_label,
                        'channel': username,
                        'channel_name': channel_info.get('name', channel_name),
                        **msg
                    })

    return messages


def get_engagement_score(msg):
    """Calculate engagement score: views + forwards*10 + reactions*5."""
    views = msg.get('views', 0) or 0
    forwards = msg.get('forwards', 0) or 0
    reactions = sum(r.get('count', 0) for r in msg.get('reactions', []))
    return views + forwards * 10 + reactions * 5


def get_top_posts_diverse(messages, n=3):
    """Get top N posts by engagement, max 1 per channel, exclude chats."""
    # Filter out chat messages
    channel_msgs = [m for m in messages if 'чат' not in m.get('category_label', '').lower()]

    # Score all messages
    scored = [(msg, get_engagement_score(msg)) for msg in channel_msgs]
    scored.sort(key=lambda x: -x[1])

    # Pick top from different channels
    selected = []
    seen_channels = set()

    for msg, score in scored:
        channel = msg.get('channel', '')
        if channel not in seen_channels and score > 0:
            selected.append(msg)
            seen_channels.add(channel)
            if len(selected) >= n:
                break

    return selected


def format_reactions(reactions):
    """Format reactions as string."""
    if not reactions:
        return ""
    parts = [f"{r['emoji']}{r['count']}" for r in reactions[:4]]
    return " ".join(parts)


def format_date_ru(date_str):
    """Format date in Russian: '2 февраля 2026'."""
    dt = datetime.fromisoformat(date_str)
    return f"{dt.day} {MONTHS_RU[dt.month]} {dt.year}"


def get_nav_links(current_date):
    """Get prev/next date links."""
    idx = DATES.index(current_date)
    prev_link = f"{DATES[idx-1]}.html" if idx > 0 else None
    next_link = f"{DATES[idx+1]}.html" if idx < len(DATES) - 1 else None
    return prev_link, next_link


def group_by_category(messages):
    """Group messages by category."""
    by_cat = defaultdict(list)
    for msg in messages:
        by_cat[msg['category_label']].append(msg)
    return dict(by_cat)


def escape_html(text):
    """Escape HTML and format for display."""
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    # Convert markdown bold to HTML
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = text.replace('\n', '<br>')
    return text


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


def get_day_delta(data, current_date, prev_date):
    """
    Calculate activity delta between two days.

    Returns:
        dict with keys:
        - total_today: int
        - total_yesterday: int
        - total_delta: int (difference in message count)
        - total_delta_pct: float (percentage change)
        - tl_mentions_today: int
        - tl_mentions_yesterday: int
        - trend: 'up' | 'down' | 'stable'
        - label: str (e.g., "ТИХИЙ ДЕНЬ", "АКТИВНЫЙ ДЕНЬ", "ОБЫЧНЫЙ ДЕНЬ")
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
        for seen_text in list(seen_texts.keys()):
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
                        del seen_texts[seen_text]
                        seen_texts[text] = {'msg': msg, 'score': get_engagement_score(msg)}
                    break

        if not is_duplicate:
            unique.append(msg)
            seen_texts[text] = {'msg': msg, 'score': get_engagement_score(msg)}

    return unique


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


def generate_signal_html(msg, priority):
    """Generate HTML for a single signal card."""
    text = msg.get('text', '')[:150]
    if len(msg.get('text', '')) > 150:
        text += '...'
    text = escape_html(text)

    channel = msg.get('channel', '')
    channel_name = msg.get('channel_name', channel)
    link = get_source_link(msg)
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


def get_chat_discussions(messages, n=5):
    """Get interesting chat discussions with context."""
    chat_msgs = [m for m in messages if 'чат' in m.get('category_label', '').lower()]

    if not chat_msgs:
        return []

    # Filter: messages with at least 50 chars and some engagement or keywords
    interesting = []
    keywords = ['яндекс', 'комисси', 'отключ', 'тревеллайн', 'travelline', 'бново', 'bnovo',
                'островок', 'авито', 'проблем', 'помогите', 'подскажите', 'опыт', 'кто', 'как']

    for msg in chat_msgs:
        text = msg.get('text', '').lower()
        text_len = len(msg.get('text', ''))
        reactions_count = sum(r.get('count', 0) for r in msg.get('reactions', []))
        replies = msg.get('replies_count', 0) or 0

        # Score based on: length, reactions, replies, keywords
        score = 0
        if text_len > 100:
            score += 2
        if text_len > 200:
            score += 2
        score += reactions_count
        score += replies * 2

        for kw in keywords:
            if kw in text:
                score += 3
                break

        if score > 3 and text_len > 50:
            interesting.append((msg, score))

    interesting.sort(key=lambda x: -x[1])
    return [msg for msg, score in interesting[:n]]


def generate_html(date_str, messages, data):
    """Generate HTML report for a day."""

    # Deduplicate messages
    messages = deduplicate_messages(messages)

    # Get previous date for delta
    idx = DATES.index(date_str)
    prev_date = DATES[idx-1] if idx > 0 else None

    # Calculate delta
    delta = get_day_delta(data, date_str, prev_date)

    # Group by priority
    priority_groups = group_by_priority(messages)

    date_ru = format_date_ru(date_str)
    prev_link, next_link = get_nav_links(date_str)

    # Navigation HTML
    nav_html = '<div class="day-nav">'
    if prev_link:
        nav_html += f'<a href="{prev_link}" class="nav-link">← Предыдущий день</a>'
    else:
        nav_html += '<span class="nav-link disabled">← Предыдущий день</span>'
    nav_html += '<a href="index.html" class="nav-link week">Вся неделя</a>'
    if next_link:
        nav_html += f'<a href="{next_link}" class="nav-link">Следующий день →</a>'
    else:
        nav_html += '<span class="nav-link disabled">Следующий день →</span>'
    nav_html += '</div>'

    # Build day summary header
    delta_sign = '+' if delta['total_delta'] >= 0 else ''
    delta_class = delta['trend']
    tl_arrow = '↓' if delta['tl_mentions_today'] < delta['tl_mentions_yesterday'] else '↑'

    header_html = f'''
  <div class="day-summary">
    <h1>📊 {date_ru}
      <span class="day-label {delta_class}">{delta['label']} ({delta_sign}{delta['total_delta_pct']}%)</span>
    </h1>
    <div class="day-stats">
      <span>💬 {delta['total_today']} сообщений (вчера: {delta['total_yesterday']})</span>
      <span>📍 TravelLine: {delta['tl_mentions_today']} {tl_arrow} vs {delta['tl_mentions_yesterday']}</span>
    </div>
  </div>'''

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

    # If no priority signals, show a note
    if not priority_sections:
        priority_sections = '<p style="color:var(--text2)">Нет значимых сигналов за этот день</p>'

    # Stats section with competitor mentions
    comp_stats = ''.join(
        f'<span>{comp}: {count}</span>'
        for comp, count in sorted(priority_groups['stats']['competitors'].items(), key=lambda x: -x[1])[:4]
    )

    stats_html = f'''
  <div class="section-title">📈 Статистика</div>
  <div class="day-stats" style="margin-bottom:20px">
    <span>TL упоминаний: {priority_groups['stats']['tl_mentions']}</span>
    {comp_stats}
  </div>
  <div style="font-size:12px;color:var(--text2)">
    Источник: анализ {priority_groups['stats']['total_analyzed']} сообщений из 21 канала
  </div>'''

    html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CPO News — {date_ru}</title>

<!-- Yandex.Metrika counter -->
<script type="text/javascript">
   (function(m,e,t,r,i,k,a){{m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};
   m[i].l=1*new Date();
   for (var j = 0; j < document.scripts.length; j++) {{if (document.scripts[j].src === r) {{ return; }}}}
   k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)}})
   (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

   ym(106707351, "init", {{
        clickmap:true,
        trackLinks:true,
        accurateTrackBounce:true,
        webvisor:true
   }});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/106707351" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->

<style>
  :root {{
    /* Telegram Dark Theme (same as weekly report) */
    --bg: #17212b;
    --surface: #232e3c;
    --surface2: #2b3a4a;
    --border: #3d4d5f;
    --text: #f5f5f5;
    --text2: #8b9bab;
    --accent: #64b5f6;
    --accent2: #4ecdc4;
    --red: #e53935;
    --orange: #ff9800;
    --green: #4fae4e;
    --yellow: #ffc107;
    --radius: 10px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 16px; }}

  .day-nav {{
    display: flex;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 20px;
  }}
  .nav-link {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text2);
    padding: 8px 14px;
    border-radius: 20px;
    font-size: 13px;
    text-decoration: none;
    transition: all .2s;
  }}
  .nav-link:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .nav-link.week {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .nav-link.disabled {{ opacity: 0.4; cursor: default; }}
  .nav-link.disabled:hover {{ background: var(--surface); color: var(--text2); }}

  .section-title {{
    font-size: 18px;
    font-weight: 700;
    margin: 24px 0 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  /* Priority sections */
  .priority-section {{ margin-bottom: 24px; }}
  .priority-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    font-size: 16px;
    font-weight: 600;
  }}
  .priority-header.red {{ color: var(--red); }}
  .priority-header.yellow {{ color: var(--orange); }}
  .priority-header.green {{ color: var(--green); }}
  .priority-count {{
    background: var(--surface2);
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 12px;
  }}

  /* Signal card (matches weekly report cards) */
  .signal-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    transition: border-color .2s;
  }}
  .signal-card:hover {{ border-color: var(--accent); }}
  .signal-card.red {{ border-left: 3px solid var(--red); }}
  .signal-card.yellow {{ border-left: 3px solid var(--orange); }}
  .signal-card.green {{ border-left: 3px solid var(--green); }}
  .signal-content {{ flex: 1; }}
  .signal-title {{ font-size: 15px; font-weight: 600; margin-bottom: 8px; }}
  .signal-meta {{ font-size: 14px; color: var(--text2); }}
  .signal-meta a {{ color: var(--accent); text-decoration: none; }}
  .signal-meta a:hover {{ text-decoration: underline; }}
  .signal-source {{ flex-shrink: 0; }}
  .signal-source a {{
    color: var(--accent);
    text-decoration: none;
    font-size: 13px;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: 20px;
    background: var(--surface);
    transition: all 0.2s;
  }}
  .signal-source a:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

  /* Day summary header (matches weekly report) */
  .day-summary {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2b3a4a 100%);
    border-radius: var(--radius);
    padding: 28px 24px;
    margin-bottom: 20px;
    border: 1px solid var(--border);
  }}
  .day-summary h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; }}
  .day-label {{
    display: inline-block;
    padding: 4px 12px;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    margin-left: 8px;
  }}
  .day-label.down {{ background: rgba(229,57,53,0.2); color: var(--red); }}
  .day-label.up {{ background: rgba(79,174,78,0.2); color: var(--green); }}
  .day-label.stable {{ background: rgba(100,181,246,0.2); color: var(--accent); }}
  .day-stats {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-top: 12px;
    font-size: 13px;
    color: var(--text2);
  }}
  .day-stats span {{ display: flex; align-items: center; gap: 4px; }}

  .footer {{
    text-align: center;
    padding: 24px;
    color: var(--text2);
    font-size: 12px;
  }}
  .footer a {{
    color: var(--accent);
    text-decoration: none;
  }}

  @media (max-width: 600px) {{
    .container {{ padding: 10px; }}
    .day-summary {{ padding: 16px; }}
    .day-nav {{ flex-wrap: wrap; justify-content: center; }}
    .signal-card {{ flex-direction: column; }}
    .signal-source {{ align-self: flex-start; }}
  }}
</style>
</head>
<body>

<div class="container">
  {header_html}

  {nav_html}

  {priority_sections}

  {stats_html}
</div>

<div class="footer">
  Дневной отчёт CPO News · <a href="index.html">Недельный обзор →</a>
</div>

</body>
</html>'''

    return html


def main():
    print("Loading data...")
    data = load_data()

    for date_str in DATES:
        print(f"Generating {date_str}...")
        messages = filter_by_date(data, date_str)
        print(f"  Found {len(messages)} messages")

        html = generate_html(date_str, messages, data)
        output_file = OUTPUT_DIR / f"{date_str}.html"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  Saved to {output_file}")

    print("\nDone! Generated 6 daily reports.")


if __name__ == "__main__":
    main()
