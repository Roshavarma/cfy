import urllib.request
import json
import os
import ssl
from datetime import datetime

# Bypass SSL certificate checks for Pydroid or GitHub Actions environments
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Create local api caching folder
base_dir = 'api'
os.makedirs(base_dir, exist_ok=True)

# Request headers to safely parse modsdone endpoints
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Origin': 'https://vortextv.modsdone.com',
    'Referer': 'https://vortextv.modsdone.com/'
}

API_EVENTS = 'https://vortextv.modsdone.com/cricfy.php/events'
API_STREAMS_BASE = 'https://vortextv.modsdone.com/cricfy.php/streams/'

def fetch_json(url):
    """Helper to download and parse JSON from the stream api."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        response = urllib.request.urlopen(req, context=ctx)
        return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"  ⚠️ Error requesting {url}: {str(e)}")
        return None

def anonymize_and_map_channels(raw_streams):
    """
    TRADEMARK ANONYMIZER: Replaces trademark names like 'CRICFy' with 'Live {N}',
    and adapts keys to match the 'channels_data' specification structure.
    """
    mapped_channels = []
    anonymized_counter = 1
    
    for stream in raw_streams:
        title = stream.get('title', '')
        
        # Check and clean trademark names
        if 'cricfy' in title.lower():
            title = f"Live {anonymized_counter}"
            anonymized_counter += 1
            
        # Parse stream type safely as integer
        try:
            stream_type = int(stream.get('type', 0))
        except (ValueError, TypeError):
            stream_type = 0

        mapped_channels.append({
            "title": title,
            "link": stream.get('link', ''),
            "logo": "",
            "type": stream_type,
            "api": stream.get('api', ''),
            "tokenApi": ""
        })
        
    return mapped_channels

def auto_detect_status(start_utc, end_utc):
    """Checks current time to determine match lifecycle status."""
    if not start_utc:
        return "Upcoming"
    try:
        now = datetime.utcnow()
        start = datetime.strptime(start_utc, "%Y/%m/%d %H:%M:%S +0000")
        end = datetime.strptime(end_utc, "%Y/%m/%d %H:%M:%S +0000") if end_utc else start
        
        if now >= start and now <= end:
            return "Live"
        elif now > end:
            return "Finish"
    except Exception:
        pass
    return "Upcoming"

def run_sync():
    print("📡 Requesting schedule from VortexTV API...")
    payload = fetch_json(API_EVENTS)
    
    if not payload or payload.get('status') != 'ok':
        print("❌ API unresponsive or offline. Sync cancelled.")
        return

    match_list = payload.get('data', [])
    
    # SMART CACHE GUARD:
    # If the API returns 0 items because no games are playing, 
    # we exit immediately so we don't overwrite previous good files with blank entries.
    if not match_list or len(match_list) == 0:
        print("⚠️ API returned 0 active matches. Freezing previous database cache!")
        return

    print(f"🎉 Connection Successful! Found {len(match_list)} live events. Fetching live feeds...")

    consolidated_data = []
    
    for event in match_list:
        title = event.get('title', '')
        slug = event.get('slug', '')
        category = event.get('category', 'Live Events')
        
        # Read the rich eventInfo block directly from the /events payload
        event_info = event.get('eventInfo', {})
        
        # Build fallback eventInfo block in case it is completely missing
        if not event_info:
            team_a = title.split(' vs ')[0] if ' vs ' in title else title
            team_b = title.split(' vs ')[1] if ' vs ' in title else ""
            event_info = {
                "teamA": team_a,
                "teamB": team_b,
                "teamAFlag": "https://www.sofascore.com/static/images/tournaments/world-cup-2026-logo.webp",
                "teamBFlag": "https://www.sofascore.com/static/images/tournaments/world-cup-2026-logo.webp",
                "eventName": title,
                "isHot": "0",
                "Status": "Upcoming",
                "startTime": "",
                "endTime": ""
            }

        print(f"  👉 Crawling and sanitizing stream: {slug}")
        
        # Query individual stream endpoints to extract active play feeds
        stream_payload = fetch_json(f"{API_STREAMS_BASE}{slug}")
        raw_stream_urls = []
        if stream_payload and stream_payload.get('status') == 'ok':
            raw_stream_urls = stream_payload.get('data', {}).get('streamUrls', [])
            
        # Clean titles, map types, and formats
        channels_data = anonymize_and_map_channels(raw_stream_urls)

        # Build Status indicator dynamically based on schedule
        start_time = event_info.get("startTime", "")
        end_time = event_info.get("endTime", "")
        status = auto_detect_status(start_time, end_time)
        event_info["Status"] = event_info.get("Status", status)

        # Parse ID safely to integer to match requested formatting schema
        try:
            event_id = int(event.get('id', 0))
        except (ValueError, TypeError):
            event_id = 0

        # Construct unified card data
        consolidated_match = {
            "id": event_id,
            "title": title,
            "image": event.get('image', ''),
            "cat": event_info.get("eventCat", category),
            "eventInfo": {
                "teamA": event_info.get("teamA", ""),
                "teamB": event_info.get("teamB", ""),
                "teamAFlag": event_info.get("teamAFlag", ""),
                "teamBFlag": event_info.get("teamBFlag", ""),
                "eventName": event_info.get("eventName", title),
                "isHot": str(event_info.get("isHot", "0")),
                "Status": event_info.get("Status", "Upcoming"),
                "startTime": start_time,
                "endTime": end_time
            },
            "channels_data": channels_data
        }
        consolidated_data.append(consolidated_match)

    # Format outer structure precisely as requested
    final_output = {
        "last_updated": datetime.utcnow().isoformat(),
        "event_count": len(consolidated_data),
        "events": {
            "events": consolidated_data
        }
    }

    # Save the consolidated JSON file
    events_file = os.path.join(base_dir, 'events.json')
    with open(events_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2)
        
    print(f"\n✅ Sync completed successfully! Unified database saved: {events_file}")

if __name__ == '__main__':
    run_sync()
