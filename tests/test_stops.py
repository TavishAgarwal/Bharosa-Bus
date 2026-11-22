import pandas as pd

from bharosa.stops import build_matches, match_tickets, norm_name, norm_route, route_base, aliases

STOPS = pd.DataFrame({
    "stop_id": ["1", "2", "3", "4", "5"],
    "stop_name": ["Ali Village", "Mahamaya Flyover West", "Nehru Place Terminal",
                  "Nehru Place Terminal", "Kashmere Gate ISBT"],
})
ROUTE_STOPS = pd.DataFrame({
    "route_name": ["8UP", "8UP", "8UP", "8UP", "12"],
    "stop_id": ["1", "2", "3", "4", "5"],
})


def test_normalisation():
    assert norm_name("Nehru Pl. Stn (Gate 2)") == "nehru pl station"
    assert norm_name("A & B") == "a and b"
    assert norm_route("8 up") == "8UP"
    assert route_base("717ADOWN") == "717A" and route_base("8UP") == "8"


def test_methods_and_ambiguity():
    pairs = pd.DataFrame({"route": ["8UP", "8up", "8UP", "99", "8UP", "99"],
                          "stop_name": ["Ali Village", "mahamaya flyover west", "Nehru Place Terminal",
                                        "Kashmere Gate ISBT", "Totally Unknown", "Kashmere Gate Isbt "]})
    m = build_matches(pairs, STOPS, ROUTE_STOPS)
    by = {(r.route, r.stop_name): r for r in m.itertuples()}
    assert by[("8UP", "Ali Village")].method == "exact_route"
    assert by[("8up", "mahamaya flyover west")].method == "exact_route"
    assert by[("8UP", "Nehru Place Terminal")].stop_ids == ["3", "4"]       # two directions kept
    assert by[("99", "Kashmere Gate ISBT")].method == "exact_global"        # route not in GTFS
    assert not by[("99", "Kashmere Gate ISBT")].route_in_gtfs
    assert by[("8UP", "Totally Unknown")].method == "unmatched"


def test_fuzzy_route_and_bridge():
    pairs = pd.DataFrame({"route": ["8UP", "8UP"], "stop_name": ["Mahamaya Flyovr Wst", "Weird Name"]})
    m = build_matches(pairs, STOPS, ROUTE_STOPS, bridge={norm_name("Weird Name"): "1"})
    assert m.loc[0, "method"] == "fuzzy_route" and m.loc[0, "stop_ids"] == ["2"]
    assert m.loc[1, "method"] == "bridge" and m.loc[1, "stop_ids"] == ["1"]


def test_end_to_end(tmp_path):
    import duckdb
    g = tmp_path / "gtfs"
    g.mkdir()
    (g / "stops.txt").write_text("stop_id,stop_name\n" + "\n".join(f"{a},{b}" for a, b in zip(STOPS.stop_id, STOPS.stop_name)) + "\n")
    (g / "routes.txt").write_text("route_id,route_short_name\nR1,8UP\nR2,12\n")
    (g / "trips.txt").write_text("route_id,trip_id\nR1,T1\nR2,T2\n")
    (g / "stop_times.txt").write_text("trip_id,stop_id,stop_sequence\nT1,1,1\nT1,2,2\nT1,3,3\nT2,5,1\n")
    tk = pd.DataFrame({"route": ["8UP", "8UP", "12"], "start_stop_name": ["Ali Village", "Ali Village", "Kashmere Gate ISBT"],
                       "end_stop_name": ["Mahamaya Flyover West", "Nowhere", "Nowhere"]})
    p = tmp_path / "tickets.parquet"
    duckdb.connect().register("tk", tk).execute(f"COPY tk TO '{p}' (FORMAT PARQUET)")
    rep = match_tickets(p, g, tmp_path / "none.csv", tmp_path, tmp_path / "out")
    assert rep["tickets"] == 3
    assert abs(rep["ticket_match_rate_both_ends"] - 1 / 3) < 1e-3
    assert rep["meets_target"] is False
    un = pd.read_csv(tmp_path / "out" / "stops_unmatched.csv")
    assert un.loc[0, "stop_name"] == "Nowhere" and un.loc[0, "tickets"] == 2


def test_direction_suffix_falls_back_to_base_route():
    stops = pd.DataFrame({"stop_id": ["1", "2"], "stop_name": ["Alpha Stop", "Beta Stop"]})
    rs = pd.DataFrame({"route_name": ["717A", "717A"], "stop_id": ["1", "2"]})
    pairs = pd.DataFrame({"route": ["717AUP", "717ADOWN"], "stop_name": ["Alpha Stp", "Beta Stop"]})
    m = build_matches(pairs, stops, rs)
    assert m["route_in_gtfs"].all()
    assert list(m["method"]) == ["fuzzy_route", "exact_route"]


def test_compound_gtfs_names_match_on_any_part():
    assert "badarpur" in aliases("Badarpur /Jaitpur Crossing") and "jaitpur crossing" in aliases("Badarpur /Jaitpur Crossing")
    stops = pd.DataFrame({"stop_id": ["1"], "stop_name": ["GTB Nagar / GTB Nagar Metro Station"]})
    rs = pd.DataFrame({"route_name": ["5UP"], "stop_id": ["1"]})
    m = build_matches(pd.DataFrame({"route": ["5UP"], "stop_name": ["GTB Nagar Metro Station"]}), stops, rs)
    assert m.loc[0, "method"] == "exact_route" and m.loc[0, "gtfs_stop_name"] == "GTB Nagar / GTB Nagar Metro Station"
