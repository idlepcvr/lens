"""Monthly review — NEXT_SESSION.md #1 (2026-08-26): the month's trades
grouped by setup_tag, computed live rather than by hand in sqlite, plus
somewhere to record a verdict on a veto combination so a tune/keep/retire
call has a date and a reason, the way a plan amendment does
(see `plan.amend`).

Cadence: `POST /api/review/notify` fires from cron on the 1st, ntfy same
topic/channel as everything else, pointing here at last month.

# ponytail: table created on first write/read, not in database.init_db —
# append-only, off the hot path. Same pattern as veto_log.py.
"""
from __future__ import annotations

import calendar
import html
import json
from datetime import date, datetime, timezone

from .database import _conn
from .theme import shell

_DDL = """
CREATE TABLE IF NOT EXISTS review_verdicts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    month   TEXT    NOT NULL,
    combo   TEXT    NOT NULL,
    verdict TEXT    NOT NULL,
    reason  TEXT    NOT NULL
)
"""

VERDICTS = ("keep", "tune", "retire")
MIN_REASON = 10
MIN_COMBO_N = 5   # combos below this are noise even to look at


def _month_bounds(month: str) -> tuple[str, str]:
    y, m = (int(x) for x in month.split("-"))
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}T23:59:59"


def _shift(month: str, delta: int) -> str:
    y, m = (int(x) for x in month.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _default_month() -> str:
    """The most recently *completed* calendar month — what a review on the
    1st is reviewing."""
    return _shift(date.today().strftime("%Y-%m"), -1)


def record_verdict(month: str, combo: str, verdict: str, reason: str) -> int:
    verdict = (verdict or "").strip().lower()
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        raise ValueError(f"reason needs at least {MIN_REASON} characters")
    if not combo.strip():
        raise ValueError("combo required")
    c = _conn()
    c.execute(_DDL)
    cur = c.execute(
        "INSERT INTO review_verdicts (ts, month, combo, verdict, reason) "
        "VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), month, combo.strip(), verdict, reason))
    c.commit()
    rid = cur.lastrowid
    c.close()
    return rid


def all_verdicts() -> list[dict]:
    c = _conn()
    c.execute(_DDL)
    rows = c.execute("SELECT * FROM review_verdicts ORDER BY id DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]


def _stat(pnls: list[float]) -> dict:
    n = len(pnls)
    return {
        "n": n,
        "total": sum(pnls),
        "avg": (sum(pnls) / n) if n else 0.0,
        "win": (sum(1 for p in pnls if p > 0) / n * 100) if n else 0.0,
    }


def combo_reasons(combo: str) -> list[dict]:
    """His own typed reasoning, from every trade tagged with this exact
    combo that was also a recorded override — across the whole book, not
    just one month, since the combo itself is a lifetime pattern (this is
    what override_miner.py tests against). "The verdict shouldn't be typed
    blind — it should show what I actually said" (his words). Most combos
    will come back empty: veto_overrides only exists from 2026-08-21
    onward (execution went live then), so anything tagged before that has
    no linked reasoning to show, honestly, not silently.
    """
    from .veto_log import _DDL as VETO_DDL
    c = _conn()
    c.execute(VETO_DDL)
    rows = c.execute("""
        SELECT vo.ts, vo.user_reason, vo.veto_reasons, t.id AS trade_id, t.pnl
          FROM veto_overrides vo JOIN trades t ON t.id = vo.linked_trade_id
         WHERE t.setup_tag = ?
      ORDER BY vo.ts DESC
    """, (f"VETO:{combo}",)).fetchall()
    c.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["veto_reasons"] = json.loads(d["veto_reasons"] or "null")
        except (TypeError, ValueError):
            pass
        out.append(d)
    return out


def split(month: str) -> dict:
    """Three-way split by what the scanner said at entry (fired / nothing /
    VETO), plus a per-VETO-combo breakdown, for trades opened in `month`."""
    start, end = _month_bounds(month)
    c = _conn()
    rows = c.execute(
        """SELECT pnl, setup_tag FROM trades
           WHERE exit IS NOT NULL AND pnl IS NOT NULL
             AND opened_at >= ? AND opened_at <= ?""",
        (start, end)).fetchall()
    c.close()

    cats: dict[str, list[float]] = {"fired": [], "nothing": [], "veto": []}
    combos: dict[str, list[float]] = {}
    for r in rows:
        tag = r["setup_tag"] or ""
        pnl = r["pnl"] or 0.0
        if tag.startswith("VETO:"):
            cats["veto"].append(pnl)
            combos.setdefault(tag[5:], []).append(pnl)
        elif tag in ("", "NONE"):
            cats["nothing"].append(pnl)
        else:
            cats["fired"].append(pnl)

    return {
        "cats": {k: _stat(v) for k, v in cats.items()},
        "combos": {k: _stat(v) for k, v in
                   sorted(combos.items(), key=lambda kv: -abs(sum(kv[1])))
                   if len(v) >= MIN_COMBO_N},
    }


def notify_monthly() -> bool:
    from .setups import _notify
    month = _default_month()
    d = split(month)
    fired, veto = d["cats"]["fired"], d["cats"]["veto"]
    body = (
        f"{month}: setup-fired {fired['n']}tr €{fired['total']:+,.0f}"
        f" · VETO {veto['n']}tr €{veto['total']:+,.0f}\n"
        f"{len(d['combos'])} veto combo(s) with n≥{MIN_COMBO_N} — "
        f"{sum(1 for r in all_verdicts() if r['month']==month)} already reviewed.\n"
        "/review for the book"
    )
    return _notify(f"Monthly review · {month}", body, tags="calendar")


def _eur(v: float) -> str:
    return f"€{v:+,.2f}"


def _cat_rows(cats: dict) -> str:
    labels = {"fired": "a setup fired", "nothing": "nothing",
              "veto": "VETO — do not take"}
    out = []
    for k in ("fired", "nothing", "veto"):
        s = cats[k]
        out.append(
            f"<tr><td>{labels[k]}</td><td>{s['n']}</td>{_row_eur(s['total'])}"
            f"{_row_eur(s['avg'])}<td class=\"m\">{s['win']:.1f}%</td></tr>")
    return "".join(out)


def _row_eur(v: float) -> str:
    cls = "g" if v > 0 else ("r" if v < 0 else "m")
    return f"<td class=\"{cls}\">{_eur(v)}</td>"


def _combo_rows(combos: dict, month: str, done: set[str]) -> str:
    if not combos:
        return f'<tr><td colspan="6" class="m">no veto combo cleared n≥{MIN_COMBO_N} this month</td></tr>'
    from urllib.parse import quote
    out = []
    for combo, s in combos.items():
        badge = '<span class="badge approved">reviewed</span>' if combo in done else ""
        tag_url = quote(f"VETO:{combo}", safe="")
        out.append(
            f"<tr><td class=\"mono\"><a href=\"/journal?setup={tag_url}\" "
            f"style=\"color:var(--ink);text-decoration:none;border-bottom:1px dotted var(--dim)\" "
            f"title=\"see the actual trades behind this combo\">{html.escape(combo)}</a></td><td>{s['n']}</td>"
            f"{_row_eur(s['total'])}{_row_eur(s['avg'])}<td class=\"m\">{s['win']:.1f}%</td>"
            f"<td>{badge}"
            f'<button class="btn ghost" style="padding:3px 8px;font-size:11px" '
            f'onclick="reviewCombo(\'{html.escape(combo)}\')">record verdict</button></td></tr>')
    return "".join(out)


def _verdict_rows(rows: list[dict]) -> str:
    if not rows:
        return '<tr><td colspan="5" class="m">no verdicts recorded yet</td></tr>'
    out = []
    for r in rows[:30]:
        out.append(
            f"<tr><td class=\"m\" style=\"white-space:nowrap\">{r['ts'][:10]}</td>"
            f"<td style=\"white-space:nowrap\">{r['month']}</td>"
            f"<td class=\"mono\">{html.escape(r['combo'])}</td>"
            f"<td style=\"white-space:nowrap\"><span class=\"badge approved\">{r['verdict']}</span></td>"
            f"<td class=\"m\">{html.escape(r['reason'])}</td></tr>")
    return "".join(out)


def parts(month: str | None = None) -> dict:
    """Body + script, so /evidence can render this as its live monthly-review
    section. month links round-trip through /evidence?month=…#review rather
    than the old standalone /review?month= — see LEGACY_ROUTES in main.py."""
    month = month or _default_month()
    d = split(month)
    verdicts = all_verdicts()
    done = {r["combo"] for r in verdicts if r["month"] == month}
    prev_m, next_m = _shift(month, -1), _shift(month, 1)
    is_current = next_m > date.today().strftime("%Y-%m")

    body = f"""
<div class="help-body" style="margin-bottom:12px">
<h4>What this page answers</h4>
<p>The scanner tags every trade at entry — a named setup, nothing, or VETO
with its reasons. This groups a month's closed trades by that tag, live,
so a finding doesn't sit in a column nobody reads
(511 of 528 hedge trades had <code>followed_plan</code> NULL before this
existed — the discipline score was measuring silence). A veto combo that
survives a permutation test somewhere else (<code>research/override_miner.py</code>)
gets recorded here with a date and a reason, the way a plan amendment does.</p>
</div>

<div class="sb-wrap" style="margin-bottom:12px;display:flex;gap:10px;align-items:center">
<a class="btn ghost" href="/evidence?month={prev_m}#review">&larr; {prev_m}</a>
<b style="font-family:var(--mono);font-size:15px">{month}</b>
{'<a class="btn ghost" href="/evidence?month=' + next_m + '#review">' + next_m + ' &rarr;</a>' if not is_current else '<span class="m">current in progress</span>'}
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb">
<tr><th colspan="5">What the scanner saw at entry</th></tr>
<tr><th>scanner said</th><th>trades</th><th>total</th><th>avg/trade</th><th>win rate</th></tr>
{_cat_rows(d['cats'])}
</table>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb">
<tr><th colspan="6">Where the VETO trades split, by combination (n&ge;{MIN_COMBO_N})</th></tr>
<tr><th>veto combination</th><th>n</th><th>total</th><th>avg</th><th>win%</th><th>verdict</th></tr>
{_combo_rows(d['combos'], month, done)}
</table>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<h4 style="margin:0 0 8px">Record a verdict</h4>
<div id="rv-reasons"></div>
<div class="tg" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
  <label>combo<br><input id="rv-combo" class="mono" style="width:260px" placeholder="click 'record verdict' above, or type one"></label>
  <label>call<br>
    <select id="rv-verdict">
      <option value="keep">keep as VETO</option>
      <option value="tune">tune the rule</option>
      <option value="retire">retire — let it through</option>
    </select>
  </label>
  <label style="flex:1;min-width:220px">reason<br><input id="rv-reason" style="width:100%" placeholder="what changed your mind, in your own words"></label>
  <button class="btn take" onclick="submitVerdict()">save</button>
</div>
<div id="rv-msg" class="m" style="margin-top:6px"></div>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb">
<tr><th colspan="5">Verdict log</th></tr>
<tr><th>date</th><th>month</th><th>combo</th><th>call</th><th>reason</th></tr>
{_verdict_rows(verdicts)}
</table>
</div>
"""
    script = f"""
const MONTH = {month!r};
async function reviewCombo(combo) {{
  document.getElementById('rv-combo').value = combo;
  document.getElementById('rv-combo').scrollIntoView({{behavior:'smooth', block:'center'}});
  const box = document.getElementById('rv-reasons');
  box.innerHTML = '<div class="m">loading your reasoning on this combo…</div>';
  try {{
    const d = await fetch('/api/review/combo-reasons?combo=' + encodeURIComponent(combo)).then(r => r.json());
    const rows = d.reasons || [];
    if (!rows.length) {{
      box.innerHTML = '<div class="m" style="margin-bottom:8px">No linked override reasoning for this combo '
        + '— veto_overrides only exists from 2026-08-21 onward, so trades tagged before that have none. '
        + 'Verdict below is on the numbers alone.</div>';
      return;
    }}
    box.innerHTML = '<div style="margin-bottom:8px"><b>What you actually said, taking these trades:</b>' + rows.map(r =>
      `<div class="sb-wrap" style="margin-top:6px;padding:8px 10px">`
      + `<div class="m" style="font-size:11px">#${{r.trade_id}} · ${{r.ts.slice(0,16).replace('T',' ')}} · `
      + `<span class="${{r.pnl>=0?'g':'r'}}">${{r.pnl>=0?'+':''}}€${{Number(r.pnl).toFixed(2)}}</span></div>`
      + `<div style="font-size:12.5px;margin-top:3px">${{(r.user_reason||'').replace(/</g,'&lt;')}}</div>`
      + `</div>`
    ).join('') + '</div>';
  }} catch(e) {{ box.innerHTML = ''; }}
}}
async function submitVerdict() {{
  const combo = document.getElementById('rv-combo').value.trim();
  const verdict = document.getElementById('rv-verdict').value;
  const reason = document.getElementById('rv-reason').value.trim();
  const msg = document.getElementById('rv-msg');
  if (!combo) {{ msg.textContent = 'pick a combo first'; return; }}
  const r = await fetch('/api/review/verdict', {{
    method: 'POST', headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{month: MONTH, combo, verdict, reason}})
  }});
  if (r.ok) {{ location.reload(); }}
  else {{ const e = await r.json(); msg.textContent = e.detail || 'failed'; }}
}}
"""
    return {"body": body, "script": script}


def render(month: str | None = None) -> str:
    """Standalone shell — kept for anything that still wants a bare page;
    the live route is /evidence#review (see main.py)."""
    p = parts(month)
    return shell("/evidence", "Review", p["body"], script=p["script"],
                 meta="monthly discipline check")
