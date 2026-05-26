# LENS

Build the dataset that makes month-6 predictive scoring possible. Every trade originates from a Pine Script strategy that emits a locked-schema JSON signal; every signal — taken or skipped — is stored alongside the executed-trade outcome. After ~150–300 trades, the (features → outcome) dataset becomes train-ready. Until then, per-strategy expectancy on real fills is the edge-discovery feedback loop. Local SQLite, FastAPI, Kraken + Bybit sync, single-page dashboard on a miniPC. No cloud.

See `LENS_PLAN.md` for the full 8-week build plan.

## Quick start

```bash
pip install -r requirements.txt
cp prism.env .env   # or write your own
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then:

```bash
curl localhost:8000/health
curl localhost:8000/api/trades
```
