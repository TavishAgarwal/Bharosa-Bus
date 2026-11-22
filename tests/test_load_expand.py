import json

import duckdb
import numpy as np
import pandas as pd

from bharosa.expand import build_cells
from bharosa.load import load_stretches


def _gtfs(tmp_path):
    g = tmp_path / "gtfs"
    g.mkdir()
    (g / "stops.txt").write_text("stop_id,stop_name\nA,Alpha\nB,Beta\nC,Gamma\nD,Delta\n")
    (g / "routes.txt").write_text("route_id,route_short_name\nR1,1UP\n")
    (g / "trips.txt").write_text("route_id,trip_id\nR1,T_short\nR1,T_full1\nR1,T_full2\n")
    (g / "stop_times.txt").write_text(
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T_short,08:00:00,08:00:00,A,0\nT_short,08:10:00,08:10:00,B,1\n"
        "T_full1,08:00:00,08:00:00,A,0\nT_full1,08:10:00,08:10:00,B,1\nT_full1,08:20:00,08:20:00,C,2\nT_full1,08:30:00,08:30:00,D,3\n"
        "T_full2,09:00:00,09:00:00,A,0\nT_full2,09:10:00,09:10:00,B,1\nT_full2,09:20:00,09:20:00,C,2\nT_full2,09:30:00,09:30:00,D,3\n")
    return g


def _tickets(tmp_path):
    ts = lambda d, hms: pd.Timestamp(f"2026-10-{d:02d} {hms}")
    rows = []
    # weekday (Mon 5 Oct, Tue 6 Oct): 2 pax A->C at 08:50, 1 pax B->D at 08:55
    for d in (5, 6):
        rows += [dict(route="1UP", ts_ist=ts(d, "08:50:00"), date=ts(d, "00:00:00").date(), day_type="weekday",
                      passenger_count=2, start_stop_ids=["A"], end_stop_ids=["C"], matched=True),
                 dict(route="1UP", ts_ist=ts(d, "08:55:00"), date=ts(d, "00:00:00").date(), day_type="weekday",
                      passenger_count=1, start_stop_ids=["B"], end_stop_ids=["D"], matched=True)]
    rows += [dict(route="1UP", ts_ist=ts(5, "08:50:00"), date=ts(5, "00:00:00").date(), day_type="weekday",
                  passenger_count=1, start_stop_ids=["D"], end_stop_ids=["A"], matched=True),       # wrong order -> dropped
             dict(route="1UP", ts_ist=ts(5, "08:50:00"), date=ts(5, "00:00:00").date(), day_type="weekday",
                  passenger_count=1, start_stop_ids=["Z"], end_stop_ids=["A"], matched=True),       # stop not on route
             dict(route="9X", ts_ist=ts(5, "08:50:00"), date=ts(5, "00:00:00").date(), day_type="weekday",
                  passenger_count=1, start_stop_ids=["A"], end_stop_ids=["B"], matched=True),       # route not in GTFS
             dict(route="1UP", ts_ist=ts(5, "08:50:00"), date=ts(5, "00:00:00").date(), day_type="weekday",
                  passenger_count=1, start_stop_ids=None, end_stop_ids=None, matched=False)]
    # one weekend day with no tickets still needs to exist in the day list
    rows += [dict(route="9X", ts_ist=ts(4, "10:00:00"), date=ts(4, "00:00:00").date(), day_type="weekend",
                  passenger_count=1, start_stop_ids=None, end_stop_ids=None, matched=False)]
    df = pd.DataFrame(rows)
    p = tmp_path / "tickets_matched.parquet"
    c = duckdb.connect(); c.register("df", df); c.execute(f"COPY df TO '{p}' (FORMAT PARQUET)")
    return p, df


