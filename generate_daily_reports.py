#!/usr/bin/env python3
"""
Generate daily HTML reports from Telegram channel data.
"""

import json
import sys
import io
import re
import argparse
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_FILE = Path("data/2026-02-11/all_channels.json")
OUTPUT_DIR = Path("public")
OVERLAY_FILE = Path("data/2026-02-11/analysis_overlay.json")
CANDIDATES_FILE = Path("data/2026-02-11/candidates.json")

# Russian month names
MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

# Dates to generate
DATES = ["2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06", "2026-02-07", "2026-02-08", "2026-02-09", "2026-02-10"]


def load_data():
    """Load all channel messages."""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_overlay(overlay_path=None):
    """Load analysis overlay JSON if it exists."""
    path = Path(overlay_path) if overlay_path else OVERLAY_FILE
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


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
    """Format reactions as string, filtering out raw Telethon objects."""
    if not reactions:
        return ""
    parts = []
    for r in reactions[:4]:
        emoji = r.get('emoji', '')
        count = r.get('count', 0)
        # Skip raw Telethon objects (ReactionPaid, ReactionCustomEmoji, etc.)
        if not emoji or 'Reaction' in str(emoji) or 'document_id' in str(emoji):
            continue
        parts.append(f"{emoji}{count}")
    return " ".join(parts)


DAYS_OF_WEEK_RU = {
    0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
    4: "пятница", 5: "суббота", 6: "воскресенье"
}

DAYS_OF_WEEK_SHORT = {
    0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"
}


def format_date_ru(date_str):
    """Format date in Russian: '8 февраля 2026, воскресенье'."""
    dt = datetime.fromisoformat(date_str)
    dow = DAYS_OF_WEEK_RU[dt.weekday()]
    return f"{dt.day} {MONTHS_RU[dt.month]} {dt.year}, {dow}"


def format_date_short(date_str):
    """Format short date with day of week: '8 фев, вс'."""
    dt = datetime.fromisoformat(date_str)
    months_short = {1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "мая", 6: "июн",
                    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"}
    dow = DAYS_OF_WEEK_SHORT[dt.weekday()]
    return f"{dt.day} {months_short[dt.month]}, {dow}"


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


def escape_html_preserve_links(text):
    """Escape HTML but preserve <a> tags."""
    # Temporarily protect <a> tags
    links = {}
    def save_link(m):
        key = f'\x00LINK{len(links)}\x00'
        links[key] = m.group(0)
        return key
    text = re.sub(r'<a\s[^>]*>.*?</a>', save_link, text)

    # Escape remaining HTML
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('\n', ' ')

    # Restore <a> tags
    for key, link in links.items():
        text = text.replace(key, link)
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


def compute_business_impact_score(msg, cls):
    """Score message by business impact for TravelLine CPO."""
    score = 0
    text = msg.get('text', '').lower()

    # Direct TL impact
    if cls['tl_related']:
        score += 30
    if cls['tl_related'] and cls['sentiment'] == 'negative':
        score += 35
    if cls['tl_related'] and cls['sentiment'] == 'positive':
        score += 10

    # Direct booking signals (opportunity/threat)
    booking_keywords = ['прямые продаж', 'прямые брони', 'прямое бронирован',
                        'модуль бронирован', 'отключились от', 'ушли от яндекс',
                        'без ота', 'без агрегатор']
    if any(kw in text for kw in booking_keywords):
        score += 25

    # Competitor feature launches
    feature_keywords = ['запустил', 'новый api', 'обновлен', 'новая функц',
                        'интеграц', 'партнёрство', 'программа лояльности']
    if cls['competitors_mentioned'] and any(kw in text for kw in feature_keywords):
        score += 20

    # Regulatory / market-structural
    if cls['category'] == 'market_signal':
        score += 15

    # Engagement multiplier
    views = msg.get('views', 0) or 0
    forwards = msg.get('forwards', 0) or 0
    if views > 2000 or forwards > 50:
        score += 10

    return score


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


def extract_candidates(data):
    """Extract candidate messages for each day, output for analysis."""
    all_candidates = {}

    for date_str in DATES:
        messages = filter_by_date(data, date_str)
        messages = deduplicate_messages(messages)

        scored = []
        for msg in messages:
            cls = classify_message(msg)
            if cls['relevance'] == 'irrelevant':
                continue

            engagement = get_engagement_score(msg)
            business_score = compute_business_impact_score(msg, cls)

            scored.append({
                'channel': msg.get('channel', ''),
                'msg_id': msg.get('id', ''),
                'message_id': f"{msg.get('channel', '')}/{msg.get('id', '')}",
                'text': msg.get('text', ''),
                'sender': msg.get('sender', ''),
                'channel_name': msg.get('channel_name', ''),
                'category': msg.get('category', ''),
                'category_label': msg.get('category_label', ''),
                'date': msg.get('date', ''),
                'engagement_score': engagement,
                'business_score': business_score,
                'classification': cls,
                'views': msg.get('views', 0),
                'forwards': msg.get('forwards', 0),
                'reactions': msg.get('reactions', []),
                'source_link': get_source_link(msg)
            })

        # Sort by hybrid score: business impact (60%) + engagement (40%)
        scored.sort(key=lambda x: -(x['business_score'] * 0.6 + x['engagement_score'] * 0.4 / 1000))

        # Max 2 per channel
        selected = []
        channel_counts = {}
        for item in scored:
            ch = item['channel']
            channel_counts[ch] = channel_counts.get(ch, 0) + 1
            if channel_counts[ch] <= 2:
                selected.append(item)
            if len(selected) >= 20:
                break

        all_candidates[date_str] = selected

    return all_candidates


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


def clean_markdown(text, keep_links=False):
    """Remove markdown formatting from text, preserving URLs.
    If keep_links=True, convert [text](url) to <a> tags instead of stripping.
    """
    # Temporarily protect bare URLs from underscore removal
    urls = {}
    def save_url(m):
        key = f'\x00URL{len(urls)}\x00'
        urls[key] = m.group(0)
        return key
    text = re.sub(r'(?<!\()https?://\S+', save_url, text)

    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'[*_~`]', '', text)

    if keep_links:
        # Convert [text](url) to clickable <a> tags
        text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',
                       r'<a href="\2" target="_blank" style="color:var(--accent);text-decoration:none">\1</a>', text)
    else:
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Restore bare URLs
    for key, url in urls.items():
        text = text.replace(key, url)
    return text


