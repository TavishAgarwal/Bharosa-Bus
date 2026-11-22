"""Write what the web UI reads: web/data/demo_journeys.json (precomputed planner answers for demo pairs).

Precomputing keeps the demo from breaking on stage; the comfort slider re-ranks these options in the browser.
Also copies the run's assumptions into the file so the UI can show them.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from . import config
from .levels import scenarios, DEFAULT_SCENARIO

ROOT = Path(__file__).resolve().parents[2]
TIMES = [("08:30", "weekday"), ("13:00", "weekday"), ("18:00", "weekday"), ("18:00", "weekend"), ("21:30", "weekday")]


def run(pairs_path: Path | None = None, out_path: Path | None = None) -> None:
    sys.path.insert(0, str(ROOT))
    from planner.csa import load_network, plan  # noqa: E402

    pairs = json.loads(Path(pairs_path or ROOT / "planner" / "demo_pairs.json").read_text())
    net = load_network(config.GTFS_DIR, config.INTERIM_DIR, config.OUT_DIR)
    seats, standing = scenarios()["custom" if "custom" in scenarios() else DEFAULT_SCENARIO]
    out = {
        "generated": str(date.today()),
        "assumptions": {"sample_rate": list(config.SAMPLE_RATE), "pass_holder_uplift": list(config.PASS_HOLDER_UPLIFT),
                        "capacity_seats": seats, "capacity_rated_standing": standing,
                        "capacity_source": ("press reports; bus size per route inferred (short D-routes = 9 m DEVI, 23 seats + 13 standing; "
                                            "others 12 m, 39 + 24)" if not (config.CAPACITY_SEATS and config.CAPACITY_STANDING)
                                            else "configured in .env"),
                        "min_tickets_per_cell": config.MIN_TICKETS_PER_CELL,
                        "times_are": "scheduled GTFS, not observed"},
        "queries": [],
    }
    for pr in pairs:
        for t, dt in TIMES:
            opts = plan(pr["from"], pr["to"], t, dt, 0.0, net)
            out["queries"].append({"from": pr["from"], "to": pr["to"], "depart": t, "day_type": dt, "options": opts,
                                   "from_resolved": opts[0]["from"] if opts else "", "to_resolved": opts[0]["to"] if opts else ""})
    dst = Path(out_path or ROOT / "web" / "data" / "demo_journeys.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=1))
    n = sum(len(q["options"]) for q in out["queries"])
    empty = [f'{q["from"]}->{q["to"]} {q["depart"]} {q["day_type"]}' for q in out["queries"] if not q["options"]]
    print(f"wrote {dst} ({len(out['queries'])} queries, {n} options); no result for {len(empty)}: {empty[:5]}")


# ---- operator view and route explorer (I-F8, map) ----------------------------------------------------

def export_operator(out_dir: Path | None = None, top: int = 60) -> Path:
    """Routes and day parts where many stretches are confidently crowded: where extra buses would help most."""
    import duckdb
    od = Path(out_dir or config.OUT_DIR)
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT route, band, day_type,
               count(*) AS stretches_with_evidence,
               sum(CAST(level = 'crowded' AS INT)) AS crowded_stretches,
               sum(CAST(level = 'crowded' AND level_if_low = 'crowded' AS INT)) AS crowded_even_at_low_estimate,
               least(round(max(load)), 101) AS max_load, sum(n_tickets) AS tickets,
               arg_max(from_stop || ' to ' || to_stop, load) AS busiest_stretch
        FROM read_parquet('{od / 'crowding_band_levels.parquet'}') WHERE abstain_reason = ''
        GROUP BY route, band, day_type
        HAVING sum(CAST(level = 'crowded' AS INT)) > 0 AND count(*) >= 5
        ORDER BY crowded_even_at_low_estimate DESC, crowded_stretches DESC, route, day_type, band LIMIT {top}""").df()
    df["crowded_share"] = (df["crowded_stretches"] / df["stretches_with_evidence"]).round(2)
    df.to_csv(od / "operator_overload.csv", index=False)
    web = ROOT / "web" / "data"
    web.mkdir(parents=True, exist_ok=True)
    (web / "operator_overload.json").write_text(df.to_json(orient="records", indent=1))
    return od / "operator_overload.csv"


