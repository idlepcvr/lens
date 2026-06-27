"""
PRISM — Kraken Futures fill sync.

Uses python-kraken-sdk:  from kraken.futures import User, Market
Fills come from User.get_execution_events() (paginated, newest-first).
EUR/USD rate comes from Market.get_tickers() (PF_EURUSD).
EUR balance timeline from User.get_account_log() for leverage / balance_after.

Each completed round-trip trade (position opens then returns to ~0) is emitted
as one trade dict that maps directly to the SQLite trades table.
"""

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional


def _retry(fn, tries: int = 3, delay: float = 2.0):
    """Call fn(), retrying on any error (Kraken read-timeouts are intermittent).
    A full sync makes ~20+ sequential calls; without this, one hung request
    fails the whole run. Endpoints normally answer in ~1s, so retries are rare."""
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — transient network, retry all
            last = e
            time.sleep(delay)
    raise last

from dotenv import load_dotenv
from kraken.futures import User, Market

load_dotenv()

# The SDK defaults to a 10s read timeout. The fill-history endpoints
# (get_execution_events / get_account_log) occasionally exceed it on a cold
# connection — which silently fails the WHOLE hourly sync, so trades stop
# importing even though the (fast) balance call still works. The call itself
# returns in ~1s; 30s just absorbs transient network blips.
User.TIMEOUT = 30
Market.TIMEOUT = 30


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_ts(t) -> datetime:
    """Accept ms-integer, ISO string, or datetime → UTC datetime."""
    if isinstance(t, datetime):
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(t / 1000, tz=timezone.utc)
    s = str(t).replace("Z", "+00:00").replace("+00:00+00:00", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)


def _symbol(kraken_sym: str) -> str:
    """Map Kraken contract name → clean display name."""
    s = kraken_sym.upper()
    if "XBT" in s or "BTC" in s:
        return "BTC/USD"
    return kraken_sym


def _market_type(kraken_sym: str) -> str:
    """PF_ = perpetual futures, PI_ = inverse perpetual, FI_ = fixed-date."""
    s = kraken_sym.upper()
    if s.startswith("PF_"):
        return "perpetual"
    if s.startswith("PI_"):
        return "inverse"
    if s.startswith("FI_"):
        return "fixed"
    return "unknown"


def _wavg(fills: list[dict]) -> float:
    total_sz = sum(f["_qty"] for f in fills)
    if total_sz == 0:
        return 0.0
    return sum(f["_qty"] * f["price"] for f in fills) / total_sz


def _balance_at(timeline: list[tuple], target_ts: datetime) -> Optional[float]:
    """Return the EUR balance most recently recorded at or before target_ts."""
    val = None
    for ts, bal in timeline:
        if ts <= target_ts:
            val = bal
        else:
            break
    return val


# ─── Market data ──────────────────────────────────────────────────────────────

def _get_eur_usd(market_client: Market) -> float:
    try:
        for tk in _retry(lambda: market_client.get_tickers()).get("tickers", []):
            if tk.get("symbol") == "PF_EURUSD":
                rate = tk.get("last") or tk.get("markPrice")
                if rate:
                    return float(rate)
    except Exception:
        pass
    return 1.10   # safe fallback


# ─── Deposits & Withdrawals ───────────────────────────────────────────────────

