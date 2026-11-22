"""Integrity checks on the exported web data, plus static checks on the pages."""
import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
pytestmark = pytest.mark.skipif(not (WEB / "data" / "demo_journeys.json").exists(), reason="run make export first")
CROWD = {"seats", "standing", "crowded", "unknown"}


def _load(name):
    return json.loads((WEB / "data" / name).read_text())


def test_journeys_have_options_and_valid_fields():
    qs = _load("demo_journeys.json")["queries"]
    assert qs
    for q in qs:
        assert q["options"], f"empty query {q['from']} -> {q['to']}"
        for o in q["options"]:
            assert o["minutes_from_request"] >= 0 and o["transfers"] >= 0
            assert 0 <= o["crowding_known_share"] <= 1
            for leg in o["legs"]:
                assert leg["type"] in {"walk", "ride"}
                if leg["type"] == "ride":
                    assert leg["crowding"] in CROWD
                    assert leg["minutes"] > 0


def test_no_markup_in_data_strings():
    for name in ("demo_journeys.json", "route_profiles.json", "operator_overload.json"):
        assert "<" not in (WEB / "data" / name).read_text(), name


def test_route_profiles_and_operators_shape():
    r = _load("route_profiles.json")
    assert len(r["bands"]) == 5 and r["routes"]
    for rt in r["routes"].values():
        assert len(rt["stops"]) >= 2
    ops = _load("operator_overload.json")
    assert ops and all(o["crowded_stretches"] <= o["stretches_with_evidence"] for o in ops)


@pytest.mark.parametrize("page", ["index.html", "routes.html", "operators.html"])
def test_pages_static_hygiene(page):
    s = (WEB / page).read_text()
    assert 'lang="en"' in s and "viewport" in s and "<title>" in s
    assert "make export` first" not in s  # misleading on file:// failures
    ids = re.findall(r'\sid="([^"]+)"', s)
    assert len(ids) == len(set(ids))


def test_pages_share_one_stylesheet_that_fits_phones():
    for page in ("index.html", "routes.html", "operators.html"):
        assert 'href="app.css"' in (WEB / page).read_text(), page
    css = (WEB / "app.css").read_text()
    assert "@media (max-width:860px)" in css and "minmax(0,1fr)" in css


def test_every_operator_row_has_a_route_to_draw():
    routes = _load("route_profiles.json")["routes"]
    for name in ("operator_overload.json", "extra_bus.json"):
        assert all(r["route"] in routes for r in _load(name)), name


def test_rides_carry_map_path_matching_stretch_levels():
    for q in _load("demo_journeys.json")["queries"]:
        for o in q["options"]:
            assert len(o["origin"]) == 2 and len(o["dest"]) == 2
            for leg in o["legs"]:
                if leg["type"] == "ride":
                    assert len(leg["path"]) >= 2
                    assert len(leg["seg_levels"]) == len(leg["path"]) - 1
                    assert set(leg["seg_levels"]) <= CROWD
