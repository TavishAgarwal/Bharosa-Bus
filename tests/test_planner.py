import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner.csa import _leg_crowding, load_network, plan  # noqa: E402

A, B, C, D = (28.600, 77.200), (28.610, 77.200), (28.620, 77.200), (28.630, 77.200)   # ~1.1 km apart


def _net(tmp_path, t2="08:15:00"):
    g = tmp_path / "gtfs"
    g.mkdir()
    (g / "stops.txt").write_text("stop_id,stop_name,stop_lat,stop_lon\n" + "\n".join(
        f"{i},{n},{la},{lo}" for i, n, (la, lo) in (("A", "Alpha", A), ("B", "Beta", B), ("C", "Gamma", C), ("D", "Delta", D))) + "\n")
    (g / "routes.txt").write_text("route_id,route_short_name\nr1,R1\nr2,R2\nr3,R3\n")
    (g / "trips.txt").write_text("route_id,trip_id\nr1,t1\nr2,t2\nr3,t3\n")
    (g / "stop_times.txt").write_text(
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "t1,08:00:00,08:00:00,A,0\nt1,08:05:00,08:05:00,B,1\nt1,08:10:00,08:10:00,C,2\n"
        f"t2,{t2},{t2},C,0\nt2,08:20:00,08:20:00,D,1\n"
        "t3,08:02:00,08:02:00,A,0\nt3,08:30:00,08:30:00,D,1\n")
    return load_network(g)


def test_fastest_uses_transfer_and_alternative_is_direct(tmp_path):
    net = _net(tmp_path)
    opts = plan(A, D, "08:00", "weekday", 0.0, net)
    by_routes = {tuple(o["routes"]): o for o in opts}
    assert ("R1", "R2") in by_routes and ("R3",) in by_routes
    fast = by_routes[("R1", "R2")]
    assert fast["arrive"] == "08:20" and fast["transfers"] == 1
    assert by_routes[("R3",)]["arrive"] == "08:30" and by_routes[("R3",)]["transfers"] == 0


def test_transfer_buffer_is_respected(tmp_path):
    # t1 reaches C at 08:10:00; t2 leaves C at 08:10:30, inside the 60 s change buffer, so it cannot be used.
    net = _net(tmp_path, t2="08:10:30")
    opts = plan(A, D, "08:00", "weekday", 0.0, net)
    assert [o["routes"] for o in opts] == [["R3"]]


def test_crowding_join_and_ranking(tmp_path):
    net = _net(tmp_path)
    for pos, sid in enumerate("ABC"):
        net.canon_pos[("R1", sid)] = [pos]
        net.canon_off[("R1", pos)] = pos * 300
    net.levels[("R1", 0, 8, "weekday")] = ("crowded", 90, 60, 120, 50, 20)
    net.levels[("R1", 1, 8, "weekday")] = ("standing", 50, 40, 60, 30, 20)
    net.canon_pos[("R3", "A")], net.canon_pos[("R3", "D")] = [0], [1]
    net.canon_off[("R3", 0)] = 0
    net.canon_off[("R3", 1)] = 1680
    net.levels[("R3", 0, 8, "weekday")] = ("seats", 10, 5, 15, 40, 20)
    cr = _leg_crowding(net, "R1", "A", "C", 8 * 3600, "weekday")
    assert cr["level"] == "crowded" and cr["peak_load"] == 90 and cr["coverage"] == 1.0
    assert _leg_crowding(net, "R2", "C", "D", 8 * 3600, "weekday")["level"] == "unknown"   # no canonical data
    relaxed = plan(A, D, "08:00", "weekday", 0.0, net)
    comfy = plan(A, D, "08:00", "weekday", 1.0, net)
    assert relaxed[0]["routes"] == ["R1", "R2"]                 # fastest first when comfort is ignored
    assert comfy[0]["routes"] == ["R3"]                         # crowded R1 leg gets penalised at full comfort weight


def test_pooled_band_fallback_and_evidence(tmp_path):
    net = _net(tmp_path)
    for pos, sid in enumerate("ABC"):
        net.canon_pos[("R1", sid)] = [pos]
        net.canon_off[("R1", pos)] = pos * 300
        net.canon_stop_map[("R1", pos)] = sid
    # no hour cell; only the pooled am-peak band (id 1) has evidence for both stretches
    net.band_levels[("R1", 0, 1, "weekday")] = ("standing", 60, 40, 80, 120, 22)
    net.band_levels[("R1", 1, 1, "weekday")] = ("standing", 55, 35, 75, 110, 22)
    cr = _leg_crowding(net, "R1", "A", "C", 8 * 3600, "weekday")
    assert cr["level"] == "standing" and cr["evidence"]["grain"] == "pooled band"
    assert cr["evidence"]["tickets"] == 120 and cr["evidence"]["days"] == 22 and cr["evidence"]["stretch"] == "Alpha to Beta"


def test_route_typical_fallback_when_stretches_lack_data(tmp_path):
    net = _net(tmp_path)
    for pos, sid in enumerate("ABC"):
        net.canon_pos[("R1", sid)] = [pos]
        net.canon_off[("R1", pos)] = pos * 300
        net.canon_stop_map[("R1", pos)] = sid
    net.route_band[("R1", 1, "weekday")] = ("standing", 48.0, 20, 900)       # band 1 = am peak
    cr = _leg_crowding(net, "R1", "A", "C", 8 * 3600, "weekday")
    assert cr["level"] == "standing" and cr["basis"] == "route" and cr["evidence"]["grain"] == "route typical"
    assert _leg_crowding(net, "R1", "A", "C", 13 * 3600, "weekday")["level"] == "unknown"   # midday band has no route data


def test_wait_and_walk_minutes(tmp_path):
    # R1 reaches C at 08:10, R2 leaves C at 08:15: one 5-minute wait at a stop. The direct R3 has no wait.
    net = _net(tmp_path)
    by_routes = {tuple(o["routes"]): o for o in plan(A, D, "08:00", "weekday", 0.0, net)}
    fast, direct = by_routes[("R1", "R2")], by_routes[("R3",)]
    assert fast["wait_min"] == 5.0 and fast["max_wait_min"] == 5.0
    assert direct["wait_min"] == 0.0 and direct["max_wait_min"] == 0.0
    walks = sum(l["minutes"] for l in fast["legs"] if l["type"] == "walk")
    assert abs(fast["walk_min"] - walks) < 0.2
