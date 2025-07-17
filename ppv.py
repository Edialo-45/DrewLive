"""
stream_playlist_generator.py

Event start times are extracted from the channel string when present and included in the M3U8 playlist as part of the channel name and as a custom #EXT-X-START-TIME tag.
"""

import asyncio
from playwright.async_api import async_playwright
import aiohttp
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import platform
import re

API_URL = "https://ppv.to/api/streams"

CUSTOM_HEADERS = [
    '#EXTVLCOPT:http-origin=https://veplay.top',
    '#EXTVLCOPT:http-referrer=https://veplay.top/',
    '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0'
]

ALLOWED_CATEGORIES = {
    "24/7 Streams", "Wrestling", "Football", "Basketball", "Baseball",
    "Combat Sports", "Motorsports", "Miscellaneous", "Boxing", "Darts"
}

CATEGORY_LOGOS = {
    "24/7 Streams": "http://drewlive24.duckdns.org:9000/Logos/247.png",
    "Wrestling": "http://drewlive24.duckdns.org:9000/Logos/Wrestling.png",
    "Football": "http://drewlive24.duckdns.org:9000/Logos/Soccer2.png",
    "Basketball": "http://drewlive24.duckdns.org:9000/Logos/Basketball-2.png",
    "Baseball": "http://drewlive24.duckdns.org:9000/Logos/Baseball.png",
    "Combat Sports": "http://drewlive24.duckdns.org:9000/Logos/Boxing.png",
    "Motorsports": "http://drewlive24.duckdns.org:9000/Logos/F12.png",
    "Miscellaneous": "http://drewlive24.duckdns.org:9000/Logos/247.png",
    "Boxing": "http://drewlive24.duckdns.org:9000/Logos/Boxing.png",
    "Darts": "http://drewlive24.duckdns.org:9000/Logos/Darts.png"
}

CATEGORY_TVG_IDS = {
    "24/7 Streams": "24.7.Dummy.us",
    "Football": "Soccer.Dummy.us",
    "Wrestling": "PPV.EVENTS.Dummy.us",
    "Combat Sports": "PPV.EVENTS.Dummy.us",
    "Baseball": "MLB.Baseball.Dummy.us",
    "Basketball": "Basketball.Dummy.us",
    "Motorsports": "Racing.Dummy.us",
    "Miscellaneous": "PPV.EVENTS.Dummy.us",
    "Boxing": "PPV.EVENTS.Dummy.us",
    "Darts": "Darts.Dummy.us"
}

GROUP_RENAME_MAP = {
    "24/7 Streams": "PPVLand - Live Channels 24/7",
    "Wrestling": "PPVLand - Wrestling Events",
    "Football": "PPVLand - Global Football Streams",
    "Basketball": "PPVLand - Basketball Hub",
    "Baseball": "PPVLand - Baseball Action HD",
    "Combat Sports": "PPVLand - MMA & Fight Nights",
    "Motorsports": "PPVLand - Motorsport Live",
    "Miscellaneous": "PPVLand - Random Events",
    "Boxing": "PPVLand - Boxing",
    "Darts": "PPVLand - Darts"
}

def parse_backend_time(timestr):
    try:
        h, m, s = map(int, timestr.strip().split(":"))
        now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
        return now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=h, minutes=m, seconds=s)
    except Exception as e:
        print(f"❌ Failed to parse time '{timestr}': {e}")
        return None

def convert_to_local_str(dt_obj):
    try:
        # Updated timezone to America/New_York (Eastern Time)
        local_tz = ZoneInfo("America/New_York")
        dt_local = dt_obj.astimezone(local_tz)
        is_windows = platform.system() == "Windows"
        format_str = "%b %#d, %Y %#I:%M %p" if is_windows else "%b %-d, %Y %-I:%M %p"
        return dt_local.strftime(format_str)
    except Exception as e:
        print(f"❌ Failed to format time: {e}")
        return None

