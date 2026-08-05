"""LENS /philosophy — ONE idea: he is not all in on bitcoin. Twelve percent.

Second pass 2026-08-05, same evening. The first pass had five sections — FIRE,
the allocation, cold vs hot, stock-to-flow, and a closing meditation. His read:
"most people when it comes to the philosophy they just want to know the split,
the allocation map... I feel like even that is a bit crazy for people to get.
I think one concept is enough."

He's right, and the page is now built around that instead of arguing with it.
The hundred-dot grid is the whole argument: everything he owns, twelve dots of
it crypto. A reader who sees only that picture has understood the page, and it
does the thing no paragraph on the old version managed — it kills the "bitcoin
guy is all in on bitcoin" assumption in about a second, without a sentence.

Everything else was DEMOTED, not deleted:

  · the seven-class table → the detail layer under the grid, where it explains
    the picture instead of competing with it
  · cold vs hot → two sentences inside that same detail layer, which is where
    it always belonged; it is a split *inside* class 7, not a worldview
  · FIRE, 25x vs 50x, and DCA → one fold with its own hook, second and quieter
  · stock-to-flow → a short closing note with the primary sources kept, because
    the links are genuinely worth someone's time

⛔ CUT, at his explicit request: the old closing section, "Skeptical of my own
conclusions, on purpose." His words — "you don't need to be like a fucking
saint... the whole like I'm a skeptic about my own system, you don't need to be
like that." He was right. It read as piety, and a page that performs humility
is doing the same job as one that boasts. Do not restore it.

⚠️ The target weights are DUPLICATED here from `~/mine/spec/seed_allocation.csv`
(Compact!OB1:OE75) because this app cannot read `~/mine`. The dot grid is
GENERATED from the same list, so the picture can never disagree with the table
below it — but neither can notice if the seed file changes. The self-check at
the bottom catches a bad edit here; nothing catches drift over there.

⚠️ NOT called "the Adaptive Horizons Partnership GLTLP Trust Structure Service
Agreement", which is his own name for it. GP/LP language on a public page reads
as an offering document to exactly the reader who must never read it that way.
Its own root row says "Diversified Income Strategies" — accurate, and also his.

Same rules as /about: no P&L, no account size, no creditors or amounts owed,
no solicitation, no AKA Blockchains, no retyped statistics.
"""

from .site import site_shell

# Class-level target weights, from ~/mine/spec/seed_allocation.csv. Percentages
# are whole numbers so they double as the dot count in the grid.
ALLOCATION = [
    ("Cash & liquidity", 15, "Two banks and money-market funds. Boring on purpose."),
    ("Savings & bonds", 20, "Deposits, government and corporate bonds, bond ETFs."),
    ("Core compounding", 20, "Index funds, dividend stocks, growth stocks."),
    ("Real estate", 15, "Direct property, REITs, land."),
    ("Alternatives", 8, "Precious metals, commodities, private loans."),
    ("Private equity / VC", 10, "Funds, venture, hedge funds."),
    ("Crypto", 12, "Ten of these twelve is bitcoin in cold storage, never traded."),
]
CRYPTO_PCT = dict((n, p) for n, p, _ in ALLOCATION)["Crypto"]

_CSS = r"""<style>
/* ── the hundred dots · the only picture on the page ────────────────────
   One dot is one percent of everything he owns. Twelve are lit. The whole
   argument of the page is a proportion, so the proportion is drawn and
   nothing is allowed to inflate it — no glow on the lit dots, because a
   bloom makes twelve read as nearer twenty. */
.dots{display:grid;grid-template-columns:repeat(10,1fr);gap:6px;max-width:340px;
  margin:4px 0 0}
.dots i{aspect-ratio:1;border-radius:50%;background:var(--ghost);display:block}
.dots i.on{background:var(--accent)}
.dkey{display:flex;gap:20px;flex-wrap:wrap;font-family:var(--mono);font-size:10px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-top:18px}
.dkey i{width:8px;height:8px;border-radius:50%;display:inline-block;
  margin-right:7px;background:var(--ghost);vertical-align:middle}
.dkey i.on{background:var(--accent)}

/* ── the seven classes · the detail layer under the picture ───────────── */
.alloc{margin:18px 0 0;border:1px solid var(--line)}
.alloc .r{display:grid;grid-template-columns:1fr auto;gap:3px 14px;
  align-items:baseline;padding:11px 14px;border-top:1px solid var(--line)}
.alloc .r:first-child{border-top:0}
.alloc .r.btc{background:var(--panel)}
.alloc .nm{font-family:var(--hud);font-weight:700;font-size:13px;
  letter-spacing:.03em;color:var(--ink)}
.alloc .r.btc .nm{color:var(--accent)}
.alloc .pc{font-family:var(--hud);font-weight:700;font-size:14px;color:var(--dim)}
.alloc .r.btc .pc{color:var(--accent)}
.alloc .nt{grid-column:1/-1;font-size:12px;line-height:1.5;color:var(--faint)}
/* 20% is the largest class, so 5x scales it to a full row and the rest read
   against it honestly */
.alloc .br{grid-column:1/-1;height:3px;background:var(--line2);margin-top:4px}
.alloc .br i{display:block;height:100%;background:var(--dim)}
.alloc .r.btc .br i{background:var(--accent)}
</style>"""


