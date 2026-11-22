"""I-F3 (part 2): per-trip load per cell, scale-up for the ticket sample, and bootstrap intervals.

Cell = (route, seg, hour, day_type). Route names are directional in this dataset (102AUP / 102ADOWN).
Per day:   load = passengers on the stretch in that hour / scheduled trips leaving the stretch in that hour
           (days with no tickets count as zero, so quiet cells are not overstated).
Interval:  bootstrap over the days of that day_type (5th-95th percentile of the mean).
Scale-up:  raw / sample_rate * pass_holder_uplift. Both are ASSUMED RANGES from config, applied
           equally to every route. Route-level coverage differences are NOT modelled (see docs/METHOD.md).

Writes data/out/crowding_cells.parquet and data/interim/expand_report.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import config
from .routeinfo import load_route_info

CHUNK = 20_000
# Heuristic: even the LOW end of the interval is more people than a full bus carries, so the GTFS
# schedule probably undercounts the buses actually running (e.g. 2 scheduled trips/hour on a busy corridor).
SUSPECT_LOAD_LO = 100.0


def _bootstrap_means(daily: np.ndarray, B: int, rng: np.random.Generator) -> np.ndarray:
    """daily: cells x days. Returns cells x B bootstrap means over days (shared resamples per chunk)."""
    n_days = daily.shape[1]
    idx = rng.integers(0, n_days, size=(B, n_days))
    W = np.zeros((n_days, B), dtype=np.float32)
    for b in range(B):
        W[:, b] = np.bincount(idx[b], minlength=n_days) / n_days
    return daily @ W


def build_trip_counts(con: duckdb.DuckDBPyConnection, interim_dir: Path, observed: bool) -> None:
    """Creates sched_adj(route, pos, hour, day_type, trips, obs_veh, sched).

    trips = max(scheduled trips leaving the stretch in that hour, observed buses). Observed buses = the 75th
    percentile over days of distinct vehicle_numbers seen on tickets for that route and hour (about half of
    tickets carry a vehicle number, so this is a LOWER bound on running buses). It fixes cells where the GTFS
    schedule has far fewer trips than the buses that clearly ran, and fills hours the schedule lacks."""
    rp = lambda n: f"read_parquet('{Path(interim_dir) / (n + '.parquet')}')"
    con.execute(f"""
        CREATE OR REPLACE TABLE obs AS
        SELECT route, hour, day_type, CAST(ceil(quantile_cont(v, 0.75)) AS INTEGER) AS veh FROM (
          SELECT upper(regexp_replace(route, '[\\s\\-_]+', '', 'g')) AS route, date, hour, day_type,
                 count(DISTINCT vehicle_number) AS v FROM {rp('tickets')}
          WHERE vehicle_number IS NOT NULL GROUP BY ALL) GROUP BY route, hour, day_type""")
    if not observed:
        con.execute("DELETE FROM obs")
    con.execute(f"""
        CREATE OR REPLACE TABLE sched_adj AS
        SELECT coalesce(s.route, g.route) AS route, coalesce(s.pos, g.pos) AS pos, coalesce(s.hour, g.hour) AS hour,
               coalesce(s.day_type, g.day_type) AS day_type,
               greatest(coalesce(s.trips, 0), coalesce(g.veh, 0)) AS trips,
               coalesce(g.veh, 0) AS obs_veh, coalesce(s.trips, 0) AS sched
        FROM (SELECT t.route, t.pos, t.hour, d.day_type, t.trips FROM {rp('sched_trips')} t
              CROSS JOIN (SELECT DISTINCT day_type FROM {rp('tickets')}) d) s
        FULL OUTER JOIN (SELECT c.route, c.pos, o.hour, o.day_type, o.veh FROM {rp('canonical_routes')} c
                         JOIN obs o ON o.route = c.route) g
          ON s.route = g.route AND s.pos = g.pos AND s.hour = g.hour AND s.day_type = g.day_type""")


def prepare_daily(con: duckdb.DuckDBPyConnection, interim_dir: Path, observed: bool | None = None) -> tuple[list, int, int]:
    """Creates table daily(route, seg, hour, day_type, date, passengers, tickets, trips_per_day).
    Returns (list of (day_type, date) for every ticket day, row count, rows without a schedule)."""
    observed = config.OBSERVED_TRIPS if observed is None else observed
    build_trip_counts(con, interim_dir, observed)
    rp = lambda n: f"read_parquet('{Path(interim_dir) / (n + '.parquet')}')"
    days = con.execute(f"SELECT day_type, date FROM (SELECT DISTINCT day_type, date FROM {rp('tickets')}) "
                       "ORDER BY day_type, date").fetchall()
    con.execute(f"""
        CREATE OR REPLACE TABLE daily AS
        SELECT d.route, d.seg, d.hour, d.day_type, d.date, d.passengers, d.tickets,
               s.trips AS trips_per_day
        FROM {rp('stretch_daily')} d
        LEFT JOIN sched_adj s ON s.route = d.route AND s.pos = d.seg AND s.hour = d.hour AND s.day_type = d.day_type""")
    n_rows, n_no_sched = con.execute("SELECT count(*), sum((trips_per_day IS NULL)::INT) FROM daily").fetchone()
    return days, int(n_rows), int(n_no_sched or 0)


BAND_SQL = ("CASE WHEN {h} BETWEEN 7 AND 10 THEN 1 WHEN {h} BETWEEN 11 AND 16 THEN 2 "
            "WHEN {h} BETWEEN 17 AND 20 THEN 3 WHEN {h} BETWEEN 5 AND 6 THEN 0 ELSE 4 END")
BAND_NAMES = {0: "early 5-6", 1: "am peak 7-10", 2: "midday 11-16", 3: "pm peak 17-20", 4: "late 21-4"}


def prepare_daily_band(con: duckdb.DuckDBPyConnection, interim_dir: Path) -> None:
    """Pooled grain: table daily_b with `hour` holding the band id and trips_per_day summed over the band's hours."""
    rp = lambda n: f"read_parquet('{Path(interim_dir) / (n + '.parquet')}')"
    con.execute(f"""
        CREATE OR REPLACE TABLE band_trips AS
        SELECT route, pos AS seg, day_type, {BAND_SQL.format(h='hour')} AS b, sum(trips) AS trips
        FROM sched_adj GROUP BY ALL""")
    con.execute(f"""
        CREATE OR REPLACE TABLE daily_b AS
        SELECT d.route, d.seg, {BAND_SQL.format(h='d.hour')} AS hour, d.day_type, d.date,
               sum(d.passengers) AS passengers, sum(d.tickets) AS tickets, any_value(bt.trips) AS trips_per_day
        FROM {rp('stretch_daily')} d
        LEFT JOIN band_trips bt ON bt.route = d.route AND bt.seg = d.seg AND bt.day_type = d.day_type AND bt.b = {BAND_SQL.format(h='d.hour')}
        GROUP BY d.route, d.seg, {BAND_SQL.format(h='d.hour')}, d.day_type, d.date""")