def _build_transfers(raw_logs: list[dict]) -> list[dict]:
    """
    Extract deposit/withdrawal/transfer entries from account log.
    Kraken sets type='?' for all entries; the real classification is in 'info'.
    Returns list of transfer dicts ready for upsert_transfer().
    """
    transfers = []
    transfer_keywords = {"transfer", "deposit", "withdrawal", "cross-exchange"}
    for entry in raw_logs:
        info   = str(entry.get("info", "")).lower()
        t_type = str(entry.get("type", "")).lower()
        # Match on info field (Kraken Futures uses this) or type field
        if not any(kw in info for kw in transfer_keywords) and \
           not any(kw in t_type for kw in transfer_keywords):
            continue
        change = entry.get("amount") or entry.get("change")
        if change is None:
            # Derive from balance change
            old = entry.get("old_balance")
            new = entry.get("new_balance")
            if old is not None and new is not None:
                change = float(new) - float(old)
            else:
                continue
        try:
            amount = float(change)
            transfers.append({
                "kraken_id":     str(entry.get("id") or entry.get("uid") or entry.get("booking_uid") or entry.get("date")),
                "transfer_type": "deposit" if amount > 0 else "withdrawal",
                "asset":         entry.get("asset", "eur"),
                "amount":        amount,
                "balance_after": float(entry.get("new_balance") or 0),
                "ts":            _parse_ts(entry["date"]),
            })
        except Exception:
            continue
    return transfers


# ─── EUR balance timeline ─────────────────────────────────────────────────────

def _build_eur_timeline(user_client: User) -> tuple[list[tuple], list[dict]]:
    """
    Return (timeline, raw_logs) where:
    - timeline: list of (datetime, eur_balance) sorted oldest-first
    - raw_logs: all raw account log entries (used for transfer extraction)

    Paginates get_account_log() using the `before` entry-ID cursor to fetch
    the complete account history (not just the most recent 2000 entries).
    """
    timeline     = []
    all_raw_logs = []
    try:
        before = None
        while True:
            kwargs = {"count": 1000}
            if before is not None:
                kwargs["before"] = before

            log      = _retry(lambda: user_client.get_account_log(**kwargs))
            raw_logs = log.get("logs", [])
            if not raw_logs:
                break

            all_raw_logs.extend(raw_logs)

            for entry in raw_logs:
                if entry.get("asset") != "eur":
                    continue
                bal = entry.get("new_balance")
                if bal is None:
                    continue
                try:
                    timeline.append((_parse_ts(entry["date"]), float(bal)))
                except Exception:
                    continue

            # Paginate: `before` = smallest entry id in this page
            ids = [int(e["id"]) for e in raw_logs if e.get("id") is not None]
            if not ids or len(raw_logs) < 1000:
                break
            before = min(ids)

    except Exception:
        pass
    return sorted(timeline, key=lambda x: x[0]), all_raw_logs


# ─── Pull fills ───────────────────────────────────────────────────────────────

def _pull_fills(user_client: User, since_dt: datetime) -> list[dict]:
    """
    Paginate get_execution_events() newest-first.
    Stop when fill timestamp is older than since_dt.
    Returns all fills sorted oldest-first.
    """
    since_ts = int(since_dt.timestamp() * 1000)
    fills    = []
    cont     = None

    while True:
        kwargs = {"sort": "desc"}
        if cont:
            kwargs["continuation_token"] = cont

        resp     = _retry(lambda: user_client.get_execution_events(**kwargs))
        elements = resp.get("elements", [])

        if not elements:
            break

        done = False
        for el in elements:
            try:
                exec_data = el["event"]["execution"]["execution"]
                ts_ms     = exec_data["timestamp"]

                if ts_ms < since_ts:
                    done = True
                    break

                order    = exec_data["order"]
                fee_info = (exec_data.get("orderData") or {}).get("feeCalculationInfo") or {}

                # Fee rate — "percentageFee" is a PERCENT (verified live: "0.05000000"
                # = 0.05%), so → fraction is /100. (Was /100/100 = 100× too small.)
                raw_fee_pct = fee_info.get("percentageFee")
                fee_pct = float(raw_fee_pct) / 100 if raw_fee_pct is not None else 0.0005

                # Maker vs taker: taker fee ~0.05%, maker ~0.02% (or rebate)
                fill_type = "maker" if fee_pct <= 0.0002 else "taker"

                fills.append({
                    "fill_id":        exec_data.get("uid", ""),
                    "order_id":       order.get("uid", ""),
                    "symbol":         order.get("tradeable", "PF_XBTUSD"),
                    "side":           order.get("direction", "buy").lower(),
                    "order_type":     order.get("orderType", "market").lower(),
                    "size":           float(exec_data.get("quantity", 0)),
                    "price":          float(exec_data.get("price", 0)),
                    "fee_pct":        fee_pct,
                    "fill_type":      fill_type,
                    "pos_size_after": float((exec_data.get("orderData") or {}).get("positionSize", 0)),
                    "funding":        float((exec_data.get("orderData") or {}).get("unrealizedFunding", 0) or 0),
                    "fill_time":      _parse_ts(ts_ms),
                })
            except (KeyError, TypeError, ValueError):
                continue

        if done:
            break

        cont = resp.get("continuationToken")
        if not cont:
            break

    return sorted(fills, key=lambda f: f["fill_time"])