def _dots_html() -> str:
    """One hundred dots, generated from ALLOCATION so it can never disagree
    with the table. The crypto block sits last: a contiguous run reads as a
    proportion, whereas scattering it reads as a texture."""
    lit = CRYPTO_PCT
    cells = "".join('<i></i>' for _ in range(100 - lit)) + \
            "".join('<i class="on"></i>' for _ in range(lit))
    return (f'<div class="dots" role="img" aria-label="One hundred dots, one for '
            f'each percent of everything he owns. {lit} are lit: that is all the '
            f'crypto.">{cells}</div>'
            f'<div class="dkey"><span><i class="on"></i>crypto · {lit}</span>'
            f'<span><i></i>everything else · {100 - lit}</span></div>')


def _alloc_html() -> str:
    rows = "".join(
        f'<div class="r{" btc" if nm == "Crypto" else ""}">'
        f'<div class="nm">{nm}</div><div class="pc">{pc}%</div>'
        f'<div class="nt">{note}</div>'
        f'<div class="br"><i style="width:{pc * 5}%"></i></div></div>'
        for nm, pc, note in ALLOCATION)
    return f'<div class="alloc">{rows}</div>'


def _body() -> str:
    return f"""
<h1>People assume I'm all in on bitcoin. It's
<em>{CRYPTO_PCT} percent</em>.</h1>

<p class="lede">Hold a spread of things, keep the costs low, let time do the
work. <b>None of that is original</b> — the research is decades old and the
calculators are free. This is just where I actually put it.</p>

<section>
  <div class="lbl">everything I own, as a hundred dots</div>
  {_dots_html()}
  <p class="hook">Twelve dots. That's <em>all</em> of the crypto.</p>

  <p class="detail">Bitcoin is the engine, not the destination. It's the thing
  volatile enough to get me back to a number that matters — and the whole plan
  is to spend years moving it out into the other six rows, until I don't need
  it to keep behaving.</p>

  {_alloc_html()}

  <p class="detail">Two of those twelve points are money at work: a funded
  exchange account, one strategy, a fixed risk budget. <b>The other ten sit in
  cold storage and are never traded.</b> Keeping those two apart is most of the
  discipline — the failure mode that ends people is letting the active side
  borrow from the patient side after a bad run, to make it back.</p>
</section>

<section>
  <div class="lbl">when I get to stop</div>
  <p class="hook">Enough is <em>fifty times</em> what I spend in a year.</p>

  <p class="detail">The standard number is 25 times your annual spending, which
  is the same as withdrawing 4% a year. <b>I use fifty.</b> That rule was
  measured on stocks and bonds, and a withdrawal rate that survives a normal
  recession will not survive an 80% drawdown lasting two years. Doubling it is
  what holding a volatile asset actually costs.</p>

  <p class="detail">And because it's a multiple of spending rather than a fixed
  sum, where I live moves the finish line. Fifty times a Bangkok year is a far
  smaller pile than fifty times a New York one. Getting there is unglamorous:
  ten or twenty a day into a regulated exchange, whatever the price is that
  morning, for years.</p>
</section>

<section>
  <div class="lbl">one thing I got badly wrong</div>
  <p class="hook">I believed a model with a perfect record and <em>no</em>
  mechanism.</p>

  <p class="detail">Stock-to-flow said bitcoin's price followed from its
  programmed scarcity. It was quantitative, it fit history almost exactly, and
  after 2021 it missed by orders of magnitude. A flawless backtest and no test
  against data it hadn't already seen — that's the definition of over-fitting,
  and it's why nothing gets counted here until it survives data it has never
  met.</p>

  <p class="small">Worth your time rather than my summary:
  <a href="https://bitcoin.org/bitcoin.pdf">the bitcoin whitepaper</a> ·
  <a href="https://medium.com/@100trillionUSD/modeling-bitcoins-value-with-scarcity-91fa0fc03e25">the
  original 2019 stock-to-flow thesis</a> ·
  <a href="https://www.bitcoinmagazinepro.com/charts/stock-to-flow-model/">the model
  charted against what actually happened</a> — that last one is the model next
  to reality, rather than the model on its own.</p>
</section>
"""


def render() -> str:
    return site_shell("/philosophy", "Philosophy", _body(), extra_css=_CSS)


if __name__ == "__main__":
    import re
    # ponytail: the picture and the table are generated from one list, so the
    # only thing that can break is the list itself. A grid of 100 dots showing
    # a weight set that sums to 97 is worse than no page.
    assert len(ALLOCATION) == 7, ALLOCATION
    assert sum(p for _, p, _ in ALLOCATION) == 100, ALLOCATION
    body = _body()
    # Count inside the GRID only — the legend below it repeats one of each dot,
    # and the allocation bars are <i style=...>. Scope, then count.
    grid = body.split('<div class="dkey">')[0].split('<div class="dots"')[1]
    assert grid.count('<i class="on"></i>') == CRYPTO_PCT, grid.count('<i class="on"></i>')
    assert grid.count("<i></i>") == 100 - CRYPTO_PCT
    assert grid.count("<i") == 100, "the grid is one dot per percent"
    for banned in ("owed", "creditor", "creditors", "gltlp", "adaptive horizons"):
        assert not re.search(rf"\b{banned}\b", body.lower()), banned
    print(f"ok — {CRYPTO_PCT} lit of 100, seven classes summing to 100")
