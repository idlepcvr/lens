"""LENS /geometry — where the stop and the target come from, and why.

Supersedes the 2026-07-02 audit's geometry. That one was fitted to the MAE/MFE
of *winning* trades: it asked "how far did my winners run?" and set the target
there. Two things were wrong with it. It only ever looked at winners, so the
stop was tuned on a sample selected by the outcome it was meant to predict. And
it never asked how LONG the resulting trade takes to resolve — so it never
noticed that a 0.63% stop and a 0.30% round trip means the toll is half the
risk before the trade has an opinion.

This page derives the geometry instead of fitting it, from two numbers that are
measured rather than chosen: live daily σ, and the round-trip friction actually
paid. Everything else follows from the barrier identities in app/geometry.py.

The uncomfortable part is kept in view rather than buried: the whole result
lives inside a few points of win rate around a coin flip, and the measured
ledger currently sits on the wrong side of it.
"""

from math import sqrt

from . import geometry as G
from .theme import shell

# The chosen operating point. Hold and R:R are decisions; σ and friction are
# measurements. Keeping them adjacent makes clear which is which.
HOLD_DAYS = 2.5           # ~2 trades/week — the original instinct, and the
                          # shortest hold that clears friction with margin
RR = 1.0                  # 2026-08-01: was 4.0. R:R 1 is the only R:R anything
                          # in this book was validated at — see setups.SL_PCT.
WIN_RATE = 0.681          # MEASURED, not assumed: short non-VETO at 2.83/2.83,
                          # n=91, vs a 50% coin flip at R:R 1 (short_edge.json)
MAX_DD = 0.25
STREAK = 15

# Hold-time ladder — the centrepiece. Short holds are the ones that fail.
# 60h is the chosen 2.5d operating point. The floor moved with the R:R: at R:R 4
# / 25% WR it was ~43h, at R:R 1 / 68.1% WR it is ~5h — a measured win rate that
# high buys back most of the short-hold penalty. 60h is now a choice, not a
# constraint; it is where the edge was measured, which is the reason to keep it.
LADDER_HOURS = [4, 8, 16, 24, 43, 60, 5 * 24, 10 * 24]

# The geometry this replaced, kept so the change stays legible on the page that
# made it. From the 2026-07-02 audit — MFE/MAE of winning trades.
OLD_SL, OLD_TP = 0.63, 1.5

SIGMA_FALLBACK = 1.79     # if the OHLCV cache is cold, so the page still renders


def _sigma() -> tuple[float, bool]:
    """(daily σ as %, is_live). Falls back rather than 500s — a stale number
    with a warning beats a dead page."""
    try:
        from .volatility import fetch_volatility
        s = fetch_volatility().get("daily_sigma")
        if s and s > 0:
            return float(s) * 100.0, True
    except Exception:
        pass
    return SIGMA_FALLBACK, False


def _fmt_hold(days: float) -> str:
    h = days * 24
    return f"{h:.0f}h" if h < 48 else f"{days:.1f}d"


def _holds() -> list[float]:
    """Realized holding periods in hours, from the closed book."""
    import sqlite3
    from datetime import datetime

    from .database import DB_PATH
    rows = sqlite3.connect(DB_PATH).execute(
        "SELECT opened_at, closed_at FROM trades "
        "WHERE closed_at IS NOT NULL AND opened_at IS NOT NULL").fetchall()

    def p(s):
        return datetime.fromisoformat(s.replace("Z", ""))
    out = []
    for a, b in rows:
        try:
            h = (p(b) - p(a)).total_seconds() / 3600
        except Exception:
            continue
        if h >= 0:
            out.append(h)
    return sorted(out)


