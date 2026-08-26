# LENS — Next session

[Open as HTML](DONE-2026-08-21-execution-live-orders-veto-override.html)

[Open as HTML](NEXT_SESSION.html)

*Written 2026-08-21 03:00 after the first live order went through. Everything
below is a consequence of actually using the thing.*

## Where this picks up

LENS placed its first live order tonight: a 0.001 BTC reduce on the open long,
which filled and took the position 0.043 → 0.042. The chain works end to end —
form, checks, confirm dialog, Kraken. Execution is **live**
(`KRAKEN_FUTURES_SANDBOX=0`) with a **0.005 BTC** ceiling.

What's wrong is everything *around* the order: the app can send one, but it
can't yet show you what happened afterwards, and the numbers it shows about an
open trade are its own guesses rather than the exchange's facts.

---

## 1. Read the live orders — the one that matters

**The problem.** `/hedge-position` shows a take profit and a stop loss computed
from the win/loss model. The real resting orders on Kraken right now are:

| | LENS shows | Kraken actually has |
|---|---|---|
| Take profit | model-derived | **74464** · reduce-only · mark trigger |
| Stop loss | model-derived | **70168** · reduce-only · mark trigger |

Both were placed from the website at 12:10:16 on 2026-08-20. LENS has never
read them. That is the entire reason the numbers look wrong on the open
position and in the journal — they were never claiming to be real, but nothing
on screen said so.

**The fix.** `User.get_open_orders()` returns them, already normalised:
`orderType`, `side`, `stopPrice`, `limitPrice`, `reduceOnly`, `triggerSignal`,
`status`, `receivedTime`, `order_id`.

- New `GET /api/orders/live` wrapping it.
- On the open position, show the **real** TP/SL, not the planned ones.
- Keep the planned levels where they belong: on the *ticket being built*, which
  is a forecast. Two different things that must stop sharing a label.
- Where they disagree, say so. A trade running with a stop 300 wide of plan is
  a fact worth seeing, not an error to hide.

## 2. Feedback that an order exists

Right now an order is placed and then vanishes from the interface. No resting
order list, nothing in the journal, no way to answer "did that go through" from
inside LENS. With multiple orders working this becomes untenable.

- Resting orders visible on the position page, with a cancel control per order.
- The journal should show placed orders, not only filled trades.
- `cancel_all` already exists in `execute.py`; per-order cancel needs
  `Trade.cancel_order(order_id=...)`.

## 3. Replace the size cap with something that means something

`LENS_MAX_ORDER_BTC` was added on my own initiative, never requested, and `0.005`
was a guess. BTC is the wrong unit — the number is meaningless until converted.
Against a €305 balance:

| cap | notional | leverage on balance |
|---|---|---|
| 0.001 | €62 | 0.2× |
| 0.005 | €310 | 1.0× |
| 0.05 | €3,100 | 10.2× |
| 0.5 | €30,999 | **101.5×** |

Expressed as leverage the fat-finger case rejects itself without a magic number.

- Ceiling becomes **balance × max leverage**, derived live.
- Displayed in **BTC and USD**, not BTC alone.
- Removing the cap entirely is a legitimate alternative — Kraken enforces its own
  leverage limit regardless.

## 4. The price strip

Only mark price is shown, and the LIVE badge went missing from the header. The
ticker already carries everything:

`markPrice 72599.26` · `indexPrice 72610.95` · `last 72599` · `bid 72597` ·
`ask 72598` · `fundingRate` · 24h high/low.

Mark, index and last should sit together in the strip — the TP/SL trigger source
is selectable, so the price it triggers on should be visible.

## 5. Centre the confirm dialog

Still rendering top-left. I set `position:fixed; inset:0; margin:auto` and it
did not take, so the cause is elsewhere — likely a competing rule on `dialog`
or the entrance transform. **Verify in the browser, not in the source.**

---

## Not doing

- **Prop execution.** The eval is `BREAKOUT_1STEP_TURBO`, at Breakout, not
  Kraken. No credentials, no API in the codebase. He places those by phone and
  that is fine. Do not build toward it without first confirming Breakout even
  offers an API.

## Carried over, still true

- `.env` lines 2, 5 and 6 do not parse and dotenv skips them silently.
- Four pre-existing test failures: three in `tests/test_plan.py` (temp-DB
  fixture has no tables), one in `tests/test_nav_parity.py` (`Track` has no
  prop twin).
- Six rules in `lens.css` still use `--faint` as readable text at 2.3:1:
  `.muted` `.foot` `.badge.expired` `.cond.no` `.tg .sub` `.sect .caret`.
- `docs/` has six `.md` files with no HTML twins. One command:
  `python3 tools/md2html.py docs/*.md`.
- Close position is all-or-nothing; there is no partial close.

## The one that isn't code

`LENS_PLAN.md`'s first open item, written 2026-07-14: *"Run the loop. Still the
real bottleneck, not code — 4 of ~500 trades carry a signal link."* Five weeks
later it is 11 of 540, and tonight added more code. Over the 30 days to
2026-08-20: **147 signals fired, 4 were acted on.**

Tonight was worth it — the loop can only be run once the order can be placed
from the same screen that calls it. But the plan has been right about the
bottleneck since July, and nothing on this list closes it.
