import numpy as np
import pandas as pd

from bharosa.backtest import confusion, level_scores
from bharosa.fares import slab_of_fare, slab_of_km
from bharosa.levels import assign_levels


def test_fare_slabs_match_discounted_delhi_fares():
    ac = np.array([False, False, False, True, True, True, True, False])
    fare = np.array([4.5, 9.0, 13.5, 9.0, 13.5, 18.0, 22.5, 7.0])
    assert list(slab_of_fare(fare, ac)) == [0, 1, 2, 0, 1, 2, 3, -1]      # 7.0 is not a slab fare
    km = np.array([3.0, 6.0, 12.0, 3.0, 6.0, 9.0, 15.0, 1.0])
    assert list(slab_of_km(km, ac)[:7]) == [0, 1, 2, 0, 1, 2, 3]


def test_level_scores_kappa_and_always_seats_baseline():
    act = np.array(["seats"] * 8 + ["crowded"] * 2)
    same = level_scores(confusion(act, act))
    assert same["level_exact"] == 1.0 and same["kappa"] == 1.0 and same["always_seats_exact"] == 0.8
    lazy = level_scores(confusion(act, np.array(["seats"] * 10)))   # always-seats predictor: 80% right, no skill
    assert lazy["level_exact"] == 0.8 and lazy["kappa"] == 0.0 and lazy["busy_recall"] == 0.0


def test_per_route_capacity_used_when_cells_carry_it():
    cells = pd.DataFrame({"load": [30.0, 30.0], "load_lo": [30.0, 30.0], "load_hi": [30.0, 30.0],
                          "n_tickets": [100, 100], "suspect_schedule": [False, False], "n_pass": [1, 1],
                          "seats": [23, 39], "standing": [13, 24]})
    out = assign_levels(cells, min_tickets=30)
    assert out["scenario"].iloc[0] == "per_route_inferred"
    assert list(out["level"]) == ["standing", "seats"]          # 30 people: standing on a 9 m bus, seats on 12 m
