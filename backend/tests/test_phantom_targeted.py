"""Targeted scouts (query building) and the calibration backtest (no network, no LLM)."""

from datetime import datetime, timezone

from app.phantom.backtest import run, section
from app.phantom.targeted import _q, official_queries


def test_queries_are_short_and_deduplicated():
    assert _q("CapitaLand India", "CapitaLand DC Navi Mumbai Tower 2 (Airoli)", "Navi Mumbai") == "CapitaLand India DC Navi Mumbai Tower 2 data centre"
    assert all("site:" in q for qs in official_queries().values() for q in qs)


def test_filings_queries_search_each_project_on_its_countrys_filing_sites():
    from app.phantom.targeted import filings_queries
    qs = filings_queries([{"name": "YTL Kulai campus", "developer": "YTL", "country": "Malaysia"},
                          {"name": "Yotta D1", "developer": "Yotta", "country": "India"},
                          {"name": "Somewhere", "developer": "X", "country": "Atlantis"}])
    assert set(qs) == {"malaysia", "india"}
    assert qs["malaysia"] == ["YTL Kulai campus data centre (site:bursamalaysia.com OR site:mida.gov.my OR site:st.gov.my OR site:tnb.com.my)"]
    assert "site:bseindia.com" in qs["india"][0]


def test_filing_dates_err_late_and_never_in_the_future():
    from app.phantom.targeted import date_in_text
    now = datetime(2026, 11, 21, tzinfo=timezone.utc)
    d = date_in_text("Board meeting held on 12th March 2023. Outcome filed 14/03/2023.", now)
    assert d == datetime(2023, 3, 14, tzinfo=timezone.utc)                       # the latest stated date, numeric read day-first
    assert date_in_text("Dated March 5, 2022; to be commissioned by 31 Dec 2030", now) == datetime(2022, 3, 5, tzinfo=timezone.utc)
    assert date_in_text("no date here", now) is None


def _m(i, name, dev, published, events):
    return {"id": i, "article_id": f"a{i}", "text_kind": "full", "published": published,
            "data": {"project_name": name, "developer": dev, "country": "Malaysia", "city": "Kulai", "capacity_mw": 100, "events": events}}


def test_backtest_scores_with_past_evidence_only_and_reads_the_outcome_after():
    old, new = datetime(2023, 3, 1, tzinfo=timezone.utc), datetime(2025, 9, 1, tzinfo=timezone.utc)
    ms = [
        _m(1, "YTL Kulai campus", "YTL", old, [{"layer": "ANNOUNCED", "quote": "YTL announced", "published": old}]),
        _m(2, "YTL Kulai campus", "YTL", new, [{"layer": "BUILDING", "quote": "Construction began on the 100 MW Kulai campus", "published": new}]),
        _m(3, "AirTrunk JHB9", "AirTrunk", old, [{"layer": "ANNOUNCED", "quote": "AirTrunk plans JHB9", "published": old}]),
    ]
    res = run(ms)
    rows = {r["name"]: r for r in res["rows"]}
    ytl = next(r for n, r in rows.items() if "YTL" in n)
    assert ytl["stage_then"] == "ANNOUNCED" and ytl["stage_now"] == "BUILDING" and ytl["progressed"]
    assert ytl["reality_score"] < 0.5                       # scored as of the cutoff, before construction was known
    assert not next(r for n, r in rows.items() if "JHB9" in n)["progressed"]
    assert res["all"]["n"] == 2 and "Brier" in "\n".join(section(res))


def _case(project, stage, progressed, adj=0.0, cutoff="2023-06-30"):
    from app.phantom import score as S
    i = S.LAYERS.index(stage)
    return {"name": project, "project": project, "cutoff": cutoff, "stage_then": stage, "progressed": progressed, "adj": adj,
            "cancelled_then": False, "prior_only": S.PRIOR_ASSUMED[i], "reality_score": round(S.sigmoid(S.logit(S.PRIOR_ASSUMED[i]) + adj), 3)}


def test_fitted_priors_follow_the_outcomes_but_thin_layers_stay_near_the_assumption():
    from app.phantom import backtest as B, score as S
    rows = [_case(f"a{i}", "ANNOUNCED", i < 10) for i in range(100)] + [_case("p1", "POWER", False), _case("b1", "BUILDING", True)]
    f = B.fit(rows)
    assert 0.10 < f[0] < 0.14                      # 10 of 100 progressed: the data wins over the stated 25%
    assert f[3] > 0.65                             # one POWER case cannot move a prior backed by 20 pseudo-cases
    assert all(f[i] <= f[i + 1] for i in range(5))  # never falls as the ladder rises
    rescored = B.rescore(rows, f)
    assert rescored[0]["reality_score"] == f[0] and rescored[0]["reality_score"] < rows[0]["reality_score"]
    assert B.rescore([{**rows[0], "cancelled_then": True}], f)[0]["reality_score"] == 0.03
    assert S.PRIOR == S.PRIOR_ASSUMED              # fitting never changes the live scorer by itself


def test_cross_validation_never_scores_a_project_with_its_own_outcome():
    from app.phantom import backtest as B
    rows = [_case(f"a{i}", "ANNOUNCED", i % 5 == 0, cutoff=c) for i in range(40) for c in ("2022-06-30", "2023-06-30")]
    cv = B.cross_validate(rows, folds=4)
    assert len(cv) == len(rows)
    by_project = {}
    for r in cv:
        by_project.setdefault(r["project"], set()).add(r["reality_score"])
    assert all(len(v) == 1 for v in by_project.values())      # both cutoffs of a project sit in the same fold


def test_auc_brier_and_the_baselines():
    from app.phantom import backtest as B
    assert B.auc([(0.9, True), (0.1, False)]) == 1.0 and B.auc([(0.1, True), (0.9, False)]) == 0.0
    assert B.auc([(0.5, True), (0.5, False)]) == 0.5 and B.auc([(0.5, True)]) is None
    rows = [_case(f"a{i}", "ANNOUNCED", i < 2) for i in range(10)] + [_case(f"b{i}", "BUILDING", True) for i in range(5)]
    e = B.evaluate(rows, ci=False)
    assert e["n"] == 15 and e["projects"] == 15 and e["auc"] > 0.8
    assert e["brier"] < e["baselines"]["flat_35"] and e["brier"] < e["baselines"]["base_rate"]
    assert e["phantom_calls"] == {"n": 10, "right": 8, "accuracy": 0.8} and e["likely_calls"]["accuracy"] == 1.0


def test_scorer_loads_a_calibration_file_and_ignores_a_broken_one(tmp_path):
    import json
    from app.phantom import score as S
    good = tmp_path / "c.json"
    good.write_text(json.dumps({"priors": {str(i): v for i, v in enumerate([0.16, 0.4, 0.5, 0.6, 0.92, 0.99])}}), encoding="utf-8")
    assert S.load_calibration(good)["priors"][0] == 0.16
    bad = tmp_path / "bad.json"
    bad.write_text('{"priors": {"0": 0.2}}', encoding="utf-8")
    assert S.load_calibration(bad) is None and S.load_calibration(tmp_path / "missing.json") is None
    p = {"events": [{"layer": "ANNOUNCED"}], "article_ids": ["a", "b"]}
    assert S.reality(p, priors={**S.PRIOR_ASSUMED, 0: 0.16})[0] == 0.16 and S.reality(p)[0] == 0.25
