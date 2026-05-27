"""
Server-side discipline filters for incoming signals.

Rules derived from PRISM v0.1 fingerprint analysis
(see strategies/_research/prism_fingerprint.md):

  1. NO SATURDAY        — Sat in PRISM cost €2,606 net, PF 0.38
  2. NO REVENGE         — <5 min between trades cost €1,946, PF 0.89
  3. AVOID BLEED HOURS  — 02 UTC (PF 0.26), 11 UTC (PF 0.38) — only
                          the hours that stay bleeding across years
  4. KRAKEN ONLY        — Bybit cost €1,874 in 84 trades, PF 0.40

Rejected signals are still STORED (with status='rejected', rejection_reason
set) so the dataset stays complete — we can audit what would have happened
if a filter had been disabled, and re-run analyses going forward.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional


# Hard-coded for now; promote to lens_config if any of these need tuning later.
SKIP_DAYS_WEEKDAY        = {5}                 # Mon=0..Sun=6  →  5 = Saturday
SKIP_HOURS_UTC           = {2, 11}             # only hours that bleed across all years
COOLDOWN_MIN             = 5                   # min minutes since last accepted signal (same symbol)
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

    # 1. Saturday
    if ts.weekday() in SKIP_DAYS_WEEKDAY:
        return "filter:saturday"

    # 2. Known bleed hours
    if ts.hour in SKIP_HOURS_UTC:
        return f"filter:bleed_hour_{ts.hour:02d}utc"

    # 3. Venue
    venue = (signal.get("venue") or "").lower()
    if venue and venue not in ALLOWED_VENUES:
        return f"filter:bad_venue_{venue}"

    # 4. Cooldown
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
        "skip_days_weekday":   sorted(SKIP_DAYS_WEEKDAY),
        "skip_hours_utc":      sorted(SKIP_HOURS_UTC),
        "cooldown_min":        COOLDOWN_MIN,
        "allowed_venues":      sorted(ALLOWED_VENUES),
    }