# ─── Build trades (position tracking) ────────────────────────────────────────

def _build_trades(
    fills:        list[dict],
    eur_timeline: list[tuple],
    eur_usd:      float,
) -> list[dict]:
    """
    Convert raw fills into completed trade records using position tracking.
    When running position returns to ~0 a round-trip trade is emitted.
    """
    if not fills:
        return []

    position   = 0.0
    open_fills = []   # fills that make up the current open leg
    trades_out = []

    def _record(opening_fills, close_fill, close_size, trade_side):
        entry_avg  = _wavg(opening_fills)
        exit_price = close_fill["price"]

        if trade_side == "LONG":
            pnl_usd = (exit_price - entry_avg) * close_size
        else:
            pnl_usd = (entry_avg - exit_price) * close_size

        open_fee_usd   = sum(f["_qty"] * f["price"] * f["fee_pct"] for f in opening_fills)
        close_fee_usd  = close_size * exit_price * close_fill["fee_pct"]
        total_fees_usd = open_fee_usd + close_fee_usd
        pnl_usd       -= total_fees_usd

        pnl_eur        = round(pnl_usd / eur_usd, 2)
        fees_eur       = round(total_fees_usd / eur_usd, 6)
        close_ts       = close_fill["fill_time"]
        open_time      = opening_fills[0]["fill_time"]
        notional_usd   = close_size * entry_avg
        notional_eur   = notional_usd / eur_usd

        balance_after  = _balance_at(eur_timeline, close_ts)
        balance_before = (balance_after - pnl_eur) if balance_after is not None else None
        try:
            leverage = max(1, round(notional_eur / balance_before)) if balance_before and balance_before > 0 else 1
        except Exception:
            leverage = 1

        # Fill metadata for the round-trip
        all_fills   = opening_fills + [dict(close_fill, _qty=close_size)]
        fill_types  = {f["fill_type"] for f in all_fills}
        order_types = {f["order_type"] for f in all_fills}
        fill_type   = next(iter(fill_types)) if len(fill_types) == 1 else "mixed"
        order_type  = next(iter(order_types)) if len(order_types) == 1 else "mixed"
        funding_cost = round(abs(close_fill.get("funding", 0)) / eur_usd, 6)
        open_sz      = sum(f["_qty"] for f in opening_fills)
        contract     = close_fill["symbol"]

        trades_out.append({
            "symbol":          _symbol(contract),
            "contract":        contract,
            "market_type":     _market_type(contract),
            "venue":           "kraken_futures",
            "direction":       "long" if trade_side == "LONG" else "short",
            "entry":           round(entry_avg, 2),
            "exit":            round(exit_price, 2),
            "size":            round(open_sz, 6),
            "leverage":        int(leverage),
            "pnl":             pnl_eur,
            "fees":            fees_eur,
            "funding_cost":    funding_cost,
            "fill_type":       fill_type,
            "order_type":      order_type,
            "fill_uuid":       close_fill["fill_id"],
            "kraken_order_id": close_fill["order_id"],
            "fill_count":      len(all_fills),
            "opened_at":       open_time,
            "closed_at":       close_ts,
            "balance_after":   round(balance_after, 2) if balance_after is not None else None,
            "balance_before":  round(balance_before, 2) if balance_before is not None else None,
            "notes":           None,
        })

    for fill in fills:
        qty  = fill["size"]
        side = fill["side"]  # "buy" | "sell"

        if side == "buy":
            if position < -1e-6:
                # Closing a short
                close_qty = min(qty, abs(position))
                used      = []
                remaining = close_qty
                for of in open_fills:
                    take = min(of["_qty"], remaining)
                    used.append(dict(of, _qty=take))
                    remaining -= take
                    if remaining <= 1e-6:
                        break
                if abs(position + close_qty) < 1e-6:
                    _record(used or open_fills, fill, close_qty, "SHORT")
                    open_fills = []
                position += close_qty
                qty      -= close_qty
            if qty > 1e-6:
                open_fills.append({**fill, "_qty": qty})
                position += qty

        else:  # sell
            if position > 1e-6:
                # Closing a long
                close_qty = min(qty, position)
                used      = []
                remaining = close_qty
                for of in open_fills:
                    take = min(of["_qty"], remaining)
                    used.append(dict(of, _qty=take))
                    remaining -= take
                    if remaining <= 1e-6:
                        break
                if abs(position - close_qty) < 1e-6:
                    _record(used or open_fills, fill, close_qty, "LONG")
                    open_fills = []
                position -= close_qty
                qty      -= close_qty
            if qty > 1e-6:
                open_fills.append({**fill, "_qty": qty})
                position -= qty

    return trades_out


