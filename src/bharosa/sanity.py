"""I-F6: sanity checks against known patterns, as plots plus a pass/fail report.

Checks: weekday peaks fall in 7-10 and 17-20; weekdays carry more tickets per day than weekends;
the busiest corridors are listed for a human to eyeball; daily volume across the month is plotted
(weekends shaded; 2 Oct Gandhi Jayanti and about 20 Oct Dussehra marked, verify the dates).

Writes data/out/sanity/*.png, sanity.html, top_stretches.csv, top_routes.csv, sanity_report.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402

HOLIDAYS = {"2026-10-02": "Gandhi Jayanti", "2026-10-20": "Dussehra (verify)"}


def run_sanity(interim_dir: Path, out_dir: Path) -> dict:
    interim_dir, out_dir = Path(interim_dir), Path(out_dir)
    sd = out_dir / "sanity"
    sd.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    tix = f"read_parquet('{interim_dir / 'tickets.parquet'}')"
    cells = f"read_parquet('{out_dir / 'crowding_levels.parquet'}')"

    daily = con.execute(f"SELECT date, day_type, sum(passenger_count) pax FROM {tix} GROUP BY 1, 2 ORDER BY 1").df()
    hourly = con.execute(f"""
        SELECT t.day_type, t.hour, sum(t.passenger_count) / d.n AS pax_per_day
        FROM {tix} t JOIN (SELECT day_type, count(DISTINCT date) n FROM {tix} GROUP BY 1) d USING (day_type)
        GROUP BY t.day_type, t.hour, d.n ORDER BY 1, 2""").df()
    load_h = con.execute(f"""
        SELECT day_type, hour, median(load) AS med_load, quantile_cont(load, 0.9) AS p90_load
        FROM {cells} WHERE abstain_reason = '' GROUP BY 1, 2 ORDER BY 1, 2""").df()
    top_routes = con.execute(f"SELECT route, sum(passenger_count) pax, count(*) tickets FROM {tix} "
                             "GROUP BY 1 ORDER BY 2 DESC LIMIT 25").df()
    top_str = con.execute(f"""
        SELECT route, from_stop, to_stop, hour, day_type, round(load) AS load, round(load_lo) lo, round(load_hi) hi, n_tickets
        FROM {cells} WHERE abstain_reason = '' AND day_type = 'weekday'
        ORDER BY load DESC LIMIT 30""").df()
    top_routes.to_csv(sd / "top_routes.csv", index=False)
    top_str.to_csv(sd / "top_stretches.csv", index=False)

    # 1 hourly profile
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    for dt_, c in (("weekday", "#1f77b4"), ("weekend", "#ff7f0e")):
        h = hourly[hourly.day_type == dt_]
        ax[0].plot(h.hour, h.pax_per_day, marker="o", label=dt_, color=c)
        m = load_h[load_h.day_type == dt_]
        ax[1].plot(m.hour, m.med_load, marker="o", label=f"{dt_} median", color=c)
        ax[1].plot(m.hour, m.p90_load, ls="--", label=f"{dt_} p90", color=c, alpha=.6)
    ax[0].set(title="Ticketed passengers per day, by hour", xlabel="hour (IST)", ylabel="passengers/day")
    ax[1].set(title="Expanded load per bus (cells with enough tickets)", xlabel="hour (IST)", ylabel="passengers/bus")
    for a in ax:
        a.legend(); a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(sd / "hourly_profile.png", dpi=130); plt.close(fig)

    # 2 daily volume
    fig, ax = plt.subplots(figsize=(11, 3.6))
    d = pd.to_datetime(daily["date"])
    ax.bar(d, daily["pax"], color=np.where(daily.day_type == "weekend", "#ff7f0e", "#1f77b4"))
    for k, v in HOLIDAYS.items():
        ax.axvline(pd.Timestamp(k), color="red", ls=":"); ax.text(pd.Timestamp(k), ax.get_ylim()[1] * .95, v, rotation=90, va="top", fontsize=8)
    ax.set(title="Ticketed passengers per day (orange = weekend)", ylabel="passengers"); ax.grid(alpha=.3, axis="y")
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(sd / "daily_volume.png", dpi=130); plt.close(fig)

    # 3 corridors
    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    r = top_routes.head(15).iloc[::-1]
    ax[0].barh(r.route, r.pax, color="#1f77b4"); ax[0].set(title="Top routes by ticketed passengers (month)")
    s = top_str.head(15).iloc[::-1]
    ax[1].barh([f"{a[:18]}→{b[:18]} ({h}h)" for a, b, h in zip(s.from_stop, s.to_stop, s.hour)], s.load, color="#d62728")
    ax[1].set(title="Busiest stretches, weekday (expanded load/bus)")
    for a in ax:
        a.grid(alpha=.3, axis="x"); a.tick_params(labelsize=7)
    fig.tight_layout(); fig.savefig(sd / "top_corridors.png", dpi=130); plt.close(fig)

    wd, we = hourly[hourly.day_type == "weekday"], hourly[hourly.day_type == "weekend"]
    am = int(wd.loc[wd.hour.between(5, 13), "pax_per_day"].idxmax()); am = int(wd.loc[am, "hour"])
    pm_i = wd.loc[wd.hour.between(14, 23), "pax_per_day"].idxmax(); pm = int(wd.loc[pm_i, "hour"])
    avg_wd = float(daily.loc[daily.day_type == "weekday", "pax"].mean())
    avg_we = float(daily.loc[daily.day_type == "weekend", "pax"].mean())
    checks = {
        "weekday_am_peak_hour": am, "weekday_am_peak_in_7_10": 7 <= am <= 10,
        "weekday_pm_peak_hour": pm, "weekday_pm_peak_in_17_20": 17 <= pm <= 20,
        "avg_pax_per_weekday": round(avg_wd), "avg_pax_per_weekend_day": round(avg_we),
        "weekend_to_weekday_ratio": round(avg_we / avg_wd, 3), "weekday_busier_than_weekend": avg_wd > avg_we,
        "weekday_peak_to_midday_ratio": round(float(wd.loc[wd.hour.isin([am, pm]), "pax_per_day"].mean() /
                                                    wd.loc[wd.hour.between(12, 15), "pax_per_day"].mean()), 2),
        "busiest_weekend_day": str(daily.loc[daily.day_type == "weekend"].sort_values("pax").iloc[-1].date),
        "lowest_volume_days": [str(x) for x in daily.sort_values("pax").head(3).date],
    }
    checks["share_shown_cells_over_150_pax_per_bus"] = round(float(con.execute(
        f"SELECT avg(CAST(load > 150 AS INT)) FROM {cells} WHERE abstain_reason = ''").fetchone()[0]), 4)
    checks["note"] = ("Shown loads above 150 people per bus are rare after the ticket-based trip floor, but absolute loads "
                      "remain unvalidated: the floor is only a lower bound on buses and the scale-up is assumed.")
    checks["all_pass"] = bool(checks["weekday_am_peak_in_7_10"] and checks["weekday_pm_peak_in_17_20"]
                              and checks["weekday_busier_than_weekend"])
    (sd / "sanity_report.json").write_text(json.dumps(checks, indent=2, default=str))
    html = ["<!DOCTYPE html><meta charset=utf-8><title>Bharosa Bus: sanity checks</title>",
            "<body style='font-family:sans-serif;max-width:1000px;margin:2em auto'><h1>Sanity checks</h1>",
            f"<pre>{json.dumps(checks, indent=2, default=str)}</pre>"]
    html += [f"<h3>{t}</h3><img src='{f}' style='max-width:100%'>" for t, f in
             (("Hourly profile", "hourly_profile.png"), ("Daily volume", "daily_volume.png"), ("Corridors", "top_corridors.png"))]
    html += ["<p>Eyeball the corridor lists in top_routes.csv and top_stretches.csv against known busy Delhi corridors.</p></body>"]
    (sd / "sanity.html").write_text("\n".join(html))
    print(json.dumps(checks, indent=2, default=str))
    return checks


def run() -> None:
    run_sanity(config.INTERIM_DIR, config.OUT_DIR)


if __name__ == "__main__":
    run()
