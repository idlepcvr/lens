# NEXT SESSION — LENS: close the short gap, then the discipline holes

[Open as HTML](DONE-2026-07-24-short-gap-discipline-holes.html)

> **CLOSED SESSION — built 2026-07-24.** Close the short gap, then the discipline holes. Renamed from
> `NEXT_SESSION*` on 2026-07-31: three files named "next session" all
> described finished work. As of 2026-07-31 there is no live handoff at all —
> the last one was archived alongside this file once its final item was built.
> Nothing in this repository is pending. A session with real scope should
> create a fresh `NEXT_SESSION.md` at the root.


*Written 2026-07-24 from evidence gathered that day. The previous spec
(DAILY_BREAK trailing/pyramiding, ✅ built, ❌ NO-GO) is archived at
`docs/done/DONE-2026-07-24-daily-break-trailing-pyramiding.md`. Items are ordered by measured cost, not by effort.*

---

## Item 1 · LENS cannot signal a short for 21 hours of the day

**This is the headline, and it is a coverage bug, not a discipline problem.**

He reported executing shorts that never appeared as signals. Measured — every
short he has taken since the loop went live (2026-06-16):

| trade | UTC hour | could LENS have signalled it? |
|---|---|---|
| 2026-07-22 17:20 | 17 | no |
| 2026-07-21 04:09 | 04 | no |
| 2026-07-17 22:12 | 22 | no |
| 2026-07-16 22:17 | 22 | no |
| 2026-07-13 06:26 | 06 | no |
| 2026-07-09 01:38 | 01 | no |

**Six of six.** Only two of the five playbook setups are shorts:

- **S1** requires `killzone == "ny_am_kz"`, which is **13:00–16:00 UTC only**.
- **S2** has no time gate — and was vetoed **5 times out of 5** in the last 30
  days, and is structurally self-defeating (premium + bear displacement implies
  up-slope and a fresh PDH raid, which trips `slope_against` + `pd_raid_fade`
  automatically).

So outside a three-hour window, LENS is **structurally long-only**. It is not
that he ignored the feed; the feed cannot speak. This also fully explains the
"the engine looks asleep" complaint that produced the veto log.

**Do not fix this by loosening the vetoes.** The vetoes are the measured edge.
Fix it by giving the short side a setup that can fire outside 13–16 UTC. The
raw material already exists: `strategy_search.json` holds hundreds of scored
combos and the board already ranks short-capable strategies (H13 · weak-bounce
fade is live). The question to answer is why the S-playbook has no short
equivalent, and whether a board-derived short belongs in the playbook.

**Also decide S2 and S4 explicitly.** S4 matched 25 times in 30 days and was
vetoed 25 times — a long on `rsi<40` in discount trips `slope_against` every
time. Both are rules that read as active and cannot fire. Kill them or fix
them; leaving them is worse than either.

---

## Item 2 · The board signal path applies no vetoes at all

`emit_board_signals()` contains zero calls to `vetoes()`. The playbook path is
veto-filtered; the board path is not. 21 signals have gone out unfiltered.

The mining says the single biggest lever is not trading vetoed contexts, and
half the pipeline does not apply it. Either the vetoes belong on both paths, or
there is a reason they should not apply to board strategies — but right now
that is an accident, not a decision.

---

## Item 3 · The goal target exists in three contradictory versions

| source | says |
|---|---|
| `lens_config` row 1 (feeds `/edge` Fit + `compute_goal`) | 150 BTC, valued at spot |
| `LENS_PLAN.md` line 18 | "50 BTC by 2028-12-31" |
| `LENS_PLAN.md` line 395 | "150 BTC @ €250k by 31 Dec 2028" |

The config is what actually grades feasibility verdicts. Pick one, write it in
both places, delete the others. `LENS_PLAN.md` open item 3 flagged this class of
problem; it is still live, just with different numbers than when it was written.

---

## Item 4 · `fvg_entry` is the most-fired veto and the only one in profit

69 hits in 30 days — more than any other rule — and the bucket is **+€2,000
over 26 trades** while its frozen `VETO_LABELS` string still reads
"−€15/trade". Every other veto bucket is in the red, as designed.

The blocked cards on `/signals` now show the live number, but `/desk` still
renders the frozen one. Either re-derive `VETO_LABELS` from the ledger or drop
the baked-in stats entirely and always read live.

---

## Item 5 · The auto-linker may be missing about half the links

Corrected denominator: **469 of the 509 trades predate the system**. The live
era is 40 trades, 5 linked — not 5 of 509. Do not quote the big number.

Within the live era, 10 distinct trades sit within 6h of an approved signal in
the same direction; 5 carry a link. That is an indication, not proof — the 6h
same-direction test is looser than the real linker's. Worth an hour to confirm
before touching the linker, because the signal→trade dataset is the whole point
of the system.

Related and unmeasured: 41 signals approved, 38 expired. Nothing currently
reports approve-to-execute conversion, only signal-to-trade.

---

## Item 6 · The breeder's champions have never met a baseline

`strategy_search3` scores survivors against a buy-every-bar baseline and carries
a `beats_baseline` flag. `strategy_breeder` has no baseline comparison at all,
and its 7-year run returned 65 long genomes out of 78 over a period where BTC
rose roughly tenfold. Run the champions through the same baseline gate before
any of them is treated as a finding.

---

## Standing context

- Auto-execution is never in scope.
- The 7-year window is Binance **spot**; the 30-month is Bybit **perp**. Never
  compare them bar-for-bar.
- Three separate investigations on 2026-07-24 (exits, search depth, vault
  diversity) all returned "the constraint is evidence, not machinery". Item 1 is
  the exception that genuinely is a machinery gap — the short side has no
  mechanism at all, which is a different thing from a weak mechanism.