# ─── Open positions → open trade records ─────────────────────────────────────

def _open_position_to_trade(pos: dict) -> dict:
    """Convert an open position from get_open_positions() into a trade dict."""
    contract  = pos.get("symbol", "PF_XBTUSD")
    size      = abs(float(pos.get("size", 0)))
    price     = float(pos.get("price", 0))
    side      = pos.get("side", "long").lower()
    direction = "long" if side in ("long", "buy") else "short"
    return {
        "symbol":          _symbol(contract),
        "contract":        contract,
        "market_type":     _market_type(contract),
        "venue":           "kraken_futures",
        "direction":       direction,
        "entry":           round(price, 2),
        "exit":            None,
        "size":            round(size, 6),
        "leverage":        1,
        "pnl":             None,
        "fees":            None,
        "funding_cost":    None,
        "fill_type":       None,
        "order_type":      None,
        "fill_uuid":       None,
        "kraken_order_id": None,
        "fill_count":      None,
        "opened_at":       datetime.now(timezone.utc),
        "closed_at":       None,
        "balance_after":   None,
        "notes":           "auto-synced open position",
    }


# ─── Sync orchestrator ────────────────────────────────────────────────────────

def sync_account(
    api_key:        str,
    api_secret:     str,
    db_upsert_fn,
    db_close_fn=None,         # kept for API compatibility, unused
    db_transfer_fn=None,      # optional: upsert_transfer from supabase_database
    db_clear_open_fn=None,    # optional: clear_synced_open_positions — wipe-and-replace open rows
    last_fill_time: Optional[str] = None,
) -> dict:
    """
    Pull fills + open positions + transfers from Kraken and persist into DB.
    db_upsert_fn(trade_dict)     → TradeResponse | None  (None = duplicate)
    db_transfer_fn(transfer_dict) → bool  (False = duplicate)
    db_clear_open_fn(venue)       → int   (auto-synced open rows deleted)
    Returns a summary dict.
    """
    errors             = []
    imported           = 0
    skipped            = 0
    transfers_imported = 0
    eur_usd            = 1.10
    fills              = []
    trades             = []

    if last_fill_time:
        since_dt = _parse_ts(last_fill_time)
    else:
        since_dt = datetime(2018, 1, 1, tzinfo=timezone.utc)

    try:
        user_client   = User(key=api_key, secret=api_secret)
        market_client = Market(key=api_key, secret=api_secret)

        eur_usd                  = _get_eur_usd(market_client)
        eur_timeline, raw_logs   = _build_eur_timeline(user_client)
        fills                    = _pull_fills(user_client, since_dt)
        trades                   = _build_trades(fills, eur_timeline, eur_usd)
        open_positions           = _retry(lambda: user_client.get_open_positions()).get("openPositions", [])
    except Exception as e:
        return {"imported": 0, "closed": 0, "skipped": 0, "errors": [str(e)],
                "fills_fetched": 0, "trades_processed": 0, "transfers_imported": 0}

    for t in trades:
        try:
            result = db_upsert_fn(t)
            if result is None:
                skipped += 1
            else:
                imported += 1
        except Exception as e:
            errors.append(f"upsert {t.get('kraken_order_id')}: {e}")
            skipped += 1

    # Open positions carry no exchange order_id, so they can't be deduped on
    # insert. Wipe the previous sync's auto-synced open rows, then re-insert
    # whatever is currently open → exactly one row per live position, and a
    # closed position simply leaves no phantom behind.
    if db_clear_open_fn:
        try:
            db_clear_open_fn("kraken_futures")
        except Exception as e:
            errors.append(f"clear_open: {e}")

    for pos in open_positions:
        t = _open_position_to_trade(pos)
        try:
            result = db_upsert_fn(t)
            if result is None:
                skipped += 1
            else:
                imported += 1
        except Exception as e:
            errors.append(f"open_pos {pos.get('symbol')}: {e}")
            skipped += 1

    if db_transfer_fn:
        for tf in _build_transfers(raw_logs):
            try:
                if db_transfer_fn(tf):
                    transfers_imported += 1
            except Exception as e:
                errors.append(f"transfer {tf.get('kraken_id')}: {e}")

    return {
        "imported":            imported,
        "closed":              0,
        "skipped":             skipped,
        "errors":              errors,
        "fills_fetched":       len(fills),
        "trades_processed":    len(trades),
        "transfers_imported":  transfers_imported,
        "eur_usd":             round(eur_usd, 4),
        "eur_timeline":        eur_timeline,
    }


