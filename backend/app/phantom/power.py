"""Power forensics: what do the sources say about each project's POWER, not just its size?

A data centre is a power project with servers attached. The evidence ladder says how
far a project has got; this module reads the same verified sentences for the details a
power, cooling or electrical supplier needs:

    grid         has it got a grid position?  agreement signed · applied / in talks
    utility      who supplies it (TNB, Tata Power, MSEDCL …)
    grid_kv/mva  connection voltage and contracted capacity
    substation   dedicated substation / intake station
    onsite       behind-the-meter generation: gas, fuel cells, on-site solar, batteries, diesel backup, nuclear
    renewable    how it buys green power: PPA, green tariff, CRESS, open access, captive
    cooling      liquid / direct-to-chip / immersion / air / chilled water / waterless
    rack_kw/pue  design density and efficiency
    water        reclaimed or recycled water
    contractor / equipment / financier   who is building, supplying and funding it

Everything here is DETERMINISTIC: a fact is a pattern found in a sentence that is about
the project (`extract.project_sentences`), and the sentence is kept as the quote. So every
fact can be checked by eye, costs no LLM time, and improving a rule upgrades all history
on the next rebuild — the same contract as the Evidence Miner.

GRID POSITION (the one question the market is arguing about) is derived per project:

    ENERGIZED    a phase is operating (LIVE evidence)
    AGREEMENT    a verified supply / connection agreement, or secured MW
    POWER_DEAL   a verified power deal (e.g. a renewable PPA) but no grid agreement found
    APPLIED      applied for power, or in talks with a utility
    NO_EVIDENCE  nothing found in public sources (NOT proof there is no agreement)

"Secured" = ENERGIZED + AGREEMENT, the same definition FSX uses for its headline split.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

GRID_POSITIONS = ["ENERGIZED", "AGREEMENT", "POWER_DEAL", "UNDER_CONSTRUCTION", "APPLIED", "NO_EVIDENCE"]
SECURED = {"ENERGIZED", "AGREEMENT"}
GRID_LABEL = {
    "ENERGIZED": "Energized (operating)", "AGREEMENT": "Grid agreement signed", "POWER_DEAL": "Power deal, grid not confirmed",
    "UNDER_CONSTRUCTION": "Under construction, power agreement not found",
    "APPLIED": "Applied / in talks", "NO_EVIDENCE": "No public evidence of power",
}

# ── grid ──
# Agreement nouns: a signed one is a grid position; the same words with "in talks" are an application.
GRID_AGREEMENT = re.compile(
    r"(?:electricity|power|energy) supply agreement|supply agreement with|\bESA\b|grid[- ]connection agreement|interconnection agreement"
    r"|connection agreement|secure[ds]? (?:a |an |up to |about |nearly |over )?(?:total of )?\d[\d,.]*\s?(?:MW|MVA|GW|megawatts?)(?: of| in)? (?:electricity|power|grid|supply|sanctioned)"
    r"|secure[ds]? (?:the |its )?(?:power|electricity|grid) (?:supply|connection|allocation)"
    r"|(?:ink|sign|seal)(?:s|ed)? [^.]{0,40}?\d[\d,.]*\s?(?:MW|GW) (?:power|electricity|energy) (?:deal|supply)"
    r"|(?:power|load|electricity) (?:allocation|sanction)\b|sanctioned (?:load|power)", re.I)
# State words: only ever positive evidence.
GRID_LIVE = re.compile(r"\b(?:has been|was|were|is now|now) energi[sz]ed|\bconnected to the (?:national |state |main )?grid", re.I)
_SIGNED = re.compile(r"\b(signed|signs|secured|secures|inked|inks?|executed|entered into|obtained|received|granted|approved|commissioned|finali[sz]ed|sanctioned|has|have)\b", re.I)
_PENDING = re.compile(
    r"\b(in talks|negotiat\w*|seeks?|seeking|plans? to (?:sign|secure|apply)|appl(?:ied|ies|ying) (?:for|to)|awaiting|yet to|pending|expects? to (?:sign|secure)"
    r"|hopes? to|looking to (?:sign|secure)|would need|needs? to secure|subject to|has not|have not|is yet|still needs?)\b", re.I)
GRID_APPLIED = re.compile(
    r"appl(?:ied|ies|ying|ication) (?:for|to) [^.]{0,40}(?:power|electricity|grid|connection|supply)|awaiting (?:power|grid|electricity)"
    r"|in talks with [^.]{0,40}(?:utility|tnb|tenaga|power|discom)|power (?:application|request)|requested \d[\d,.]*\s?(?:MW|MVA)", re.I)

VOLTAGE = re.compile(r"\b(\d{2,3})\s?kV\b", re.I)
_GRID_VOLTS = {33, 66, 110, 132, 220, 230, 275, 400, 500, 765}
MVA = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s?MVA\b", re.I)
SUBSTATION = re.compile(r"\bsub-?stations?\b|main intake|switching station|consumer landing station|\bPMU\b", re.I)
_DEDICATED = re.compile(r"\b(dedicated|own|on-?site|captive|new|private)\b", re.I)

# Utilities and independent power producers (extends resolve.UTILITIES)
POWER_COMPANIES = {
    "TNB": r"\btnb\b|tenaga nasional", "YTL Power": r"ytl power", "Gentari": r"gentari", "Solarvest": r"solarvest",
    "Sarawak Energy": r"sarawak energy", "Malakoff": r"malakoff", "Leader Energy": r"leader energy", "UEM Lestra": r"uem lestra",
    "Cypark": r"cypark", "Edra Power": r"\bedra\b", "Tata Power": r"tata power", "NTPC": r"\bntpc\b", "Adani Green": r"adani green",
    "Adani Electricity": r"adani electricity", "ReNew": r"\bReNew\b(?! data)", "JSW Energy": r"jsw energy", "Torrent Power": r"torrent power",
    "CleanMax": r"clean ?max", "AMPIN": r"\bampin\b|amp energy", "Sembcorp": r"sembcorp", "Avaada": r"avaada", "ACME": r"\bacme (?:solar|group)",
    "Serentica": r"serentica", "Fourth Partner": r"fourth partner", "Hindustan Power": r"hindustan power", "Juniper Green": r"juniper green",
    "Brookfield Renewable": r"brookfield (?:renewable|hydro)", "ENGIE": r"\bengie\b", "MSEDCL": r"\bmsedcl\b|mahadiscom|mahavitaran",
    "TANGEDCO": r"tangedco|\btneb\b", "BESCOM": r"\bbescom\b", "Power Grid": r"power ?grid corporation|\bpgcil\b", "UPPCL": r"\buppcl\b",
    "Noida Power": r"noida power|\bnpcl\b", "APTRANSCO": r"aptransco|\bapepdcl\b", "CESC": r"\bcesc\b", "BSES": r"\bbses\b",
    "TGSPDCL": r"\bt[gs]spdcl\b", "MSETCL": r"\bmsetcl\b|mahatransco", "Bloom Energy": r"bloom energy",
}
_SUPPLY_CUE = re.compile(r"\b(power|electricity|energy|supply|supplies|supplied|agreement|ppa|substation|grid|connect\w*|megawatts?|mw|mva|solar|renewable|tariff)\b", re.I)

# ── behind-the-meter / on-site generation ──
ONSITE = {
    "gas generation": r"gas[- ](?:fired|turbines?|engines?|gensets?|power(?:ed)? (?:plant|generation|station))|natural gas (?:generation|power|plant|turbines?|facility)|\bCCGT\b",
    "fuel cells": r"fuel[- ]cells?",
    "on-site solar": r"(?:on-?site|rooftop|captive|behind[- ]the[- ]meter) solar|solar (?:farm|plant|park|array|rooftops?) (?:on|at|within|adjacent|next to)|co-?located solar",
    "battery storage": r"battery (?:energy )?storage|\bBESS\b",
    "diesel backup": r"diesel[- ](?:generators?|gensets?|rotary)|back-?up generators?|standby generators?|\bDG sets?\b",
    "nuclear / SMR": r"\bSMRs?\b|small modular reactors?|nuclear (?:power|energy|reactor)",
    "hydrogen": r"hydrogen[- ](?:fuel|power(?:ed)?|ready|generators?|turbines?|engines?)|green hydrogen (?:plant|power)",
    "on-site generation": r"behind[- ]the[- ]meter|on-?site (?:power )?generation|captive power (?:plant|generation)|self[- ]generat\w+",
}
RENEWABLE = {
    "PPA": r"power purchase agreements?|\bV?PPAs?\b",
    "green tariff": r"green electricity tariff|green tariff",
    "CRESS": r"\bCRESS\b|corporate renewable energy supply scheme",
    "open access": r"open[- ]access",
    "captive renewables": r"captive (?:solar|wind|renewable|hybrid)",
    "renewable energy": r"100\s?% renewable|renewable (?:energy|power|electricity)|green (?:energy|power)|solar (?:power|energy)|wind (?:power|energy)|hydro(?:power|electric(?:ity)?)?\b|carbon[- ]free energy",
}

# ── cooling and density ──
COOLING = {
    "direct-to-chip": r"direct[- ]to[- ]chip|\bD2C\b|\bDLC\b|direct liquid",
    "immersion": r"immersion[- ]cool\w*|immersion",
    "liquid cooling": r"liquid[- ]cool\w*",
    "rear-door heat exchanger": r"rear[- ]door",
    "air cooling": r"air[- ]cool\w*",
    "chilled water": r"chilled[- ]water|\bchillers?\b",
    "evaporative": r"evaporative|adiabatic",
    "waterless / closed loop": r"waterless|water[- ]free|zero[- ]water|closed[- ]loop",
}
WATER = {"reclaimed water": r"reclaimed water|recycled water|treated (?:waste ?)?water|grey ?water", "desalination": r"desalinat\w+"}
RACK_KW = re.compile(r"(\d{2,3})\s?kW(?:\s?per\s|\s?/\s?|\s?a\s)rack|racks? (?:of |up to |at |above |over )(\d{2,3})\s?kW|(\d{2,3})\s?kW[- ]racks?", re.I)
PUE = re.compile(r"\bPUE\b[^.\d]{0,40}?(1\.\d{1,2})|(1\.\d{1,2})\s?PUE", re.I)

# ── ecosystem: who builds, supplies and funds it ──
CONTRACTORS = {
    "Gamuda": r"\bgamuda\b", "Sunway Construction": r"sunway construction|\bsuncon\b", "IJM": r"\bIJM\b", "Kerjaya Prospek": r"kerjaya",
    "MN Holdings": r"mn holdings", "Binastra": r"binastra", "Southern Score": r"southern score", "Critical Holdings": r"critical holdings",
    "Pekat": r"\bpekat\b", "L&T Construction": r"l&t construction|larsen & toubro|larsen and toubro", "Sterling and Wilson": r"sterling (?:and|&) wilson",
    "Tata Projects": r"tata projects", "Shapoorji Pallonji": r"shapoorji", "AECOM": r"\baecom\b", "Jacobs": r"\bJacobs\b", "Arup": r"\bArup\b",
    "ISG": r"\bISG\b", "Exyte": r"\bexyte\b", "Linesight": r"linesight", "Mace": r"\bMace\b", "Turner & Townsend": r"turner (?:&|and) townsend",
    "China State Construction": r"china state construction", "CTCI": r"\bCTCI\b", "Kienta": r"kienta", "NTT Facilities": r"ntt facilities",
    "Leighton": r"leighton", "DSCO": r"\bDSCO\b", "AWC": r"\bAWC\b", "LFE": r"\bLFE\b", "Econpile": r"econpile", "Vestian": r"vestian",
}
_BUILD_CUE = re.compile(r"\b(contracts?|contractors?|awarded|letter of award|appointed|built by|build|construct\w*|EPC|MEP|engineering|design(?:ed)? by|works|subcontract\w*)\b", re.I)
EQUIPMENT = {
    "Schneider Electric": r"schneider", "Vertiv": r"\bvertiv\b", "ABB": r"\bABB\b", "Siemens": r"\bsiemens\b", "Eaton": r"\bEaton\b(?! Fiber)",
    "Cummins": r"\bcummins\b", "Caterpillar": r"caterpillar", "Rolls-Royce / mtu": r"rolls[- ]royce|\bmtu\b", "Hitachi Energy": r"hitachi energy",
    "GE Vernova": r"ge vernova", "Mitsubishi": r"mitsubishi (?:electric|heavy|power)", "Johnson Controls": r"johnson controls", "Carrier": r"\bCarrier (?:Global|Corporation|HVAC)",
    "Trane": r"\btrane\b", "Daikin": r"\bdaikin\b", "Kirloskar": r"kirloskar", "Legrand": r"\blegrand\b", "Delta Electronics": r"delta electronics",
    "Huawei Digital Power": r"huawei digital power", "Bloom Energy": r"bloom energy", "Wärtsilä": r"w[aä]rtsil[aä]",
}
FINANCIERS = {
    "Maybank": r"\bmaybank\b", "CIMB": r"\bcimb\b", "RHB": r"\brhb\b", "OCBC": r"\bocbc\b", "UOB": r"\buob\b", "DBS": r"\bdbs\b",
    "HSBC": r"\bhsbc\b", "Standard Chartered": r"standard chartered", "SMBC": r"\bsmbc\b|sumitomo mitsui", "MUFG": r"\bmufg\b",
    "Mizuho": r"\bmizuho\b", "SBI": r"\bsbi\b|state bank of india", "Axis Bank": r"axis bank", "ICICI": r"\bicici\b", "HDFC": r"\bhdfc\b",
    "Kotak": r"\bkotak\b", "IFC": r"\bifc\b|international finance corporation", "ADB": r"asian development bank", "DFC": r"\bdfc\b",
    "Citi": r"\bciti(?:bank|group)?\b", "JPMorgan": r"jp ?morgan", "Deutsche Bank": r"deutsche bank", "BNP Paribas": r"bnp paribas",
    "ING": r"\bING\b", "Natixis": r"natixis", "Crédit Agricole": r"cr[eé]dit agricole", "Bank of China": r"bank of china", "KKR": r"\bkkr\b",
    "Blackstone": r"blackstone", "Brookfield": r"brookfield", "GIC": r"\bgic\b", "Temasek": r"temasek", "Bain Capital": r"bain capital",
}
_FINANCE_CUE = re.compile(r"\b(loans?|financ(?:e[ds]?|ing)|debt|credit facility|facility agreement|bonds?|lenders?|arrangers?|bookrunners?|raised|funding|fund(?:ed|s)?|invest(?:s|ed|ment|or|ors)|backed by|stake)\b", re.I)

_NEGATED = re.compile(r"\b(?:no|not|without|avoid\w*|instead of|rather than|eliminat\w+|replac\w+)\s+(?:\w+\s+){0,2}$", re.I)   # "avoiding evaporative cooling"
# Industry commentary, not a statement about one project
_REMARK = re.compile(r"\bdevelopers are\b|\bdata cent(?:er|re)s (?:globally|worldwide|are|have|will|need)\b|\b(?:globally|worldwide)\b|\bthe (?:industry|sector|market)\b"
                     r"|\bevery data cent(?:er|re)\b|\ball data cent(?:er|re)s\b", re.I)

FIELDS = ["grid", "utility", "grid_kv", "grid_mva", "substation", "onsite", "renewable", "cooling", "rack_kw", "pue", "water",
          "contractor", "equipment", "financier"]


_ESCAPES = re.compile(r"\\.")


def _find(pat: str, s: str):
    """Company patterns written with capitals (ABB, ING, IJM, Mace) are matched case-sensitively."""
    return re.search(pat, s, 0 if re.search(r"[A-Z]", _ESCAPES.sub("", pat)) else re.I)


def _same_company(name: str, developer: Optional[str]) -> bool:
    """A developer is not its own contractor / utility / financier ("YTL Power" for a YTL campus, L&T for L&T Vyoma)."""
    fix = lambda x: re.sub(r"larsen (?:&|and) toubro", "l&t", (x or "").lower())  # noqa: E731
    a, b = re.sub(r"[^a-z0-9]", "", fix(name)), re.sub(r"[^a-z0-9]", "", fix(developer))
    first = lambda x: next(iter(re.findall(r"[a-z0-9&]{2,}", fix(x))), "")  # noqa: E731
    return bool(a and b) and (a in b or b in a or first(name) == first(developer))


def facts_in(sentence: str, developer: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every power fact stated in ONE sentence. `planned` marks design intent / future tense."""
    from app.phantom.extract import _FUTURE
    s = sentence
    planned = bool(_FUTURE.search(s))
    out: List[Dict[str, Any]] = []

    def add(field: str, value: Any, plan: Optional[bool] = None):
        out.append({"field": field, "value": value, "quote": s[:400], "planned": planned if plan is None else plan})

    if GRID_AGREEMENT.search(s):
        if _PENDING.search(s):
            add("grid", "applied", True)
        elif _SIGNED.search(s):
            add("grid", "agreement", False)
        # an agreement merely referred to ("the ESA underpins phase one") proves neither
    elif GRID_LIVE.search(s) and not _PENDING.search(s) and not planned:
        add("grid", "agreement", False)
    elif GRID_APPLIED.search(s):
        add("grid", "applied", True)
    supply = bool(_SUPPLY_CUE.search(s))
    for name, pat in POWER_COMPANIES.items():
        if supply and _find(pat, s) and not _same_company(name, developer):
            add("utility", name)
    volts = sorted({int(v) for v in VOLTAGE.findall(s) if int(v) in _GRID_VOLTS}, reverse=True)
    if volts:
        add("grid_kv", volts[0])
    for v in MVA.findall(s):
        try:
            add("grid_mva", float(v.replace(",", "")))
        except ValueError:
            pass
    if SUBSTATION.search(s):
        add("substation", "dedicated" if _DEDICATED.search(s) else "mentioned")
    for group, table in (("onsite", ONSITE), ("renewable", RENEWABLE), ("cooling", COOLING), ("water", WATER)):
        for value, pat in table.items():
            m = re.search(pat, s, re.I)
            if m and not _NEGATED.search(s[max(0, m.start() - 30):m.start()]):
                add(group, value)
    m = RACK_KW.search(s)
    if m:
        add("rack_kw", int(next(g for g in m.groups() if g)))
    m = PUE.search(s)
    if m:
        add("pue", float(next(g for g in m.groups() if g)))
    if _BUILD_CUE.search(s):
        for name, pat in CONTRACTORS.items():
            if _find(pat, s) and not _same_company(name, developer):
                add("contractor", name)
    for name, pat in EQUIPMENT.items():
        if _find(pat, s) and not _same_company(name, developer):
            add("equipment", name)
    if _FINANCE_CUE.search(s):
        for name, pat in FINANCIERS.items():
            if _find(pat, s) and not _same_company(name, developer):
                add("financier", name)
    return out


