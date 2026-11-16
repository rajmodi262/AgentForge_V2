"""Power forensics (no network, no LLM): facts, subject check, grid position, headline numbers."""

from app.phantom import power as P


def _fields(sentence, dev=None):
    return {(f["field"], f["value"]) for f in P.facts_in(sentence, dev)}


def test_a_signed_supply_agreement_is_a_grid_position_with_its_specs():
    s = "Vantage has signed an Electricity Supply Agreement (ESA) with TNB for 500MVA-rated power capacity via a dedicated 275kV high-voltage substation for KUL2."
    got = _fields(s, "Vantage Data Centers")
    assert {("grid", "agreement"), ("utility", "TNB"), ("grid_mva", 500.0), ("grid_kv", 275), ("substation", "dedicated")} <= got


def test_talks_are_not_an_agreement_and_a_passing_reference_proves_nothing():
    assert ("grid", "applied") in _fields("YTL is in talks with TNB over an electricity supply agreement for the campus.")
    assert not any(f == "grid" for f, _ in _fields("The electricity supply agreement underpins the first phase of the planned campus."))
    assert ("grid", "agreement") in _fields("TNB and Bridge Data Centres Ink 400MW Power Deal to Boost Malaysia's Digital Hub Status")


def test_lookalikes_are_not_facts():
    assert not any(f == "equipment" for f, _ in _fields("The facility is carrier-neutral and Uptime Tier III certified."))
    assert not any(f == "substation" for f, _ in _fields("It offers connectivity to multiple subsea cable landing stations."))
    assert not any(f == "financier" for f, _ in _fields("The site is in the Financial District, next to Infosys, ICICI and Wipro."))
    assert not any(f == "utility" for f, _ in _fields("The lease has an option to renew for another 39 years by agreement."))
    assert ("cooling", "evaporative") not in _fields("The hub will use a closed-loop system, thereby avoiding evaporative cooling.")
    assert ("cooling", "waterless / closed loop") in _fields("The hub will use a closed-loop system, thereby avoiding evaporative cooling.")


def test_design_details_density_and_cooling():
    got = _fields("The buildings will support ultra-high density racks of up to 135 kW per rack with direct-to-chip liquid cooling and a PUE of 1.25.")
    assert {("rack_kw", 135), ("cooling", "direct-to-chip"), ("cooling", "liquid cooling"), ("pue", 1.25)} <= got
    assert all(f["planned"] for f in P.facts_in("The campus will feature on-site solar and a battery energy storage system."))


def test_a_developer_is_not_its_own_supplier():
    assert not any(f == "utility" for f, _ in _fields("YTL Power will supply electricity to the campus.", "YTL"))
    assert not any(f == "contractor" for f, _ in _fields("Larsen & Toubro has started construction of the data centre.", "L&T Vyoma"))
    assert ("contractor", "Gamuda") in _fields("Google has appointed Gamuda Berhad to build both facilities.", "Google")


def test_subject_check_drops_other_projects_industry_talk_and_unnamed_companies():
    facts = (P.facts_in("AirTrunk signed a loan for JHB2 led by DBS Bank and HSBC.") +                      # ours
             P.facts_in("SBI Q2 results: net profit rises on loan growth.") +                              # a bank headline, developer not named
             P.facts_in("Developers are increasingly being pushed towards on-site generation with gas turbines.") +   # industry remark
             P.facts_in("The Cyberjaya campus uses immersion cooling.") +                                   # another state
             P.facts_in("The facility will use direct-to-chip liquid cooling."))                           # ours, by reference
    kept = {(f["field"], f["value"]) for f in P.project_facts(facts, "AirTrunk", "JHB2", "Johor Bahru")}
    assert {("financier", "DBS"), ("financier", "HSBC"), ("cooling", "direct-to-chip")} <= kept
    assert not any(v in ("SBI", "gas generation", "immersion") for _, v in kept)


def test_a_sentence_shared_by_two_projects_goes_only_where_it_points():
    shared = P.facts_in("CtrlS has already secured 250 MW of sanctioned power for the Hyderabad campus.")
    a = {"project_name": "CtrlS Chandanvelly campus", "city": "Hyderabad"}
    b = {"project_name": "CtrlS Kolkata data centre", "city": "Kolkata"}
    kept_a, kept_b = P.drop_shared([shared, list(shared)], [a, b])
    assert kept_a and not kept_b
    vague = P.facts_in("The company has secured 250 MW of sanctioned power.")
    assert P.drop_shared([vague, list(vague)], [a, b]) == [[], []]


