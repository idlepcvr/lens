# Strategies

Pine v5 strategies that emit LENS-schema JSON via `alert()`. Every strategy must:

1. **Emit every Setup + Trade-plan field** in the JSON payload (see `app/models.py::SignalIngest`).
2. **Bump `strategyVersion`** on any logic change.
3. **Store its baseline in `BASELINE.md`** before going live.

## Setting up an alert in TradingView

1. Open the strategy on a chart in TradingView.
2. Click **Alerts → Create Alert**.
3. **Condition:** select the strategy → `alert() function calls only`.
4. **Message:** leave as `{{message}}` (the JSON is built inside Pine).
5. **Notifications tab:**
   - **Week 2 (now):** check "Webhook URL" but leave it blank or point to a placeholder. Copy the alert message text to validate it parses.
   - **Week 3+ (ingestion decided):** set "Webhook URL" to your chosen ingestion path (Cloudflare-tunneled `/api/signals`, email-to-poll, or phone-tap URL).
6. **Expiration:** open-ended.
7. **Alert frequency:** "Once per bar close" — Pine `alert()` enforces this via `freq_once_per_bar_close`.

## Manual webhook smoke test

Take an alert message TradingView fired (or one constructed by hand) and pipe it into the dev server:

```bash
curl -X POST http://localhost:8765/api/signals \
  -H "Content-Type: application/json" \
  -d '<paste alert message JSON here>'
```

A `201 Created` with the full signal row means schema parses. A `422` means a field is missing or wrong-typed — fix the Pine, bump the version.

## Current strategies

| Name | Status | Baseline | Notes |
|---|---|---|---|
| `MACD_MTF_v1` | scaffold | TBD | Week 2 build, first live strategy |
| `MACD_MTF_BOS_v1` | not started | — | Week 8 — adds Break-of-Structure confirmation |
