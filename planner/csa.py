"""Connection Scan Algorithm over static GTFS, with crowding joined onto each ride.

plan(origin, destination, depart, day_type, comfort_weight) returns up to 5 journey options. Each ride
leg carries a crowding level taken from data/out/crowding_levels.parquet (worst stretch on the ride,
or "unknown" when too few stretches have evidence). Travel times are SCHEDULED, not observed.

Alternatives come from re-running the scan at later departures and with each used route banned.
Ranking: score = minutes_from_request + 4 * transfers + 2 * comfort_weight * crowd_penalty_min, where each ride minute
costs 0 (seats), 0.35 (standing / unknown) or 1.0 (crowded).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
from rapidfuzz import fuzz, process

WALK_SPEED = 1.25        # m/s
DETOUR = 1.3             # straight line to walked distance
MAX_ACCESS_M = 800
MAX_ACCESS_STOPS = 25
FOOT_M = 200             # walk transfers between nearby stops
MIN_TRANSFER = 60        # s buffer when changing vehicles
TRANSFER_PENALTY_MIN = 4  # minutes added to the score per change of vehicle
LEVEL_ORDER = {"seats": 0, "standing": 1, "crowded": 2}
LEVEL_COST = {"seats": 0.0, "standing": 0.35, "crowded": 1.0, "unknown": 0.35}
def band_of(h: int) -> int:
    return 1 if 7 <= h <= 10 else 2 if 11 <= h <= 16 else 3 if 17 <= h <= 20 else 0 if 5 <= h <= 6 else 4


ROUTE_KEY = "upper(regexp_replace({c}, '[\\s\\-_]+', '', 'g'))"


def hav(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 12742000 * np.arcsin(np.sqrt(a))


def clock(sec: float) -> str:
    sec = int(round(sec))
    return f"{(sec // 3600) % 24:02d}:{(sec % 3600) // 60:02d}"


@dataclass
class Network:
    stop_ids: list
    stop_names: list
    lat: np.ndarray
    lon: np.ndarray
    dep_stop: np.ndarray
    arr_stop: np.ndarray
    dep_time: np.ndarray
    arr_time: np.ndarray
    trip: np.ndarray
    trip_ids: list
    trip_route: np.ndarray        # trip index -> route index
    routes: list                  # route key by route index
    foot: dict = field(default_factory=dict)
    canon_pos: dict = field(default_factory=dict)   # (route, stop_id) -> [pos]
    canon_off: dict = field(default_factory=dict)   # (route, pos) -> seconds from first stop
    levels: dict = field(default_factory=dict)      # (route, seg, hour, day_type) -> (level, load, lo, hi, n_tickets, n_days)
    band_levels: dict = field(default_factory=dict)  # same key with hour replaced by band id (pooled grain)
    route_band: dict = field(default_factory=dict)   # (route, band, day_type) -> (level, p75_load, n_cells, tickets)
    name_index: list = field(default_factory=list)
    canon_stop_map: dict = field(default_factory=dict)   # (route, pos) -> stop_id
    bus: dict = field(default_factory=dict)              # route -> (bus_class, seats, rated standing), inferred

    def canon_stop(self, route: str, pos: int):
        return self.canon_stop_map.get((route, pos))

    def stop_name(self, stop_id) -> str:
        if not hasattr(self, "_sn"):
            self._sn = dict(zip(self.stop_ids, self.stop_names))
        return str(self._sn.get(stop_id, "?"))


def load_network(gtfs_dir: Path, interim_dir: Path | None = None, out_dir: Path | None = None) -> Network:
    g = Path(gtfs_dir)
    rd = lambda n: f"read_csv('{g / (n + '.txt')}', header=true, all_varchar=true, null_padding=true)"
    con = duckdb.connect()
    secs = lambda c: (f"(TRY_CAST(split_part({c}, ':', 1) AS INTEGER) * 3600 + TRY_CAST(split_part({c}, ':', 2) AS INTEGER) * 60"
                      f" + coalesce(TRY_CAST(split_part({c}, ':', 3) AS INTEGER), 0))")
    con.execute(f"""CREATE TABLE stops AS SELECT row_number() OVER (ORDER BY stop_id) - 1 AS ix, stop_id, stop_name,
                    CAST(stop_lat AS DOUBLE) AS lat, CAST(stop_lon AS DOUBLE) AS lon FROM {rd('stops')}
                    WHERE TRY_CAST(stop_lat AS DOUBLE) IS NOT NULL""")
    con.execute(f"""CREATE TABLE routes_ix AS SELECT row_number() OVER (ORDER BY route) - 1 AS rix, route FROM
                    (SELECT DISTINCT {ROUTE_KEY.format(c='route_short_name')} AS route FROM {rd('routes')})""")
    con.execute(f"""CREATE TABLE trips_ix AS SELECT row_number() OVER (ORDER BY t.trip_id) - 1 AS tix, t.trip_id, ri.rix
                    FROM {rd('trips')} t JOIN {rd('routes')} r USING (route_id)
                    JOIN routes_ix ri ON ri.route = {ROUTE_KEY.format(c='r.route_short_name')}""")
    con.execute(f"""CREATE TABLE conns AS
        SELECT ti.tix, s1.ix AS ds, s2.ix AS asx, x.dt, x.atime FROM (
          SELECT trip_id, stop_id, {secs('departure_time')} AS dt,
                 lead(stop_id) OVER w AS next_stop, lead({secs('arrival_time')}) OVER w AS atime
          FROM {rd('stop_times')} WINDOW w AS (PARTITION BY trip_id ORDER BY CAST(stop_sequence AS INTEGER))) x
        JOIN trips_ix ti USING (trip_id) JOIN stops s1 ON s1.stop_id = x.stop_id JOIN stops s2 ON s2.stop_id = x.next_stop
        WHERE x.atime IS NOT NULL AND x.dt IS NOT NULL AND x.atime >= x.dt""")
    st = con.execute("SELECT stop_id, stop_name, lat, lon FROM stops ORDER BY ix").fetchnumpy()
    cn = con.execute("SELECT tix, ds, asx, dt, atime FROM conns ORDER BY dt, tix, ds, asx").fetchnumpy()
    ti = con.execute("SELECT trip_id, rix FROM trips_ix ORDER BY tix").fetchnumpy()
    rt = con.execute("SELECT route FROM routes_ix ORDER BY rix").fetchnumpy()
    net = Network(list(st["stop_id"]), list(st["stop_name"]), st["lat"], st["lon"],
                  cn["ds"].astype(np.int32), cn["asx"].astype(np.int32), cn["dt"].astype(np.int32),
                  cn["atime"].astype(np.int32), cn["tix"].astype(np.int32), list(ti["trip_id"]),
                  ti["rix"].astype(np.int32), list(rt["route"]))
    # footpaths between nearby stops
    n = len(net.lat)
    for a in range(0, n, 500):
        d = hav(net.lat[a:a + 500, None], net.lon[a:a + 500, None], net.lat[None, :], net.lon[None, :])
        for i in range(d.shape[0]):
            idx = np.where(d[i] <= FOOT_M)[0]
            net.foot[a + i] = [(int(j), d[i, j] * DETOUR / WALK_SPEED) for j in idx if j != a + i]
    net.name_index = [re.sub(r"[^a-z0-9 ]+", " ", str(s).lower()) for s in net.stop_names]
    if interim_dir is not None:
        ip = Path(interim_dir) / "canonical_routes.parquet"
        if ip.exists():
            for r, pos, sid, off in duckdb.connect().execute(f"SELECT route, pos, stop_id, off_sec FROM read_parquet('{ip}')").fetchall():
                net.canon_pos.setdefault((r, sid), []).append(pos)
                net.canon_off[(r, pos)] = off
                net.canon_stop_map[(r, pos)] = sid
        rp = Path(interim_dir) / "route_info.parquet"
        if rp.exists():
            for r, bc, se, st in duckdb.connect().execute(
                    f"SELECT route, bus_class, seats, standing FROM read_parquet('{rp}')").fetchall():
                net.bus[r] = (bc, int(se), int(st))
    if out_dir is not None:
        for fname, target in (("crowding_levels.parquet", net.levels), ("crowding_band_levels.parquet", net.band_levels)):
            lp = Path(out_dir) / fname
            if lp.exists():
                q = ("SELECT route, seg, hour, day_type, level, load, load_lo, load_hi, n_tickets, n_days "
                     f"FROM read_parquet('{lp}') WHERE abstain_reason = ''")
                for r, s, h, d, lv, ld, lo_, hi_, nt, nd in duckdb.connect().execute(q).fetchall():
                    target[(r, s, h, d)] = (lv, ld, lo_, hi_, nt, nd)
        rb = Path(out_dir) / "crowding_route_band.parquet"
        if rb.exists():
            q = f"SELECT route, hour, day_type, level, p75_load, n_cells, tickets FROM read_parquet('{rb}')"
            for r, b, d, lv, p75, nc, tk in duckdb.connect().execute(q).fetchall():
                net.route_band[(r, b, d)] = (lv, p75, nc, tk)
    return net


def resolve_place(net: Network, place) -> tuple[float, float, str]:
    """(lat, lon) tuple, or a stop-name search string. Returns lat, lon, label."""
    if isinstance(place, (tuple, list)):
        return float(place[0]), float(place[1]), f"{place[0]:.4f},{place[1]:.4f}"
    q = re.sub(r"[^a-z0-9 ]+", " ", str(place).lower())
    best = process.extract(q, net.name_index, scorer=fuzz.token_set_ratio, limit=5)
    # among near-ties prefer the shortest name (the main stop rather than a compound label)
    top = max(b[1] for b in best)
    cands = [b for b in best if b[1] >= top - 1]
    _, _, i = min(cands, key=lambda b: len(net.name_index[b[2]]))
    return float(net.lat[i]), float(net.lon[i]), net.stop_names[i]


def nearby(net: Network, lat: float, lon: float) -> dict[int, float]:
    d = hav(lat, lon, net.lat, net.lon)
    idx = np.argsort(d, kind="stable")[:MAX_ACCESS_STOPS]
    return {int(i): float(d[i] * DETOUR / WALK_SPEED) for i in idx if d[i] <= MAX_ACCESS_M}


def _unroll(parent) -> list:
    if parent[0] == "access":
        return [("walk", parent[1])]
    if parent[0] == "foot":
        return _unroll(parent[3]) + [("walk", parent[2])]
    return _unroll(parent[4]) + [("ride", parent[1], parent[2], parent[3])]


def csa(net: Network, access: dict, egress: dict, t0: int, banned=frozenset(), window: int = 3 * 3600):
    lo = int(np.searchsorted(net.dep_time, t0))
    hi = int(np.searchsorted(net.dep_time, t0 + window))
    sl = slice(lo, hi)
    trip = net.trip[sl]
    keep = np.ones(len(trip), dtype=bool)
    if banned:
        ban_ix = [net.routes.index(r) for r in banned if r in net.routes]
        keep = ~np.isin(net.trip_route[trip], ban_ix)
    dep_s, arr_s = net.dep_stop[sl][keep].tolist(), net.arr_stop[sl][keep].tolist()
    dep_t, arr_t, trip = net.dep_time[sl][keep].tolist(), net.arr_time[sl][keep].tolist(), trip[keep].tolist()
    ea, parent, boarded = {}, {}, {}
    for s, w in access.items():
        ea[s], parent[s] = t0 + w, ("access", w)
    best, best_end = 1 << 60, None
    for k in range(len(dep_t)):
        dt = dep_t[k]
        if dt >= best:
            break
        tr = trip[k]
        if tr not in boarded:
            e = ea.get(dep_s[k])
            if e is None or e > dt:
                continue
            boarded[tr] = (k, parent[dep_s[k]])
        bk, bpar = boarded[tr]
        a, at = arr_s[k], arr_t[k]
        w = egress.get(a)
        if w is not None and at + w < best:
            best, best_end = at + w, (("ride", tr, bk, k, bpar), w)
        if at + MIN_TRANSFER < ea.get(a, 1 << 60):
            ea[a], parent[a] = at + MIN_TRANSFER, ("ride", tr, bk, k, bpar)
            for b, wsec in net.foot.get(a, ()):
                if at + wsec < ea.get(b, 1 << 60):
                    ea[b], parent[b] = at + wsec, ("foot", a, wsec, parent[a])
    if best_end is None:
        return None
    legs = _unroll(best_end[0]) + [("walk", best_end[1])]
    return {"arrival": best, "legs": legs, "local": (dep_s, arr_s, dep_t, arr_t, trip)}


def _ll(net: Network, stop_id) -> list:
    """[lat, lon] of a stop, rounded for compact JSON."""
    if not hasattr(net, "_ix"):
        net._ix = {s: i for i, s in enumerate(net.stop_ids)}
    i = net._ix.get(stop_id)
    return [round(float(net.lat[i]), 5), round(float(net.lon[i]), 5)] if i is not None else None


def _bus(net: Network, route: str) -> dict:
    b = net.bus.get(route)
    return {"bus": b[0], "seats": b[1], "rated_standing": b[2]} if b else {}


def _leg_crowding(net: Network, route: str, board_stop: str, alight_stop: str, t_board: int, day_type: str) -> dict:
    """Worst stretch on the ride. A stretch uses its hour cell, else the pooled hour-band cell."""
    pb, pa = net.canon_pos.get((route, board_stop), []), net.canon_pos.get((route, alight_stop), [])
    pairs = [(b, a) for b in pb for a in pa if a > b]
    if not pairs:
        return {"level": "unknown", "peak_load": None, "coverage": 0.0, "evidence": None,
                "path": [_ll(net, board_stop), _ll(net, alight_stop)], "seg_levels": ["unknown"]}
    b, a = min(pairs, key=lambda p: p[1] - p[0])
    hits, pooled = [], 0
    for seg in range(b, a):
        t = t_board + net.canon_off.get((route, seg), 0) - net.canon_off.get((route, b), 0)
        h = int(t // 3600) % 24
        hit, grain = net.levels.get((route, seg, h, day_type)), "hour"
        if hit is None:
            hit, grain = net.band_levels.get((route, seg, band_of(h), day_type)), "pooled band"
        if hit:
            hits.append((seg, grain, hit))
            pooled += grain != "hour"
    path = [_ll(net, net.canon_stop(route, p)) for p in range(b, a + 1)]
    by_seg = {h[0]: h[2][0] for h in hits}
    cov = len(hits) / max(a - b, 1)
    if cov < 0.5 or not hits:
        rb = net.route_band.get((route, band_of(int(t_board // 3600) % 24), day_type))
        if rb:   # too few evidenced stretches on this ride: use the route's typical crowding at this time of day
            return {"level": rb[0], "peak_load": min(round(rb[1]), 101), "coverage": round(cov, 2), "basis": "route",
                    "path": path, "seg_levels": [by_seg.get(sg, rb[0]) for sg in range(b, a)],
                    "evidence": {"grain": "route typical", "tickets": int(rb[3]), "stretches_with_data": int(rb[2]),
                                 "load": min(round(rb[1]), 101), **_bus(net, route)}}
        return {"level": "unknown", "peak_load": None, "coverage": round(cov, 2), "evidence": None,
                "path": path, "seg_levels": [by_seg.get(sg, "unknown") for sg in range(b, a)]}
    worst = max((h[2][0] for h in hits), key=lambda l: LEVEL_ORDER[l])
    seg, grain, (lv, ld, lo_, hi_, nt, nd) = max(hits, key=lambda h: h[2][1])
    ld, lo_, hi_ = min(ld, 101), min(lo_, 101), min(hi_, 101)   # display cap: anything above 100 is shown as 100+
    evidence = {"stretch": f"{net.stop_name(net.canon_stop(route, seg))} to {net.stop_name(net.canon_stop(route, seg + 1))}",
                "grain": grain, "tickets": int(nt), "days": int(nd), "load": round(ld), "low": round(lo_), "high": round(hi_),
                "pooled_stretches": pooled, "stretches": a - b, **_bus(net, route)}
    return {"level": worst, "peak_load": round(ld), "coverage": round(cov, 2), "evidence": evidence, "basis": "stretch",
            "path": path, "seg_levels": [by_seg.get(sg, "unknown") for sg in range(b, a)]}


def _describe(net: Network, res: dict, t_request: int, day_type: str, o_label: str, d_label: str) -> dict:
    dep_s, arr_s, dep_t, arr_t, trip = res["local"]
    legs, pen, rides, known_min, ride_min = [], 0.0, [], 0.0, 0.0
    for leg in res["legs"]:
        if leg[0] == "walk":
            legs.append({"type": "walk", "minutes": round(leg[1] / 60, 1)})
            continue
        _, tr, bk, k = leg
        route = net.routes[net.trip_route[tr]]
        bs, as_ = net.stop_ids[dep_s[bk]], net.stop_ids[arr_s[k]]
        cr = _leg_crowding(net, route, bs, as_, dep_t[bk], day_type)
        mins = (arr_t[k] - dep_t[bk]) / 60
        pen += mins * LEVEL_COST[cr["level"]]
        ride_min += mins
        known_min += mins if cr["level"] != "unknown" else 0.0
        legs.append({"type": "ride", "route": route, "board": net.stop_names[dep_s[bk]], "alight": net.stop_names[arr_s[k]],
                     "board_time": clock(dep_t[bk]), "alight_time": clock(arr_t[k]), "minutes": round(mins, 1),
                     "crowding": cr["level"], "peak_load": cr["peak_load"], "evidence_coverage": cr["coverage"],
                     "evidence": cr["evidence"], "basis": cr.get("basis", "stretch"),
                     "path": cr["path"], "seg_levels": cr["seg_levels"]})
        rides.append(route)
    first_board = next(l for l in res["legs"] if l[0] == "ride")
    walk0 = res["legs"][0][1] if res["legs"][0][0] == "walk" else 0
    leave = dep_t[first_board[2]] - walk0
    order = [LEVEL_ORDER[l["crowding"]] for l in legs if l["type"] == "ride" and l["crowding"] != "unknown"]
    return {"from": o_label, "to": d_label, "leave_origin": clock(leave), "arrive": clock(res["arrival"]),
            "minutes_from_request": round((res["arrival"] - t_request) / 60, 1),
            "door_to_door_min": round((res["arrival"] - leave) / 60, 1),
            "transfers": len(rides) - 1, "routes": rides, "legs": legs,
            "worst_crowding": ["seats", "standing", "crowded"][max(order)] if order else "unknown",
            "crowd_penalty_min": round(pen, 1), "day_type": day_type,
            "crowding_known_share": round(known_min / ride_min, 2) if ride_min else 0.0}


def plan(origin, destination, depart: str = "08:30", day_type: str = "weekday", comfort_weight: float = 0.0,
         net: Network | None = None, max_options: int = 5) -> list[dict]:
    """depart is 'HH:MM'. Returns options sorted by score (see module docstring)."""
    if net is None:
        raise ValueError("pass net=load_network(...)")
    h, m = (int(x) for x in depart.split(":")[:2])
    t0 = h * 3600 + m * 60
    olat, olon, olab = resolve_place(net, origin)
    dlat, dlon, dlab = resolve_place(net, destination)
    access, egress = nearby(net, olat, olon), nearby(net, dlat, dlon)
    seen, options = set(), []

    def attempt(t, banned=frozenset()):
        res = csa(net, access, egress, t, banned)
        if not res:
            return None
        opt = _describe(net, res, t0, day_type, olab, dlab)
        key = tuple((l["route"], l["board"], l["alight"]) for l in opt["legs"] if l["type"] == "ride")
        if key not in seen:
            seen.add(key)
            options.append(opt)
        return opt

    ends = {"origin": [round(olat, 5), round(olon, 5)], "dest": [round(dlat, 5), round(dlon, 5)]}
    base = attempt(t0)
    for off in (10, 20, 30):
        attempt(t0 + off * 60)
    for r in (base["routes"] if base else []):
        attempt(t0, frozenset({r}))
        attempt(t0 + 10 * 60, frozenset({r}))
    for o in options:
        o["score"] = round(o["minutes_from_request"] + TRANSFER_PENALTY_MIN * o["transfers"]
                           + 2 * comfort_weight * o["crowd_penalty_min"], 1)
    for o in options:
        o.update(ends)
    return sorted(options, key=lambda o: (o["score"], o["arrive"], o["routes"]))[:max_options]
