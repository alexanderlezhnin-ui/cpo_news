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


def generate_html(date_str, messages):
    """Generate HTML report for a day."""

    date_ru = format_date_ru(date_str)
    prev_link, next_link = get_nav_links(date_str)
    top_posts = get_top_posts_diverse(messages, n=3)
    by_category = group_by_category(messages)
    chat_discussions = get_chat_discussions(messages, n=5)

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

    # Top posts HTML - expanded content
    top_posts_html = ""
    for msg in top_posts:
        full_text = msg.get('text', '')
        # Show up to 500 chars for better context
        text = full_text[:500]
        if len(full_text) > 500:
            text += "..."
        text = escape_html(text)

        views = msg.get('views', 0) or 0
        forwards = msg.get('forwards', 0) or 0
        reactions_str = format_reactions(msg.get('reactions', []))

        channel = msg.get('channel', '')
        channel_name = msg.get('channel_name', channel)
        msg_id = msg.get('id', '')
        link = f"https://t.me/{channel}/{msg_id}" if channel and msg_id else "#"

        # Category tag
        category = msg.get('category_label', '')

        top_posts_html += f'''
    <div class="card top-post">
      <div class="post-header">
        <span class="channel-name">{channel_name}</span>
        <span class="category-tag">{category}</span>
      </div>
      <div class="card-body">{text}</div>
      <div class="engagement">
        <span class="badge views">👁 {views:,}</span>
        {"<span class='badge fwd'>↗ " + str(forwards) + "</span>" if forwards else ""}
        {"<span class='badge react'>" + reactions_str + "</span>" if reactions_str else ""}
      </div>
      <div class="source-tag"><a href="{link}" target="_blank">Читать в Telegram →</a></div>
    </div>'''

    # Category summary HTML
    category_html = ""
    for cat_label, cat_messages in sorted(by_category.items()):
        if 'чат' in cat_label.lower():
            continue
        count = len(cat_messages)
        category_html += f'''
    <div class="stat-card">
      <div class="number">{count}</div>
      <div class="label">{cat_label}</div>
    </div>'''

    # Chat discussions HTML - expanded with context
    chats_html = ""
    if chat_discussions:
        for msg in chat_discussions:
            full_text = msg.get('text', '')
            # Show up to 400 chars
            text = full_text[:400]
            if len(full_text) > 400:
                text += "..."
            text = escape_html(text)

            sender = msg.get('sender', 'Аноним')
            channel = msg.get('channel', '')
            channel_name = msg.get('channel_name', channel)
            msg_id = msg.get('id', '')
            link = f"https://t.me/{channel}/{msg_id}" if channel and msg_id else "#"

            reactions_str = format_reactions(msg.get('reactions', []))
            replies = msg.get('replies_count', 0) or 0

            chats_html += f'''
    <div class="chat-msg">
      <div class="chat-header">
        <span class="chat-sender">{sender}</span>
        <span class="chat-source">в {channel_name}</span>
      </div>
      <div class="chat-text">{text}</div>
      <div class="chat-meta">
        {"<span>💬 " + str(replies) + " ответов</span>" if replies else ""}
        {"<span>" + reactions_str + "</span>" if reactions_str else ""}
        <a href="{link}" target="_blank">Открыть →</a>
      </div>
    </div>'''

    # Count channels and chats separately
    channel_count = len(set(m['channel'] for m in messages if 'чат' not in m.get('category_label', '').lower()))
    chat_count = len([m for m in messages if 'чат' in m.get('category_label', '').lower()])

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
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #232736;
    --border: #2e3347;
    --text: #e4e6ef;
    --text2: #9ca0b5;
    --accent: #6c8cff;
    --accent2: #4ecdc4;
    --red: #ff6b6b;
    --orange: #ffa94d;
    --green: #51cf66;
    --yellow: #ffd43b;
    --radius: 12px;
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

  .header {{
    background: linear-gradient(135deg, #1e2a4a 0%, #2a1e4a 100%);
    border-radius: var(--radius);
    padding: 28px 24px;
    margin-bottom: 20px;
    border: 1px solid var(--border);
  }}
  .header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; }}
  .header .meta {{ color: var(--text2); font-size: 14px; }}

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

  .stats-bar {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    margin-bottom: 20px;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    text-align: center;
  }}
  .stat-card .number {{ font-size: 28px; font-weight: 800; color: var(--accent); }}
  .stat-card .label {{ font-size: 12px; color: var(--text2); margin-top: 2px; }}

  .section-title {{
    font-size: 18px;
    font-weight: 700;
    margin: 24px 0 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  /* Top posts */
  .card.top-post {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 16px;
  }}
  .card.top-post:hover {{ border-color: var(--accent); }}

  .post-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }}
  .channel-name {{
    font-size: 16px;
    font-weight: 700;
    color: var(--text);
  }}
  .category-tag {{
    font-size: 11px;
    background: rgba(108,140,255,.15);
    color: var(--accent);
    padding: 3px 10px;
    border-radius: 10px;
  }}

  .card-body {{
    font-size: 14px;
    color: var(--text2);
    line-height: 1.7;
  }}
  .card-body strong {{
    color: var(--text);
  }}

  .engagement {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
  }}
  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    background: var(--surface2);
    padding: 4px 10px;
    border-radius: 10px;
    font-size: 12px;
    color: var(--text2);
  }}
  .badge.views {{ color: var(--accent); }}
  .badge.fwd {{ color: var(--orange); }}
  .badge.react {{ color: var(--yellow); }}

  .source-tag {{
    display: inline-block;
    font-size: 12px;
    margin-top: 12px;
  }}
  .source-tag a {{
    color: var(--accent);
    text-decoration: none;
  }}
  .source-tag a:hover {{
    text-decoration: underline;
  }}

  /* Chat messages */
  .chat-msg {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 20px;
    margin-bottom: 12px;
  }}
  .chat-msg:hover {{
    border-color: var(--accent2);
  }}
  .chat-header {{
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
  }}
  .chat-sender {{
    font-weight: 600;
    color: var(--accent2);
  }}
  .chat-source {{
    font-size: 12px;
    color: var(--text2);
  }}
  .chat-text {{
    font-size: 14px;
    color: var(--text);
    line-height: 1.7;
    margin-bottom: 10px;
  }}
  .chat-meta {{
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: var(--text2);
  }}
  .chat-meta a {{
    color: var(--accent);
    text-decoration: none;
  }}

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
    .header {{ padding: 20px 16px; }}
    .day-nav {{ flex-wrap: wrap; justify-content: center; }}
    .stats-bar {{ grid-template-columns: repeat(2, 1fr); }}
    .post-header {{ flex-direction: column; align-items: flex-start; gap: 6px; }}
  }}
</style>
</head>
<body>

<div class="container">
  <div class="header">
    <h1>📅 {date_ru}</h1>
    <div class="meta">💬 {len(messages)} сообщений · {channel_count} каналов · {chat_count} в чатах</div>
  </div>

  {nav_html}

  <div class="stats-bar">
    <div class="stat-card">
      <div class="number">{len(messages)}</div>
      <div class="label">сообщений</div>
    </div>
    {category_html}
  </div>

  <div class="section-title">🔥 Главные публикации дня</div>
  {top_posts_html if top_posts_html else '<p style="color:var(--text2)">Нет значимых публикаций за этот день</p>'}

  <div class="section-title">🗣 Обсуждения в чатах</div>
  {chats_html if chats_html else '<p style="color:var(--text2)">Нет интересных обсуждений за этот день</p>'}

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

        html = generate_html(date_str, messages)
        output_file = OUTPUT_DIR / f"{date_str}.html"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  Saved to {output_file}")

    print("\nDone! Generated 6 daily reports.")


if __name__ == "__main__":
    main()
