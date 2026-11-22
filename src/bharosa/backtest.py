"""I-F5: leave-one-day-out backtest of the crowding table.

For every day, hide it, predict each cell's per-trip load from the OTHER days of the same day_type
(mean, zeros included), and compare with what happened. Works in raw units (passengers per scheduled
trip), so errors do not depend on the sample-rate and uplift assumptions. Only cells with at least
MIN_TICKETS_PER_CELL tickets in the training days are scored, the same rule the UI uses to show a level.

Reported: WAPE (sum|pred - actual| / sum actual), bias, two baselines (hour-of-day mean across all cells, and the
stronger route x hour mean that ignores which stretch), level agreement next to the "always seats" baseline,
Cohen's kappa (agreement beyond chance), recall / precision for busy cells (standing or crowded), results by
route volume and hour band, and split-half stability of cell means.

A single held-out day carries only a few tickets per cell, so day-level labels are mostly noise. The split-half
check is the fairer test of a "typical day" label: label each cell from the first half of the month and from the
second half, and compare.
Headline days: the first weekday and first weekend day are in backtest_by_day.csv with all the others.

Writes data/out/backtest.json, backtest_by_day.csv, backtest_groups.csv.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import config
from .expand import day_matrices, prepare_daily
from .levels import DEFAULT_SCENARIO, level_of, scenarios
from .routeinfo import load_route_info


def hour_band(h: np.ndarray) -> np.ndarray:
    return np.select([(h >= 7) & (h <= 10), (h >= 17) & (h <= 20)], ["am_peak_7-10", "pm_peak_17-20"], "other")


def _rank(x: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(x)).astype(float)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    return float(np.corrcoef(_rank(a), _rank(b))[0, 1])


ORDER = {"seats": 0, "standing": 1, "crowded": 2}


def confusion(actual: np.ndarray, pred: np.ndarray) -> np.ndarray:
    a = np.vectorize(ORDER.get)(actual) if len(actual) else np.array([], int)
    p = np.vectorize(ORDER.get)(pred) if len(pred) else np.array([], int)
    cm = np.zeros((3, 3), dtype=float)
    np.add.at(cm, (a, p), 1)
    return cm


def level_scores(cm: np.ndarray) -> dict:
    """Agreement, the always-seats baseline, Cohen's kappa and busy (standing or crowded) recall / precision."""
    n = cm.sum()
    if n == 0:
        return {}
    po = np.trace(cm) / n
    pe = float((cm.sum(0) * cm.sum(1)).sum()) / n ** 2
    busy_tp = cm[1:, 1:].sum()
    return {"cells": int(n), "level_exact": round(float(po), 4),
            "always_seats_exact": round(float(cm[0].sum() / n), 4),
            "kappa": round(float((po - pe) / (1 - pe)) if pe < 1 else 0.0, 4),
            "actual_busy_share": round(float(cm[1:].sum() / n), 4),
            "busy_recall": round(float(busy_tp / cm[1:].sum()), 4) if cm[1:].sum() else None,
            "busy_precision": round(float(busy_tp / cm[:, 1:].sum()), 4) if cm[:, 1:].sum() else None,
            "crowded_recall": round(float(cm[2, 2] / cm[2].sum()), 4) if cm[2].sum() else None}