def day_matrices(con: duckdb.DuckDBPyConnection, day_type: str, dates: list[str], min_trips: int = 1,
                 table: str = "daily"):
    """Per-day load matrices for one day_type. Returns (meta, M, T):
    meta rows = cells (route, seg, hour, trips, n_tickets, n_pass, n_days_seen); M = cells x days of
    passengers per scheduled trip (zero when no tickets that day); T = cells x days of ticket counts."""
    D = len(dates)
    date_ix = {x: i for i, x in enumerate(dates)}
    df = con.execute("""
        SELECT route, seg, hour, strftime(date, '%Y-%m-%d') AS d, passengers / trips_per_day AS load,
               tickets, passengers, trips_per_day
        FROM {table} WHERE day_type = ? AND trips_per_day >= ?""".replace("{table}", table), [day_type, min_trips]).df()
    key = (df["route"] + "|" + df["seg"].astype(str) + "|" + df["hour"].astype(str)).to_numpy()
    keys, inv = np.unique(key, return_inverse=True)
    di = df["d"].map(date_ix).to_numpy()
    M = np.zeros((len(keys), D), dtype=np.float32)
    T = np.zeros((len(keys), D), dtype=np.float32)
    M[inv, di] = df["load"].to_numpy(dtype=np.float32)
    T[inv, di] = df["tickets"].to_numpy(dtype=np.float32)
    meta = df.groupby(inv).agg(route=("route", "first"), seg=("seg", "first"), hour=("hour", "first"),
                               n_tickets=("tickets", "sum"), n_pass=("passengers", "sum"),
                               trips=("trips_per_day", "first"), n_days_seen=("d", "nunique")).reset_index(drop=True)
    return meta, M, T


