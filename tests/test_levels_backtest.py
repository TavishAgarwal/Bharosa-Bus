import datetime as dt

import duckdb
import numpy as np
import pandas as pd

from bharosa.backtest import run_backtest, spearman
from bharosa.levels import ABSTAIN, assign_levels, level_of


def test_level_of_boundaries():
    got = level_of([0, 35, 35.1, 65, 65.1], seats=35, standing=30)
    assert list(got) == ["seats", "seats", "standing", "standing", "crowded"]


def test_assign_levels_abstains_and_flags_confidence():
    cells = pd.DataFrame({
        "load": [10.0, 50.0, 90.0, 20.0, 20.0], "load_lo": [5.0, 30.0, 80.0, 15.0, 15.0],
        "load_hi": [20.0, 70.0, 120.0, 25.0, 25.0], "n_tickets": [100, 100, 100, 5, 100],
        "suspect_schedule": [False, False, False, False, True], "n_pass": [1, 1, 1, 1, 1]})
    out = assign_levels(cells, "12m", min_tickets=30)
    assert list(out["level"]) == ["seats", "standing", "crowded", ABSTAIN, ABSTAIN]
    assert list(out["abstain_reason"]) == ["", "", "", "few_tickets", "schedule_suspect"]
    assert list(out["confident"]) == [True, False, True, False, False]   # row 1 spans seats..crowded


def test_spearman_monotone():
    a = np.arange(10.0)
    assert abs(spearman(a, a ** 3) - 1.0) < 1e-9 and abs(spearman(a, -a) + 1.0) < 1e-9


def test_backtest_constant_cell_is_perfect_and_beats_baseline(tmp_path):
    days = [dt.date(2026, 10, d) for d in (5, 6, 7, 8, 9)]            # five weekdays
    con = duckdb.connect()
    tix = pd.DataFrame({"day_type": "weekday", "date": days, "route": "A", "hour": 8, "vehicle_number": None})
    sd = pd.DataFrame([dict(route=r, seg=0, hour=8, date=d, day_type="weekday", passengers=p, tickets=p)
                       for r, p in (("A", 10), ("B", 30)) for d in days])      # loads 5 and 15 per trip
    sc = pd.DataFrame([dict(route="A", pos=0, hour=8, trips=2), dict(route="B", pos=0, hour=8, trips=2)])
    cr = pd.DataFrame([dict(route="A", pos=0), dict(route="B", pos=0)])
    for name, df in (("tickets", tix), ("stretch_daily", sd), ("sched_trips", sc), ("canonical_routes", cr)):
        con.register("df", df)
        con.execute(f"COPY df TO '{tmp_path / (name + '.parquet')}' (FORMAT PARQUET)")
    rep = run_backtest(tmp_path, tmp_path / "out", min_tickets=1, observed=False)
    s = rep["summary_by_day_type"]["weekday"]
    assert s["wape"] == 0.0                       # constant cells are predicted exactly
    assert abs(s["baseline_wape"] - 0.5) < 1e-6   # hour mean (10) misses 5 and 15 by 5 each: 10/20
    assert rep["days_scored"] == 5