def test_load_and_expand(tmp_path):
    g = _gtfs(tmp_path)
    p, df = _tickets(tmp_path)
    interim = tmp_path / "interim"; interim.mkdir()
    # expand reads the plain tickets table for the day list
    d_ = df[["day_type", "date"]].assign(route="1UP", hour=8, vehicle_number=None)
    c = duckdb.connect(); c.register("d", d_); c.execute(f"COPY d TO '{interim / 'tickets.parquet'}' (FORMAT PARQUET)")

    rep = load_stretches(p, g, interim)
    assert rep["tickets_matched_names"] == 7
    assert rep["valid_pair"] == 4                      # 2 days x 2 tickets; reversed, off-route, unknown route dropped
    canon = duckdb.connect().execute(f"select pos, stop_id, off_sec from read_parquet('{interim / 'canonical_routes.parquet'}') order by pos").fetchall()
    assert [r[1] for r in canon] == ["A", "B", "C", "D"]      # the longest trip is canonical, not T_short
    assert [r[2] for r in canon] == [0, 600, 1200, 1800]

    daily = duckdb.connect().execute(f"select seg, hour, date, passengers from read_parquet('{interim / 'stretch_daily.parquet'}') order by date, seg").fetchall()
    # A->C at 08:50 covers seg0 (08:50, hour 8) and seg1 (+10 min = 09:00, hour 9); B->D at 08:55 covers seg1 (hour 8) and seg2 (hour 9)
    day = [(s, h, int(pax)) for s, h, d, pax in daily if str(d) == "2026-10-05"]
    assert sorted(day) == [(0, 8, 2), (1, 8, 1), (1, 9, 2), (2, 9, 1)]

    out = tmp_path / "out"
    r = build_cells(interim, out, sample_rate=(0.05, 0.05), uplift=(1.0, 1.0), B=200, observed=False)
    cells = pd.read_parquet(out / "crowding_cells.parquet") if False else duckdb.connect().execute(
        f"select * from read_parquet('{out / 'crowding_cells.parquet'}')").df()
    row = cells[(cells.seg == 0) & (cells.hour == 8) & (cells.day_type == "weekday")].iloc[0]
    # trips leaving stop A in hour 8: T_short and T_full1 = 2. raw load = 2 pax / 2 trips = 1 on both weekdays
    assert row.n_days == 2 and abs(row.raw_load - 1.0) < 1e-6
    assert abs(row.load - 1.0 / 0.05) < 1e-4            # scale-up by 1/rate
    assert row.raw_lo <= row.raw_load <= row.raw_hi
    assert row.from_stop == "Alpha" and row.to_stop == "Beta"
    assert (cells.n_tickets > 0).all() and cells[["load_lo", "load", "load_hi"]].notna().all().all()


def test_observed_vehicles_raise_the_trip_floor(tmp_path):
    import datetime as dt
    days = [dt.date(2026, 10, d) for d in (5, 6, 7, 8, 9)]
    con = duckdb.connect()
    # route A: schedule says 2 trips at 08:00, but 5 distinct vehicles sold tickets every day in that hour
    tix = pd.DataFrame([dict(day_type="weekday", date=d, route="A", hour=8, vehicle_number=f"DL1V{i}") for d in days for i in range(5)]
                       + [dict(day_type="weekday", date=d, route="A", hour=9, vehicle_number=None) for d in days])
    sd = pd.DataFrame([dict(route="A", seg=0, hour=8, date=d, day_type="weekday", passengers=100, tickets=40) for d in days]
                      + [dict(route="A", seg=0, hour=9, date=d, day_type="weekday", passengers=10, tickets=4) for d in days])
    sc = pd.DataFrame([dict(route="A", pos=0, hour=8, trips=2), dict(route="A", pos=0, hour=9, trips=2)])
    cr = pd.DataFrame([dict(route="A", pos=0, stop_id="S0", stop_name="Zero"), dict(route="A", pos=1, stop_id="S1", stop_name="One")])
    interim = tmp_path / "i"; interim.mkdir()
    for name, df in (("tickets", tix), ("stretch_daily", sd), ("sched_trips", sc), ("canonical_routes", cr)):
        con.register("df", df)
        con.execute(f"COPY df TO '{interim / (name + '.parquet')}' (FORMAT PARQUET)")
    kw = dict(sample_rate=(0.05, 0.05), uplift=(1.0, 1.0), B=50)
    sched_only = build_cells(interim, tmp_path / "o1", observed=False, **kw)
    got = duckdb.connect().execute(f"select hour, raw_load, trips from read_parquet('{tmp_path / 'o1' / 'crowding_cells.parquet'}') order by hour").fetchall()
    assert got[0][1] == 50.0 and got[0][2] == 2                 # 100 passengers / 2 scheduled trips
    build_cells(interim, tmp_path / "o2", observed=True, **kw)
    got = duckdb.connect().execute(f"select hour, raw_load, trips from read_parquet('{tmp_path / 'o2' / 'crowding_cells.parquet'}') order by hour").fetchall()
    assert got[0][1] == 20.0 and got[0][2] == 5                 # floor of 5 observed vehicles: 100 / 5
    assert got[1][1] == 5.0 and got[1][2] == 2                  # hour 9 has no vehicle ids, schedule stays
