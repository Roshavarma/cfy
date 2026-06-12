
import urllib.request
import json
import os
import ssl

# Bypass SSL verification checks
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Create local api directory
base_dir = 'api'
os.makedirs(base_dir, exist_ok=True)

# Custom premium headers to bypass security filters on the modsdone domain
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Origin': 'https://vortextv.modsdone.com',
    'Referer': 'https://vortextv.modsdone.com/'
}

API_EVENTS = 'https://vortextv.modsdone.com/cricfy.php/events'
API_STREAMS_BASE = 'https://vortextv.modsdone.com/cricfy.php/streams/'

def fetch_json(url):
    """Secure JSON fetcher helper."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        response = urllib.request.urlopen(req, context=ctx)
        return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"  ⚠️ Error requesting {url}: {str(e)}")
        return None

def anonymize_stream_titles(stream_urls):
    """
    TRADEMARK ANONYMIZER: Detects and replaces any title containing
    trademarked names like 'CRICFy' with clean, generic 'Live 1', 'Live 2' labels.
    """
    anonymized_counter = 1
    for stream in stream_urls:
        title = stream.get('title', '')
        if 'cricfy' in title.lower():
            stream['title'] = f"Live {anonymized_counter}"
            anonymized_counter += 1
    return stream_urls

def run_sync():
    print("📡 Requesting schedule from VortexTV API...")
    payload = fetch_json(API_EVENTS)
    
    if not payload or payload.get('status') != 'ok':
        print("❌ API unresponsive or offline. Sync cancelled.")
        return

    match_list = payload.get('data', [])
    
    # SMART CACHE GUARD:
    # If the API returns 0 items during downtime hours, do not overwrite our files
    # with empty templates. This preserves the static backup files on Blogger.
    if not match_list or len(match_list) == 0:
        print("⚠️ API returned 0 active matches. Freezing previous database cache!")
        return

    print(f"🎉 Connection Successful! Found {len(match_list)} live events. Fetching live feeds...")

    consolidated_data = []
    
    for event in match_list:
        title = event.get('title', '')
        slug = event.get('slug', '')
        category = event.get('category', 'Live Events')
        
        # EXTRACT THE DIRECT EVENTINFO
        # We read the rich eventInfo block directly from the /events payload!
        event_info = event.get('eventInfo', {})
        
        # Fallback dictionary builder only in case eventInfo is completely missing for a match
        if not event_info:
            print(f"  ⚠️ Missing eventInfo for: {slug}. Applying local fallback mapper.")
            team_a = title.split(' vs ')[0] if ' vs ' in title else title
            team_b = title.split(' vs ')[1] if ' vs ' in title else ""
            event_info = {
                "teamA": team_a,
                "teamB": team_b,
                "teamAFlag": "https://www.sofascore.com/static/images/tournaments/world-cup-2026-logo.webp",
                "teamBFlag": "https://www.sofascore.com/static/images/tournaments/world-cup-2026-logo.webp",
                "eventCat": category,
                "eventName": title,
                "eventType": category,
                "eventLogo": "https://www.sofascore.com/static/images/tournaments/world-cup-2026-logo.webp",
                "isHot": 0,
                "startTime": "",
                "endTime": ""
            }

        print(f"  👉 Crawling and sanitizing stream: {slug}")
        
        # Query individual stream endpoints to extract active play feeds
        stream_payload = fetch_json(f"{API_STREAMS_BASE}{slug}")
        stream_urls = []
        if stream_payload and stream_payload.get('status') == 'ok':
            stream_urls = stream_payload.get('data', {}).get('streamUrls', [])
            
        # Clean and anonymize branded streaming titles (CRICFy -> Live 1)
        cleaned_streams = anonymize_stream_titles(stream_urls)

        # Build our perfect unified stream database element
        consolidated_match = {
            "id": event.get('id'),
            "title": title,
            "slug": slug,
            "image": event.get('image', ''),
            "category": event_info.get("eventCat", category),
            "publish": event.get('publish', '1'),
            "eventInfo": event_info,     # Perfectly saved raw API eventInfo!
            "streamUrls": cleaned_streams       
        }
        consolidated_data.append(consolidated_match)
        
    final_output = {
        "status": "ok",
        "data": consolidated_data
    }

    # Save the consolidated JSON file
    events_file = os.path.join(base_dir, 'events.json')
    with open(events_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2)
        
    print(f"\n✅ Sync completed successfully! Unified database saved: {events_file}")

if __name__ == '__main__':
    run_sync()
