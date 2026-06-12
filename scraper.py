import urllib.request
import json
import os
import ssl

# Bypass SSL verification checks (prevents environment certificate blocks)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Create our local api cache folder structure
base_dir = 'api'
os.makedirs(base_dir, exist_ok=True)

# Custom request headers to pass through VortexTV Cloudflare protections
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Origin': 'https://vortextv.modsdone.com',
    'Referer': 'https://vortextv.modsdone.com/'
}

API_EVENTS = 'https://vortextv.modsdone.com/cricfy.php/events'
API_STREAMS_BASE = 'https://vortextv.modsdone.com/cricfy.php/streams/'

def fetch_json(url):
    """Helper to fetch raw data and parse it safely into JSON."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        response = urllib.request.urlopen(req, context=ctx)
        return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"  ⚠️ Error fetching: {url} -> {str(e)}")
        return None

def anonymize_stream_titles(stream_urls):
    """
    TRADEMARK ANONYMIZER: Replaces any streaming feed titles containing
    trademarked names like 'CRICFy' with clean, generic labels.
    """
    anonymized_counter = 1
    for stream in stream_urls:
        title = stream.get('title', '')
        if 'cricfy' in title.lower():
            stream['title'] = f"Live {anonymized_counter}"
            anonymized_counter += 1
    return stream_urls

def auto_detect_event_info(title, category):
    """
    HEURISTICS ENGINE: Rebuilds detailed event maps (teams, flags, timers)
    by parsing match title strings dynamically.
    """
    title_lower = title.lower()
    detected_cat = "Live Events"
    
    # Detect Category
    if any(k in title_lower for k in ["wwe", "raw", "smackdown", "nxt", "ufc", "fight", "boxing", "aew"]):
        detected_cat = "WWE & Combat"
    elif any(k in title_lower for k in ["f1", "motogp", "formula-1", "grand prix", "racing"]):
        detected_cat = "Motorsport"
    elif any(k in title_lower for k in ["cricket", "vs", "t20", "odi", "test"]):
        if any(k in title_lower for k in ["fc", "united", "real", "athletic", "city", "club", "cup", "league"]):
            detected_cat = "Football"
        else:
            detected_cat = "Cricket"
            
    if category and category != "Live Events":
        detected_cat = category

    # Extract Team Names
    team_a = title
    team_b = ""
    for separator in [" vs ", " Vs ", " VS "]:
        if separator in title:
            parts = title.split(separator)
            team_a = parts[0].strip()
            team_b = parts[1].strip()
            break

    # Generate Country Flags & Logos using Sofascore static asset servers
    logo_a = "https://www.sofascore.com/static/images/tournaments/world-cup-2026-logo.webp"
    logo_b = "https://www.sofascore.com/static/images/tournaments/world-cup-2026-logo.webp"

    if team_b:
        slug_a = team_a.lower().replace(" women", "").replace(" ", "-")
        slug_b = team_b.lower().replace(" women", "").replace(" ", "-")
        logo_a = f"https://www.sofascore.com/static/images/flags/{slug_a}.png"
        logo_b = f"https://www.sofascore.com/static/images/flags/{slug_b}.png"

    if detected_cat == "WWE & Combat":
        logo_a = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/03/WWE_Logo.svg/2243px-WWE_Logo.svg.png"
    elif detected_cat == "Motorsport":
        logo_a = "https://www.sofascore.com/static/images/tournaments/formula-1-logo.webp"

    return {
        "teamA": team_a,
        "teamB": team_b,
        "teamAFlag": logo_a,
        "teamBFlag": logo_b,
        "eventCat": detected_cat,
        "eventName": title,
        "eventType": detected_cat if team_b == "" else f"{detected_cat} Duel",
        "eventLogo": logo_a,
        "isHot": 1 if "wwe" in title_lower or "f1" in title_lower or "motogp" in title_lower else 0,
        "startTime": "",
        "endTime": ""
    }

def run_sync():
    print("📡 Requesting schedule from VortexTV API...")
    payload = fetch_json(API_EVENTS)
    
    if not payload or payload.get('status') != 'ok':
        print("❌ API unresponsive or offline. Sync cancelled.")
        return

    match_list = payload.get('data', [])
    
    # SMART CACHE GUARD:
    # If API returns 0 items during hours with no active schedules,
    # we exit immediately to keep our previous static database active on Blogger!
    if not match_list or len(match_list) == 0:
        print("⚠️ API returned 0 active matches. Freezing offline cache so site never goes blank!")
        return

    print(f"🎉 API Online! Found {len(match_list)} matches. Compiling streaming links...")

    consolidated_data = []
    
    for event in match_list:
        title = event.get('title', '')
        category = event.get('category', 'Live Events')
        slug = event.get('slug', '')
        
        print(f"  👉 Processing: {slug}...")
        
        # 1. Resolve match categorizations and design structures
        enriched_info = auto_detect_event_info(title, category)
        
        # 2. Extract play streams
        stream_payload = fetch_json(f"{API_STREAMS_BASE}{slug}")
        stream_urls = []
        if stream_payload and stream_payload.get('status') == 'ok':
            stream_urls = stream_payload.get('data', {}).get('streamUrls', [])
            
        # 3. Clean and anonymize branded streaming titles (CRICFy -> Live 1)
        cleaned_streams = anonymize_stream_titles(stream_urls)

        # 4. Construct unified card data
        consolidated_match = {
            "id": event.get('id'),
            "title": title,
            "slug": slug,
            "image": event.get('image', ''),
            "category": enriched_info["eventCat"],
            "publish": event.get('publish', '1'),
            "eventInfo": enriched_info,     
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
        
    print(f"\n✅ Synchronization successful! Unified DB saved at: {events_file}")

if __name__ == '__main__':
    run_sync()
