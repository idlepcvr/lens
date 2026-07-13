"""
Server-side discipline filters for incoming signals.

Rules re-derived 2026-07-12 from the LENS ledger itself (corrected P&L,
Bangkok = UTC+7, no DST):

  1. NO 09:00 BKK (02 UTC) — −€2,634 / 16 trades, 13% WR in 2026 alone;
                             the bleed hour right before the 10:00 BKK edge
                             (+€2,817, 59% WR).
  2. NO REVENGE            — cooldown raised 5 → 60 min (his call, 2026-07-12)
  3. KRAKEN ONLY           — Bybit cost €1,874 in 84 trades, PF 0.40

Removed 2026-07-12 — the old rules were PRISM-era and the current ledger
contradicts them:
  • NO SATURDAY — Saturday (BKK) is now his BEST weekday: +€1,024 / 39 trades /
    46% WR in 2026 alone (+€997 lifetime). The €2,606 loss was PRISM data.
  • 11 UTC bleed — 18:00 BKK is now +€911, 58% WR.

Rejected signals are still STORED (with status='rejected', rejection_reason
set) so the dataset stays complete — we can audit what would have happened
if a filter had been disabled, and re-run analyses going forward.

Robustness (permutation test, perm_test.py, 10k shuffles, 2026-07-13):
  • 09:00 BKK: p=0.007 if hour 9 had been picked in advance — but it wasn't,
    it was the worst of 24 buckets, and SOME hour looks this bad in 26% of
    pure-noise shuffles (p=0.26). Verdict: suggestive, NOT proven. Kept anyway
    (cheap insurance: one skipped hour vs a possibly-real bleed). The stored
    rejected signals are the out-of-sample evidence — re-run perm_test.py
    after ~50 more trades.
  • Saturday: its "best day" status is unremarkable (p=0.85), but the removed
    veto only needed Saturday to be not-bad, which it clearly is. Stands.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional


# Hard-coded for now; promote to lens_config if any of these need tuning later.
SKIP_HOURS_BKK           = {9}                 # hour-of-day in Bangkok (UTC+7)
COOLDOWN_MIN             = 60                  # min minutes since last accepted signal (same symbol)
ALLOWED_VENUES           = {"kraken", "kraken_futures"}   # bybit is auto-rejected


def evaluate(signal: dict, last_signal_for_symbol: Optional[dict]) -> Optional[str]:
    """Return None if signal passes all filters, or a 'filter:<rule>' reason string if rejected.

    `last_signal_for_symbol` is the most recent NON-rejected signal for the same
    symbol (or None if there is none). Used for the cooldown check.
    """
    received_at = signal.get("received_at")
    if received_at is None:
        ts = datetime.utcnow().replace(tzinfo=timezone.utc)
    elif isinstance(received_at, str):
        ts = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    elif isinstance(received_at, datetime):
        ts = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
    else:
        ts = datetime.utcnow().replace(tzinfo=timezone.utc)

    # 1. Known bleed hours, Bangkok clock
    bkk_hour = (ts + timedelta(hours=7)).hour
    if bkk_hour in SKIP_HOURS_BKK:
        return f"filter:bleed_hour_{bkk_hour:02d}bkk"

    # 2. Venue
    venue = (signal.get("venue") or "").lower()
    if venue and venue not in ALLOWED_VENUES:
        return f"filter:bad_venue_{venue}"

    # 3. Cooldown
    if last_signal_for_symbol:
        last_ts_raw = last_signal_for_symbol.get("received_at")
        if last_ts_raw:
            last_ts = datetime.fromisoformat(str(last_ts_raw).replace("Z", "+00:00"))
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            gap_min = (ts - last_ts).total_seconds() / 60
            if 0 < gap_min < COOLDOWN_MIN:
                return f"filter:cooldown_{gap_min:.0f}min"

    return None


def settings() -> dict:
    """Expose current discipline settings for the dashboard / API."""
    return {
        "skip_hours_bkk":      sorted(SKIP_HOURS_BKK),
        "cooldown_min":        COOLDOWN_MIN,
        "allowed_venues":      sorted(ALLOWED_VENUES),
    }
