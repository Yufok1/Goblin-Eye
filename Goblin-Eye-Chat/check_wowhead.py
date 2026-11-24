import urllib.request
import json

for i in [6624, 16189, 20558, 250187, 281265, 273637]:
    try:
        url = f'https://nether.wowhead.com/classic/api/tooltip/{i}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"Item {i}: {data.get('name')}")
    except Exception as e:
        print(f"Item {i} error: {e}")
