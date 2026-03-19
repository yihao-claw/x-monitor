#!/usr/bin/env python3
"""
X Monitor daily runner — scrape all accounts in x-accounts.json,
collect new tweets, format a Telegram summary.

Usage: python3 x-daily-run.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
ACCOUNTS_FILE = BASE / "x-accounts.json"
STATE_FILE = BASE / "x-monitor-state.json"
SECRETS_PATH = Path("/home/node/.openclaw/agents/bird/agent/secrets/brightdata.json")
SCRAPE_SH = Path("/home/node/.openclaw/workspace/projects/x-tracker/scripts/x-scrape.sh")
CHECK_PY = Path("/home/node/.openclaw/workspace/projects/x-tracker/scripts/x-check-new.py")

sys.path.insert(0, str(BASE))
from x_rate_limiter import RateLimiter, WARN_THRESHOLD


def scrape_profile(handle: str, token: str) -> str:
    url = f"https://x.com/{handle.lstrip('@')}"
    result = subprocess.run(
        [str(SCRAPE_SH), url, "90"],
        capture_output=True, text=True,
        env={**os.environ, "BRIGHTDATA_API_TOKEN": token}
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def check_new(markdown: str, handle: str, state: str) -> dict:
    cmd = [sys.executable, str(CHECK_PY), "--handle", handle,
           "--state", state, "--update-state", "--max", "3"]
    result = subprocess.run(cmd, input=markdown, capture_output=True, text=True)
    if result.returncode != 0:
        return {"hasNew": False, "handle": handle}
    return json.loads(result.stdout)


def format_telegram(all_results: list) -> str:
    lines = ["🐦 *X Monitor Daily*\n"]
    has_any = False
    for r in all_results:
        if not r.get("hasNew"):
            continue
        has_any = True
        handle = r["handle"]
        lines.append(f"*{handle}*")
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
    creds = json.loads(SECRETS_PATH.read_text())
    token = creds["BRIGHTDATA_API_TOKEN"]
    accounts = json.loads(ACCOUNTS_FILE.read_text())
    rl = RateLimiter()

    # Pre-flight budget check
    needed = len(accounts)
    status = rl.status()
    print(f"[rate] {status['used']}/{status['budget']} used this month ({status['usage_pct']}%)", file=sys.stderr)

    if not rl.can_request(count=needed):
        print(f"[rate] BUDGET EXHAUSTED — skipping run. Remaining: {rl.remaining}", file=sys.stderr)
        print("⚠️ *X Monitor: Monthly Brightdata budget exhausted. Run skipped.*")
        return

    if status["warn"]:
        print(f"[rate] WARNING: usage >= {int(WARN_THRESHOLD*100)}% of monthly budget", file=sys.stderr)

    all_results = []
    for acc in accounts:
        handle = acc["handle"]
        print(f"Checking @{handle}...", file=sys.stderr)
        if not rl.can_request(count=1):
            print(f"  → budget hit mid-run, stopping", file=sys.stderr)
            break
        try:
            md = scrape_profile(handle, token)
            rl.record(count=1, source="daily-monitor", handle=handle)
            if not md.strip():
                print(f"  → empty response", file=sys.stderr)
                continue
            r = check_new(md, f"@{handle}", str(STATE_FILE))
            all_results.append(r)
            if r.get("hasNew"):
                print(f"  → {r['newCount']} new", file=sys.stderr)
            else:
                print(f"  → no new", file=sys.stderr)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    summary = format_telegram(all_results)
    # Append usage footer
    s = rl.status()
    summary += f"\n\n_Brightdata: {s['used']}/{s['budget']} requests used this month ({s['usage_pct']}%)_"
    if s["warn"]:
        summary += "\n⚠️ _Usage >= 80% — approaching monthly limit_"
    print(summary)


if __name__ == "__main__":
    main()
