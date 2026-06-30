# Product

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

LENS is a **watch-only trading cockpit**. It reads live Kraken equity and open
positions, tracks prop-eval progress against target/floor walls, journals
closed trades, and scores strategies from a real backtest. The owner places
every trade manually; LENS observes and measures — it never executes. Success
is a clean, trustworthy instrument panel the owner is proud to show people as
"my system" — not to sell, but as a thing made with craft.

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
- **Watch-only honesty.** The UI never implies LENS trades for you.
- **Mobile-first, desktop-equal.** Phone is already strong; desktop must feel
  as deliberate, not a stretched phone.

## Accessibility & Inclusion

Dark theme throughout; body text must hold ≥4.5:1 against its surface (the dim
grays are the risk). Color is never the only signal (long/short also carry
arrows and labels). Every animation needs a `prefers-reduced-motion` fallback.