# ─── Convenience: load keys from env ──────────────────────────────────────────

def get_api_keys(account: str = "personal") -> tuple[str, str]:
    """
    Returns (api_key, api_secret) for the given account.
    account = "personal" | "biz"
    """
    if account == "biz":
        key    = os.getenv("KRAKEN_FUTURES_API_KEY_BIZ", "")
        secret = os.getenv("KRAKEN_FUTURES_API_SECRET_BIZ", "")
    else:
        key    = os.getenv("KRAKEN_FUTURES_API_KEY", "")
        secret = os.getenv("KRAKEN_FUTURES_API_SECRET", "")

    if not key or not secret:
        raise RuntimeError(f"Kraken API keys not set for account='{account}' in .env")
    return key, secret


def fetch_live_balance(api_key: str, api_secret: str) -> dict:
    """Return total portfolio value (EUR) from the flex multi-collateral account.
    portfolioValue = wallet + all collateral mark-to-market. Includes unrealized PnL when in position."""
    try:
        user_client   = User(key=api_key, secret=api_secret)
        market_client = Market(key=api_key, secret=api_secret)
        eur_usd = _get_eur_usd(market_client)
        wallets = user_client.get_wallets()
        flex = wallets.get("accounts", {}).get("flex", {})
        portfolio_usd = float(flex.get("portfolioValue") or 0)
        pnl_usd       = float(flex.get("pnl") or flex.get("totalUnrealized") or 0)
        avail_usd     = float(flex.get("availableMargin") or flex.get("availableFunds") or 0)
        eur_balance   = round(portfolio_usd / eur_usd, 2) if eur_usd else 0.0
        unrealized    = round(pnl_usd / eur_usd, 2)      if eur_usd else 0.0
        avail_margin  = round(avail_usd / eur_usd, 2)    if eur_usd else 0.0
        return {"eur_balance": eur_balance, "unrealized_pnl": unrealized,
                "available_margin": avail_margin, "eur_usd": round(eur_usd, 4)}
    except Exception as e:
        return {"eur_balance": 0.0, "unrealized_pnl": 0.0, "error": str(e)}


