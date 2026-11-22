"""Fare consistency check: does the fare on each ticket fit the distance between its matched stops?

Delhi bus fares go by distance slab. The fares in the data are exactly the published slabs less a 10% e-ticket
discount: non-AC 4.5 / 9 / 13.5 (Rs 5 / 10 / 15), AC 9 / 13.5 / 18 / 22.5 (Rs 10 / 15 / 20 / 25).
Slab edges used (km): non-AC 4, 10; AC 4, 8, 12.

The fare was computed by the ticketing system from the stops the rider declared, so this does NOT tell us where
people really got off. It tests OUR side: the stop-name matching and the stop order on the canonical route.
A ticket whose fare slab is far from the slab its matched stops imply was probably matched to the wrong stop.

Distance between stops is the sum of straight-line hops along the route, times a road factor. The factor is
fitted (the value in ROAD_FACTORS that makes most tickets agree), not assumed.

Writes data/out/fare_check.json and data/out/fare_check_by_route.csv.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import config

DISCOUNT = 0.9
SLABS = {False: ([4.0, 10.0], [5, 10, 15]), True: ([4.0, 8.0, 12.0], [10, 15, 20, 25])}
ROAD_FACTORS = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]


def slab_of_km(km: np.ndarray, ac: np.ndarray) -> np.ndarray:
    out = np.empty(len(km), dtype=int)
    for flag, (edges, _) in SLABS.items():
        m = ac == flag
        out[m] = np.searchsorted(edges, km[m], side="left")
    return out


def slab_of_fare(fare: np.ndarray, ac: np.ndarray) -> np.ndarray:
    """Slab index of a per-passenger fare, or -1 when the fare is not a slab fare."""
    out = np.full(len(fare), -1, dtype=int)
    for flag, (_, prices) in SLABS.items():
        m = ac == flag
        for k, pr in enumerate(prices):
            hit = m & (np.abs(fare - pr * DISCOUNT) < 0.06)
            out[hit] = k
    return out


def run_check(interim_dir: Path, gtfs_dir: Path, out_dir: Path) -> dict:
    interim_dir, out_dir = Path(interim_dir), Path(out_dir)
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE cum AS
        WITH s AS (SELECT stop_id, CAST(stop_lat AS DOUBLE) AS lat, CAST(stop_lon AS DOUBLE) AS lon
                   FROM read_csv('{Path(gtfs_dir) / 'stops.txt'}', header=true, all_varchar=true)),
        c AS (SELECT route, pos, lat, lon FROM read_parquet('{interim_dir / 'canonical_routes.parquet'}') JOIN s USING (stop_id)),
        h AS (SELECT route, pos, coalesce(2 * 6371 * asin(sqrt(pow(sin(radians(lat - lag(lat) OVER w) / 2), 2) +
                   cos(radians(lag(lat) OVER w)) * cos(radians(lat)) * pow(sin(radians(lon - lag(lon) OVER w) / 2), 2))), 0) AS km
              FROM c WINDOW w AS (PARTITION BY route ORDER BY pos))
        SELECT route, pos, sum(km) OVER (PARTITION BY route ORDER BY pos) AS cum_km FROM h""")
    df = con.execute(f"""
        SELECT p.route, p.pc, p.amount / p.pc AS fare, p.is_ac, p.start_method, p.end_method,
               b.cum_km - a.cum_km AS km
        FROM read_parquet('{interim_dir / 'ticket_pairs.parquet'}') p
        JOIN cum a ON a.route = p.route AND a.pos = p.i
        JOIN cum b ON b.route = p.route AND b.pos = p.j
        WHERE p.amount > 0 AND p.pc > 0 AND p.is_ac IS NOT NULL""").df()
    ac = df["is_ac"].to_numpy(bool)
    fs = slab_of_fare(df["fare"].to_numpy(float), ac)
    valid = fs >= 0
    km = df["km"].to_numpy(float)
    fit = {}
    for f in ROAD_FACTORS:
        ks = slab_of_km(km * f, ac)
        fit[f] = float((ks[valid] == fs[valid]).mean())
    best = max(fit, key=fit.get)
    ks = slab_of_km(km * best, ac)
    df["fare_slab"], df["stop_slab"] = fs, ks
    d = df[valid].copy()
    d["agree"] = d["fare_slab"] == d["stop_slab"]
    d["within_one"] = (d["fare_slab"] - d["stop_slab"]).abs() <= 1
    d["fuzzy"] = d["start_method"].astype(str).str.contains("fuzzy") | d["end_method"].astype(str).str.contains("fuzzy")
    by_method = d.groupby("fuzzy")["agree"].agg(["mean", "size"]).round(4)
    # fare says a longer trip than the matched stops (rider declared a farther stop than we matched, or wrong match)
    longer = float((d["fare_slab"] > d["stop_slab"]).mean())
    shorter = float((d["fare_slab"] < d["stop_slab"]).mean())
    by_route = (d.groupby("route").agg(tickets=("agree", "size"), agree=("agree", "mean"))
                .query("tickets >= 200").sort_values("agree").round(4))
    by_route.to_csv(out_dir / "fare_check_by_route.csv")
    rep = {"tickets_checked": int(len(d)), "tickets_with_non_slab_fare": int((~valid).sum()),
           "road_factor_fit": {str(k): round(v, 4) for k, v in fit.items()}, "road_factor_used": best,
           "slab_agreement": round(float(d["agree"].mean()), 4),
           "within_one_slab": round(float(d["within_one"].mean()), 4),
           "fare_implies_longer_trip": round(longer, 4), "fare_implies_shorter_trip": round(shorter, 4),
           "agreement_exact_name_matches": float(by_method.loc[False, "mean"]) if False in by_method.index else None,
           "agreement_with_a_fuzzy_match": float(by_method.loc[True, "mean"]) if True in by_method.index else None,
           "routes_scored": int(len(by_route)),
           "routes_below_60pct_agreement": int((by_route["agree"] < 0.6).sum())}
    (out_dir / "fare_check.json").write_text(json.dumps(rep, indent=2))
    for k, v in rep.items():
        print(f"{k:>30}: {v}")
    return rep


def run() -> None:
    run_check(config.INTERIM_DIR, config.GTFS_DIR, config.OUT_DIR)


if __name__ == "__main__":
    run()
