from datetime import datetime
from zoneinfo import ZoneInfo
import re
from playwright.async_api import Request

async def scrape_stream_url(context, url):
    m3u8_links = set()
    event_name = "Unknown Event"
    event_datetime_et = None
    page = await context.new_page()

    def capture_request(request: Request):
        if ".m3u8" in request.url.lower() and not m3u8_links:
            print(f"🎯 Found stream: {request.url}")
            m3u8_links.add(request.url)

    page.on("request", capture_request)

    try:
        if not await safe_goto(page, url):
            return event_name, [], None
        await asyncio.sleep(1)

        # Extract event title
        event_name = await page.evaluate("""
            () => {
                const selectors = ['h1', '.event-title', '.title', '.stream-title'];
                for (let sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) return el.textContent.trim();
                }
                return document.title.trim();
            }
        """)

        # Extract date and time from page
        date_time_str = await page.evaluate("""
            () => {
                let dateEl = document.querySelector('.event-date') || document.querySelector('.date');
                let timeEl = document.querySelector('.event-time') || document.querySelector('.time');
                let date = dateEl ? dateEl.textContent.trim() : "";
                let time = timeEl ? timeEl.textContent.trim() : "";
                if (date && time) return date + " " + time;
                if (date) return date;
                if (time) return time;
                return document.title;
            }
        """)

        # Parse date and time, convert to ET
        event_datetime_et = None
        if date_time_str:
            matches = re.search(r'([A-Za-z]+ \d{1,2}, \d{4})\s+(\d{1,2}:\d{2} ?[APMapm]{2})', date_time_str)
            if matches:
                date_str, time_str = matches.groups()
                try:
                    dt_naive = datetime.strptime(f"{date_str} {time_str}", "%B %d, %Y %I:%M %p")
                    dt_et = dt_naive.replace(tzinfo=ZoneInfo("America/New_York"))
                    event_datetime_et = dt_et
                except Exception as e:
                    print(f"❌ Date parsing failed: {e}")

        await page.mouse.click(500, 500)
        for _ in range(10):
            if m3u8_links:
                break
            await asyncio.sleep(0.5)

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return event_name, list(m3u8_links), event_datetime_et
