"""Per-route facts used by the crowding model: length, inferred bus size, and ticket coverage.

Bus size (inferred, not given in the data):
  DEVI mohalla buses are 9 m electric buses on short feeder routes of about 10-15 km (press reports).
  In this GTFS, routes whose name starts with "D" have a median length of 10 km against 19 km for the rest.
  Rule: name starts with D and the route is at most DEVI_MAX_KM long -> 9 m (23 seats + 13 standing), else 12 m
  (39 + 24). The 9 m / 12 m / 40+40 sensitivity table in levels.py still shows what happens if this is wrong.

Coverage: a share of tickets on a route cannot be placed on a stretch (stop not on the route's longest trip,
wrong order, unmatched name). Loads are built from the resolved ones only, while the scale-up assumes all
tickets. cov_factor = all passengers on the route / resolved passengers, capped at COV_CAP. The point estimate
uses it; the low end of the range does not (it assumes the dropped tickets rode nowhere busy).

Writes data/interim/route_info.parquet and route_info_report.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from . import config

DEVI_MAX_KM = 20.0
COV_CAP = 2.0
CAPACITY = {"9m": (23, 13), "12m": (39, 24)}


def build(interim_dir: Path, gtfs_dir: Path) -> dict:
    interim_dir, g = Path(interim_dir), Path(gtfs_dir)
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE ri AS
        WITH s AS (SELECT stop_id, CAST(stop_lat AS DOUBLE) AS lat, CAST(stop_lon AS DOUBLE) AS lon
                   FROM read_csv('{g / 'stops.txt'}', header=true, all_varchar=true)),
        c AS (SELECT route, pos, lat, lon FROM read_parquet('{interim_dir / 'canonical_routes.parquet'}') JOIN s USING (stop_id)),
        seg AS (SELECT a.route, 2 * 6371 * asin(sqrt(pow(sin(radians(b.lat - a.lat) / 2), 2) +
                       cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2))) AS km
                FROM c a JOIN c b ON a.route = b.route AND b.pos = a.pos + 1),
        rl AS (SELECT route, sum(km) AS route_km FROM seg GROUP BY 1)
        SELECT rl.route, rl.route_km,
               CASE WHEN rl.route LIKE 'D%' AND rl.route_km <= {DEVI_MAX_KM} THEN '9m' ELSE '12m' END AS bus_class,
               coalesce(r.pax_total, 0) AS pax_total, coalesce(r.pax_resolved, 0) AS pax_resolved,
               CASE WHEN coalesce(r.pax_resolved, 0) > 0
                    THEN least(r.pax_total / r.pax_resolved, {COV_CAP}) ELSE 1.0 END AS cov_factor
        FROM rl LEFT JOIN read_parquet('{interim_dir / 'route_resolved.parquet'}') r USING (route)""")
    con.execute("ALTER TABLE ri ADD COLUMN seats INTEGER; ALTER TABLE ri ADD COLUMN standing INTEGER")
    for k, (se, st) in CAPACITY.items():
        con.execute("UPDATE ri SET seats = ?, standing = ? WHERE bus_class = ?", [se, st, k])
    con.execute(f"COPY ri TO '{interim_dir / 'route_info.parquet'}' (FORMAT PARQUET)")
    one = lambda q: con.execute(q).fetchone()
    n9, n12 = one("SELECT count(*) FILTER (WHERE bus_class='9m'), count(*) FILTER (WHERE bus_class='12m') FROM ri")
    p9 = one("SELECT sum(pax_total) FILTER (WHERE bus_class='9m') / sum(pax_total) FROM ri")[0]
    rep = {"routes": n9 + n12, "routes_9m_inferred": n9, "routes_12m": n12,
           "ticketed_pax_share_on_9m_routes": round(float(p9 or 0), 4),
           "network_resolved_share": round(float(one("SELECT sum(pax_resolved) / sum(pax_total) FROM ri WHERE pax_total > 0")[0]), 4),
           "median_cov_factor": round(float(one("SELECT median(cov_factor) FROM ri WHERE pax_resolved > 0")[0]), 3),
           "routes_at_cov_cap": int(one(f"SELECT count(*) FROM ri WHERE cov_factor >= {COV_CAP}")[0]),
           "devi_rule": f"name starts with D and length <= {DEVI_MAX_KM} km"}
    (interim_dir / "route_info_report.json").write_text(json.dumps(rep, indent=2))
    for k, v in rep.items():
        print(f"{k:>34}: {v}")
    return rep


def load_route_info(interim_dir: Path):
    """route_info as a DataFrame, or None when the stage has not run (unit tests, old outputs)."""
    p = Path(interim_dir) / "route_info.parquet"
    if not p.exists():
        return None
    return duckdb.connect().execute(f"SELECT * FROM read_parquet('{p}')").df()


def run() -> None:
    build(config.INTERIM_DIR, config.GTFS_DIR)


if __name__ == "__main__":
    run()
