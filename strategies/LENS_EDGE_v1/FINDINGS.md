# LENS_EDGE_v1 — Reverse-Engineered from 455 Real Trades

## Source Data
- **455 closed trades** from Kraken futures, 60.4 weeks (Apr 2025 – Jun 2026)
- **7.5 trades/week**, 42.6% base WR

## Key Discovery

Your edge is real but drowning in counter-trend noise:

| Bucket | n | tpw | WR | PnL |
|---|---|---|---|---|
| Quality (aligned bar + 4H trend) | 77 | 1.3 | 48.1% | **+€2,172** |
| Garbage (counter-bar OR counter-4H) | 340 | 5.6 | 40.6% | **−€1,082** |
| **Net** | 455 | 7.5 | 42.6% | **+€936** |

Stop taking the 340 garbage trades. Your quality P&L triples.

## Ranked Discriminators

| Feature | WR True | WR False | Delta |
|---|---|---|---|
| **Entry bar aligned** | 52.1% | 32.3% | **+19.8pp** |
| **4H EMA trend aligned** | 47.8% | 39.0% | +8.8pp |
| EMA21 slope aligned | 45.8% | 38.5% | +7.3pp |
| Daily trend | 44.0% | 40.9% | +3.2pp |
| MACD rising | 42.5% | 42.7% | **~0 — ignore** |
| 1H EMA21>EMA50 | 42.1% | 43.3% | **negative — ignore** |

## Two Setups

### DIP (RSI < 40 + 4H aligned + aligned bar)
- WR: 44.2%  n=43  tpw=0.7
- Avg win: +1.42% price move
- Avg loss: −0.78% price move

### MOMENTUM (RSI > 55 + 4H aligned + aligned bar)
- WR: **52.9%**  n=34  tpw=0.6
- This is your best mechanical setup
- Avg win: +0.92% price move

## RSI Zones
| RSI | WR | Action |
|---|---|---|
| < 40 | 51.1% | ✅ DIP setups |
| 30–40 | 51.1% | ✅ Best dip zone |
| 40–45 | 36.4% | ❌ AVOID |
| 45–55 | 32–36% | ❌ AVOID (worst zone) |
| 55–70 | 46–55% | ✅ Momentum setups |
| > 70 | 48.5% | ✅ Strong momentum |

## Session / Day Observations
- **Hour 11 UTC**: 61.9% WR (21 trades) — London midday
- **Hour 3 UTC**: 59.1% WR (22 trades) — Asian session
- **Saturday**: 54.1% WR (37 trades) — counter-intuitive, check
- **Tuesday + Sunday**: worst (~38%)

## Pine Script
`strategy.pine` implements:
- 4H trend gate via `request.security("240", ...)`
- RSI zone backgrounds (green=dip, blue=momentum, red=avoid)
- Bull/bear bar requirement built into signal
- Separate DIP vs MOMENTUM labels
- 1% stop / 3.5% TP (matches projection math)

## What to Do Differently
1. **Only enter long on a bull bar. Only enter short on a bear bar.** (+19.8pp)
2. **Check 4H chart first.** If counter-trend, skip. (+8.8pp)
3. **Skip RSI 40-55 zone.** Wait for RSI<40 or RSI>55.
4. **Hold your winners.** Wins avg 251min, losses avg 160min — you're cutting both equally. Let winners run to 3.5% TP.
5. **Ignore MACD.** Zero effect in real data.
