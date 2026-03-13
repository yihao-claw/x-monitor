# X Monitor 🐦

Search and monitor X (Twitter) for tech news and insights using an authenticated session.

## Setup

Requires `auth_token` cookie in `/home/node/.openclaw/agents/bird/agent/secrets/x-cookies.json`.

## Usage

```bash
# Search for latest tweets
python3 x-search.py "AI agent" --count 10 --mode latest

# Search specific accounts
python3 x-search.py "from:elonmusk AI" --count 5

# Top tweets
python3 x-search.py "LLM breakthrough" --mode top
```

## Dependencies
- Python 3.11+
- Playwright with Chromium (`python3 -m playwright install chromium --with-deps`)

## Integration
Used by Bird agent for daily tech news gathering and X monitoring.
