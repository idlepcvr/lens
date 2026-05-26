"""
PRISM — Bybit Futures fill sync.

Uses pybit:  from pybit.unified_trading import HTTP
Trades come from session.get_closed_pnl() — one entry per completed round-trip.
Supports both linear (USDT-margined) and inverse (BTC-margined) perpetuals.

For inverse (e.g. BTCUSD):
  - closedPnl is in BTC → convert via avgExitPrice × EUR/USD
  - fees (openFee + closeFee) are in BTC
  - size is in cumEntryValue (BTC)
  - side in get_closed_pnl is the CLOSING side: "Buy" = was SHORT, "Sell" = was LONG

For linear (e.g. BTCUSDT):
  - closedPnl is in USDT → divide by EUR/USDT
  - fees in USDT
  - size in BTC (base currency)
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


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


def _symbol(bybit_sym: str) -> str:
    """BTCUSD / BTCUSDT → BTC/USD,  ETHUSDT → ETH/USD, etc."""
    s = bybit_sym.upper()
    for suffix in ("USDT", "USD", "PERP"):
        if s.endswith(suffix):
            base = s[: -len(suffix)]
            return f"{base}/USD"
    return bybit_sym


def _market_type(bybit_sym: str) -> str:
    s = bybit_sym.upper()
    if s.endswith("USDT"):
        return "perpetual"   # linear
    if s.endswith("USD"):
        return "inverse"
    return "unknown"


# ─── EUR rate ─────────────────────────────────────────────────────────────────

def _get_eur_usdt() -> float:
    """Return EUR/USDT rate from Kraken public API (Bybit has no EUR pair). Fallback 1.10."""
    try:
        import requests as _req
        resp = _req.get(
            "https://api.kraken.com/0/public/Ticker",
            params={"pair": "EURUSD"},
            timeout=6,
        )
        data = resp.json()
        if not data.get("error"):
            return float(list(data["result"].values())[0]["c"][0])
    except Exception:
        pass
    return 1.10


# ─── BTC price ────────────────────────────────────────────────────────────────

def _get_btc_price_usd(session) -> float:
    """Current BTC/USD mark price from Bybit inverse ticker."""
    try:
        resp = session.get_tickers(category="inverse", symbol="BTCUSD")
        lst  = (resp.get("result") or {}).get("list") or []
        if lst:
            p = lst[0].get("lastPrice") or lst[0].get("markPrice")
            if p:
                return float(p)
    except Exception:
        pass
    return 70000.0   # safe fallback


# ─── Pull closed trades via get_closed_pnl ───────────────────────────────────

def _pull_closed_pnl(session, since_dt: datetime, category: str) -> list[dict]:
    """
    Paginate get_closed_pnl() for a given category ("linear" or "inverse").
    Returns list of closed round-trip dicts, newest-first order as returned.
    Stops pagination when updatedTime < since_dt.
    """
    since_ts = int(since_dt.timestamp() * 1000)
    items    = []
    cursor   = None

    while True:
        kwargs = {"category": category, "limit": 100}
        if cursor:
            kwargs["cursor"] = cursor

        try:
            resp   = session.get_closed_pnl(**kwargs)
            result = resp.get("result") or {}
            page   = result.get("list") or []
        except Exception:
            break

        if not page:
            break

        done = False
        for item in page:
            ts = int(item.get("updatedTime") or 0)
            if ts < since_ts:
                done = True
                break
            items.append(item)

        if done:
            break

        cursor = result.get("nextPageCursor")
        if not cursor:
            break

    return items


# ─── Convert closed_pnl item → trade dict ────────────────────────────────────

def _item_to_trade(item: dict, category: str, eur_usdt: float) -> dict:
    """
    Convert a single get_closed_pnl entry to a trade dict.

    Inverse (BTCUSD):
      - closedPnl, openFee, closeFee all in BTC
      - avgExitPrice (USD) used to convert BTC→USD at trade time
      - size in BTC = cumEntryValue field
      - side is CLOSING side: "Buy"=was SHORT, "Sell"=was LONG

    Linear (BTCUSDT):
      - closedPnl, openFee, closeFee in USDT
      - size in BTC = qty field (base currency)
      - side is CLOSING side: "Buy"=was SHORT, "Sell"=was LONG
    """
    symbol      = item.get("symbol", "BTCUSD")
    is_inverse  = (category == "inverse") or _market_type(symbol) == "inverse"

    # Direction: closing side is inverted vs trade direction
    closing_side = (item.get("side") or "Buy").lower()
    direction    = "long" if closing_side in ("sell", "short") else "short"

    entry_price = float(item.get("avgEntryPrice") or 0)
    exit_price  = float(item.get("avgExitPrice")  or 0)
    closed_pnl  = float(item.get("closedPnl")     or 0)  # NET of fees
    open_fee    = float(item.get("openFee")        or 0)
    close_fee   = float(item.get("closeFee")       or 0)
    total_fees  = open_fee + close_fee
    fill_count  = int(item.get("fillCount")        or 1)
    leverage    = int(float(item.get("leverage")   or 1))

    open_ts  = _parse_ts(int(item.get("createdTime") or 0))
    close_ts = _parse_ts(int(item.get("updatedTime") or 0))

    if is_inverse:
        # BTC-denominated: convert via exit price (USD per BTC at trade time)
        usd_per_btc = exit_price if exit_price > 0 else 70000.0
        pnl_eur     = round(closed_pnl * usd_per_btc / eur_usdt, 2)
        fees_eur    = round(total_fees  * usd_per_btc / eur_usdt, 6)
        size_btc    = round(float(item.get("cumEntryValue") or 0), 6)
    else:
        # USDT-denominated: divide by EUR/USDT rate
        pnl_eur  = round(closed_pnl / eur_usdt, 2)
        fees_eur = round(total_fees  / eur_usdt, 6)
        size_btc = round(float(item.get("qty") or 0), 6)

    order_id = item.get("orderId", "")

    return {
        "symbol":          _symbol(symbol),
        "contract":        symbol,
        "market_type":     _market_type(symbol),
        "venue":           "bybit_futures",
        "direction":       direction,
        "entry":           round(entry_price, 2),
        "exit":            round(exit_price,  2),
        "size":            size_btc,
        "leverage":        leverage,
        "pnl":             pnl_eur,
        "fees":            fees_eur,
        "funding_cost":    None,
        "fill_type":       None,
        "order_type":      (item.get("orderType") or "Market").lower(),
        "fill_uuid":       order_id,
        "kraken_order_id": order_id,   # reused as exchange_order_id for dedup
        "fill_count":      fill_count,
        "opened_at":       open_ts,
        "closed_at":       close_ts,
        "balance_after":   None,
        "notes":           None,
    }


# ─── Open positions → open trade records ─────────────────────────────────────

def _open_position_to_trade(pos: dict, category: str) -> "Optional[dict]":
    """Convert a Bybit open position to a trade dict (exit=None, pnl=None)."""
    symbol = pos.get("symbol", "BTCUSD")
    size   = abs(float(pos.get("size", 0) or 0))
    if size == 0:
        return None

    price     = float(pos.get("avgPrice") or 0)
    side      = (pos.get("side") or "Buy").lower()
    direction = "long" if side in ("buy", "long") else "short"
    lev       = int(float(pos.get("leverage") or 1))

    is_inverse = _market_type(symbol) == "inverse"
    if is_inverse:
        size_btc = round(float(pos.get("positionValue") or size), 6)
    else:
        size_btc = round(size, 6)

    return {
        "symbol":          _symbol(symbol),
        "contract":        symbol,
        "market_type":     _market_type(symbol),
        "venue":           "bybit_futures",
        "direction":       direction,
        "entry":           round(price, 2),
        "exit":            None,
        "size":            size_btc,
        "leverage":        lev,
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
    db_close_fn=None,
    db_transfer_fn=None,
    last_fill_time: Optional[str] = None,
) -> dict:
    """
    Pull closed PnL + open positions from Bybit and persist into DB.
    Checks both 'inverse' and 'linear' categories.
    """
    try:
        from pybit.unified_trading import HTTP
    except ImportError:
        return {
            "imported": 0, "closed": 0, "skipped": 0,
            "errors": ["pybit not installed — run: pip install pybit"],
            "fills_fetched": 0, "trades_processed": 0, "transfers_imported": 0,
        }

    errors    = []
    imported  = 0
    skipped   = 0
    all_items = []

    if last_fill_time:
        since_dt = _parse_ts(last_fill_time)
    else:
        since_dt = datetime(2019, 1, 1, tzinfo=timezone.utc)

    try:
        session  = HTTP(api_key=api_key, api_secret=api_secret)
        eur_usdt = _get_eur_usdt()

        # Pull closed trades for both categories
        for cat in ("inverse", "linear"):
            try:
                items = _pull_closed_pnl(session, since_dt, cat)
                all_items.extend((item, cat) for item in items)
            except Exception as e:
                errors.append(f"closed_pnl {cat}: {e}")

        # Open positions from both categories
        open_positions = []
        for cat in ("inverse", "linear"):
            try:
                resp = session.get_positions(category=cat, settleCoin="USDT" if cat == "linear" else "BTC")
                for pos in (resp.get("result") or {}).get("list") or []:
                    if float(pos.get("size", 0) or 0) > 0:
                        open_positions.append((pos, cat))
            except Exception as e:
                errors.append(f"positions {cat}: {e}")

    except Exception as e:
        return {
            "imported": 0, "closed": 0, "skipped": 0, "errors": [str(e)],
            "fills_fetched": 0, "trades_processed": 0, "transfers_imported": 0,
        }

    for item, cat in all_items:
        try:
            t      = _item_to_trade(item, cat, eur_usdt)
            result = db_upsert_fn(t)
            if result is None:
                skipped += 1
            else:
                imported += 1
        except Exception as e:
            errors.append(f"upsert {item.get('orderId')}: {e}")
            skipped += 1

    for pos, cat in open_positions:
        t = _open_position_to_trade(pos, cat)
        if t is None:
            continue
        try:
            result = db_upsert_fn(t)
            if result is None:
                skipped += 1
            else:
                imported += 1
        except Exception as e:
            errors.append(f"open_pos {pos.get('symbol')}: {e}")
            skipped += 1

    return {
        "imported":           imported,
        "closed":             0,
        "skipped":            skipped,
        "errors":             errors,
        "fills_fetched":      len(all_items),
        "trades_processed":   len(all_items),
        "transfers_imported": 0,
        "eur_usdt":           round(eur_usdt, 4),
    }


# ─── Live balance ──────────────────────────────────────────────────────────────

def fetch_live_balance(api_key: str, api_secret: str) -> dict:
    """Return live account snapshot in the same shape as Kraken's balance endpoint."""
    from pybit.unified_trading import HTTP
    session  = HTTP(api_key=api_key, api_secret=api_secret)
    eur_usdt = _get_eur_usdt()

    eur_balance = 0.0
    available   = 0.0
    unrealised  = 0.0
    margin_used = 0.0
    portfolio   = 0.0
    btc_equiv   = None
    btc_price   = _get_btc_price_usd(session)

    def _parse_wallet(acc: dict) -> None:
        nonlocal eur_balance, available, unrealised, margin_used, portfolio, btc_equiv
        total_usd = float(acc.get("totalWalletBalance") or acc.get("totalEquity") or 0)
        if total_usd == 0:
            return
        eur_balance = round(total_usd / eur_usdt, 2)
        portfolio   = eur_balance
        for c in acc.get("coin") or []:
            coin_name = c.get("coin", "")
            if coin_name == "BTC":
                btc_avail = float(c.get("availableToWithdraw") or c.get("availableBalance") or 0)
                available = round(btc_avail * btc_price / eur_usdt, 2) if btc_price else 0.0
                unreal_btc = float(c.get("unrealisedPnl") or 0)
                unrealised = round(unreal_btc * btc_price / eur_usdt, 2) if btc_price else 0.0
                margin_used = round((eur_balance - available) if available < eur_balance else 0, 2)
                btc_equiv = round(float(c.get("walletBalance") or c.get("equity") or 0), 8)
                break
            elif coin_name == "USDT":
                usdt_bal = float(c.get("walletBalance") or 0)
                if usdt_bal > 0:
                    available   = round(float(c.get("availableToWithdraw") or 0) / eur_usdt, 2)
                    unrealised  = round(float(c.get("unrealisedPnl") or 0) / eur_usdt, 2)
                    margin_used = round(float(c.get("totalPositionMM") or 0) / eur_usdt, 2)

    # Try UNIFIED first, fall back to CONTRACT (classic/standard accounts)
    for acct_type in ("UNIFIED", "CONTRACT"):
        try:
            wb  = session.get_wallet_balance(accountType=acct_type)
            acc = ((wb.get("result") or {}).get("list") or [{}])[0]
            _parse_wallet(acc)
            if eur_balance > 0:
                break
        except Exception:
            continue

    # If btc_equiv not set from coin list, derive from EUR balance
    if btc_equiv is None and btc_price and btc_price > 0:
        btc_equiv = round(eur_balance * eur_usdt / btc_price, 8)

    # Try SPOT account for non-UTA (Standard) accounts.
    # On Unified Trading Accounts the SPOT wallet is merged into UNIFIED, so this
    # returns 0 (or errors) — fine; it means spot is already included in eur_balance.
    spot_eur = None
    try:
        spot_wb  = session.get_wallet_balance(accountType="SPOT")
        spot_acc = ((spot_wb.get("result") or {}).get("list") or [{}])[0]
        spot_usd = float(spot_acc.get("totalWalletBalance") or 0)
        if spot_usd > 0:
            spot_eur = round(spot_usd / eur_usdt, 2)
    except Exception:
        pass

    open_position = None
    for cat in ("inverse", "linear"):
        if open_position:
            break
        try:
            settle   = "BTC" if cat == "inverse" else "USDT"
            pos_resp = session.get_positions(category=cat, settleCoin=settle)
            for pos in (pos_resp.get("result") or {}).get("list") or []:
                size = abs(float(pos.get("size", 0) or 0))
                if size == 0:
                    continue
                entry     = float(pos.get("avgPrice", 0) or 0)
                mark      = btc_price or entry
                side      = (pos.get("side") or "Buy").lower()
                direction = "long" if side in ("buy", "long") else "short"
                lev       = float(pos.get("leverage", 10) or 10)
                FEE       = 0.0006
                breakeven = round(entry * (1 + FEE) if direction == "long" else entry * (1 - FEE), 2)
                liq_dist  = 0.5 / max(lev, 1)
                liq       = round(entry * (1 - liq_dist) if direction == "long" else entry * (1 + liq_dist), 2)
                move_pct  = round(((mark - entry) / entry * 100) * (1 if direction == "long" else -1), 3) if entry else 0
                unreal_btc = float(pos.get("unrealisedPnl", 0) or 0)
                # For inverse, unrealisedPnl is in BTC; for linear it's in USDT
                if cat == "inverse":
                    unreal_eur = round(unreal_btc * btc_price / eur_usdt, 2)
                else:
                    unreal_eur = round(unreal_btc / eur_usdt, 2)
                open_position = {
                    "direction":      direction,
                    "size":           size,
                    "symbol":         pos.get("symbol", "BTCUSD"),
                    "entry":          round(entry, 2),
                    "mark":           round(mark, 2),
                    "move_pct":       move_pct,
                    "unrealised_eur": unreal_eur,
                    "breakeven":      breakeven,
                    "liquidation":    liq,
                    "leverage":       round(lev, 1),
                }
                break
        except Exception:
            continue

    total_eur = round(eur_balance + (spot_eur or 0), 2)
    return {
        "eur_balance":     eur_balance,
        "btc_equiv":       btc_equiv,
        "btc_price_usd":   round(btc_price, 2) if btc_price else None,
        "eur_usd":         round(eur_usdt, 4),
        "portfolio_eur":   portfolio,
        "unrealised_eur":  unrealised,
        "margin_used_eur": margin_used,
        "available_eur":   available,
        "open_position":   open_position,
        "spot_eur":        spot_eur,
        "total_eur":       total_eur,
        "exchange":        "bybit",
    }