def mine_power(m: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    """Power facts for one mention: patterns applied only to sentences about the project."""
    from app.phantom.extract import project_sentences
    seen, out = set(), []
    for s in project_sentences(m, text):
        for f in facts_in(s, m.get("developer")):
            key = (f["field"], f["value"])
            if key not in seen:
                seen.add(key)
                out.append(f)
    return out


ECOSYSTEM = {"contractor", "equipment", "financier"}
# A sentence that does not name the developer must at least point at a facility ("the campus will feature…")
_REFERENT = re.compile(
    r"\b(?:the|this|that|its|our|their|each|both|new|upcoming) (?:\w+[- ]){0,3}?(?:facilit(?:y|ies)|campus|site|data[\s-]?cent(?:er|re)s?|datacent(?:er|re)|project|hub|park|buildings?"
    r"|development|phase|halls?|plant)\b|\b(?:it|the company|the firm|the operator|the developer) (?:will|has|have|is|also|features?|uses?|plans?)\b|\b\d[\d,.]*\s?(?:MW|MVA|kV)\b", re.I)


def project_facts(facts: Iterable[Dict[str, Any]], developer: Optional[str], code: Optional[str], place: Optional[str]) -> List[Dict[str, Any]]:
    """Facts that survive the subject check for ONE resolved project.

    * the same test evidence gets (`resolve.about_project`): not page boilerplate, not a
      portfolio-wide statement, not another developer / facility code / region;
    * company names (contractor, equipment, financier) only count when the sentence itself
      names this project's developer or facility code — a "related stories" headline about a
      bank is not this project's lender.
    """
    from app.phantom.extract import KNOWN_DEVELOPERS
    from app.phantom.resolve import about_project, canonical_developer
    from app.phantom.verify import norm
    canon = canonical_developer(developer) if developer else None
    names = [a for a in (KNOWN_DEVELOPERS.get(canon) or []) if len(a) >= 3] + ([norm(canon).split(" ")[0]] if canon and len(canon) > 3 else [])
    out, seen = [], set()
    for f in facts:
        q = f.get("quote") or ""
        if not about_project(q, code, place, developer, None) or _REMARK.search(q):
            continue
        nq = norm(q)
        named = any(re.search(rf"\b{re.escape(a)}\b", nq) for a in names) or bool(code and norm(code) in nq)
        if f["field"] in ECOSYSTEM and not named:
            continue
        if not named and not _REFERENT.search(q):
            continue  # an industry-wide remark ("developers are being pushed towards on-site generation")
        key = (f["field"], f["value"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def drop_shared(per_mention: List[List[Dict[str, Any]]], mentions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """One article, several projects: a sentence the miner attached to MORE THAN ONE of them
    ("the company has secured 250 MW of power") is kept only by a project the sentence itself
    points at (its facility code, city or capacity); if it points at none, nobody gets it."""
    from app.phantom.geo import PLACES, resolve_place
    from app.phantom.resolve import facility_code
    from app.phantom.verify import norm
    count: Dict[str, int] = {}
    for facts in per_mention:
        for q in {f["quote"] for f in facts}:
            count[q] = count.get(q, 0) + 1

    def points_at(q: str, m: Dict[str, Any]) -> bool:
        nq = norm(q)
        code = facility_code(m.get("project_name"))
        place = resolve_place(m.get("city"), m.get("state"), m.get("project_name"))
        cap = norm(m.get("capacity_text") or "")
        return bool((code and norm(code) in nq) or (place and any(re.search(rf"\b{re.escape(a)}\b", nq) for a in PLACES[place][4]))
                    or (cap and len(cap) >= 4 and cap in nq))

    return [[f for f in facts if count[f["quote"]] == 1 or points_at(f["quote"], m)] for facts, m in zip(per_mention, mentions)]


def _uniq(xs: Iterable[Any]) -> List[Any]:
    return list(dict.fromkeys(x for x in xs if x not in (None, "")))


def grid_position(stage: int, facts: List[Dict[str, Any]], power_events: Iterable[Dict[str, Any]] = ()) -> str:
    """One label per project, strongest evidence first."""
    power_events = list(power_events)
    if stage >= 5:
        return "ENERGIZED"
    if any(f["field"] == "grid" and f["value"] == "agreement" for f in facts):
        return "AGREEMENT"
    if any(GRID_AGREEMENT.search(e.get("quote") or "") and not _PENDING.search(e.get("quote") or "") for e in power_events):
        return "AGREEMENT"
    if power_events:
        return "POWER_DEAL"
    if stage == 4:
        return "UNDER_CONSTRUCTION"
    if any(f["field"] == "grid" and f["value"] == "applied" for f in facts):
        return "APPLIED"
    return "NO_EVIDENCE"


def dossier(facts: List[Dict[str, Any]], stage: int, power_events: Iterable[Dict[str, Any]] = ()) -> Dict[str, Any]:
    """Roll one project's facts into the fields a supplier reads, keeping every quote."""
    def vals(field: str, firm_first: bool = True) -> List[Any]:
        fs = [f for f in facts if f["field"] == field]
        fs.sort(key=lambda f: bool(f.get("planned")) if firm_first else 0)
        return _uniq(f["value"] for f in fs)

    kv, mva, rack, pue = vals("grid_kv"), vals("grid_mva"), vals("rack_kw"), vals("pue")
    sub = vals("substation")
    pos = grid_position(stage, facts, power_events)
    return {
        "grid_position": pos, "grid_label": GRID_LABEL[pos], "secured": pos in SECURED,
        "utilities": vals("utility"), "grid_kv": max(kv) if kv else None, "grid_mva": max(mva) if mva else None,
        "substation": "dedicated" if "dedicated" in sub else ("mentioned" if sub else None),
        "onsite": vals("onsite"), "renewable": vals("renewable"), "cooling": vals("cooling"),
        "rack_kw": max(rack) if rack else None, "pue": min(pue) if pue else None, "water": vals("water"),
        "contractors": vals("contractor"), "equipment": vals("equipment"), "financiers": vals("financier"),
        "n_facts": len(facts), "facts": facts,
    }


LIQUID = {"direct-to-chip", "immersion", "liquid cooling", "rear-door heat exchanger"}
BTM = set(ONSITE) - {"diesel backup"}   # diesel sets are standby, not a power strategy


def headline(projects: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Portfolio view in FSX's own vocabulary. Each project: {capacity_mw, stage, power: dossier}."""
    ps = [p for p in projects]
    capped = [p for p in ps if p.get("capacity_mw")]
    total = sum(p["capacity_mw"] for p in capped)

    def mw(pred) -> float:
        return round(sum(p["capacity_mw"] for p in capped if pred(p.get("power") or {})), 1)

    def n(pred) -> int:
        return sum(1 for p in ps if pred(p.get("power") or {}))

    by_pos = {k: {"projects": n(lambda d, k=k: d.get("grid_position") == k), "mw": mw(lambda d, k=k: d.get("grid_position") == k)} for k in GRID_POSITIONS}
    pipeline = [p for p in capped if (p.get("stage") or 0) < 5]          # not yet operating: where suppliers can still win
    pipe_mw = sum(p["capacity_mw"] for p in pipeline)

    def pipe(pred) -> Dict[str, Any]:
        v = round(sum(p["capacity_mw"] for p in pipeline if pred(p.get("power") or {})), 1)
        return {"mw": v, "share": round(v / pipe_mw, 3) if pipe_mw else None,
                "projects": sum(1 for p in ps if (p.get("stage") or 0) < 5 and pred(p.get("power") or {}))}

    secured = by_pos["ENERGIZED"]["mw"] + by_pos["AGREEMENT"]["mw"]
    return {
        "projects": len(ps), "announced_mw": round(total, 1),
        "grid": by_pos, "secured_mw": round(secured, 1), "unsecured_mw": round(total - secured, 1),
        "secured_share": round(secured / total, 3) if total else None,
        "pipeline_mw": round(pipe_mw, 1),
        "pipeline_secured": pipe(lambda d: d.get("grid_position") == "AGREEMENT"),
        "pipeline_unsecured": pipe(lambda d: d.get("grid_position") != "AGREEMENT"),
        "btm_signal": pipe(lambda d: bool(set(d.get("onsite") or []) & BTM)),
        "liquid_cooling_signal": pipe(lambda d: bool(set(d.get("cooling") or []) & LIQUID)),
        "low_water_signal": pipe(lambda d: "waterless / closed loop" in (d.get("cooling") or []) or bool(d.get("water"))),
        "renewable_signal": pipe(lambda d: bool(d.get("renewable"))),
        "no_utility_named": pipe(lambda d: not d.get("utilities")),
        "coverage": {f: n(lambda d, f=f: bool(d.get(f))) for f in
                     ("utilities", "grid_kv", "grid_mva", "substation", "onsite", "renewable", "cooling", "rack_kw", "pue", "water",
                      "contractors", "equipment", "financiers")},
        "with_any_fact": n(lambda d: bool(d.get("n_facts"))),
    }
