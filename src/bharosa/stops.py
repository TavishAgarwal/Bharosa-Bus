"""I-F2: match ticket stop names to GTFS stops, report the match rate and the unmatched list.

Inputs : data/interim/tickets.parquet (from clean), GTFS dir (stops, routes, trips, stop_times),
         optional data/raw/stop_bridge.csv with columns ticket_stop_name,stop_id (manual fixes).
Outputs: data/interim/stop_match.parquet     one row per distinct (route, ticket stop name)
         data/interim/tickets_matched.parquet tickets + start/end GTFS name and candidate stop_ids
         data/out/stops_unmatched.csv         unmatched names by ticket volume
         data/interim/stops_report.json

A name can map to several stop_ids on one route (two directions, two sides of the road).
We return the GTFS name and ALL candidate ids; direction is resolved later (I-F3) from stop order.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import pandas as pd
from rapidfuzz import fuzz, process

from . import config

ROUTE_CUTOFF = 88      # fuzzy score needed when the candidate set is the route's own stops
GLOBAL_CUTOFF = 93     # stricter when searching all stops
MARGIN = 3             # best must beat the runner-up (different name) by this much
TARGET_RATE = 0.90     # TASKS.md I-F2: >90% of tickets matched

_ABBR = {
    "stn": "station", "nr": "near", "opp": "opposite", "mkt": "market", "dpt": "depot",
    "bs": "bus stand", "ter": "terminal", "pt": "point", "rd": "road", "sec": "sector",
    "clny": "colony", "hosp": "hospital", "chowk": "chowk", "xing": "crossing",
    "flyovr": "flyover", "f/o": "flyover", "ndmc": "ndmc", "mcd": "mcd",
}


def norm_name(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)             # drop bracketed notes
    s = re.sub(r"[^a-z0-9/ ]+", " ", s)
    toks = [_ABBR.get(t, t) for t in s.split()]
    return " ".join(toks)


_GENERIC = {"metro station", "terminal", "bus stand", "depot", "chowk", "crossing", "market", "village"}


def aliases(stop_name: str) -> set[str]:
    """GTFS names are often compound ('Badarpur /Jaitpur Crossing'); tickets use one part.
    Returns the full normalised name plus each '/'-separated part."""
    full = norm_name(stop_name)
    out = {full}
    for part in re.split(r"\s*/\s*|\s+/\s+", stop_name or ""):
        a = norm_name(part)
        if len(a) >= 3 and a not in _GENERIC:
            out.add(a)
    return out


def norm_route(s: str) -> str:
    return re.sub(r"[\s\-_]+", "", (s or "").upper())


def route_base(s: str) -> str:
    """Ticket routes carry a direction suffix (717AUP, 717ADOWN); GTFS short names usually do not."""
    return re.sub(r"(UP|DOWN)$", "", norm_route(s))


def _read_gtfs(gtfs_dir: Path):
    con = duckdb.connect()

    def rd(name: str):
        p = gtfs_dir / name
        if not p.exists():
            raise FileNotFoundError(f"GTFS file missing: {p}")
        return f"read_csv('{p}', header=true, all_varchar=true, null_padding=true)"

    stops = con.execute(f"SELECT stop_id, stop_name FROM {rd('stops.txt')}").df()
    route_stops = con.execute(f"""
        SELECT DISTINCT coalesce(nullif(trim(r.route_short_name), ''), r.route_id) AS route_name,
                        st.stop_id
        FROM {rd('stop_times.txt')} st
        JOIN {rd('trips.txt')} t USING (trip_id)
        JOIN {rd('routes.txt')} r USING (route_id)
    """).df()
    return stops, route_stops


def _bridge(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str).dropna()
    return {norm_name(a): b for a, b in zip(df["ticket_stop_name"], df["stop_id"])}


def build_matches(pairs: pd.DataFrame, stops: pd.DataFrame, route_stops: pd.DataFrame,
                  bridge: dict[str, str] | None = None) -> pd.DataFrame:
    """pairs: distinct (route, stop_name). Returns pairs + gtfs_stop_name, stop_ids, method, score."""
    bridge = bridge or {}
    name_of = dict(zip(stops["stop_id"], stops["stop_name"]))
    alias_of = {sid: aliases(n) for sid, n in name_of.items()}

    ids_by_nname: dict[str, list[str]] = {}
    for sid, als in alias_of.items():
        for a in als:
            ids_by_nname.setdefault(a, []).append(sid)
    global_names = list(ids_by_nname)

    rs = route_stops.assign(rkey=route_stops["route_name"].map(norm_route))
    route_ids: dict[str, set[str]] = rs.groupby("rkey")["stop_id"].agg(set).to_dict()

    cache_route: dict[str, tuple[list[str], dict[str, list[str]]]] = {}

    def resolve_rkey(rkey: str) -> str | None:
        if rkey in route_ids:
            return rkey
        base = route_base(rkey)
        return base if base in route_ids else None

    def route_view(rkey: str):
        if rkey not in cache_route:
            sids = route_ids.get(resolve_rkey(rkey) or "", set())
            by_nn: dict[str, list[str]] = {}
            for sid in sids:
                for a in alias_of.get(sid, ()):
                    by_nn.setdefault(a, []).append(sid)
            cache_route[rkey] = (list(by_nn), by_nn)
        return cache_route[rkey]

    def fuzzy(q: str, choices: list[str], cutoff: int):
        if not choices:
            return None
        res = process.extract(q, choices, scorer=fuzz.WRatio, limit=2, score_cutoff=cutoff)
        if not res:
            return None
        if len(res) > 1 and res[0][1] - res[1][1] < MARGIN and res[0][0] != res[1][0]:
            return None  # too close to call; leave for the manual bridge
        return res[0][0], res[0][1]

    rows = []
    for route, raw in zip(pairs["route"], pairs["stop_name"]):
        q = norm_name(raw)
        rkey = norm_route(route)
        names, by_nn = route_view(rkey)
        method, score, sids = "unmatched", 0.0, []
        if q in bridge and bridge[q] in name_of:
            method, score, sids = "bridge", 100.0, [bridge[q]]
        elif q in by_nn:
            method, score, sids = "exact_route", 100.0, by_nn[q]
        elif (hit := fuzzy(q, names, ROUTE_CUTOFF)):
            method, score, sids = "fuzzy_route", float(hit[1]), by_nn[hit[0]]
        elif q in ids_by_nname and len(ids_by_nname[q]) == 1:
            method, score, sids = "exact_global", 100.0, ids_by_nname[q]
        elif (hit := fuzzy(q, global_names, GLOBAL_CUTOFF)):
            method, score, sids = "fuzzy_global", float(hit[1]), ids_by_nname[hit[0]]
        rows.append({
            "route": route, "stop_name": raw, "method": method, "score": score,
            "stop_ids": sorted(sids),
            "gtfs_stop_name": name_of[sids[0]] if sids else None,
            "route_in_gtfs": resolve_rkey(rkey) is not None,
        })
    return pd.DataFrame(rows)


def match_tickets(tickets_parquet: Path, gtfs_dir: Path, bridge_csv: Path,
                  interim_dir: Path, out_dir: Path) -> dict:
    interim_dir, out_dir = Path(interim_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    tickets = con.execute("SELECT * FROM read_parquet(?)", [str(tickets_parquet)]).df()
    stops, route_stops = _read_gtfs(Path(gtfs_dir))

    both = pd.concat([
        tickets[["route", "start_stop_name"]].rename(columns={"start_stop_name": "stop_name"}),
        tickets[["route", "end_stop_name"]].rename(columns={"end_stop_name": "stop_name"}),
    ]).drop_duplicates()
    m = build_matches(both, stops, route_stops, _bridge(Path(bridge_csv)))

    def side(prefix: str, col: str) -> pd.DataFrame:
        j = m.rename(columns={"stop_name": col, "gtfs_stop_name": f"{prefix}_gtfs_name",
                              "stop_ids": f"{prefix}_stop_ids", "method": f"{prefix}_method"})
        return j[["route", col, f"{prefix}_gtfs_name", f"{prefix}_stop_ids", f"{prefix}_method"]]

    t = tickets.merge(side("start", "start_stop_name"), on=["route", "start_stop_name"], how="left")
    t = t.merge(side("end", "end_stop_name"), on=["route", "end_stop_name"], how="left")
    t["matched"] = t["start_gtfs_name"].notna() & t["end_gtfs_name"].notna()

    con.register("m_df", m)
    con.execute("COPY m_df TO ? (FORMAT PARQUET)", [str(interim_dir / "stop_match.parquet")])
    con.register("t_df", t)
    con.execute("COPY t_df TO ? (FORMAT PARQUET)", [str(interim_dir / "tickets_matched.parquet")])

    # Unmatched names by ticket volume (start and end counted separately).
    un = pd.concat([
        t.loc[t["start_gtfs_name"].isna(), ["route", "start_stop_name"]].rename(columns={"start_stop_name": "stop_name"}),
        t.loc[t["end_gtfs_name"].isna(), ["route", "end_stop_name"]].rename(columns={"end_stop_name": "stop_name"}),
    ])
    un = (un.groupby("stop_name").agg(tickets=("route", "size"), routes=("route", "nunique"),
                                       example_route=("route", "first"))
            .sort_values("tickets", ascending=False).reset_index())
    un.to_csv(out_dir / "stops_unmatched.csv", index=False)

    rate = float(t["matched"].mean()) if len(t) else 0.0
    report = {
        "tickets": int(len(t)),
        "ticket_match_rate_both_ends": round(rate, 4),
        "meets_target": rate >= TARGET_RATE,
        "target": TARGET_RATE,
        "start_match_rate": round(float(t["start_gtfs_name"].notna().mean()), 4) if len(t) else 0.0,
        "end_match_rate": round(float(t["end_gtfs_name"].notna().mean()), 4) if len(t) else 0.0,
        "distinct_route_name_pairs": int(len(m)),
        "pair_match_rate": round(float((m["method"] != "unmatched").mean()), 4) if len(m) else 0.0,
        "methods": {k: int(v) for k, v in m["method"].value_counts().items()},
        "routes_not_in_gtfs": sorted(m.loc[~m["route_in_gtfs"], "route"].unique().tolist())[:200],
        "unmatched_names": int(len(un)),
    }
    (interim_dir / "stops_report.json").write_text(json.dumps(report, indent=2))
    print(f"tickets matched on both ends: {rate:.1%} (target {TARGET_RATE:.0%}) "
          f"-> {'OK' if report['meets_target'] else 'BELOW TARGET'}")
    print(f"methods: {report['methods']}")
    print(f"top unmatched: {out_dir / 'stops_unmatched.csv'}")
    return report


def run() -> None:
    match_tickets(
        config.INTERIM_DIR / "tickets.parquet",
        config.GTFS_DIR,
        config.GTFS_DIR.parent / "stop_bridge.csv",
        config.INTERIM_DIR,
        config.OUT_DIR,
    )


if __name__ == "__main__":
    run()
