#!/usr/bin/env python3
"""
X (Twitter) monitor using Brightdata MCP scraping.
Scrapes X profiles and outputs new tweets as structured JSON.

Usage:
  python3 x-search.py --handles karpathy,sama --count 5
  python3 x-search.py --handles karpathy --count 10 --state /tmp/state.json --update-state

Note: X search requires login; profile scraping works without auth via Brightdata.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SECRETS_PATH = Path("/home/node/.openclaw/agents/bird/agent/secrets/brightdata.json")
SCRAPE_SH = Path("/home/node/.openclaw/workspace/projects/x-tracker/scripts/x-scrape.sh")
CHECK_PY = Path("/home/node/.openclaw/workspace/projects/x-tracker/scripts/x-check-new.py")
STATE_PATH = Path("/home/node/.openclaw/workspace/projects/x-monitor/x-monitor-state.json")


def scrape_profile(handle: str, token: str) -> str:
    """Scrape a profile via Brightdata MCP, return markdown."""
    url = f"https://x.com/{handle.lstrip('@')}"
    result = subprocess.run(
        [str(SCRAPE_SH), url, "90"],
        capture_output=True, text=True,
        env={**os.environ, "BRIGHTDATA_API_TOKEN": token}
    )
    if result.returncode != 0:
        raise RuntimeError(f"Scrape failed for {handle}: {result.stderr}")
    return result.stdout


def check_new_tweets(markdown: str, handle: str, state_path: str, update: bool, max_tweets: int) -> dict:
    """Run x-check-new.py on scraped markdown."""
    cmd = [
        sys.executable, str(CHECK_PY),
        "--handle", handle,
        "--state", state_path,
        "--max", str(max_tweets),
    ]
    if update:
        cmd.append("--update-state")
    result = subprocess.run(cmd, input=markdown, capture_output=True, text=True)
    if result.returncode != 0:
        return {"hasNew": False, "error": result.stderr, "handle": handle}
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description="X Monitor via Brightdata")
    parser.add_argument("--handles", required=True, help="Comma-separated handles e.g. karpathy,sama")
    parser.add_argument("--count", "-n", type=int, default=5, help="Max new tweets per handle")
    parser.add_argument("--state", default=str(STATE_PATH), help="State file path")
    parser.add_argument("--update-state", action="store_true", help="Mark seen tweets")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    creds = json.loads(SECRETS_PATH.read_text())
    token = creds["BRIGHTDATA_API_TOKEN"]

    handles = [h.strip() for h in args.handles.split(",")]
    results = []

    for handle in handles:
        print(f"Scraping @{handle}...", file=sys.stderr)
        try:
            markdown = scrape_profile(handle, token)
            result = check_new_tweets(markdown, f"@{handle}", args.state, args.update_state, args.count)
            results.append(result)
            if result.get("hasNew"):
                print(f"  → {result['newCount']} new tweets", file=sys.stderr)
            else:
                print(f"  → no new tweets", file=sys.stderr)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            results.append({"hasNew": False, "error": str(e), "handle": handle})

    output = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