def run_backtest(interim_dir: Path, out_dir: Path, min_tickets: int | None = None, grain: str = "hour",
                 observed: bool | None = None) -> dict:
    interim_dir, out_dir = Path(interim_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    min_tickets = config.MIN_TICKETS_PER_CELL if min_tickets is None else min_tickets
    seats, standing = scenarios()["custom" if "custom" in scenarios() else DEFAULT_SCENARIO]
    scale = (1 / (sum(config.SAMPLE_RATE) / 2)) * (sum(config.PASS_HOLDER_UPLIFT) / 2)

    con = duckdb.connect()
    days, _, _ = prepare_daily(con, interim_dir, observed)
    table = "daily"
    if grain == "band":
        from .expand import prepare_daily_band
        prepare_daily_band(con, interim_dir)
        table = "daily_b"
    sfx = "" if grain == "hour" else "_band"
    by_day, group_acc, stability, split_half, cm_lodo, week_to_week = [], {}, {}, {}, {}, {}
    ri = load_route_info(interim_dir)
    for dt in sorted({d for d, _ in days}):
        dates = [str(x) for d, x in days if d == dt]
        D = len(dates)
        if D < 3:
            continue
        meta, M, T = day_matrices(con, dt, dates, 1, table)
        S, TT = M.sum(1), T.sum(1)
        if ri is not None:   # per-cell scale (coverage correction) and capacity, as in the published table
            m2 = meta[["route"]].merge(ri[["route", "cov_factor", "seats", "standing"]], on="route", how="left")
            sc_cell = scale * m2["cov_factor"].fillna(1.0).to_numpy()
            se_cell = m2["seats"].fillna(seats).to_numpy(float)
            st_cell = m2["standing"].fillna(standing).to_numpy(float)
        else:
            sc_cell = np.full(len(meta), scale)
            se_cell, st_cell = np.full(len(meta), float(seats)), np.full(len(meta), float(standing))
        rh_key = (meta["route"] + "|" + meta["hour"].astype(str)).to_numpy()
        route_tix = meta.groupby("route")["n_tickets"].transform("sum").to_numpy()
        tert = pd.qcut(pd.Series(route_tix).rank(method="first"), 3, labels=["low_volume", "mid_volume", "high_volume"]).to_numpy()
        band = hour_band(meta["hour"].to_numpy()) if grain == "hour" else meta["hour"].map({0:"early",1:"am_peak_7-10",2:"midday",3:"pm_peak_17-20",4:"late"}).to_numpy()
        for k, date in enumerate(dates):
            pred = (S - M[:, k]) / (D - 1)
            ok = (TT - T[:, k]) >= min_tickets
            if ok.sum() == 0:
                continue
            act, p = M[ok, k], pred[ok]
            hrs = meta["hour"].to_numpy()[ok]
            hmean = pd.Series(p).groupby(hrs).transform("mean").to_numpy()   # baseline: hour-of-day mean
            rhmean = pd.Series(p).groupby(rh_key[ok]).transform("mean").to_numpy()   # baseline: route x hour mean
            err, berr, rerr = np.abs(p - act), np.abs(hmean - act), np.abs(rhmean - act)
            sck, sek, stk = sc_cell[ok], se_cell[ok], st_cell[ok]
            la, lp = level_of(act * sck, sek, stk), level_of(p * sck, sek, stk)
            cm_lodo[dt] = cm_lodo.get(dt, np.zeros((3, 3))) + confusion(la, lp)
            gap = np.abs(np.vectorize(ORDER.get)(la) - np.vectorize(ORDER.get)(lp))
            by_day.append({"day_type": dt, "date": date, "cells_scored": int(ok.sum()),
                           "wape": err.sum() / max(act.sum(), 1e-9), "baseline_wape": berr.sum() / max(act.sum(), 1e-9),
                           "route_hour_baseline_wape": rerr.sum() / max(act.sum(), 1e-9),
                           "bias": (p.sum() - act.sum()) / max(act.sum(), 1e-9),
                           "level_exact": float((gap == 0).mean()), "level_within_one": float((gap <= 1).mean())})
            for gname, garr in (("route_volume", tert[ok]), ("hour_band", band[ok])):
                for gv in np.unique(garr):
                    m = garr == gv
                    a = group_acc.setdefault((dt, gname, str(gv)), [0.0, 0.0, 0.0, 0])
                    a[0] += err[m].sum(); a[1] += berr[m].sum(); a[2] += act[m].sum(); a[3] += int(m.sum())
        # stability: do cells keep their rank between halves of the month?
        ok_all = TT >= min_tickets
        odd, even = M[ok_all][:, 0::2].mean(1), M[ok_all][:, 1::2].mean(1)
        h = D // 2
        first, second = M[ok_all][:, :h].mean(1), M[ok_all][:, h:].mean(1)
        # typical-day label check: first half of the month vs second half, same cells
        lf = level_of(first * sc_cell[ok_all], se_cell[ok_all], st_cell[ok_all])
        ls = level_of(second * sc_cell[ok_all], se_cell[ok_all], st_cell[ok_all])
        split_half[dt] = level_scores(confusion(ls, lf))
        split_half[dt]["wape"] = round(float(np.abs(first - second).sum() / max(second.sum(), 1e-9)), 4)
        # week to week: each ISO week against the rest of the month (the brief asks for this explicitly)
        wk = np.array([pd.Timestamp(x).isocalendar().week for x in dates])
        weeks = []
        for w in np.unique(wk):
            inw = wk == w
            if inw.sum() < (3 if dt == "weekday" else 2) or (~inw).sum() < 3:
                continue
            a_w, a_r = M[ok_all][:, inw].mean(1), M[ok_all][:, ~inw].mean(1)
            lw = level_of(a_w * sc_cell[ok_all], se_cell[ok_all], st_cell[ok_all])
            lr = level_of(a_r * sc_cell[ok_all], se_cell[ok_all], st_cell[ok_all])
            sc_ = level_scores(confusion(lw, lr))
            weeks.append({"iso_week": int(w), "days": int(inw.sum()), "spearman_vs_rest": round(spearman(a_w, a_r), 4),
                          "level_exact": sc_["level_exact"], "kappa": sc_["kappa"]})
        week_to_week[dt] = weeks
        stability[dt] = {"cells": int(ok_all.sum()), "spearman_odd_vs_even_days": round(spearman(odd, even), 4),
                         "spearman_first_vs_second_half": round(spearman(first, second), 4)}

    bd = pd.DataFrame(by_day)
    groups = pd.DataFrame([{"day_type": k[0], "group_by": k[1], "group": k[2], "cells_scored": v[3],
                            "wape": v[0] / max(v[2], 1e-9), "baseline_wape": v[1] / max(v[2], 1e-9)}
                           for k, v in sorted(group_acc.items())])
    bd.to_csv(out_dir / f"backtest{sfx}_by_day.csv", index=False)
    groups.to_csv(out_dir / f"backtest{sfx}_groups.csv", index=False)
    summ = bd.groupby("day_type")[["wape", "baseline_wape", "route_hour_baseline_wape", "bias", "level_exact",
                                   "level_within_one", "cells_scored"]].mean()
    report = {
        "min_tickets_for_scoring": min_tickets, "capacity_scenario_for_levels": [seats, standing],
        "summary_by_day_type": {k: {c: round(float(v), 4) for c, v in r.items()} for k, r in summ.iterrows()},
        "days_scored": int(len(bd)), "stability": stability,
        "levels_leave_one_day_out": {k: level_scores(v) for k, v in cm_lodo.items()},
        "levels_split_half": split_half,
        "week_vs_rest_of_month": week_to_week,
    }
    (out_dir / f"backtest{sfx}.json").write_text(json.dumps(report, indent=2))
    print(summ.round(3).to_string())
    print(json.dumps(stability))
    print(json.dumps({"lodo": report["levels_leave_one_day_out"], "split_half": split_half}, indent=1))
    print(groups.round(3).to_string(index=False))
    return report


def run() -> None:
    run_backtest(config.INTERIM_DIR, config.OUT_DIR)
    run_backtest(config.INTERIM_DIR, config.OUT_DIR, grain="band")


if __name__ == "__main__":
    run()
