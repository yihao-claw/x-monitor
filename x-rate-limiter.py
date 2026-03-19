#!/usr/bin/env python3
"""
X Monitor Rate Limiter — track monthly Brightdata request usage.

Usage:
  from x_rate_limiter import RateLimiter

  rl = RateLimiter()
  if rl.can_request(count=1):
      rl.record(count=1, source="daily-monitor", handle="karpathy")
  else:
      print("Budget exhausted")
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

COUNTER_FILE = Path(__file__).parent / "x-rate-counter.json"
MONTHLY_BUDGET = 5000
WARN_THRESHOLD = 0.80  # 80%


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load() -> dict:
    if COUNTER_FILE.exists():
        data = json.loads(COUNTER_FILE.read_text())
        # Reset if new month
        if data.get("month") != _current_month():
            data = {"month": _current_month(), "used": 0, "log": []}
        return data
    return {"month": _current_month(), "used": 0, "log": []}


def _save(data: dict):
    COUNTER_FILE.write_text(json.dumps(data, indent=2))


class RateLimiter:
    def __init__(self, budget: int = MONTHLY_BUDGET):
        self.budget = budget
        self._data = _load()

    @property
    def used(self) -> int:
        return self._data["used"]

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.used)

    @property
    def usage_pct(self) -> float:
        return self.used / self.budget

    def can_request(self, count: int = 1) -> bool:
        return self.used + count <= self.budget

    def record(self, count: int = 1, source: str = "", handle: str = ""):
        self._data["used"] += count
        self._data["log"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "count": count,
            "source": source,
            "handle": handle,
        })
        # Keep only last 500 log entries
        if len(self._data["log"]) > 500:
            self._data["log"] = self._data["log"][-500:]
        _save(self._data)

    def status(self) -> dict:
        return {
            "month": self._data["month"],
            "used": self.used,
            "remaining": self.remaining,
            "budget": self.budget,
            "usage_pct": round(self.usage_pct * 100, 1),
            "warn": self.usage_pct >= WARN_THRESHOLD,
        }


if __name__ == "__main__":
    rl = RateLimiter()
    s = rl.status()
    print(f"Month: {s['month']}")
    print(f"Used:  {s['used']} / {s['budget']} ({s['usage_pct']}%)")
    print(f"Left:  {s['remaining']}")
    if s["warn"]:
        print("⚠️  WARNING: Usage >= 80% of monthly budget!")