def fetch_open_positions(api_key: str, api_secret: str) -> list[dict]:
    """Used by /api/sync/kraken/status endpoint."""
    client = User(key=api_key, secret=api_secret)
    return client.get_open_positions().get("openPositions", [])


def fetch_open_positions_enriched(api_key: str, api_secret: str, account: str = "") -> list[dict]:
    """Live open positions with the Kraken-style detail: mark price, value,
    unrealised P&L (€ + %), RoE, initial margin, est. liquidation, leverage.
    Prices in USD (BTC), money in EUR (the account's pnlCurrency). Liquidation
    is an ESTIMATE (entry ± 1/lev) — Kraken's true liq depends on wallet margin."""
    user   = User(key=api_key, secret=api_secret)
    market = Market(key=api_key, secret=api_secret)
    eur_usd = _get_eur_usd(market)

    marks: dict[str, float] = {}
    try:
        for tk in _retry(lambda: market.get_tickers()).get("tickers", []):
            mp = tk.get("markPrice") or tk.get("last")
            if mp:
                marks[tk.get("symbol")] = float(mp)
    except Exception:
        pass

    out: list[dict] = []
    for p in _retry(lambda: user.get_open_positions()).get("openPositions", []):
        sym   = p.get("symbol", "PF_XBTUSD")
        entry = float(p.get("price", 0) or 0)
        size  = abs(float(p.get("size", 0) or 0))
        side  = str(p.get("side", "long")).lower()
        if size == 0 or entry == 0:
            continue
        mark  = marks.get(sym, entry)
        lev   = float(p.get("maxFixedLeverage", 10) or 10)
        upnl  = float(p.get("unrealizedPnl", 0) or 0)        # EUR
        is_short = side in ("short", "sell")

        notional_usd = size * mark             # quote-qty / position value, USD
        cost_usd     = size * entry            # opening value, USD
        value_eur    = notional_usd / eur_usd if eur_usd else 0.0
        margin_usd   = notional_usd / lev if lev else notional_usd
        margin_eur   = margin_usd / eur_usd if eur_usd else 0.0
        upnl_usd     = upnl * eur_usd          # Kraken reports pnl in EUR; → USD
        roe          = (upnl / margin_eur * 100) if margin_eur else None
        upnl_pct     = (upnl_usd / cost_usd * 100) if cost_usd else None
        move_pct     = ((mark - entry) / entry * 100) * (-1 if is_short else 1) if entry else None
        liq          = entry * (1 + 1 / lev) if is_short else entry * (1 - 1 / lev)
        venue_label  = "Business Futures" if account == "biz" else "Kraken Futures"

        out.append({
            "account":       account,
            "venue":         venue_label,
            "symbol":        _symbol(sym),
            "contract":      sym,
            "direction":     "short" if is_short else "long",
            "size":          round(size, 6),            # base qty (BTC)
            "quote_qty":     round(notional_usd, 2),    # quote qty / value (USD)
            "entry":         round(entry, 2),
            "mark":          round(mark, 2),
            "move_pct":      round(move_pct, 3) if move_pct is not None else None,
            "value_eur":     round(value_eur, 2),
            "cost_usd":      round(cost_usd, 2),
            "margin_usd":    round(margin_usd, 2),
            "margin_eur":    round(margin_eur, 2),
            "upnl_usd":      round(upnl_usd, 2),
            "upnl_eur":      round(upnl, 2),
            "upnl_pct":      round(upnl_pct, 2) if upnl_pct is not None else None,
            "roe_pct":       round(roe, 2) if roe is not None else None,
            "liquidation":   round(liq, 2),
            "leverage":      round(lev, 1),
            "funding":       round(float(p.get("unrealizedFunding", 0) or 0), 4),
            "eur_usd":       round(eur_usd, 4),
        })
    return out