# ─── Convenience: load keys from env ──────────────────────────────────────────

def get_api_keys(account: str = "personal") -> tuple[str, str]:
    if account == "biz":
        key    = os.getenv("BYBIT_FUTURES_API_KEY_BIZ", "")
        secret = os.getenv("BYBIT_FUTURES_API_SECRET_BIZ", "")
    else:
        key    = os.getenv("BYBIT_FUTURES_API_KEY", "")
        secret = os.getenv("BYBIT_FUTURES_API_SECRET", "")

    if not key or not secret:
        raise RuntimeError(f"Bybit API keys not set for account='{account}' in .env")
    return key, secret


def fetch_open_positions(api_key: str, api_secret: str) -> list[dict]:
    """Used by /api/sync/bybit/status endpoint."""
    from pybit.unified_trading import HTTP
    session  = HTTP(api_key=api_key, api_secret=api_secret)
    all_pos  = []
    for cat in ("inverse", "linear"):
        try:
            settle   = "BTC" if cat == "inverse" else "USDT"
            pos_resp = session.get_positions(category=cat, settleCoin=settle)
            for p in (pos_resp.get("result") or {}).get("list") or []:
                if float(p.get("size", 0) or 0) > 0:
                    all_pos.append({**p, "_category": cat})
        except Exception:
            pass
    return all_pos