def _find_first_text_line(lines):
    """Find index and cleaned text of first meaningful line (skip empty, URLs, emoji-only)."""
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue
        if re.match(r'^https?://', line_clean):
            continue
        if len(re.sub(r'[\s\U0001F000-\U0001FFFF\u2600-\u27BF\u200d\uFE0F#\-—•→←↗↘▸▾]+', '', line_clean)) == 0:
            continue
        # Remove leading emoji
        cleaned_line = re.sub(r'^[\U0001F000-\U0001FFFF\u2600-\u27BF\u200d\uFE0F\s#]+', '', line_clean).strip()
        if cleaned_line:
            return i, cleaned_line
    return -1, ''


def extract_headline_and_summary(text):
    """
    Extract a headline (full first line) and summary (up to 100 words) from message text.

    Headline: first meaningful line, full text (no truncation).
    Summary: remaining content up to 100 words, with markdown links preserved as <a> tags.
    """
    if not text:
        return '', ''

    # Clean markdown for headline (no links in headlines)
    cleaned = clean_markdown(text, keep_links=False)
    lines = cleaned.strip().split('\n')

    idx, headline = _find_first_text_line(lines)

    if not headline:
        # Entire text is URL(s)
        if re.match(r'^https?://', cleaned.strip()):
            domain_match = re.match(r'https?://(?:www\.)?([^/]+)', cleaned.strip())
            headline = f'Ссылка: {domain_match.group(1)}' if domain_match else 'Ссылка'
        return headline or 'Сообщение', ''

    # If headline turned out to be a URL, try next line
    if re.match(r'^https?://', headline):
        next_idx, next_line = _find_first_text_line(lines[idx + 1:])
        if next_line and not re.match(r'^https?://', next_line):
            headline = next_line
            idx = idx + 1 + next_idx
        else:
            domain_match = re.match(r'https?://(?:www\.)?([^/]+)', headline)
            headline = f'Ссылка: {domain_match.group(1)}' if domain_match else 'Ссылка'
            return headline, ''

    summary_start_idx = idx + 1

    # Build summary from remaining lines — use original text with links preserved
    cleaned_with_links = clean_markdown(text, keep_links=True)
    link_lines = cleaned_with_links.strip().split('\n')

    remaining_parts = []
    for line in link_lines[summary_start_idx:]:
        line_clean = line.strip()
        if not line_clean:
            continue
        # Skip bare URLs (not wrapped in <a>)
        if re.match(r'^https?://', line_clean) and '<a ' not in line_clean:
            continue
        # Skip emoji-only lines (strip <a> tags for check)
        text_only = re.sub(r'<[^>]+>', '', line_clean)
        if len(re.sub(r'[\s\U0001F000-\U0001FFFF\u2600-\u27BF\u200d\uFE0F#\-—•→←↗↘▸▾]+', '', text_only)) == 0:
            continue
        remaining_parts.append(line_clean)

    remaining_text = ' '.join(remaining_parts)
    remaining_text = re.sub(r'\s+', ' ', remaining_text).strip()

    # Count words (ignoring HTML tags for word count)
    text_for_counting = re.sub(r'<[^>]+>', '', remaining_text)
    word_count = len(text_for_counting.split())

    if word_count > 100:
        # Truncate to ~100 words while preserving HTML tags
        words_seen = 0
        result = []
        i = 0
        in_tag = False
        current_word = []
        while i < len(remaining_text):
            ch = remaining_text[i]
            if ch == '<':
                in_tag = True
                if current_word:
                    result.append(''.join(current_word))
                    current_word = []
                tag_chars = [ch]
                i += 1
                while i < len(remaining_text) and remaining_text[i] != '>':
                    tag_chars.append(remaining_text[i])
                    i += 1
                if i < len(remaining_text):
                    tag_chars.append('>')
                    i += 1
                result.append(''.join(tag_chars))
                in_tag = False
                continue
            if ch in (' ', '\t', '\n'):
                if current_word:
                    result.append(''.join(current_word))
                    current_word = []
                    words_seen += 1
                    if words_seen >= 100:
                        break
                result.append(ch)
            else:
                current_word.append(ch)
            i += 1
        if current_word:
            result.append(''.join(current_word))
        summary = ''.join(result).strip() + '...'
    elif word_count > 0:
        summary = remaining_text
    else:
        summary = ''

    return headline, summary


