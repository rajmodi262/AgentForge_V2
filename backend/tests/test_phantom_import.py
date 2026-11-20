"""Import mode (no network, no LLM): parse any project list, match it to tracked projects, never guess."""

import pytest

from app.phantom import importer as I


def _t(i, name, dev, city, mw, score=0.6, country="India"):
    return {"id": f"p{i}", "anchor": f"a{i}", "name": name, "developer": dev, "country": country, "city": city, "state": None,
            "capacity_mw": mw, "stage": 1, "reality_score": score, "n_sources": 2, "grid_position": "NO_EVIDENCE", "weakest_assumption": "x"}


def test_parse_accepts_common_headers_and_rejects_a_list_without_names():
    rows = I.parse("﻿Project,Operator,Location,MW\nKUL2,Vantage Data Centers,Cyberjaya,\"1,000\"\n,,,\nJHB1,AirTrunk,Johor,abc\n")
    assert rows == [{"row": 2, "name": "KUL2", "developer": "Vantage Data Centers", "city": "Cyberjaya", "country": None, "capacity_mw": 1000.0},
                    {"row": 4, "name": "JHB1", "developer": "AirTrunk", "city": "Johor", "country": None, "capacity_mw": None}]
    with pytest.raises(ValueError):
        I.parse("developer,city\nYotta,Noida\n")


def test_match_finds_the_tracked_project_and_admits_what_it_does_not_know():
    tracked = [_t(1, "Vantage Data Centers KUL2", "Vantage Data Centers", "Cyberjaya", 256, 0.9, "Malaysia"),
               _t(2, "Sify Navi Mumbai campus", "Sify", "Navi Mumbai", 19, 0.4)]
    rows = I.parse("name,developer,city,mw\nKUL2 campus,Vantage,Cyberjaya,256\n"
                   "Navi Mumbai data centre,Google,Navi Mumbai,19\n"            # same place and size, other developer: not a match
                   "Unknown campus,Nobody,Nagpur,50\n")
    r = I.match(rows, tracked)
    a, b, c = r["rows"]
    assert a["matched"] and a["project_id"] == "p1" and a["reality_score"] == 0.9 and a["confidence"] >= 0.8
    assert not b["matched"] and not c["matched"]
    assert r["summary"] == {"rows": 3, "matched": 1, "unmatched": 2, "announced_mw": 325.0, "matched_mw": 256.0, "reality_mw": 230.4}


def test_investigator_plans_the_search_its_weakest_assumption_needs_and_widens_after_a_miss():
    from app.phantom.investigate import plan
    w = "No verified evidence that power is secured (PPA, grid connection or substation) (would lift the score by 30 pts)"
    first = plan(w, "YTL", "Kulai", "YTL Kulai campus", [], None)
    assert first["angle"] == "power" and first["query"] == "YTL Kulai data centre power supply agreement"
    second = plan(w, "YTL", "Kulai", "YTL Kulai campus", [first["query"]], 0)        # found nothing: drop the place
    assert second["query"] == "YTL data centre power supply agreement" and "widening" in second["why"]
    assert plan("No verified evidence that construction has started", "Sify", "", "x", [], None)["angle"] == "BUILDING"
    tried = []
    while (n := plan(w, "YTL", "Kulai", "YTL Kulai campus", tried, 1)):
        tried.append(n["query"])
    assert len(tried) == len(set(tried)) == 4                                         # finite, never repeats itself


def test_a_facility_code_wins_and_an_unknown_country_is_not_called_out_of_scope():
    tracked = [_t(1, "AirTrunk Big Watt PowerHouse", "AirTrunk", "Johor", 150, 0.2, "Malaysia"),
               _t(2, "AirTrunk JHB1", "AirTrunk", "Johor Bahru", 150, 0.9, "Malaysia")]
    a, b = I.match(I.parse("name,developer,city,country,mw\nJHB1,AirTrunk,Johor,Malaysia,150\nMega campus,Someone,Nagpur,,500\n"), tracked)["rows"]
    assert a["matched"] and a["project_id"] == "p2"
    assert not b["matched"] and b["in_scope"] is None