# ─── Bybit transaction / transfer sync ────────────────────────────────────────

def sync_transfers(api_key: str, api_secret: str, eur_usdt: float = 0.0) -> list[dict]:
    """
    Pull Bybit wallet transaction log (deposits, withdrawals, transfers).
    Returns list of dicts in the same shape as Kraken transfers for storage.

    Uses /v5/asset/transaction-log — covers all fund movements on the account.
    """
    try:
        from pybit.unified_trading import HTTP
    except ImportError:
        return []

    if not eur_usdt:
        eur_usdt = _get_eur_usdt()

    session  = HTTP(api_key=api_key, api_secret=api_secret)
    transfers = []
    cursor    = None

    # Map Bybit transaction types to our transfer_type labels
    type_map = {
        "DEPOSIT":    "deposit",
        "WITHDRAW":   "withdrawal",
        "TRANSFER_IN":  "transfer_in",
        "TRANSFER_OUT": "transfer_out",
        "REALIZED_PNL": None,  # skip — we track trades separately
        "COMMISSION":   None,
        "FUNDING_FEE":  None,
    }

    # Bybit returns BTC for inverse, USDT for unified — convert both to EUR
    btc_price_usd = 70000.0
    try:
        tickers = session.get_tickers(category="inverse", symbol="BTCUSD")
        lst = (tickers.get("result") or {}).get("list") or []
        if lst:
            p = lst[0].get("lastPrice") or lst[0].get("markPrice")
            if p:
                btc_price_usd = float(p)
    except Exception:
        pass

    def _fetch_pages(account_type: str) -> list[dict]:
        found = []
        cur = None
        while True:
            try:
                kwargs = {"accountType": account_type, "limit": 50}
                if cur:
                    kwargs["cursor"] = cur
                resp   = session.get_transaction_log(**kwargs)
                result = (resp.get("result") or {})
                page   = result.get("list") or []
            except Exception:
                break

            if not page:
                break

            for entry in page:
                tx_type = entry.get("type", "")
                label   = type_map.get(tx_type)
                if label is None:
                    continue

                coin    = entry.get("coin", "USDT")
                amount  = float(entry.get("change") or entry.get("cashFlow") or 0)
                balance = float(entry.get("cashBalance") or 0)
                ts_ms   = int(entry.get("transactionTime") or 0)
                ts      = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)

                if coin == "BTC":
                    amount_eur  = round(amount  * btc_price_usd / eur_usdt, 2)
                    balance_eur = round(balance * btc_price_usd / eur_usdt, 2)
                else:
                    amount_eur  = round(amount  / eur_usdt, 2)
                    balance_eur = round(balance / eur_usdt, 2)

                uid = f"bybit_{account_type}_{tx_type}_{coin}_{ts_ms}"
                found.append({
                    "kraken_id":     uid,
                    "transfer_type": label,
                    "asset":         coin.lower(),
                    "amount":        amount_eur,
                    "balance_after": balance_eur,
                    "ts":            ts.isoformat(),
                    "venue":         f"bybit_{account_type.lower()}",
                })

            cur = result.get("nextPageCursor")
            if not cur:
                break
        return found

    # Try UNIFIED first (newer accounts), fall back to CONTRACT (inverse perpetuals)
    for acct_type in ("UNIFIED", "CONTRACT"):
        rows = _fetch_pages(acct_type)
        if rows:
            transfers.extend(rows)
            break  # stop after first successful account type

    return transfers