def export_extra_bus(out_dir: Path | None = None, top: int = 40) -> Path:
    """Rank (route, day part, day type) by how much ONE extra bus in that day part would cut standing time.

    For each evidenced stretch: standing passenger-minutes per day = max(load - seats, 0) x trips x stretch minutes.
    With one more trip the same riders spread over trips + 1 buses: load' = load x trips / (trips + 1).
    Saving = before - after, summed over the route's stretches. Also computed from the LOW end of the load range,
    so a route that only helps under the high assumptions is visible as such. Stretch minutes come from the schedule.
    """
    import duckdb
    od = Path(out_dir or config.OUT_DIR)
    con = duckdb.connect()
    df = con.execute(f"""
        WITH c AS (SELECT route, pos, off_sec FROM read_parquet('{config.INTERIM_DIR / 'canonical_routes.parquet'}')),
        m AS (SELECT a.route, a.pos AS seg, greatest((b.off_sec - a.off_sec) / 60.0, 0.5) AS mins
              FROM c a JOIN c b ON a.route = b.route AND b.pos = a.pos + 1),
        x AS (SELECT l.*, m.mins FROM read_parquet('{od / 'crowding_band_levels.parquet'}') l JOIN m USING (route, seg)
              WHERE l.abstain_reason = '' AND l.trips > 0),
        s AS (SELECT route, band, day_type, any_value(bus_class) AS bus_class, any_value(seats) AS seats,
                     round(avg(trips)) AS buses_in_day_part, count(*) AS stretches,
                     sum(greatest(load - seats, 0) * trips * mins) AS standing_min,
                     sum(greatest(load * trips / (trips + 1) - seats, 0) * (trips + 1) * mins) AS standing_min_after,
                     sum(greatest(load_lo - seats, 0) * trips * mins) AS standing_min_lo,
                     sum(greatest(load_lo * trips / (trips + 1) - seats, 0) * (trips + 1) * mins) AS standing_min_lo_after,
                     sum(CAST(level = 'crowded' AS INT)) AS crowded_stretches,
                     least(round(max(load)), 101) AS max_load,
                     arg_max(from_stop || ' to ' || to_stop, load) AS busiest_stretch, sum(n_tickets) AS tickets
              FROM x GROUP BY route, band, day_type HAVING count(*) >= 5)
        SELECT *, round(standing_min - standing_min_after) AS standing_min_saved,
               round(standing_min_lo - standing_min_lo_after) AS standing_min_saved_low
        FROM s WHERE standing_min > 0 ORDER BY standing_min_saved_low DESC, standing_min_saved DESC, route, day_type, band LIMIT {top}""").df()
    df["standing_min"] = df["standing_min"].round()
    df = df.drop(columns=["standing_min_after", "standing_min_lo", "standing_min_lo_after"])
    df.to_csv(od / "extra_bus_benefit.csv", index=False)
    (ROOT / "web" / "data" / "extra_bus.json").write_text(df.to_json(orient="records", indent=1))
    return od / "extra_bus_benefit.csv"


def export_route_profiles(n_routes: int = 40, out_dir: Path | None = None) -> Path:
    """Per-route stop coordinates plus crowding level per stretch for each (day type, band). Feeds the map page."""
    import duckdb
    sys.path.insert(0, str(ROOT))
    from planner.csa import load_network
    od = Path(out_dir or config.OUT_DIR)
    net = load_network(config.GTFS_DIR, config.INTERIM_DIR, None)
    ix = {s: i for i, s in enumerate(net.stop_ids)}
    con = duckdb.connect()
    bp = f"read_parquet('{od / 'crowding_band_levels.parquet'}')"
    routes = [r for (r,) in con.execute(f"SELECT route FROM {bp} GROUP BY route ORDER BY sum(n_tickets) DESC, route LIMIT {n_routes}").fetchall()]
    # every route on the operators page also gets geometry, so selecting a row can show it on the map
    for name in ("extra_bus_benefit.csv", "operator_overload.csv"):
        f = od / name
        if f.exists():
            routes += [r for (r,) in con.execute(f"SELECT DISTINCT route FROM read_csv('{f}') ORDER BY route").fetchall() if r not in routes]
    code = {"seats": 0, "standing": 1, "crowded": 2}
    out = {"bands": ["early 5-6", "am peak 7-10", "midday 11-16", "pm peak 17-20", "late 21-4"], "routes": {}}
    for r in routes:
        stops = sorted((p, sid) for (rr, p), sid in net.canon_stop_map.items() if rr == r)
        pts = [[round(float(net.lat[ix[sid]]), 5), round(float(net.lon[ix[sid]]), 5), net.stop_names[ix[sid]]] for _, sid in stops if sid in ix]
        n_seg = max(len(pts) - 1, 0)
        prof = {}
        for dt in ("weekday", "weekend"):
            for b in range(5):
                lv, ld = [-1] * n_seg, [0] * n_seg
                for seg, level, load, nt in con.execute(
                        f"SELECT seg, level, load, n_tickets FROM {bp} WHERE route=? AND day_type=? AND hour=? AND abstain_reason=''",
                        [r, dt, b]).fetchall():
                    if seg < n_seg:
                        lv[seg], ld[seg] = code[level], min(int(round(load)), 101)
                prof[f"{dt}|{b}"] = {"level": lv, "load": ld}
        out["routes"][r] = {"stops": pts, "profile": prof}
    dst = ROOT / "web" / "data" / "route_profiles.json"
    dst.write_text(json.dumps(out, separators=(",", ":")))
    return dst


def run_all() -> None:
    run()
    print("operator table:", export_operator())
    print("extra bus table:", export_extra_bus())
    print("route profiles:", export_route_profiles())


if __name__ == "__main__":
    run_all()