def fetch_market_btc(api_key: str, api_secret: str, contract: str = "PF_XBTUSD") -> dict:
    """Live BTC perp mark price + funding rate from Kraken Futures public tickers.
    Same market the prop (Breakout) eval trades on — used to mark a logged prop
    fill to live, since the eval account itself has no readable API. The key is
    only needed to build the client; the tickers endpoint is public."""
    market = Market(key=api_key, secret=api_secret)
    for tk in _retry(lambda: market.get_tickers()).get("tickers", []):
        if tk.get("symbol") == contract:
            mp = tk.get("markPrice") or tk.get("last")
            return {"mark": float(mp) if mp else None,
                    "funding": float(tk.get("fundingRate") or 0.0)}
    return {"mark": None, "funding": None}


# ─── Spot API Ledger Sync ──────────────────────────────────────────────────────

def sync_spot_ledger(api_key: str, api_secret: str, db_transfer_fn) -> dict:
    """
    Fetch funding history from Kraken Spot API and upsert into transfers table.

    Queries deposit / withdrawal / transfer types separately — far more efficient
    than scanning all 17k+ ledger entries (most of which are derivatives activity).

    Uses python-kraken-sdk: kraken.spot.User.get_ledgers_info(type_=...)
    Note: parameter is `type_` not `type` in python-kraken-sdk >= 3.x
    """
    from kraken.spot import User as SpotUser

    client = SpotUser(key=api_key, secret=api_secret)
    imported = skipped = 0
    errors: list[str] = []

    # Map Spot API type → our transfer_type label
    # For "transfer" entries: sign determines direction from Spot's perspective
    FUNDING_TYPES = ("deposit", "withdrawal", "transfer")

    for ledger_type in FUNDING_TYPES:
        offset = 0
        while True:
            try:
                resp = client.get_ledgers_info(type_=ledger_type, ofs=offset)
            except Exception as e:
                errors.append(f"API error ({ledger_type} ofs={offset}): {e}")
                break

            ledger: dict = resp.get("ledger", {})
            total_count: int = resp.get("count", 0)
            if not ledger:
                break

            for refid, entry in ledger.items():
                amount = float(entry.get("amount", 0))
                if amount == 0:
                    continue  # skip dust / failed entries

                # Normalise asset: ZEUR→EUR, XXBT→BTC, USDC stays USDC
                raw_asset = entry.get("asset", "")
                asset = raw_asset.lstrip("Z").lstrip("X") if len(raw_asset) > 3 else raw_asset

                if ledger_type == "transfer":
                    # From Spot wallet perspective:
                    # negative = EUR leaving Spot (going TO Futures)
                    # positive = EUR arriving in Spot (coming FROM Futures)
                    transfer_type = "transfer_to_futures" if amount < 0 else "transfer_from_futures"
                else:
                    transfer_type = ledger_type  # "deposit" or "withdrawal"

                bal = entry.get("balance")
                tf = {
                    "kraken_id":     refid,
                    "transfer_type": transfer_type,
                    "asset":         asset,
                    "amount":        amount,
                    "balance_after": float(bal) if bal is not None else None,
                    "ts":            datetime.fromtimestamp(float(entry["time"]), tz=timezone.utc),
                }
                try:
                    new = db_transfer_fn(tf)
                    if new:
                        imported += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append(f"{ledger_type} {refid}: {e}")

            offset += len(ledger)
            if offset >= total_count:
                break

    return {"imported": imported, "skipped": skipped, "errors": errors}
