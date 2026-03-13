#!/usr/bin/env python3
"""
X (Twitter) search using Playwright with authenticated session.
Searches for tweets and outputs structured JSON.

Usage:
  python3 x-search.py "AI agent" --count 10
  python3 x-search.py "from:elonmusk AI" --count 5 --mode latest
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

SECRETS_PATH = Path("/home/node/.openclaw/agents/bird/agent/secrets/x-cookies.json")


async def search_x(query: str, count: int = 10, mode: str = "latest"):
    from playwright.async_api import async_playwright

    creds = json.loads(SECRETS_PATH.read_text())

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )

        await context.add_cookies([{
            "name": "auth_token",
            "value": creds["auth_token"],
            "domain": ".x.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
        }])

        page = await context.new_page()

        # Build search URL
        mode_param = "live" if mode == "latest" else "top"
        from urllib.parse import quote
        url = f"https://x.com/search?q={quote(query)}&src=typed_query&f={mode_param}"

        print(f"Searching X: {query} (mode={mode})", file=sys.stderr)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # Scroll to load more tweets if needed
        tweet_count = await page.locator('[data-testid="tweet"]').count()
        scroll_attempts = 0
        while tweet_count < count and scroll_attempts < 5:
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(2000)
            tweet_count = await page.locator('[data-testid="tweet"]').count()
            scroll_attempts += 1

        # Extract tweets
        tweets = []
        tweet_els = page.locator('[data-testid="tweet"]')
        actual_count = min(count, await tweet_els.count())

        for i in range(actual_count):
            try:
                el = tweet_els.nth(i)
                text = await el.inner_text()
                
                # Parse the tweet text structure
                lines = text.strip().split("\n")
                
                # Try to extract username, handle, time
                tweet_data = {
                    "index": i,
                    "raw_text": text[:500],
                }

                # Look for links
                links = await el.locator("a[href*='/status/']").all()
                for link in links:
                    href = await link.get_attribute("href")
                    if href and "/status/" in href:
                        tweet_data["url"] = f"https://x.com{href}" if href.startswith("/") else href
                        break

                tweets.append(tweet_data)
            except Exception as e:
                print(f"Error extracting tweet {i}: {e}", file=sys.stderr)

        await browser.close()

        result = {
            "query": query,
            "mode": mode,
            "count": len(tweets),
            "tweets": tweets,
        }
        return result


def main():
    parser = argparse.ArgumentParser(description="Search X (Twitter)")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--count", "-n", type=int, default=10, help="Number of tweets")
    parser.add_argument("--mode", "-m", choices=["latest", "top"], default="latest")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    result = asyncio.run(search_x(args.query, args.count, args.mode))

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
