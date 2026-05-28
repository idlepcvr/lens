# Strategies

Pine v6 strategies that emit LENS-schema JSON via `alert()`. Every strategy must:

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

| Name | Status | Baseline | TF | Notes |
|---|---|---|---|---|
| `MACD_MTF_v1` | ⚠ DEPRECATED | PF 0.11, WR 14.9% | 15m | Kept as negative-baseline reference only |
| `MOM_BREAK_v1` | ready to test | TBD | 5m/15m | Consolidation-break scalp — ⚠ note scalps bleed in PRISM; test before committing |
| `SWING_PULL_v1` | **ready to test** | TBD | **4h** | EMA pullback in daily trend — targets >24hr holds (the real edge bucket) |
| `DAILY_BREAK_v1` | **ready to test** | TBD | **1h/4h** | Prev-day high/low breakout — multi-day swing, 3R target |
| `MACD_MTF_BOS_v1` | not started | — | — | Week 8 — MACD + Break-of-Structure (defer until baselines done) |

### Priority testing order

Run `SWING_PULL_v1` first, then `DAILY_BREAK_v1`. Both are built for the
>24hr hold edge that PRISM data shows is real. `MOM_BREAK_v1` (scalp) is the
*least* aligned with the fingerprint — test it last and only keep it if baseline
shows PF ≥ 1.5.

## Research artifacts

- `_research/prism_fingerprint.md` — Statistical fingerprint of 2,315 PRISM v0.1 trades. Source for the discipline filters in `app/discipline.py` and the design of `MOM_BREAK_v1`.
