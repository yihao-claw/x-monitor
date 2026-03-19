#!/usr/bin/env python3
"""
X Monitor daily runner — scrape all accounts using Brightdata REST API (batch mode).
One API call for all handles (vs 19 individual MCP calls). ~15s vs 10min timeout.

Usage: python3 x-daily-run.py
"""

import json
import os
import sys
import time
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
ACCOUNTS_FILE = BASE / "x-accounts.json"
STATE_FILE = BASE / "x-monitor-state.json"
SECRETS_PATH = Path("/home/node/.openclaw/agents/bird/agent/secrets/brightdata.json")

DATASET_ID = "gd_lwxmeb2u1cniijd7t4"  # Twitter profile scraper
BASE_URL = "https://api.brightdata.com/datasets/v3"
MAX_POSTS_PER_HANDLE = 5

sys.path.insert(0, str(BASE))
from x_rate_limiter import RateLimiter, WARN_THRESHOLD


def load_token() -> str:
    return json.loads(SECRETS_PATH.read_text())["BRIGHTDATA_API_TOKEN"]


def trigger_scrape(token: str, handles: list[str], max_posts: int = MAX_POSTS_PER_HANDLE) -> str:
    """Trigger batch scrape for all handles, return snapshot_id."""
    url = f"{BASE_URL}/trigger?dataset_id={DATASET_ID}&format=json&uncompressed_webhook=true&notify=false&include_errors=true"
    payload = [{"url": f"https://x.com/{h.lstrip('@')}", "max_number_of_posts": max_posts} for h in handles]

    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, json.dumps(payload).encode()) as resp:
        data = json.loads(resp.read())
        return data["snapshot_id"]


def poll_snapshot(token: str, snapshot_id: str, timeout: int = 180, interval: int = 5) -> list:
    """Poll for results until ready or timeout."""
    url = f"{BASE_URL}/snapshot/{snapshot_id}?format=json"
    deadline = time.time() + timeout

    while time.time() < deadline:
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")

        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 202:
                pass  # Still processing
            else:
                raise

        time.sleep(interval)

    raise TimeoutError(f"Snapshot {snapshot_id} not ready after {timeout}s")


def extract_new_tweets(profile: dict, handle_key: str, seen: set, max_new: int = 3) -> list:
    """Extract new tweets from a REST API profile object."""
    posts = profile.get("posts") or []
    new_tweets = []
    for p in posts:
        post_id = str(p.get("post_id", ""))
        if not post_id or post_id in seen:
            continue
        text = p.get("description", "").strip()
        if len(text) < 5:
            continue
        new_tweets.append({
            "id": post_id,
            "date": p.get("date_posted", ""),
            "text": text,
            "url": p.get("post_url", f"https://x.com/{handle_key}/status/{post_id}"),
            "hash": hashlib.sha256(post_id.encode()).hexdigest()[:16],
        })
        if len(new_tweets) >= max_new:
            break
    return new_tweets


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seenIds": {}, "lastCheck": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def format_telegram(all_results: list) -> str:
    lines = ["🐦 *X Monitor Daily*\n"]
    has_any = False
    for r in all_results:
        if not r.get("hasNew"):
            continue
        has_any = True
        handle = r["handle"]
        name = r.get("name", handle)
        lines.append(f"*{name}* ({handle})")
        for t in r["newTweets"][:2]:
            text = t["text"][:200].replace("*", "").replace("_", "").replace("`", "")
            url = t["url"]
            date = t.get("date", "")
            lines.append(f"• [{text[:100]}...]({url}) _{date}_")
        lines.append("")
    if not has_any:
        lines.append("No new tweets found.")
    return "\n".join(lines)


def main():
    token = load_token()
    accounts = json.loads(ACCOUNTS_FILE.read_text())
    rl = RateLimiter()

    # Rate limit: batch counts as 1 request (19 handles, 1 API call)
    status = rl.status()
    print(f"[rate] {status['used']}/{status['budget']} used this month ({status['usage_pct']}%)", file=sys.stderr)

    if not rl.can_request(count=1):
        print(f"[rate] BUDGET EXHAUSTED — skipping run.", file=sys.stderr)
        print("⚠️ *X Monitor: Monthly Brightdata budget exhausted. Run skipped.*")
        return

    if status["warn"]:
        print(f"[rate] WARNING: usage >= {int(WARN_THRESHOLD*100)}% of monthly budget", file=sys.stderr)

    handles = [acc["handle"] for acc in accounts]
    handle_to_name = {acc["handle"]: acc.get("name", acc["handle"]) for acc in accounts}

    print(f"Triggering batch scrape for {len(handles)} handles...", file=sys.stderr)
    t0 = time.time()
    snapshot_id = trigger_scrape(token, handles, MAX_POSTS_PER_HANDLE)
    print(f"Snapshot: {snapshot_id}", file=sys.stderr)

    profiles = poll_snapshot(token, snapshot_id, timeout=180, interval=5)
    elapsed = time.time() - t0
    print(f"Got {len(profiles)} profiles in {elapsed:.1f}s", file=sys.stderr)

    # Record 1 API call for the batch
    rl.record(count=1, source="daily-monitor-batch", handle=f"{len(handles)}-handles")

    # Load state, process each profile
    state = load_state()
    if "seenIds" not in state:
        state["seenIds"] = {}

    all_results = []
    for profile in profiles:
        handle = str(profile.get("id", "")).lstrip("@")
        if not handle:
            continue

        handle_key = handle.lower()
        seen = set(state["seenIds"].get(handle_key, []))
        new_tweets = extract_new_tweets(profile, handle_key, seen, max_new=3)

        if new_tweets:
            # Update state
            if handle_key not in state["seenIds"]:
                state["seenIds"][handle_key] = []
            state["seenIds"][handle_key].extend([t["id"] for t in new_tweets])
            state["seenIds"][handle_key] = state["seenIds"][handle_key][-200:]
            print(f"  @{handle}: {len(new_tweets)} new", file=sys.stderr)
        else:
            print(f"  @{handle}: no new", file=sys.stderr)

        all_results.append({
            "handle": f"@{handle}",
            "name": handle_to_name.get(handle, handle),
            "hasNew": len(new_tweets) > 0,
            "newCount": len(new_tweets),
            "newTweets": new_tweets,
        })

    state["lastCheck"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    summary = format_telegram(all_results)
    s = rl.status()
    summary += f"\n\n_Brightdata: {s['used']}/{s['budget']} requests used this month ({s['usage_pct']}%)_"
    if s["warn"]:
        summary += "\n⚠️ _Usage >= 80% — approaching monthly limit_"
    print(summary)


if __name__ == "__main__":
    main()