def build_cells(interim_dir: Path, out_dir: Path, sample_rate=None, uplift=None,
                B: int | None = None, min_trips: int = 1, seed: int = 7, grain: str = "hour",
                observed: bool | None = None) -> dict:
    interim_dir, out_dir = Path(interim_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_rate = sample_rate or config.SAMPLE_RATE
    uplift = uplift or config.PASS_HOLDER_UPLIFT
    B = B or config.BOOTSTRAP_SAMPLES
    rng = np.random.default_rng(seed)
    con = duckdb.connect()
    rp = lambda n: f"read_parquet('{interim_dir / (n + '.parquet')}')"

    days, n_rows, n_no_sched = prepare_daily(con, interim_dir, observed)
    table = "daily"
    if grain == "band":
        prepare_daily_band(con, interim_dir)
        table = "daily_b"

    pieces = []
    for dt in sorted({d for d, _ in days}):
        dates = [str(x) for d, x in days if d == dt]
        D = len(dates)
        first, M, _ = day_matrices(con, dt, dates, min_trips, table)
        n_cells = len(first)
        lo = np.empty(n_cells, dtype=np.float32)
        hi = np.empty(n_cells, dtype=np.float32)
        for a in range(0, n_cells, CHUNK):
            bm = _bootstrap_means(M[a:a + CHUNK], B, rng)
            lo[a:a + CHUNK] = np.percentile(bm, 5, axis=1)
            hi[a:a + CHUNK] = np.percentile(bm, 95, axis=1)
        raw = M.mean(axis=1)
        u_mid, r_mid = sum(uplift) / 2, sum(sample_rate) / 2
        pieces.append(first.assign(
            day_type=dt, n_days=D, raw_load=raw, raw_lo=lo, raw_hi=hi,
            load=raw / r_mid * u_mid,
            load_lo=lo / sample_rate[1] * uplift[0],     # fewest assumed missing riders, bootstrap low
            load_hi=hi / sample_rate[0] * uplift[1],     # most assumed missing riders, bootstrap high
        ))
    cells = pd.concat(pieces, ignore_index=True)
    ri = load_route_info(interim_dir)
    if ri is not None:   # per-route coverage correction and inferred bus size (routeinfo.py)
        cells = cells.merge(ri[["route", "cov_factor", "bus_class", "seats", "standing"]], on="route", how="left")
        cells["cov_factor"] = cells["cov_factor"].fillna(1.0)
        cells["load"] *= cells["cov_factor"]
        cells["load_hi"] *= cells["cov_factor"]   # low end keeps factor 1: dropped tickets rode nowhere busy
    cells["suspect_schedule"] = cells["load_lo"] > SUSPECT_LOAD_LO
    cells["seg"] = cells["seg"].astype("int32")
    cells["hour"] = cells["hour"].astype("int32")
    if grain == "band":
        cells["band"] = cells["hour"].map(BAND_NAMES)

    stops = con.execute(f"""
        SELECT a.route, a.pos AS seg, a.stop_id AS from_stop_id, a.stop_name AS from_stop,
               b.stop_id AS to_stop_id, b.stop_name AS to_stop
        FROM {rp('canonical_routes')} a JOIN {rp('canonical_routes')} b
          ON a.route = b.route AND b.pos = a.pos + 1""").df()
    cells = cells.merge(stops, on=["route", "seg"], how="left")
    con.register("cells_df", cells)
    fname = "crowding_cells.parquet" if grain == "hour" else "crowding_band_cells.parquet"
    con.execute(f"COPY cells_df TO '{out_dir / fname}' (FORMAT PARQUET)")

    ge = cells["n_tickets"] >= config.MIN_TICKETS_PER_CELL
    report = {
        "stretch_day_rows": n_rows, "rows_without_schedule": n_no_sched,
        "share_without_schedule": round(n_no_sched / max(n_rows, 1), 4),
        "cells": int(len(cells)), "routes": int(cells["route"].nunique()),
        "bootstrap_samples": B, "sample_rate": list(sample_rate), "pass_holder_uplift": list(uplift),
        "coverage_correction": ri is not None,
        "median_load_expanded": float(cells["load"].median()),
        "p95_load_expanded": float(cells["load"].quantile(0.95)),
        "max_load_expanded": float(cells["load"].max()),
        "suspect_schedule_cells": int(cells["suspect_schedule"].sum()),
        "cells_with_ge30_tickets": int(ge.sum()),
        "share_cells_ge30_tickets": round(float(ge.mean()), 4),
    }
    (interim_dir / ("expand_report.json" if grain == "hour" else "expand_band_report.json")).write_text(json.dumps(report, indent=2))
    for k, v in report.items():
        print(f"{k:>28}: {v}")
    return report


def run() -> None:
    build_cells(config.INTERIM_DIR, config.OUT_DIR)
    build_cells(config.INTERIM_DIR, config.OUT_DIR, grain="band")


if __name__ == "__main__":
    run()
