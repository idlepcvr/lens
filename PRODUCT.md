# Product

[Open as HTML](PRODUCT.html)

## Register

product

## Users

A single user — the owner, a solo crypto-futures trader running two books: a
Kraken prop-firm evaluation ladder (PROP) and a personal account (HEDGE).
Primary device is **phone** (daily driver, checked pre-trade and at review);
**desktop** is the secondary, deeper-work surface. Context of use: "where am I,
can I trade right now, and how did the last trade go." Quick glances, not long
sessions.

## Product Purpose

LENS is a **trading cockpit that now closes the loop**. It reads live Kraken
equity and open positions, tracks prop-eval progress against target/floor
walls, journals closed trades, scores strategies from a real backtest — and,
since 2026-08-20, **places the order too**.

That last step is the point of the whole thing, not a feature bolted on. The
levels were always computed here and then retyped into the exchange's form,
and that double entry is measurable: over the 30 days to 2026-08-20, 147
signals fired and 4 were acted on. A decision made twice is a decision usually
not made. So LENS now sends the entry with its take profit and stop loss
attached, at a size it worked out itself.

Success is a clean, trustworthy instrument panel the owner is proud to show
people as "my system" — not to sell, but as a thing made with craft.

## Brand Personality

Precise, optical, disciplined. The name is LENS — optics, a scope, a measuring
instrument. The feel is a cockpit/HUD: dark, calm under fire, every number
where you expect it. Three words: **instrument, legible, composed.**

## Anti-references

- Hype crypto-bro dashboards: neon gradient slop, "to the moon" green,
  gamified confetti, gauge-needle theatrics.
- Generic SaaS-cream admin templates (light warm-neutral bg, identical card
  grids, tracked-uppercase eyebrow on every section).
- A Bloomberg-terminal wall of undifferentiated numbers with no hierarchy.

## Design Principles

- **Instrument, not toy.** Every element earns its place by informing a decision.
- **Legible at a glance.** Hierarchy first; the one number that matters is the
  loudest thing on the screen.
- **One source of truth.** All styling flows from the `LENS_CSS` tokens in
  `app/theme.py`; no hard-coded hex in pages.
- **Execution is deliberate, never ambient.** LENS places orders, so the UI owes
  the opposite of reassurance: every send is two clicks, arms with the exact
  order written on the button, and disarms itself after six seconds. Nothing
  fires from a page load, a scan, or a single click. The environment badge
  (DEMO / LIVE) is read from the server on every gate check, never assumed by
  the page — if it says LIVE it is live.
- **The rules bind at the moment of the trade.** Execution runs through
  `discipline.py`, so the bleed hour and the revenge cooldown block an *order*,
  not just a signal. A rule that only annotates history is decoration.
- **Mobile-first, desktop-equal.** Phone is already strong; desktop must feel
  as deliberate, not a stretched phone.

## Accessibility & Inclusion

Dark theme throughout; body text must hold ≥4.5:1 against its surface (the dim
grays are the risk). Color is never the only signal (long/short also carry
arrows and labels). Every animation needs a `prefers-reduced-motion` fallback.

Destructive and irreversible actions carry their consequence in words, not just
in color: the confirm state spells out side, size and whether a bracket is
attached, because a red button alone is not an explanation.

## Change log

- **2026-08-20** — Execution added. "Watch-only honesty" retired as a design
  principle; replaced by *Execution is deliberate, never ambient* and *The rules
  bind at the moment of the trade*. The claim that LENS "never executes" was
  true until this date and is preserved here as history, not as current state.
