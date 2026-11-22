"""I-F4: map expanded load to seats / standing / crowded, and abstain when evidence is thin.

CAPACITY comes from press reports of Delhi's fleet (not opened or verified by me, and the bus type of each route
is unknown, so one figure is applied everywhere):
  12m: Switch EiV12 low-floor, 39 seated + 24 standing = 63 (Electrive; one outlet gives the standing figure)
  9m : DEVI mohalla bus, 23 seated + 13 standing = 36 (one press report)
  assumed_high: 40 + 40, a generous bound kept from the first version.
"standing" here is the rated standing capacity, so "crowded" means over the rated capacity. The sensitivity table
shows how many cells change level between scenarios. Override with CAPACITY_SEATS / CAPACITY_STANDING in .env.

Level rule: load <= seats -> "seats"; <= seats + standing -> "standing"; else "crowded".
Abstain ("insufficient_evidence") when a cell has fewer than MIN_TICKETS_PER_CELL tickets in the month
or its schedule looks wrong (suspect_schedule).

Writes data/out/crowding_levels.parquet, data/out/levels_sensitivity.csv, data/interim/levels_report.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import config

SCENARIOS = {"9m": (23, 13), "12m": (39, 24), "assumed_high": (40, 40)}  # (seats, rated standing); see docstring
DEFAULT_SCENARIO = "12m"
LEVELS = ("seats", "standing", "crowded")
ABSTAIN = "insufficient_evidence"


def scenarios() -> dict[str, tuple[int, int]]:
    sc = dict(SCENARIOS)
    if config.CAPACITY_SEATS and config.CAPACITY_STANDING:
        sc["custom"] = (int(config.CAPACITY_SEATS), int(config.CAPACITY_STANDING))
    return sc


def level_of(load, seats: int, standing: int) -> np.ndarray:
    load = np.asarray(load, dtype=float)
    return np.select([load <= seats, load <= seats + standing], [LEVELS[0], LEVELS[1]], LEVELS[2])


def assign_levels(cells: pd.DataFrame, scenario: str | None = None, min_tickets: int | None = None) -> pd.DataFrame:
    """scenario None -> per-route capacity from routeinfo.py when the cells carry it (column `seats`), else the
    configured / default single capacity. A named scenario applies one capacity to every route."""
    sc = scenarios()
    min_tickets = config.MIN_TICKETS_PER_CELL if min_tickets is None else min_tickets
    out = cells.copy()
    if scenario is None and "custom" not in sc and "seats" in out and out["seats"].notna().all():
        name, seats, standing = "per_route_inferred", out["seats"].to_numpy(float), out["standing"].to_numpy(float)
    else:
        name = scenario or ("custom" if "custom" in sc else DEFAULT_SCENARIO)
        seats, standing = sc[name]
    out["level_point"] = level_of(out["load"], seats, standing)
    out["level_if_low"] = level_of(out["load_lo"], seats, standing)
    out["level_if_high"] = level_of(out["load_hi"], seats, standing)
    out["abstain_reason"] = np.select(
        [out["n_tickets"] < min_tickets, out["suspect_schedule"]], ["few_tickets", "schedule_suspect"], "")
    out["level"] = np.where(out["abstain_reason"] != "", ABSTAIN, out["level_point"])
    out["confident"] = (out["abstain_reason"] == "") & (out["level_if_low"] == out["level_if_high"])
    out["scenario"] = name
    return out


def sensitivity(cells: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = assign_levels(cells)
    keep = base["abstain_reason"] == ""
    scen = dict(scenarios())
    if base["scenario"].iloc[0] == "per_route_inferred":
        scen["per_route_inferred"] = (cells.loc[keep, "seats"].to_numpy(float), cells.loc[keep, "standing"].to_numpy(float))
    for name, (seats, standing) in scen.items():
        lv = pd.Series(level_of(cells.loc[keep, "load"], seats, standing), index=cells.index[keep])
        w = cells.loc[keep, "n_pass"]
        row = {"scenario": name, "seats_cap": seats if np.isscalar(seats) else "per route",
               "standing_cap": standing if np.isscalar(standing) else "per route", "cells": int(keep.sum())}
        for L in LEVELS:
            row[f"share_{L}"] = round(float((lv == L).mean()), 4)
            row[f"pax_share_{L}"] = round(float(w[lv == L].sum() / w.sum()), 4)
        row["share_same_level_as_default"] = round(float((lv == base.loc[keep, "level_point"]).mean()), 4)
        rows.append(row)
    return pd.DataFrame(rows)


def run() -> None:
    for grain, src, dst, rep in (("hour", "crowding_cells", "crowding_levels", "levels_report.json"),
                                 ("band", "crowding_band_cells", "crowding_band_levels", "levels_band_report.json")):
        _run_one(grain, src, dst, rep)


def _run_one(grain: str, src: str, dst: str, rep_name: str) -> None:
    print(f"== {grain} grain")
    con = duckdb.connect()
    cells = con.execute("SELECT * FROM read_parquet(?)", [str(config.OUT_DIR / (src + ".parquet"))]).df()
    lv = assign_levels(cells)
    sens = sensitivity(cells)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    con.register("lv", lv)
    con.execute(f"COPY lv TO '{config.OUT_DIR / (dst + '.parquet')}' (FORMAT PARQUET)")
    sens.to_csv(config.OUT_DIR / ("levels_sensitivity.csv" if grain == "hour" else "levels_band_sensitivity.csv"), index=False)
    ab = lv["abstain_reason"] != ""
    report = {
        "scenario": lv["scenario"].iloc[0], "cells": int(len(lv)),
        "abstained_cells": int(ab.sum()), "abstained_share": round(float(ab.mean()), 4),
        "abstain_reasons": lv.loc[ab, "abstain_reason"].value_counts().to_dict(),
        "passenger_share_covered": round(float(lv.loc[~ab, "n_pass"].sum() / lv["n_pass"].sum()), 4),
        "confident_share_of_shown": round(float(lv.loc[~ab, "confident"].mean()), 4),
        "level_counts_shown": lv.loc[~ab, "level"].value_counts().to_dict(),
    }
    (config.INTERIM_DIR / rep_name).write_text(json.dumps(report, indent=2))
    for k, v in report.items():
        print(f"{k:>26}: {v}")
    print(sens.to_string(index=False))
    if grain == "band":
        _route_band(con, lv)


MIN_ROUTE_CELLS = 8


def _route_band(con, lv: pd.DataFrame) -> None:
    """Route-wide typical crowding per (route, day part, day type): fallback when a ride has too few evidenced stretches."""
    sc = scenarios()
    seats, standing = sc["custom" if "custom" in sc else DEFAULT_SCENARIO]
    shown = lv[lv["abstain_reason"] == ""]
    g = shown.groupby(["route", "hour", "day_type"]).agg(
        n_cells=("load", "size"), tickets=("n_tickets", "sum"), median_load=("load", "median"),
        p75_load=("load", lambda x: float(np.percentile(x, 75)))).reset_index()
    g = g[g["n_cells"] >= MIN_ROUTE_CELLS].copy()
    if "seats" in shown and lv["scenario"].iloc[0] == "per_route_inferred":
        cap = shown.groupby("route")[["seats", "standing"]].first()
        g = g.merge(cap, left_on="route", right_index=True, how="left")
        g["level"] = level_of(g["p75_load"], g["seats"].to_numpy(float), g["standing"].to_numpy(float))
    else:
        g["level"] = level_of(g["p75_load"], seats, standing)
    con.register("rb", g)
    con.execute(f"COPY rb TO '{config.OUT_DIR / 'crowding_route_band.parquet'}' (FORMAT PARQUET)")
    print(f"route-band fallback rows: {len(g)}")


if __name__ == "__main__":
    run()