def test_grid_position_takes_the_strongest_evidence():
    agreement = P.facts_in("PDG has signed an energy supply agreement with TNB for the JH1 campus.")
    assert P.grid_position(5, [], []) == "ENERGIZED"
    assert P.grid_position(1, agreement, []) == "AGREEMENT"
    assert P.grid_position(3, [], [{"layer": "POWER", "quote": "signed a 10-year PPA for solar power"}]) == "POWER_DEAL"
    assert P.grid_position(3, [], [{"layer": "POWER", "quote": "has secured 280 MW of power from TNB"}]) == "AGREEMENT"
    assert P.grid_position(4, [], []) == "UNDER_CONSTRUCTION"
    assert P.grid_position(0, P.facts_in("The firm has applied for a power supply connection."), []) == "APPLIED"
    assert P.grid_position(0, [], []) == "NO_EVIDENCE"


def test_headline_splits_secured_from_unsecured_capacity():
    d = lambda stage, facts=(), ev=(): P.dossier(list(facts), stage, list(ev))  # noqa: E731
    projects = [
        {"capacity_mw": 100, "stage": 5, "power": d(5)},
        {"capacity_mw": 300, "stage": 1, "power": d(1, P.facts_in("Vantage signed an electricity supply agreement with TNB and will use direct-to-chip cooling."))},
        {"capacity_mw": 600, "stage": 0, "power": d(0, P.facts_in("The campus will have a 1 GW on-site gas-fired power plant."))},
        {"capacity_mw": None, "stage": 0, "power": d(0)},
    ]
    h = P.headline(projects)
    assert h["secured_mw"] == 400 and h["unsecured_mw"] == 600 and h["secured_share"] == 0.4
    assert h["pipeline_mw"] == 900 and h["pipeline_secured"]["mw"] == 300
    assert h["btm_signal"]["mw"] == 600 and h["liquid_cooling_signal"]["mw"] == 300
    assert h["grid"]["NO_EVIDENCE"]["projects"] == 2 and h["coverage"]["utilities"] == 1


def test_track_record_judges_only_old_projects_and_times_the_wait_to_ground():
    from datetime import datetime, timezone
    from app.phantom.track import track_records
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    d = lambda y, m=1: datetime(y, m, 1, tzinfo=timezone.utc)  # noqa: E731
    ps = [
        {"developer": "Builder", "country": "Malaysia", "capacity_mw": 100, "stage": 5, "reality_score": 0.98, "first_seen": d(2022),
         "secured": True, "evidence": [{"layer": "ANNOUNCED", "date": d(2022)}, {"layer": "BUILDING", "date": d(2023)}, {"layer": "LIVE", "date": d(2024, 6)}]},
        {"developer": "Builder", "country": "Malaysia", "capacity_mw": 200, "stage": 4, "reality_score": 0.9, "first_seen": d(2023),
         "secured": False, "evidence": [{"layer": "BUILDING", "date": d(2024, 7)}]},
        {"developer": "Builder", "country": "India", "capacity_mw": 50, "stage": 0, "reality_score": 0.2, "first_seen": d(2024), "secured": False, "evidence": []},
        {"developer": "Builder", "country": "India", "capacity_mw": 500, "stage": 0, "reality_score": 0.2, "first_seen": d(2026, 6), "secured": False, "evidence": []},
        {"developer": "Talker", "country": "India", "capacity_mw": 1000, "stage": 0, "reality_score": 0.15, "first_seen": d(2021), "secured": False, "evidence": []},
        {"developer": None, "capacity_mw": 9, "stage": 0},
    ]
    rows = {r["developer"]: r for r in track_records(ps, now)}
    b, t = rows["Builder"], rows["Talker"]
    assert (b["projects"], b["judged"], b["built_of_judged"], b["build_rate"]) == (4, 3, 2, 0.667)   # the June 2026 announcement is too new to judge
    assert b["months_to_ground"] == 15.0 and b["timed_projects"] == 2 and b["secured_mw"] == 100 and b["live_mw"] == 100
    assert t["build_rate"] is None and t["judged"] == 1 and t["months_to_ground"] is None            # one project is not a track record
    assert list(rows)[0] == "Talker"                                                                 # sorted by announced MW