def generate_signal_html(msg, priority, overlay_entry=None):
    """Generate HTML for a single signal card with analysis + citation."""
    channel = msg.get('channel', '')
    channel_name = msg.get('channel_name', channel)
    link = get_source_link(msg)
    sender = msg.get('sender', '')
    reactions = format_reactions(msg.get('reactions', []))

    # Build meta line: avoid duplicating sender and channel_name
    if sender and sender != channel_name:
        meta_source = f'{sender} · {channel_name}'
    else:
        meta_source = channel_name

    if overlay_entry:
        # Analytical mode: headline + citation
        headline = escape_html(overlay_entry.get('headline', ''))
        citation = escape_html(overlay_entry.get('citation', ''))
        tl_impact = overlay_entry.get('tl_impact', '')

        citation_html = ''
        if citation:
            citation_html = f'''
        <div class="signal-citation">
          <span class="citation-mark">&laquo;</span>{citation}<span class="citation-mark">&raquo;</span>
        </div>'''

        impact_html = ''
        if tl_impact and priority == 'red':
            impact_html = f'<div class="signal-impact">{escape_html(tl_impact)}</div>'

        return f'''
    <div class="signal-card {priority}">
      <div class="signal-content">
        <div class="signal-headline">{headline}</div>
        {citation_html}
        {impact_html}
        <div class="signal-meta">
          {meta_source}
          {' · ' + reactions if reactions else ''}
        </div>
      </div>
      <div class="signal-source">
        <a href="{link}" target="_blank">Открыть →</a>
      </div>
    </div>'''
    else:
        # Auto mode: headline + summary
        headline, summary = extract_headline_and_summary(msg.get('text', ''))
        headline = escape_html(headline) if headline else 'Сообщение'
        # Summary contains <a> tags from clean_markdown(keep_links=True) — escape text but preserve links
        summary_safe = escape_html_preserve_links(summary) if summary else ''
        summary_html = f'<div class="signal-summary">{summary_safe}</div>' if summary_safe else ''

        return f'''
    <div class="signal-card {priority}">
      <div class="signal-content">
        <div class="signal-headline">{headline}</div>
        {summary_html}
        <div class="signal-meta">
          {meta_source}
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


def generate_html(date_str, messages, data, overlay=None):
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

    # Build overlay lookup for this date
    overlay_lookup = {}
    day_headline = ''
    if overlay and date_str in overlay.get('dates', {}):
        day_overlay = overlay['dates'][date_str]
        day_headline = day_overlay.get('day_headline', '')
        for signal in day_overlay.get('signals', []):
            key = signal.get('message_id', '')
            overlay_lookup[key] = signal

        # Override priority groups from overlay
        if overlay_lookup:
            red, yellow, green = [], [], []
            for signal in day_overlay.get('signals', []):
                msg_key = signal['message_id']
                matched = next((m for m in messages
                    if f"{m.get('channel','')}/{m.get('id','')}" == msg_key), None)
                if not matched:
                    continue
                p = signal.get('priority', 'yellow')
                if p == 'red':
                    red.append(matched)
                elif p == 'green':
                    green.append(matched)
                else:
                    yellow.append(matched)

            priority_groups['red'] = red[:5]
            priority_groups['yellow'] = yellow[:7]
            priority_groups['green'] = green[:3]

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

    headline_html = f'<div class="day-headline">{escape_html(day_headline)}</div>' if day_headline else ''

    header_html = f'''
  <div class="day-summary">
    <h1>📊 {date_ru}</h1>
    {headline_html}
  </div>'''

    # Generate priority sections
    priority_sections = ''

    if priority_groups['red']:
        priority_sections += f'''
  <div class="priority-section">
    <div class="priority-header red">
      🔴 ТРЕБУЕТ ВНИМАНИЯ <span class="priority-count">{len(priority_groups['red'])}</span>
    </div>
    <div class="priority-description">Прямая угроза или возможность для прямых бронирований TL</div>
    {''.join(generate_signal_html(m, 'red', overlay_lookup.get(f"{m.get('channel','')}/{m.get('id','')}")) for m in priority_groups['red'])}
  </div>'''

    if priority_groups['yellow']:
        priority_sections += f'''
  <div class="priority-section">
    <div class="priority-header yellow">
      🟡 МОНИТОРИТЬ <span class="priority-count">{len(priority_groups['yellow'])}</span>
    </div>
    <div class="priority-description">Действия конкурентов, регуляторика, рыночные тренды</div>
    {''.join(generate_signal_html(m, 'yellow', overlay_lookup.get(f"{m.get('channel','')}/{m.get('id','')}")) for m in priority_groups['yellow'])}
  </div>'''

    if priority_groups['green']:
        priority_sections += f'''
  <div class="priority-section">
    <div class="priority-header green">
      🟢 ПОЗИТИВ <span class="priority-count">{len(priority_groups['green'])}</span>
    </div>
    <div class="priority-description">Хорошие новости для TL, рост лояльности, партнёрства</div>
    {''.join(generate_signal_html(m, 'green', overlay_lookup.get(f"{m.get('channel','')}/{m.get('id','')}")) for m in priority_groups['green'])}
  </div>'''

    # If no priority signals, show a note
    if not priority_sections:
        priority_sections = '<p style="color:var(--text2)">Нет значимых сигналов за этот день</p>'

    stats_html = ''  # Removed: was non-informative metrics

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
  .priority-description {{
    font-size: 12px;
    color: var(--text2);
    margin: -6px 0 12px 0;
    font-style: italic;
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
  .signal-summary {{ font-size: 14px; color: var(--text2); margin-bottom: 8px; line-height: 1.5; }}
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

  /* Analytical headline (bold, larger) */
  .signal-headline {{
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 10px;
    line-height: 1.45;
  }}

  /* Citation block (italic, indented, left border) */
  .signal-citation {{
    border-left: 2px solid var(--border);
    padding: 6px 12px;
    margin: 8px 0 10px 0;
    font-style: italic;
    font-size: 13px;
    color: var(--text2);
    background: rgba(35,46,60,0.5);
    border-radius: 0 6px 6px 0;
  }}
  .citation-mark {{
    color: var(--accent);
    font-style: normal;
    font-weight: 600;
  }}

  /* TL impact note (only on red cards) */
  .signal-impact {{
    font-size: 13px;
    color: var(--accent);
    padding: 6px 10px;
    background: rgba(100,181,246,0.08);
    border-radius: 6px;
    margin-bottom: 8px;
  }}

  /* Day headline in summary */
  .day-headline {{
    font-size: 14px;
    color: var(--text2);
    margin-top: 4px;
    font-weight: 400;
  }}

  /* Day summary header (matches weekly report) */
  .day-summary {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2b3a4a 100%);
    border-radius: var(--radius);
    padding: 28px 24px;
    margin-bottom: 20px;
    border: 1px solid var(--border);
  }}
  .day-summary h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; }}

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

  /* Sources block */
  .sources-block {{
    text-align: left;
    max-width: 900px;
    margin: 0 auto 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 16px;
  }}
  .sources-block summary {{
    cursor: pointer;
    font-size: 13px;
    color: var(--text2);
    font-weight: 500;
  }}
  .sources-block summary:hover {{ color: var(--accent); }}
  .sources-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-top: 12px;
    font-size: 12px;
  }}
  .source-category {{
    display: flex;
    flex-direction: column;
    gap: 3px;
  }}
  .source-category strong {{
    color: var(--text);
    font-size: 12px;
    margin-bottom: 2px;
  }}
  .source-category a {{
    color: var(--text2);
    text-decoration: none;
  }}
  .source-category a:hover {{ color: var(--accent); }}
  .source-category span {{ color: var(--text2); }}

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
  <details class="sources-block">
    <summary>Источники: 21 канал в 5 категориях</summary>
    <div class="sources-grid">
      <div class="source-category">
        <strong>OTA-конкуренты</strong>
        <a href="https://t.me/yandex_travel_pro">Яндекс Путешествия PRO</a>
        <a href="https://t.me/extranetetg">Островок Экстранет</a>
        <a href="https://t.me/bronevik_com">Bronevik.com</a>
      </div>
      <div class="source-category">
        <strong>B2B SaaS конкуренты</strong>
        <a href="https://t.me/bnovonews">Bnovo</a>
        <a href="https://t.me/hotellab_io">Hotellab</a>
        <a href="https://t.me/otelkontur">Контур.Отель</a>
        <a href="https://t.me/bronirui_online">Бронируй Онлайн</a>
        <a href="https://t.me/uhotelsapp">Uhotels</a>
      </div>
      <div class="source-category">
        <strong>Отраслевые СМИ</strong>
        <a href="https://t.me/wrkhotel">WRKHotel</a>
        <a href="https://t.me/hotel_geek">Hotel Geek</a>
        <a href="https://t.me/russianhospitalityawards">Russian Hospitality</a>
        <a href="https://t.me/portierdenuit">Ночной портье</a>
        <a href="https://t.me/AZO_channel">Ассоциация загородных отелей</a>
        <a href="https://t.me/Hoteliernews">Новости отелей</a>
        <a href="https://t.me/HotelierPRO">Hotelier.PRO</a>
        <a href="https://t.me/frontdesk_ru">Front Desk</a>
      </div>
      <div class="source-category">
        <strong>TravelLine</strong>
        <a href="https://t.me/travelline_news">TravelLine (офиц.)</a>
      </div>
      <div class="source-category">
        <strong>Чаты отельеров</strong>
        <a href="https://t.me/chat_hotel">Закрытый чат WRKHotel</a>
        <a href="https://t.me/hotel_advisors">Hotel Advisors</a>
        <a href="https://t.me/HRSRussia">HRS Russia</a>
        <span>TL: Беседка (приватная группа)</span>
      </div>
    </div>
  </details>
  <div style="margin-top:12px">Дневной отчёт CPO News · <a href="index.html">Недельный обзор →</a></div>
</div>

</body>
</html>'''

    return html


