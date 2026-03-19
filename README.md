# X Monitor 🐦

自動化 X/Twitter 帳號監控系統。追蹤指定帳號的最新推文，去重篩選後產出 Telegram 摘要。

## 架構

```
x-monitor/
├── x-search.py            # 單帳號 scraping + 去重（CLI 工具）
├── x-daily-run.py          # 每日批次執行（掃全部帳號 → Telegram 摘要）
├── x_search.py             # x-search 模組
├── x_rate_limiter.py       # Brightdata 月度用量追蹤（5000 req/月）
├── x-accounts.json         # 追蹤帳號清單（handle, name, category）
├── x-monitor-state.json    # 去重狀態（已見 tweet IDs）
└── x-rate-counter.json     # 月度 API 用量計數器
```

## 依賴

- Python 3.11+
- Brightdata MCP API（token 存於 `/home/node/.openclaw/agents/bird/agent/secrets/brightdata.json`）
- x-tracker 的共用腳本：`x-scrape.sh`、`x-check-new.py`（位於 `projects/x-tracker/scripts/`）

## 使用方式

### 單帳號查詢

```bash
# 查指定帳號最新推文
python3 x-search.py --handles karpathy,sama --count 5

# 查詢並更新去重狀態
python3 x-search.py --handles karpathy --count 10 --state ./x-monitor-state.json --update-state
```

### 每日批次執行

```bash
# 掃描所有帳號，產出 Telegram 格式摘要
python3 x-daily-run.py
```

### Rate Limiter 狀態

```bash
python3 x_rate_limiter.py
# Month: 2026-03
# Used:  120 / 5000 (2.4%)
# Left:  4880
```

## 追蹤帳號

編輯 `x-accounts.json`，格式：

```json
[
  {"handle": "karpathy", "name": "Andrej Karpathy", "category": "AI/LLM"},
  {"handle": "VitalikButerin", "name": "Vitalik Buterin", "category": "Crypto"}
]
```

目前追蹤 19 個帳號，涵蓋 AI/LLM、Crypto、Tech 三大類。

## 執行流程

1. 逐帳號透過 Brightdata MCP 抓取 X profile 頁面
2. `x-check-new.py` 解析 markdown、提取推文、對比 state 去重
3. 新推文格式化為 Telegram 訊息
4. Rate limiter 記錄 API 用量，月度上限 5000 次

## Cron 排程

由 Vince agent 的 `x-monitor-daily` cron job 每日 UTC 09:00 執行：

```
Job ID: cc4b1d12-9653-4345-b1bb-0952c84df692
Schedule: 0 9 * * * UTC
Timeout: 600s
```

## 注意事項

- Brightdata API 有月度預算限制（5000 req），rate limiter 會在 80% 時發出警告
- 每次 scrape 有 120 秒 timeout，避免單帳號卡住影響整體執行
- 與 `x-tracker` 專案共用 scraping 基礎設施，但各自維護帳號清單和狀態檔
