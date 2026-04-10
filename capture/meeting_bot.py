import argparse
import asyncio
import os
from datetime import datetime

import requests
from playwright.async_api import async_playwright


def detect_platform(url: str) -> str:
    if "meet.google.com" in url:
        return "google_meet"
    if "zoom.us" in url:
        return "zoom_web"
    if "teams.microsoft.com" in url:
        return "microsoft_teams_web"
    return "unknown"


def post_chunk(api_base: str, meeting_id: str, chunk: str, participants: list[str]) -> None:
    payload = {
        "meeting_id": meeting_id,
        "chunk": chunk,
        "participants": participants,
    }
    requests.post(f"{api_base}/transcript/chunk", json=payload, timeout=10)


async def auto_join(page, platform: str) -> None:
    if platform == "google_meet":
        for selector in ["button:has-text('Join now')", "button:has-text('Ask to join')"]:
            button = page.locator(selector)
            if await button.count() > 0:
                await button.first.click()
                return

    if platform == "zoom_web":
        selector = "button:has-text('Join')"
        button = page.locator(selector)
        if await button.count() > 0:
            await button.first.click()
            return

    if platform == "microsoft_teams_web":
        selector = "button:has-text('Join now')"
        button = page.locator(selector)
        if await button.count() > 0:
            await button.first.click()
            return


async def extract_participants(page) -> list[str]:
    selectors = [
        "[data-participant-id] [data-self-name]",
        "[data-participant-id] [data-name]",
        "[data-tid='roster-list-item'] [data-tid='display-name']",
        "[class*='participants'] [class*='name']",
    ]

    names = set()
    for selector in selectors:
        nodes = page.locator(selector)
        count = await nodes.count()
        for idx in range(min(count, 40)):
            text = (await nodes.nth(idx).inner_text()).strip()
            if text:
                names.add(text)

    return list(names)


async def extract_captions(page) -> list[str]:
    selectors = [
        "[aria-live='polite']",
        "[data-is-caption='true']",
        "[class*='caption']",
        "[class*='transcript']",
        "[data-tid='closed-caption-text']",
    ]

    lines = []
    for selector in selectors:
        nodes = page.locator(selector)
        count = await nodes.count()
        for idx in range(min(count, 30)):
            text = (await nodes.nth(idx).inner_text()).strip()
            if 4 <= len(text) <= 320:
                lines.append(text)

    return lines


async def run_bot(meeting_url: str, api_base: str, meeting_id: str, headless: bool) -> None:
    platform = detect_platform(meeting_url)
    seen_lines = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(meeting_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await auto_join(page, platform)

        print(f"[{datetime.utcnow().isoformat()}] Joined meeting: {meeting_url}")

        while True:
            participants = await extract_participants(page)
            lines = await extract_captions(page)

            for line in lines:
                if line in seen_lines:
                    continue
                seen_lines.add(line)
                if len(seen_lines) > 800:
                    seen_lines = set(list(seen_lines)[-300:])
                post_chunk(api_base, meeting_id, line, participants)

            await asyncio.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Meeting capture bot (Playwright)")
    parser.add_argument("--meeting-url", required=True, help="Meeting URL")
    parser.add_argument("--api-base", default=os.getenv("API_BASE", "http://localhost:8000"))
    parser.add_argument("--meeting-id", required=True)
    parser.add_argument("--headless", action="store_true", help="Run Chromium headless")
    args = parser.parse_args()

    asyncio.run(run_bot(args.meeting_url, args.api_base, args.meeting_id, args.headless))


if __name__ == "__main__":
    main()
