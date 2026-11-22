"""I-F3 (part 1): turn each matched ticket into passenger-load on the route stretches it covers.

A ticket boards at stop position i and alights at j (> i) on the route's canonical stop sequence
(the longest scheduled trip of that route). It adds passenger_count to every stretch i..j-1.
The hour of a stretch is the ticket time plus the scheduled run time from stop i to that stretch,
so a long ride is spread over the hours it really spans.

Writes data/interim/: canonical_routes.parquet, sched_trips.parquet, stretch_daily.parquet, load_report.json
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from . import config

ROUTE_KEY = "upper(regexp_replace({c}, '[\\s\\-_]+', '', 'g'))"


def _secs(col: str) -> str:
    return (f"(TRY_CAST(split_part({col}, ':', 1) AS INTEGER) * 3600 + "
            f"TRY_CAST(split_part({col}, ':', 2) AS INTEGER) * 60 + "
            f"coalesce(TRY_CAST(split_part({col}, ':', 3) AS INTEGER), 0))")


def build_canonical(con: duckdb.DuckDBPyConnection, gtfs_dir: Path) -> None:
    """Creates tables canon(route,pos,stop_id,stop_name,off_sec) and sched(route,pos,hour,trips)."""
    g = Path(gtfs_dir)
    rd = lambda n: f"read_csv('{g / (n + '.txt')}', header=true, all_varchar=true, null_padding=true)"
    con.execute(f"""
        CREATE OR REPLACE TABLE gtrips AS
        SELECT t.trip_id, {ROUTE_KEY.format(c='r.route_short_name')} AS route
        FROM {rd('trips')} t JOIN {rd('routes')} r USING (route_id)""")
    con.execute(f"""
        CREATE OR REPLACE TABLE gst AS
        SELECT trip_id, stop_id, CAST(stop_sequence AS INTEGER) AS seq,
               {_secs('arrival_time')} AS arr, {_secs('departure_time')} AS dep
        FROM {rd('stop_times')}""")
    con.execute("""
        CREATE OR REPLACE TABLE canon_trip AS
        SELECT route, trip_id FROM (
          SELECT t.route, s.trip_id, count(*) AS n FROM gst s JOIN gtrips t USING (trip_id) GROUP BY 1, 2)
        QUALIFY row_number() OVER (PARTITION BY route ORDER BY n DESC, trip_id) = 1""")
    con.execute(f"""
        CREATE OR REPLACE TABLE canon AS
        SELECT c.route,
               CAST(row_number() OVER (PARTITION BY c.route ORDER BY s.seq) - 1 AS INTEGER) AS pos,
               s.stop_id, st.stop_name,
               greatest(coalesce(s.arr, s.dep) - first(coalesce(s.arr, s.dep)) OVER
                        (PARTITION BY c.route ORDER BY s.seq), 0) AS off_sec
        FROM canon_trip c JOIN gst s USING (trip_id)
        LEFT JOIN (SELECT stop_id, stop_name FROM {rd('stops')}) st USING (stop_id)""")
    # scheduled trips leaving each canonical stop, per hour of day (service runs every day: one calendar row)
    con.execute("""
        CREATE OR REPLACE TABLE sched AS
        SELECT c.route, c.pos, CAST((coalesce(s.dep, s.arr) // 3600) % 24 AS INTEGER) AS hour,
               count(DISTINCT s.trip_id) AS trips
        FROM gst s JOIN gtrips t USING (trip_id)
        JOIN canon c ON c.route = t.route AND c.stop_id = s.stop_id
        GROUP BY 1, 2, 3""")


def load_stretches(tickets_matched: Path, gtfs_dir: Path, interim_dir: Path) -> dict:
    interim_dir = Path(interim_dir)
    con = duckdb.connect()
    build_canonical(con, gtfs_dir)

    # normalise the ticket route the same way as GTFS names (OMS(-)DOWN, D-034UP ... were silently dropped before)
    have = {r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(tickets_matched)]).fetchall()}
    opt = ", ".join(f"{c}" if c in have else f"NULL AS {c}" for c in ("amount", "is_ac", "start_method", "end_method"))
    con.execute("CREATE TABLE t AS SELECT row_number() OVER () AS tid, " + ROUTE_KEY.format(c="route") + " AS route, ts_ist, date, day_type, "
                f"passenger_count AS pc, {opt}, start_stop_ids, end_stop_ids "
                "FROM read_parquet(?) WHERE matched",
                [str(tickets_matched)])
    n_matched = con.execute("SELECT count(*) FROM t").fetchone()[0]
    con.execute("""CREATE TABLE sp AS SELECT t.tid, c.pos FROM t JOIN canon c
                   ON c.route = t.route AND list_contains(t.start_stop_ids, c.stop_id)""")
    con.execute("""CREATE TABLE ep AS SELECT t.tid, c.pos FROM t JOIN canon c
                   ON c.route = t.route AND list_contains(t.end_stop_ids, c.stop_id)""")
    # nearest valid pair (alight after board); loops can repeat a stop name
    con.execute("""
        CREATE TABLE pairs AS
        SELECT tid, arg_min(i, j - i) AS i, arg_min(j, j - i) AS j FROM (
          SELECT sp.tid, sp.pos AS i, ep.pos AS j FROM sp JOIN ep USING (tid) WHERE ep.pos > sp.pos)
        GROUP BY tid""")
    one = lambda q: con.execute(q).fetchone()[0]
    report = {
        "tickets_matched_names": n_matched,
        "route_in_gtfs_canonical": one("SELECT count(*) FROM t WHERE route IN (SELECT route FROM canon)"),
        "start_on_route": one("SELECT count(DISTINCT tid) FROM sp"),
        "end_on_route": one("SELECT count(DISTINCT tid) FROM ep"),
        "valid_pair": one("SELECT count(*) FROM pairs"),
    }
    report["valid_pair_share_of_matched"] = round(report["valid_pair"] / max(n_matched, 1), 4)

    con.execute("""
        CREATE TABLE tp AS
        SELECT t.tid, t.route, t.ts_ist, t.date, t.day_type, t.pc, p.i, p.j, c.off_sec AS off_i
        FROM t JOIN pairs p USING (tid) JOIN canon c ON c.route = t.route AND c.pos = p.i""")
    con.execute("""
        CREATE TABLE stretch_daily AS
        SELECT x.route, x.seg, CAST(hour(x.ts_ist + to_seconds(CAST(c.off_sec - x.off_i AS DOUBLE))) AS INTEGER) AS hour,
               x.date, x.day_type, sum(x.pc) AS passengers, count(*) AS tickets
        FROM (SELECT tp.*, unnest(range(tp.i, tp.j)) AS seg FROM tp) x
        JOIN canon c ON c.route = x.route AND c.pos = x.seg
        GROUP BY ALL""")
    for name in ("canon", "sched", "stretch_daily"):
        out = "canonical_routes" if name == "canon" else "sched_trips" if name == "sched" else name
        con.execute(f"COPY {name} TO '{interim_dir / (out + '.parquet')}' (FORMAT PARQUET)")
    # per-route share of passengers that resolve to a stretch (used to correct loads for dropped tickets)
    con.execute(f"""
        COPY (SELECT a.route, a.pax_total, a.tickets_total, coalesce(b.pax_resolved, 0) AS pax_resolved
              FROM (SELECT {ROUTE_KEY.format(c='route')} AS route, sum(passenger_count) AS pax_total, count(*) AS tickets_total
                    FROM read_parquet('{tickets_matched}') GROUP BY 1) a
              LEFT JOIN (SELECT route, sum(pc) AS pax_resolved FROM tp GROUP BY 1) b USING (route)
              WHERE a.route IN (SELECT route FROM canon))
        TO '{interim_dir / 'route_resolved.parquet'}' (FORMAT PARQUET)""")
    # ticket-level stop pairs for the fare consistency check (fares.py)
    con.execute(f"""COPY (SELECT tp.tid, tp.route, tp.i, tp.j, tp.pc, t.amount, t.is_ac, t.start_method, t.end_method
                         FROM tp JOIN t USING (tid))
                    TO '{interim_dir / 'ticket_pairs.parquet'}' (FORMAT PARQUET)""")
    report["stretch_daily_rows"] = one("SELECT count(*) FROM stretch_daily")
    report["canonical_routes"] = one("SELECT count(DISTINCT route) FROM canon")
    report["passenger_stretch_total"] = int(one("SELECT sum(passengers) FROM stretch_daily"))
    (interim_dir / "load_report.json").write_text(json.dumps(report, indent=2))
    for k, v in report.items():
        print(f"{k:>32}: {v:,}" if isinstance(v, int) else f"{k:>32}: {v}")
    return report


def run() -> None:
    load_stretches(config.INTERIM_DIR / "tickets_matched.parquet", config.GTFS_DIR, config.INTERIM_DIR)


if __name__ == "__main__":
    run()
