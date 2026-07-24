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

| Name | Status | Baseline | Notes |
|---|---|---|---|
| `TREND_4R_v1` | **ready to test** | TBD | **Current focus.** 4H with-trend, fixed 1% stop / 4% TP (4R). Built to the locked thesis (see repo-root `PRISM-SYSTEM-SPEC (1).md`). Tests whether 4R is reachable at a 1% stop. |
| `MOM_BREAK_v1` | ⏸ on hold | TBD | 5m/15m scalp. **Superseded for live use** by the 2026-06-02 conclusion that scalping doesn't fit the account-risk math — kept for reference only. |
| `DAILY_BREAK_v1` | ❌ NO-GO | PF 0.51, WR 21.2% (n=104, 24mo) | Prev-day break, 3R. Entry is the problem, not the exit: needs 28% WR to break even, gets 21%. Trailing + pyramiding evaluated 2026-07-24 across 54 sweep cells — **all 54 lose**. Pine left at v1.0.0. Harness is reusable for other exit questions. |
| `MACD_MTF_v1` | ⚠ DEPRECATED | PF 0.11, WR 14.9% | Kept as negative-baseline reference |
| `MACD_MTF_BOS_v1` | not started | — | Week 8 — adds Break-of-Structure confirmation |

The locked trading thesis driving `TREND_4R_v1`: **R-multiple is the lever, not win
rate.** 44% WR is accepted as fine; the edge is holding winners to 4R instead of
closing early. 4H timeframe, 10x (≡5x @ 2% stop), 1% stop = 10% account risk, 4% TP
= 40% gain. The crux — *does a 4H signal actually reach 4R behind a 1% stop?* — is
unproven and is exactly what `TREND_4R_v1`'s backtest is meant to settle.

## Research artifacts

- `_research/prism_fingerprint.md` — Statistical fingerprint of 2,315 PRISM v0.1 trades. Source for the discipline filters in `app/discipline.py` and the design of `MOM_BREAK_v1`.
