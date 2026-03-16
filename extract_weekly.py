import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('data/2026-02-16/all_channels.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

from datetime import datetime

start = datetime(2026, 2, 9)
end = datetime(2026, 2, 15, 23, 59, 59)

week_msgs = []
for cat_key, cat_data in data.items():
    channels = cat_data.get('channels', {})
    for ch_key, ch_data in channels.items():
        messages = ch_data.get('messages', [])
        for msg in messages:
            try:
                dt = datetime.fromisoformat(msg['date'].replace('+00:00','').replace('Z',''))
                if start <= dt <= end:
                    msg['_channel'] = ch_key
                    msg['_category'] = cat_key
                    week_msgs.append(msg)
            except:
                pass

print(f'Total week messages: {len(week_msgs)}')
print()