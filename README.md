# Bharosa Bus

Crowding you can audit. A Delhi bus planner that shows seats / standing / crowded for each route option, with a confidence range, a "not enough data" state, and an evidence card behind every label. Labels in English or Hindi.

Built for Transport Stack Hackathon 2026, Problem 2 (crowdedness-aware journey planner).
Docs: [technical note](docs/METHOD.md) · [proposal](docs/PROPOSAL.pdf) · [demo script](docs/DEMO.md) · [MVP checklist](TASKS.md)

## Quick start
```bash
make setup                      # venv + dependencies
cp .env.example .env            # set TICKETS_CSV if your path differs
```
Put the data in `data/raw/`:
- tickets: `October-Delhi.csv` or `.zip` (https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/October-Delhi.csv.zip), e.g. `data/raw/tickets/`
- static GTFS (needs a free Transport Stack account): https://delhi.transportstack.in/data-services/datadetails/1 , unzipped into `data/raw/gtfs/`

```bash
make crowding-all               # clean, match stops, loads, route facts, fare check, levels, backtest, sanity, export (~110 s)
make serve                      # http://localhost:8000  live planner: any stop to any stop, plus route map and operators
make web                        # same pages, static, demo trips only
make test                       # 30 tests
make site                       # dist/: upload to any static host
make query ROUTE=717AUP         # stretch-by-stretch table in the terminal
```

## What makes it different
Most Problem 2 entries will turn tickets into a load, colour it, and draw a planner. We also do these:
1. **Labels tested against a lazy baseline.** Most stretches really are "seats", so raw accuracy flatters any model. We report Cohen's kappa against an "always seats" predictor and a route × hour average. Weekday day-part labels reach kappa 0.71 between halves of the month, and 83% of busy cells are caught. We also publish where we lose (single weekend days).
2. **The `amount` column used as a check.** Fares are Delhi's distance slabs less 10%. 83% of tickets' fares match the distance between our matched stops (99.9% within one slab), which validates the stop matching independently.
3. **Bus size from the data, not one guess.** Short `D…` routes (median 10 km) are 9 m DEVI buses, with fewer seats. The same 30 people read as "standing" there and "seats" on a 12 m bus.
4. **Every ticket counted.** Route-name normalisation recovered 236k tickets (9% of all) that a plain join drops. A per-route coverage factor corrects for tickets that can't be placed on a stretch.
5. **Week-to-week stability**, as the brief asks: weekday day-part Spearman 0.87-0.89 between each week and the rest.
6. **"+3 min for a seat."** Each option says what it costs against the fastest, in one line. Leaving later, or taking the other direction of travel, are within-route comparisons that the scale-up assumptions can't distort.
7. **An answer for operators, not just a heat map.** "If you add one bus here, standing time falls by X passenger-minutes a day", ranked by the cautious estimate.
8. **We say when we don't know.** Thin cells abstain, and every label opens to its tickets, days, range and bus size.

## What you get
- `data/out/crowding_levels.parquet` (hour) and `crowding_band_levels.parquet` (day parts): level, load and range, tickets, days, bus class per route stretch.
- `data/out/backtest*.json|csv`, `fare_check.json`, `sanity/`, `operator_overload.csv`, `extra_bus_benefit.csv`.
- `web/`: planner (option list beside a map that colours each trip stretch by stretch), route map, operators page. `make serve` adds live planning for any trip. The map uses OpenStreetMap tiles and the Leaflet library from a CDN, so it needs internet; without it the list still works.

## Status and limits
All stages run on the real October tickets and GTFS. GPS cross-check not built. Absolute loads are not validated against an independent count: bus size per route is inferred, ticket share and pass-holder uplift are assumed ranges, and planner times are scheduled. See [docs/METHOD.md](docs/METHOD.md) §3-6.

## Layout
`src/bharosa/` pipeline stages (`python -m bharosa.<name>`) · `planner/` connection-scan planner · `web/` UI · `data/` raw (ignored), interim, out · `tests/`