def parts() -> dict:
    """Body + CSS, so /geometry can render it standalone or as a merged section."""
    sigma, live = _sigma()
    cfg = G.config(sigma, HOLD_DAYS, RR, WIN_RATE, max_drawdown=MAX_DD, streak=STREAK)
    min_hold = G.min_viable_hold(RR, WIN_RATE, sigma)

    # What the scanner is actually armed with right now.
    from .setups import SL_PCT, TP_PCT
    live_hold = G.implied_hold_days(SL_PCT, TP_PCT, sigma)
    live_edge = G.net_edge_pct(SL_PCT, TP_PCT, WIN_RATE)
    drift = abs(SL_PCT - cfg["stop_pct"]) / cfg["stop_pct"] > 0.15

    def pct(x, dp=2):
        return "—" if x is None else f"{x:.{dp}f}%"

    # ── 1. the law ───────────────────────────────────────────────────────────
    law = (
        '<div class="lawbox">'
        '<div class="lawl">the whole thing, in one line</div>'
        '<div class="law">win% × (target − friction) &gt; loss% × (stop + friction)</div>'
        '<div class="lawn">Leverage appears on neither side. It multiplies the win '
        'and the loss by the same factor, so it scales the P&amp;L and never flips '
        'its sign — a drawdown dial, not an edge dial. Every number below is '
        'therefore per unit of <b>notional</b>; leverage enters once, at the end, '
        'to convert a risk budget into a position size.</div></div>'
    )

    # ── 2. hold-time ladder ──────────────────────────────────────────────────
    rows = []
    for hrs in LADDER_HOURS:
        d = hrs / 24
        g = G.solve(sigma, d, RR)
        edge = G.net_edge_pct(g["stop_pct"], g["target_pct"], WIN_RATE)
        ok = edge > 0
        mark = ("<span class='y'>✓</span>" if ok else "<span class='n'>✗</span>")
        cls = "good" if ok else "bad"
        sel = " sel" if abs(d - HOLD_DAYS) < 1e-6 else ""
        rows.append(
            f"<tr class='{cls}{sel}'><td>{mark}</td><td class='m'>{_fmt_hold(d)}</td>"
            f"<td class='m'>{pct(g['stop_pct'])}</td><td class='m'>{pct(g['target_pct'])}</td>"
            f"<td class='m'>{g['friction_share_of_stop'] * 100:.0f}%</td>"
            f"<td class='m'>{pct(g['breakeven_wr'] * 100 if g['breakeven_wr'] else None, 1)}</td>"
            f"<td class='m'>{g['edge_needed_pp']:+.1f}pp</td>"
            f"<td class='m {'pos' if ok else 'neg'}'>{edge:+.3f}%</td></tr>"
        )
    ladder = (
        "<h2>How long does the trade take to resolve?</h2>"
        "<p class='lead'>A stop of <i>a</i> and a target of <i>b</i> on a random walk "
        f"of σ&nbsp;=&nbsp;{sigma:.2f}%/day resolve, on average, in <span class='m'>a·b/σ²</span> "
        "days. Fixing R:R and choosing a holding period therefore <i>determines</i> "
        "the stop — it is not a free parameter. Friction is a flat toll, but the stop "
        "shrinks with √hold, so the shorter the trade the larger the share of your "
        "risk the toll eats. That column is the one that decides it.</p>"
        "<table><tr><th></th><th>hold</th><th>stop</th><th>target</th>"
        "<th title='round-trip friction as a share of the stop'>toll / stop</th>"
        "<th>breakeven WR</th><th>edge vs coin</th><th>net / trade</th></tr>"
        + "".join(rows) + "</table>"
        f"<p class='note'>Coin-flip win rate at R:R&nbsp;{RR:g} is "
        f"<b>{cfg['coinflip_wr']:.0%}</b> — that is what a random entry gets, and every "
        f"“edge vs coin” figure is what you must supply <i>on top of it</i>. Assuming you "
        f"supply +{(WIN_RATE - cfg['coinflip_wr']) * 100:.0f}pp (a {WIN_RATE:.0%} win rate), "
        f"the shortest hold that still clears friction is "
        f"<b>{_fmt_hold(min_hold) if min_hold else 'unreachable'}</b>. "
        "Below that the trade is negative before you have an opinion about direction.</p>"
    )

    # ── 3. what changed, and whether the armed pair still matches ────────────
    old_hold = G.implied_hold_days(OLD_SL, OLD_TP, sigma)
    old_edge = G.net_edge_pct(OLD_SL, OLD_TP, WIN_RATE)
    old_g = G.solve(sigma, old_hold, OLD_TP / OLD_SL)

    verdict = (
        '<div class="cmp">'
        '<div class="cmpc old"><div class="cmpl">was — fitted 2026-07-02</div>'
        f'<div class="cmpv">{OLD_SL:.2f}% / {OLD_TP:.2f}%</div>'
        f'<div class="cmps">R:R {OLD_TP / OLD_SL:.2f} · resolves in ~{_fmt_hold(old_hold)} · '
        f'toll is {G.FRICTION_PCT / OLD_SL * 100:.0f}% of the stop</div>'
        f'<div class="cmpe {"pos" if old_edge > 0 else "neg"}">{old_edge:+.3f}% / trade '
        f'at a {WIN_RATE:.0%} win rate</div>'
        f'<div class="cmpw">needed {old_g["breakeven_wr"]:.0%} to break even, against a '
        f'{old_g["coinflip_wr"]:.0%} coin flip</div></div>'
        '<div class="cmpar">→</div>'
        '<div class="cmpc"><div class="cmpl">now — derived from σ</div>'
        f'<div class="cmpv hi">{SL_PCT:.2f}% / {TP_PCT:.2f}%</div>'
        f'<div class="cmps">R:R {TP_PCT / SL_PCT:.2f} · resolves in ~{_fmt_hold(live_hold)} · '
        f'toll is {G.FRICTION_PCT / SL_PCT * 100:.0f}% of the stop</div>'
        f'<div class="cmpe {"pos" if live_edge > 0 else "neg"}">{live_edge:+.3f}% / trade '
        f'at a {WIN_RATE:.0%} win rate</div>'
        f'<div class="cmpw">needs {cfg["breakeven_wr"]:.1%} against a '
        f'{cfg["coinflip_wr"]:.0%} coin flip — {cfg["edge_needed_pp"]:+.1f}pp of real edge</div>'
        '</div></div>'
    )

    # ── 4. the configuration ─────────────────────────────────────────────────
    def kv(k, v, sub=""):
        return (f'<div class="kv"><span class="k">{k}</span>'
                f'<span class="v">{v}</span>'
                + (f'<span class="s">{sub}</span>' if sub else "") + "</div>")

    conf = (
        "<h2>The configuration</h2>"
        '<div class="conf">'
        + kv("hold", f"{HOLD_DAYS} days", f"{cfg['trades_per_week']:.1f} trades/week")
        + kv("R:R", f"{RR:g}", f"coin-flip win rate {cfg['coinflip_wr']:.0%}")
        + kv("stop", pct(cfg["stop_pct"]), f"σ·√(hold/R) at σ={sigma:.2f}%/d")
        + kv("target", pct(cfg["target_pct"]), "stop × R:R")
        + kv("win rate assumed", f"{WIN_RATE:.0%}",
             f"breakeven is {cfg['breakeven_wr']:.1%} — margin of "
             f"{(WIN_RATE - cfg['breakeven_wr']) * 100:+.1f}pp")
        + kv("risk / trade", pct(cfg["risk_pct"]),
             f"caps a {STREAK}-loss streak at {MAX_DD:.0%} drawdown")
        + kv("leverage", f"{cfg['leverage']:.2f}×",
             "derived from the risk budget, not chosen")
        + kv("net / trade", f"{cfg['per_trade_acct_pct']:+.3f}%", "of account")
        + kv("compounded", f"{cfg['monthly_pct']:+.2f}% / month",
             f"{cfg['weekly_pct']:+.2f}% / week")
        + "</div>"
        f"<p class='note'>A {STREAK}-loss streak at a {WIN_RATE:.0%} win rate is roughly a "
        f"<b>{cfg['streak_odds_per_100']:.1f}-in-100-trades</b> event, so the drawdown cap "
        f"is sized for something that actually happens rather than a ghost.</p>"
    )

    # ── 5. friction ladder — the only input he controls by decision ──────────
    frows = []
    for label, f in G.FRICTION_LADDER.items():
        c = G.config(sigma, HOLD_DAYS, RR, WIN_RATE, friction_pct=f,
                     max_drawdown=MAX_DD, streak=STREAK)
        cur = " sel" if abs(f - G.FRICTION_PCT) < 1e-9 else ""
        frows.append(
            f"<tr class='{cur.strip()}'><td class='m'>{f:.2f}%</td><td>{label}</td>"
            f"<td class='m'>{c['breakeven_wr']:.1%}</td>"
            f"<td class='m {'pos' if c['positive'] else 'neg'}'>"
            f"{c['monthly_pct']:+.2f}%</td></tr>"
        )
    fric = (
        "<h2>The dial that actually moves it</h2>"
        "<p class='lead'>σ is the market's, and the win rate is a hope until several "
        "hundred trades say otherwise. Friction is the one input on this page you set "
        "by <i>decision</i> — limit orders instead of market orders, and the toll halves.</p>"
        "<table><tr><th>round trip</th><th>how</th><th>breakeven WR</th>"
        "<th>net / month</th></tr>" + "".join(frows) + "</table>"
    )

    # ── 6. fragility ─────────────────────────────────────────────────────────
    wrows = []
    for w in (0.20, 0.22, 0.24, 0.25, 0.28, 0.32):
        c = G.config(sigma, HOLD_DAYS, RR, w, max_drawdown=MAX_DD, streak=STREAK)
        tag = ""
        if abs(w - WIN_RATE) < 1e-9:
            tag = " sel"
        elif abs(w - cfg["coinflip_wr"]) < 1e-9:
            tag = " coin"
        wrows.append(
            f"<tr class='{tag.strip()}'><td class='m'>{w:.0%}</td>"
            f"<td class='m'>{(w - cfg['coinflip_wr']) * 100:+.0f}pp</td>"
            f"<td class='m {'pos' if c['positive'] else 'neg'}'>"
            f"{c['monthly_pct']:+.2f}%</td></tr>"
        )
    frag = (
        "<h2>How fragile is this?</h2>"
        f"<p class='lead'>Breakeven sits at <b>{cfg['breakeven_wr']:.1%}</b>, "
        f"{(cfg['breakeven_wr'] - cfg['coinflip_wr']) * 100:.1f}pp above a coin flip. "
        "The entire result therefore lives in a band a few points wide, around a "
        "quantity you cannot measure to that precision without several hundred trades. "
        "This is the honest weakness of the configuration and it is not fixable by "
        "arithmetic — only by trade count.</p>"
        "<table><tr><th>win rate</th><th>vs coin</th><th>net / month</th></tr>"
        + "".join(wrows) + "</table>"
        "<p class='note'>The measured ledger runs at <b>−6.6%/month</b> geometric, "
        "which is what this table looks like from the wrong side of breakeven — "
        "consistent with a stop inside the noise and leverage multiplying the toll. "
        "The fix is the geometry above plus not trading VETO contexts, in that order.</p>"
    )

    # ── 7. does the market even offer this? ──────────────────────────────────
    #
    # ⚠ The supply check counts DAYS whose range clears the target, but this
    # geometry is held for HOLD_DAYS. A 2.83% move accumulated over 2.5 days
    # never shows up in any single day's range, so the badge is measuring the
    # wrong window and reads far more pessimistic than the trade actually is.
    # Scale the threshold to a single day (σ√t scaling: move ÷ √hold) so the
    # comparison is at least like-for-like, and say plainly that it's a proxy.
    avail = ""
    try:
        from .realism import badge
        per_day_move = cfg["target_pct"] / sqrt(HOLD_DAYS)
        b = badge(per_day_move, cfg["trades_per_week"])
        raw = badge(cfg["target_pct"], cfg["trades_per_week"])
        if b:
            tone = {"OFFERED": "pos", "TIGHT": "warn", "STARVED": "neg"}.get(b["badge"], "")
            # Hold at which demand falls to the supply on offer — the honest
            # answer to a STARVED reading, since supply itself cannot be moved.
            alt_hold = round(7.0 / b["offers"], 1) if b.get("offers") else HOLD_DAYS
            raw_line = ""
            if raw and raw["badge"] != b["badge"]:
                raw_line = (
                    f"<br><span class='sub'>Against the undiscounted "
                    f"{cfg['target_pct']:.2f}% the same check says "
                    f"<b>{raw['badge']}</b> ({raw['offers']:g}/wk) — but that asks for the "
                    f"whole move inside one day, which is not what this trade does.</span>"
                )
            avail = (
                "<h2>Is that move on offer?</h2>"
                f'<div class="avail {tone}"><b>{b["badge"]}</b> — {b["text"]}{raw_line}</div>'
                "<p class='note'>Feasible and available are different questions, and this "
                "check answers the second one badly on purpose. It counts <i>days</i> whose "
                f"range clears a threshold, so a {cfg['target_pct']:.2f}% move gathered over "
                f"{HOLD_DAYS} days is invisible to it. The threshold above is therefore "
                f"discounted to its one-day equivalent ({per_day_move:.2f}% = target ÷ √hold). "
                "Both readings are a proxy — they ignore intraday path and cap one day at one "
                "setup. Treat this as a direction, not a number, until the ledger has enough "
                f"{HOLD_DAYS}-day trades to answer it directly.</p>"
                + (
                    "<p class='note'><b>If this reads STARVED, widening the target will not "
                    f"fix it.</b> Target ∝ √hold, so the one-day threshold is σ·√(R:R) = "
                    f"{sigma * sqrt(RR):.2f}% at <i>every</i> holding period — the supply "
                    "number above does not move when you change the hold. What moves is the "
                    f"demand: holding {alt_hold:g} days instead of {HOLD_DAYS:g} needs only "
                    f"{7.0 / alt_hold:.1f} trades a week instead of "
                    f"{cfg['trades_per_week']:.1f}, which is the same supply against a "
                    "smaller need. Fewer, longer trades — not a different target.</p>"
                    if b["badge"] == "STARVED" else ""
                )
            )
    except Exception:
        pass

    # ── 7b. the backtest: what a RANDOM entry gets on 7 years of real bars ───
    #
    # The model's two predictions are falsifiable, so they were tested: every
    # hourly bar 2019→now taken as an entry, walked forward to whichever barrier
    # is touched first (stop wins ties). This is the baseline any claimed edge
    # has to be stated against. research/barrier_test.py regenerates the cache.
    base = ""
    try:
        import json
        from .paths import RESULTS
        with open(RESULTS / "barrier_baseline.json") as fh:
            bl = json.load(fh)
        if abs(bl["stop_pct"] - SL_PCT) < 0.01 and abs(bl["target_pct"] - TP_PCT) < 0.01:
            gap = bl["edge_needed_pp"]
            base = (
                "<h2>What a random entry actually gets</h2>"
                "<p class='lead'>The model above makes two predictions that can be "
                f"checked, so they were: every hourly bar from {bl['from']} to "
                f"{bl['to']} ({bl['bars']:,} of them) taken as an entry and walked "
                "forward until a barrier is touched. No setups, no filters, no edge — "
                "this is the floor the geometry sits on.</p>"
                '<div class="conf">'
                + kv("target reached", f"{bl['win_rate']:.1%}",
                     f"model predicted {cfg['coinflip_wr']:.0%} — the random-walk "
                     "assumption holds")
                + kv("moves are reachable", f"{bl['long']['n']:,}",
                     f"entries resolved; {bl['long']['win_rate']:.1%} of longs hit "
                     f"+{TP_PCT:.2f}% before −{SL_PCT:.2f}%")
                + kv("real hold", f"{bl['median_hold_h']:.0f}h",
                     f"median — <b>not</b> the {HOLD_DAYS}d the model implies; "
                     "BTC resolves faster than a Gaussian walk")
                + kv("winners take", f"{bl['long']['median_win_h']:.0f}h",
                     f"losers take {bl['long']['median_loss_h']:.0f}h — cut fast, "
                     "hold the runners")
                + kv("random net", f"{bl['long']['net_pct']:+.3f}%",
                     "per trade, long side · shorts "
                     f"{bl['short']['net_pct']:+.3f}%")
                + kv("edge you must add", f"{gap:+.1f}pp",
                     f"random {bl['win_rate']:.1%} → breakeven "
                     f"{bl['breakeven_wr']:.1%}")
                + "</div>"
                "<p class='note'><b>Two things this settles.</b> First, the moves are "
                f"reachable — {bl['long']['n']:,} of {bl['bars']:,} entries resolved and "
                f"{bl['long']['win_rate']:.0%} of longs reached +{TP_PCT:.2f}%. The book's "
                "0-of-512 was a fact about holding time, never about the market. Second, "
                "<b>geometry alone is not an edge</b>: a random entry still loses roughly "
                "the friction, as it must. What the new geometry bought is a smaller bar "
                f"to clear — <b>{gap:.1f}pp</b> over random, where the superseded 0.63/1.5 "
                "needed <b>14.9pp</b>. Same market, a quarter of the required skill.</p>"
                "<p class='note'>The honest reading of the hold column: the barrier "
                f"identity says {HOLD_DAYS} days, the market delivers {bl['median_hold_h']:.0f}h "
                "median. Volatility clusters, so barriers get touched sooner than a "
                "constant-σ walk predicts. Good news for trade supply; it does not change "
                "the net, which is computed from the realized win rate above.</p>"
            )
    except Exception:
        pass

    # ── 8. the honest check: has this ever been done? ────────────────────────
    #
    # The reachability verdict on this book is STARVED at every cell, and it is
    # tempting to read that as "the geometry is wrong". It isn't — reach is
    # measured over the trades he TOOK, at the holds he CHOSE, and those holds
    # are hours. A 2.83% move takes ~2.5 days to arrive; a 2-hour trade cannot
    # reach it, so 0/512 is what the barrier math predicts rather than evidence
    # against it. What the ledger genuinely establishes is the harder point:
    # the config needs a holding period with essentially no precedent here.
    ledger = ""
    try:
        from .excursion import reachability
        holds = _holds()
        r = reachability(cfg["target_pct"], cfg["stop_pct"])
        if holds and r:
            n = len(holds)
            med = holds[n // 2]
            over = sum(1 for h in holds if h >= HOLD_DAYS * 24) / n
            over_min = sum(1 for h in holds if h >= (min_hold or 99) * 24) / n
            typical_move = sigma * sqrt(med / 24)
            ledger = (
                "<h2>Has this ever been done?</h2>"
                f'<div class="warn-b" style="border-color:var(--amber);'
                f'background:var(--amber-d)">'
                f'<b>No — and that is the real constraint, not the arithmetic.</b> '
                f'Median hold across {n} closed trades is <b>{med:.1f} hours</b>. '
                f'Only <b>{over:.1%}</b> were held the {HOLD_DAYS} days this geometry '
                f'assumes, and only {over_min:.1%} cleared even the {_fmt_hold(min_hold)} '
                f'breakeven floor.</div>'
                f"<p class='note'><b>{r['hit']}/{r['n']}</b> fills ever travelled "
                f"{cfg['target_pct']:.2f}%, so the book's reachability verdict on this "
                f"geometry is <b>{r['badge']}</b>. That is not evidence against it: a "
                f"{med:.1f}-hour trade moves about {typical_move:.2f}% "
                f"(σ·√t), so it <i>cannot</i> reach {cfg['target_pct']:.2f}% — the zero is "
                "what the barrier math predicts, not a refutation of it. The old 0.63/1.5 "
                "scored better on this test purely because its target was small enough to "
                "be reachable inside a two-hour trade, which is also why it lost money.</p>"
                "<p class='note'>What the ledger does establish is that this configuration "
                "is <b>untested</b> here. Every number on this page is theory until trades "
                "are actually held for days, and holding is the part that has never been "
                "done. Treat the first fifty as an experiment in <i>holding</i>, not in "
                "entry selection — the entry is the part the ledger already says isn't the "
                "binding constraint.</p>"
            )
    except Exception:
        pass

    stale = ""
    if drift:
        stale = (
            '<div class="warn-b">The armed geometry is more than 15% away from what '
            'the current volatility regime implies. <span class="m">setups.SL_PCT / '
            'TP_PCT</span> are constants, deliberately — the scanner should not change '
            'its stop without you approving it — so they need a manual edit when this '
            'banner appears.</div>'
        )

    src = (f"σ {sigma:.2f}%/day from the live 30-day close series"
           if live else
           f"σ {sigma:.2f}%/day — <b>fallback</b>, the OHLCV cache is cold")

    body = (
        f'<p class="lead top">Every stop and target LENS quotes comes from here. '
        f'Two measured inputs — {src}, and {G.FRICTION_PCT:.2f}% round-trip friction — '
        f'plus two decisions: hold {HOLD_DAYS} days at R:R {RR:g}. '
        f'Nothing on this page is fitted to past winners.</p>'
        + stale + verdict + law + ladder + conf + base + fric + frag + avail + ledger +
        '<p class="foot"><a href="/audit">→ what this supersedes</a> · '
        '<a href="/manual?doc=glossary">→ the terms</a> · '
        '<a href="/edge">→ live strategy ranks</a><br>'
        '<span class="m">python3 -m app.geometry</span> runs the same math with its '
        'assertions, if you want the identities checked rather than asserted.</p>'
    )

    css = (
        "<style>"
        "h2{font-family:var(--mono);font-size:11px;letter-spacing:.16em;"
        "text-transform:uppercase;color:var(--faint);margin:34px 0 10px;font-weight:600}"
        "p.lead{color:var(--dim);font-size:13.5px;line-height:1.65;max-width:74ch;margin:0 0 14px}"
        "p.lead.top{color:var(--ink);font-size:14px;margin-bottom:20px}"
        "p.note{color:var(--faint);font-size:12.5px;line-height:1.6;max-width:74ch;margin:12px 0 0}"
        "p.foot{margin-top:34px;font-size:12.5px;color:var(--faint);line-height:1.9}"
        "p.foot a{color:var(--accent);text-decoration:none;margin-right:4px}"
        ".m{font-family:var(--mono)}"
        "table{border-collapse:collapse;width:100%;font-size:13px;margin-top:4px}"
        "th{text-align:left;color:var(--faint);font-family:var(--mono);font-size:10px;"
        "text-transform:uppercase;letter-spacing:.12em;padding:7px 9px;"
        "border-bottom:1px solid var(--line);white-space:nowrap}"
        "td{padding:8px 9px;border-bottom:1px solid var(--line)}"
        "td.m{font-family:var(--mono);font-size:12.5px;white-space:nowrap}"
        "tr.sel{background:var(--accent-d)}"
        "tr.coin td{color:var(--faint)}"
        ".y{color:var(--long)} .n{color:var(--short)}"
        ".pos{color:var(--long)} .neg{color:var(--short)} .warn{color:var(--amber)}"
        # comparison block
        ".cmp{display:grid;grid-template-columns:1fr auto 1fr;gap:14px;align-items:center;"
        "margin:18px 0 4px}"
        ".cmpc{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}"
        ".cmpc.old{opacity:.72}"
        ".cmpw{font-family:var(--mono);font-size:10.5px;color:var(--faint);"
        "margin-top:6px;line-height:1.5}"
        ".cmpl{font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;"
        "text-transform:uppercase;color:var(--faint)}"
        ".cmpv{font-family:var(--mono);font-size:23px;font-weight:700;margin:7px 0 5px}"
        ".cmpv.hi{color:var(--accent)}"
        ".cmps{font-family:var(--mono);font-size:11px;color:var(--dim);line-height:1.5}"
        ".cmpe{font-family:var(--mono);font-size:12px;margin-top:9px;padding-top:8px;"
        "border-top:1px solid var(--line)}"
        ".cmpar{color:var(--faint);font-size:19px}"
        # law
        ".lawbox{background:var(--panel2);border:1px solid var(--line2);border-radius:10px;"
        "padding:15px 17px;margin:20px 0}"
        ".lawl{font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;"
        "text-transform:uppercase;color:var(--faint)}"
        ".law{font-family:var(--mono);font-size:15px;color:var(--ink);margin:9px 0 10px;"
        "letter-spacing:.01em}"
        ".lawn{color:var(--dim);font-size:12.5px;line-height:1.65;max-width:74ch}"
        # config grid
        # 9 cells — 3×3 exactly, so the last row isn't a ragged gap
        ".conf{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));"
        "gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;"
        "overflow:hidden;margin-top:6px}"
        ".kv{background:var(--panel);padding:12px 14px}"
        ".kv .k{display:block;font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;"
        "text-transform:uppercase;color:var(--faint)}"
        ".kv .v{display:block;font-family:var(--mono);font-size:17px;font-weight:600;margin:5px 0 3px}"
        ".kv .s{display:block;font-size:11.5px;color:var(--dim);line-height:1.45}"
        # misc
        ".warn-b{background:var(--short-d);border:1px solid var(--short);border-radius:9px;"
        "padding:12px 15px;margin:16px 0;font-size:13px;line-height:1.6}"
        ".avail{font-family:var(--mono);font-size:13px;padding:12px 15px;border-radius:9px;"
        "background:var(--panel);border:1px solid var(--line)}"
        ".avail.pos{border-color:var(--long)} .avail.neg{border-color:var(--short)}"
        ".avail.warn{border-color:var(--amber)}"
        ".avail .sub{color:var(--faint);font-size:11px;line-height:1.55;display:inline-block;margin-top:7px}"
        "@media(max-width:900px){.conf{grid-template-columns:repeat(2,minmax(0,1fr))}}"
        "@media(max-width:720px){.cmp{grid-template-columns:1fr}.cmpar{display:none}"
        ".conf{grid-template-columns:1fr}}"
        "</style>"
    )
    return {"body": body, "css": css}


def render() -> str:
    p = parts()
    return shell("/geometry", "Geometry", p["body"], head_extra=p["css"],
                 meta="where the stop comes from")