def main():
    parser = argparse.ArgumentParser(description='Generate daily CPO reports')
    parser.add_argument('--mode', choices=['generate', 'extract', 'merge'],
                        default='generate',
                        help='generate: current behavior; extract: output candidates.json; merge: use overlay.json')
    parser.add_argument('--overlay', type=str, default=None,
                        help='Path to analysis overlay JSON')
    parser.add_argument('--candidates-out', type=str, default=None,
                        help='Path to write candidates JSON')
    args = parser.parse_args()

    print("Loading data...")
    data = load_data()

    if args.mode == 'extract':
        # Mode 1: Extract candidates for Claude analysis
        candidates = extract_candidates(data)
        out_path = Path(args.candidates_out) if args.candidates_out else CANDIDATES_FILE
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        total = sum(len(v) for v in candidates.values())
        print(f"Extracted {total} candidates across {len(DATES)} days -> {out_path}")
        return

    # Load overlay if available
    overlay = None
    if args.mode == 'merge' or args.overlay:
        overlay_path = args.overlay or str(OVERLAY_FILE)
        overlay = load_overlay(overlay_path)
        if overlay:
            print(f"Loaded overlay with {sum(len(d.get('signals',[])) for d in overlay.get('dates',{}).values())} signals")
        else:
            print(f"WARNING: Overlay not found at {overlay_path}, falling back to raw mode")

    for date_str in DATES:
        print(f"Generating {date_str}...")
        messages = filter_by_date(data, date_str)
        print(f"  Found {len(messages)} messages")

        html = generate_html(date_str, messages, data, overlay=overlay)
        output_file = OUTPUT_DIR / f"{date_str}.html"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  Saved to {output_file}")

    print(f"\nDone! Generated {len(DATES)} daily reports.")


if __name__ == "__main__":
    main()