async def check_m3u8_url(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://veplay.top",
            "Origin": "https://veplay.top"
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                return resp.status == 200
    except Exception as e:
        print(f"❌ Error checking {url}: {e}")
        return False

async def get_streams():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as resp:
            resp.raise_for_status()
            return await resp.json()

async def grab_m3u8_from_iframe(page, iframe_url):
    found_streams = set()

    def handle_response(response):
        if ".m3u8" in response.url:
            found_streams.add(response.url)

    page.on("response", handle_response)
    print(f"🌐 Navigating to iframe: {iframe_url}")

    try:
        await page.goto(iframe_url, timeout=15000)
    except Exception as e:
        print(f"❌ Failed to load iframe: {e}")
        page.remove_listener("response", handle_response)
        return set()

    await asyncio.sleep(2)

    try:
        box = page.viewport_size or {"width": 1280, "height": 720}
        cx, cy = box["width"] / 2, box["height"] / 2
        for i in range(4):
            if found_streams:
                break
            print(f"🖱️ Click #{i + 1}")
            try:
                await page.mouse.click(cx, cy)
            except Exception:
                pass
            await asyncio.sleep(0.3)
    except Exception as e:
        print(f"❌ Mouse click error: {e}")

    print("⏳ Waiting 5s for final stream load...")
    await asyncio.sleep(5)
    page.remove_listener("response", handle_response)

    valid_urls = set()
    for url in found_streams:
        if await check_m3u8_url(url):
            valid_urls.add(url)
        else:
            print(f"❌ Invalid or unreachable URL: {url}")
    return valid_urls

def build_m3u(streams, url_map):
    lines = ['#EXTM3U url-tvg="https://tinyurl.com/DrewLive002-epg"']
    added_urls = set()

    for s in streams:
        unique_key = f"{s['name']}::{s['category']}::{s['iframe']}"
        urls = url_map.get(unique_key, [])
        event_time = s.get('event_time')

        if not urls:
            print(f"⚠️ No working URLs for {s['name']}")
            continue

        orig_category = s["category"].strip()
        final_group = GROUP_RENAME_MAP.get(orig_category, orig_category)
        logo = CATEGORY_LOGOS.get(orig_category, "")
        tvg_id = CATEGORY_TVG_IDS.get(orig_category, "Sports.Dummy.us")

        for url in urls:
            if url in added_urls:
                continue
            added_urls.add(url)

            display_name = s["name"]
            if event_time:
                display_name = f"{display_name} [Event Time: {event_time}]"
                lines.append(f"#EXT-X-START-TIME:{event_time}")  # Custom tag for event start time

            lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{final_group}",{display_name}')
            lines.extend(CUSTOM_HEADERS)
            lines.append(url)

    return "\n".join(lines)

async def main():
    data = await get_streams()
    streams = []

    for category in data.get("streams", []):
        cat = category.get("category", "").strip()
        if cat not in ALLOWED_CATEGORIES:
            continue
        for stream in category.get("streams", []):
            iframe = stream.get("iframe")
            channel = stream.get("channel", "")
            name = stream.get("name", "Unnamed Event")
            event_time = None

            # Robust extraction of event time using regex
            match = re.search(r'\b\d{1,2}:\d{2}:\d{2}\b', channel)
            if match:
                time_part = match.group(0)
                dt = parse_backend_time(time_part)
                if dt:
                    local_time = convert_to_local_str(dt)
                    if local_time:
                        event_time = local_time
            # Do NOT append event_time to name here!

            if iframe:
                streams.append({
                    "name": name,
                    "iframe": iframe,
                    "category": cat,
                    "event_time": event_time
                })

    if not streams:
        print("🚫 No valid streams found.")
        return

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        url_map = {}
        for s in streams:
            key = f"{s['name']}::{s['category']}::{s['iframe']}"
            print(f"\n🔍 Scraping: {s['name']} ({s['category']})")
            urls = await grab_m3u8_from_iframe(page, s["iframe"])
            if urls:
                print(f"✅ Got {len(urls)} stream(s) for {s['name']}")
            url_map[key] = urls

        await browser.close()

    print("\n💾 Writing final playlist to PPVLand.m3u8 ...")
    playlist = build_m3u(streams, url_map)
    with open("PPVLand.m3u8", "w", encoding="utf-8") as f:
        f.write(playlist)

    print(f"✅ Done! Playlist saved as PPVLand.m3u8 at {datetime.utcnow().isoformat()} UTC")

if __name__ == "__main__":
    asyncio.run(main())
