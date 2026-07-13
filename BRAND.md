# LENS — Brand

> The live version of this page renders in the app at **`/style`** (every token +
> component straight from `lens.css`). This file is the written reference. Source
> of truth for all values: **`app/theme.py`**.

LENS is a trading **instrument cluster** — it reads market state and reports it
flat. The whole brand follows from that one idea: a cockpit gauge, not a hype deck.

---

## Logo

`LEN` + accent `S` — the `S` is the only colored letter (`var(--accent)`).

```html
<span class="logo">LEN<span class="s">S</span></span>
```

- Display face: **Chakra Petch 700**, letter-spacing `.32em`, white.
- With a page label: `LENS <span class="pg">Desk</span>` — label is `--dim`, lighter weight.
- **Mark / favicon:** a scope / aperture iris (LENS = optics; concentric circles
  read as a target/scope at 16px). `FAVICON_SVG` in `app/theme.py`, served at
  `/assets/favicon.svg`. Accent ring, `--long` center dot, accent crosshair ticks
  on `--bg`, `7px` radius.
- Don't: recolor the whole word, add a tagline lockup, skew, or put it on a busy
  background. The mark sits on `--bg` only.

## Voice

**Instrument cluster, not a hype deck.** Report state; let the trader decide.

- **Terse + mechanical.** `ENTER` / `BLOCKED` / `STAND DOWN`, never "Great setup!!".
- **Numbers first, prose second.** Anything you'd read off a gauge is monospace.
- **Honest about edge.** A pattern is a coin-flip alone — say so. Never imply certainty.
- **Lowercase labels, UPPERCASE verdicts.** The interface whispers; the verdict speaks.
- No exclamation marks, no emoji in data, no "to the moon". Caution is `amber`, not hidden.

## Colors

Dark cockpit palette. Each status color pairs a bright foreground with a deep `-d`
fill for badges/banners.

| Role | Token | Hex |
|------|-------|-----|
| App background | `--bg` | `#06080c` |
| Panel / card | `--panel` | `#0b0f16` |
| Hairline border | `--line` | `#192232` |
| Primary text | `--ink` | `#e8eef8` |
| Secondary / labels | `--dim` | `#828ea6` |
| Captions | `--faint` | `#465064` |
| Accent / brand / interactive | `--accent` | `#5b9dff` |
| Long / positive / GO | `--long` | `#1fd989` |
| Short / negative / STOP | `--short` | `#ff5468` |
| Warn / veto / caution | `--amber` | `#f6ad3c` |

Semantics are fixed: **green = long/win/go, red = short/loss/stop, amber =
warn/veto, blue = neutral interactive.** Never use green/red decoratively.

## Type

- **Chakra Petch** (`--hud`) — display, verdicts, labels, UI chrome. Weights 400–700.
- **JetBrains Mono** (`--mono`) — all data: prices, R, %, tables, nav chips,
  timestamps. Weights 400–800.
- **Libre Caslon Text** (`--serif`) — **the front door only.** One serif line: the
  thesis on `/`. Caslon is the serif of engraved scientific printing, so it reads
  as an instrument plate, not a fashion magazine. The tension between it and the
  mono data is the point. Loaded by `home_page.py` alone, never by `theme.py` —
  no other page pays for it, and no other page may use it. An app screen that
  reaches for the serif is off-brand.

Scale (representative): price `30px/800`, verdict `34px/700`, big `24px/800`,
logo `17px/700`, body `14px/400`, mono data `12px/500`, nav `11px`, label
`10px` uppercase `.16em`.

## Spacing

- **Radii:** `7` (mark) · `8–10` (cards/chips) · `12–13` (panels/buttons) ·
  `16` (hero gauge) · `999` (nav chips, badges).
- **Elevation:** flat `--line` border by default; `--glow-g` / `--glow-r` glows
  signal an active ENTER / STOP state — elevation carries meaning, it isn't decoration.
- **Layout:** single column, max `460 → 720 → 1120px` at the `680 / 1080px`
  breakpoints. Phone-first.

## Components

Defined in `LENS_CSS`, shown live at `/style`: `.badge` (pending/approved/
rejected/expired), `.btn` (skip/take/aplus/ghost), `.chip` (good/bad),
inputs, topbar + scroll nav, `.scard` / `.panel` / `.gauge` cards, `.sb` tables,
`.kv` lists, the collapsible `.help-body` explainer.
