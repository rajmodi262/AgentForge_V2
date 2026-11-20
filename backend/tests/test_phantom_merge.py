"""Merge review (no network, no LLM): look-alike pairs, human decisions, and the resolver honouring them."""

from datetime import datetime, timezone

from app.phantom import merge as M
from app.phantom.resolve import resolve

A, B, C, D = (f"0000000{i}-0000-4000-8000-000000000000" for i in range(1, 5))


def _p(anchor, name, dev, city, mw, country="India"):
    return {"anchor": anchor, "name": name, "developer": dev, "country": country, "city": city, "state": None, "capacity_mw": mw}


def test_lookalikes_are_found_and_neighbours_are_not():
    same = M.similarity(_p(A, "Meta's New AI Data Center", "Meta", "Jamnagar", 168), _p(B, "Meta's AI Data Centre", "Meta", "Jamnagar", 168))
    assert same and same["score"] >= 0.8 and same["kind"] == "same_developer"
    assert M.similarity(_p(A, "Nxtra Noida III", "Nxtra", "Noida", None), _p(B, "Nxtra Data Noida II", "Nxtra", "Noida", None)) is None   # numbered sites
    assert M.similarity(_p(A, "CtrlS Mumbai DC1", "CtrlS", "Mumbai", 30), _p(B, "CtrlS Chennai campus", "CtrlS", "Chennai", 30)) is None    # other city
    assert M.similarity(_p(A, "Yotta campus", "Yotta", "Noida", 30), _p(B, "Yotta campus", "Yotta", "Noida", 250)) is None                 # other size
    assert M.similarity(_p(A, "AirTrunk JHB1", "AirTrunk", "Johor", 150, "Malaysia"), _p(B, "AirTrunk JHB2", "AirTrunk", "Johor", 150, "Malaysia")) is None
    assert M._ordinals("Noida II 40 MW campus") == {2} and M._ordinals("CtrlS DC3 Hyderabad") == {3} and M._ordinals("Vizag campus") == set()


def test_different_developers_need_the_same_place_and_size():
    jv = M.similarity(_p(A, "Reliance Jio Vizag AI campus", "Reliance Jio", "Visakhapatnam", 1000), _p(B, "Digital Connexion Vizag cluster", "Digital Connexion", "Visakhapatnam", 1000))
    assert jv and jv["kind"] == "cross_developer" and any("joint venture" in r for r in jv["reasons"])
    assert M.similarity(_p(A, "Yotta Noida campus", "Yotta", "Noida", 100), _p(B, "Sify Noida campus", "Sify", "Noida", 300)) is None


def test_candidates_skip_decided_pairs_and_rank_the_most_alike_first():
    ps = [_p(A, "Meta's New AI Data Center", "Meta", "Jamnagar", 168), _p(B, "Meta's AI Data Centre", "Meta", "Jamnagar", 168),
          _p(C, "CtrlS Mumbai campus", "CtrlS", "Mumbai", None), _p(D, "CtrlS Mumbai Datacenter campus", "CtrlS", "Mumbai", None)]
    got = M.candidates(ps, {})
    assert [(c["a"]["anchor"], c["b"]["anchor"]) for c in got][0] == (A, B) and got[0]["double_counted_mw"] == 168
    assert all({c["a"]["anchor"], c["b"]["anchor"]} != {A, B} for c in M.candidates(ps, {M.pair_key(B, A): M.DISTINCT}))


def test_the_resolver_applies_a_human_merge_and_only_that():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m = lambda i, name, dev, city, mw: {"id": i, "article_id": f"art{i}", "text_kind": "full", "published": t,  # noqa: E731
                                        "data": {"project_name": name, "developer": dev, "country": "India", "city": city, "capacity_mw": mw, "events": []}}
    ms = [m(A, "Reliance Jio Vizag AI campus", "Reliance Jio", "Visakhapatnam", 1000), m(B, "Digital Connexion Vizag cluster", "Digital Connexion", "Visakhapatnam", 1000),
          m(C, "Sify Vizag campus", "Sify", "Visakhapatnam", 500)]
    assert len(resolve([dict(x) for x in ms])) == 3
    merged = resolve([dict(x) for x in ms], {M.pair_key(A, B): M.MERGE})
    assert len(merged) == 2
    big = next(c for c in merged if len(c["mention_ids"]) == 2)
    assert big["anchor"] == A and big["capacity_mw"] == 1000 and len(big["article_ids"]) == 2     # counted once, sources pooled
    assert len(resolve([dict(x) for x in ms], {M.pair_key(A, B): M.DISTINCT})) == 3               # "distinct" never merges
    assert len(resolve([dict(x) for x in ms], {M.pair_key(A, D): M.MERGE})) == 3                  # a decision about a vanished project is ignored


def test_decisions_are_stored_validated_and_changeable(db_session):
    assert M.decide(db_session, B, A, "merge", "analyst@example.com") == {"a": A, "b": B, "decision": "merge"}
    assert M.load_decisions(db_session) == {(A, B): "merge"}
    M.decide(db_session, A, B, "distinct")
    assert M.load_decisions(db_session) == {(A, B): "distinct"}                                   # one row per pair, latest answer wins
    for bad in ((A, A, "merge"), (A, B, "maybe"), ("not-an-id", B, "merge")):
        try:
            M.decide(db_session, *bad)
            raise AssertionError("should have been rejected")
        except ValueError:
            pass
