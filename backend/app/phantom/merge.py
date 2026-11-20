"""Merge review: the pairs the resolver was not sure about, put in front of a person.

The resolver is deliberately conservative — a wrong merge hides a real project, a missed
merge only counts one twice — so some duplicates survive ("TM Nxera data centre campus" /
"TM Nxera AI-Ready Data Center Campus"). Instead of loosening the rules until they start
merging the wrong things, the leftovers go to a queue:

    candidates()  pairs of resolved projects that look like the same site, with the reasons
    decide()      a person says "same project" or "different" — stored, never guessed
    resolve()     applies every stored decision on each rebuild (see resolve.apply_decisions)

A decision names each project by its ANCHOR — the id of its earliest mention — which stays
the same however the clusters around it change, so decisions survive rebuilds and new hunts.

Human-in-the-loop on purpose: this is the one step where a wrong automatic call silently
corrupts the headline number.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

MERGE, DISTINCT = "merge", "distinct"
MIN_SCORE = 0.7
_SIZES = re.compile(r"\d[\d,.]*\s?(?:mw|gw|kw|mva|acres?|crore|billion|million)\b")
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}


def _ordinals(name: str) -> set:
    """Site numbers in a name ("Noida II", "Tower 1", "DC3"), never sizes like "40 MW"."""
    s = _SIZES.sub(" ", (name or "").lower())
    out = {int(x) for x in re.findall(r"(?<![a-z0-9])(\d{1,2})(?![a-z0-9])", s)}       # "tower 1"
    out |= {int(x) for x in re.findall(r"[a-z](\d{1,2})\b", s)}                          # "dc3", "kul2"
    out |= {_ROMAN[x] for x in re.findall(r"\b(i{1,3}|iv|vi?)\b", s) if x in _ROMAN}     # "noida ii"
    return out


def pair_key(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _name_tokens(name: str, developer: Optional[str]) -> str:
    from app.phantom.resolve import name_core
    return name_core(name, developer)


def _cap_close(a: Optional[float], b: Optional[float], tol: float) -> Optional[bool]:
    if not a or not b:
        return None
    return max(a, b) / min(a, b) <= 1 + tol


def similarity(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """How likely two resolved projects are one site: {score 0–1, reasons, kind} or None.

    a, b: {anchor, name, developer, country, city, state, capacity_mw}"""
    from app.phantom.geo import PLACES
    from app.phantom.resolve import _area, _place_fits, canonical_developer, facility_code
    if a["country"] != b["country"]:
        return None
    ca, cb = facility_code(a["name"]), facility_code(b["name"])
    if ca and cb and ca != cb:
        return None                                   # two facility codes are two buildings
    na, nb = _ordinals(a["name"]), _ordinals(b["name"])
    if na and nb and not (na & nb):
        return None                                   # "Noida II" and "Noida III" are neighbours, not duplicates
    pa, pb = a.get("city"), b.get("city")
    # same place, or the same Malaysian state / Indian metro ("Johor" vs "Johor Bahru") - a person reviews it anyway
    same_place = bool(pa and pb and (_place_fits(pa, pb) or (pa in PLACES and pb in PLACES and _area(pa) == _area(pb))))
    if pa and pb and not same_place:
        return None
    same_dev = bool(a.get("developer") and canonical_developer(a["developer"]) == canonical_developer(b.get("developer")))
    cap = _cap_close(a.get("capacity_mw"), b.get("capacity_mw"), 0.35 if same_dev else 0.10)
    if cap is False:
        return None
    name = fuzz.token_set_ratio(_name_tokens(a["name"], a.get("developer")), _name_tokens(b["name"], b.get("developer"))) / 100 \
        if _name_tokens(a["name"], a.get("developer")) and _name_tokens(b["name"], b.get("developer")) else 0.0
    reasons, score = [], 0.0
    if same_dev:
        score += 0.35
        reasons.append(f"same developer ({a['developer']})")
    if same_place:
        score += 0.25
        reasons.append(f"same place ({pa if pa == pb else f'{pa} / {pb}'})")
    if cap:
        score += 0.25
        reasons.append(f"same stated size ({a['capacity_mw']:g} / {b['capacity_mw']:g} MW)")
    if name >= 0.6:
        score += 0.2 * name
        reasons.append(f"similar names ({round(name * 100)}%)")
    if not same_dev:
        # different developers only qualify as a JV / naming duplicate: same place AND same size
        if not (same_place and cap):
            return None
        reasons.append("different developers — a joint venture or the same campus under two names?")
    elif not (same_place or cap or name >= 0.8):
        return None
    if same_dev and score < MIN_SCORE:   # a cross-developer pair already had to match place AND size
        return None
    return {"score": round(min(score, 1.0), 2), "reasons": reasons, "kind": "same_developer" if same_dev else "cross_developer"}


def candidates(projects: List[Dict[str, Any]], decided: Dict[Tuple[str, str], str], limit: int = 60) -> List[Dict[str, Any]]:
    """Undecided look-alike pairs, most alike first."""
    by_country: Dict[str, List[Dict[str, Any]]] = {}
    for p in projects:
        if p.get("anchor") and p.get("country"):
            by_country.setdefault(p["country"], []).append(p)
    out = []
    for ps in by_country.values():
        for i, a in enumerate(ps):
            for b in ps[i + 1:]:
                if pair_key(a["anchor"], b["anchor"]) in decided:
                    continue
                s = similarity(a, b)
                if s:
                    big = max((a.get("capacity_mw") or 0), (b.get("capacity_mw") or 0))
                    out.append({"a": a, "b": b, **s, "double_counted_mw": min(a.get("capacity_mw") or 0, b.get("capacity_mw") or 0) or None, "_rank": (s["score"], big)})
    out.sort(key=lambda c: c["_rank"], reverse=True)
    for c in out:
        c.pop("_rank")
    return out[:limit]


def apply_decisions(clusters: List[Dict[str, Any]], decisions: Dict[Tuple[str, str], str]) -> List[Dict[str, Any]]:
    """Union every pair of clusters a person marked as the same project (resolver clusters, before canonicalise)."""
    if not decisions:
        return clusters
    home: Dict[str, int] = {}
    for i, c in enumerate(clusters):
        for m in c["members"]:
            home[str(m["id"])] = i
    parent = list(range(len(clusters)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), d in decisions.items():
        if d == MERGE and a in home and b in home:
            ra, rb = find(home[a]), find(home[b])
            if ra != rb:
                keep, drop = (ra, rb) if len(clusters[ra]["members"]) >= len(clusters[rb]["members"]) else (rb, ra)
                parent[drop] = keep
    merged: Dict[int, Dict[str, Any]] = {}
    for i, c in enumerate(clusters):
        r = find(i)
        if r not in merged:
            merged[r] = {**clusters[r], "codes": set(clusters[r]["codes"]), "places": set(clusters[r]["places"]),
                         "caps": list(clusters[r]["caps"]), "cores": list(clusters[r]["cores"]), "members": list(clusters[r]["members"])}
        if i != r:
            t = merged[r]
            t["members"] += c["members"]
            t["codes"] |= c["codes"]
            t["places"] |= c["places"]
            t["caps"] += c["caps"]
            t["cores"] += c["cores"]
            t["country"] = t["country"] or c["country"]
    for t in merged.values():
        t["members"].sort(key=lambda m: (m["published"] is None, m["published"] or 0))
    return list(merged.values())


def load_decisions(db) -> Dict[Tuple[str, str], str]:
    from app.phantom.models import PhMergeDecision
    return {pair_key(d.anchor_a, d.anchor_b): d.decision for d in db.query(PhMergeDecision).all()}


def projects_for_review(db) -> List[Dict[str, Any]]:
    from app.phantom.models import PhMention, PhProject
    anchors: Dict[Any, str] = {}
    for pid, mid in db.query(PhMention.project_id, PhMention.id).filter(PhMention.project_id != None).all():  # noqa: E711
        s = str(mid)
        if pid not in anchors or s < anchors[pid]:
            anchors[pid] = s
    return [{"id": str(p.id), "anchor": anchors.get(p.id), "name": p.name, "developer": p.developer, "country": p.country, "city": p.city, "state": p.state,
             "capacity_mw": p.capacity_mw, "stage": p.stage or 0, "reality_score": p.reality_score, "n_sources": p.n_sources,
             "first_seen": p.first_seen.date().isoformat() if p.first_seen else None} for p in db.query(PhProject).all()]


_ANCHOR = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def decide(db, anchor_a: str, anchor_b: str, decision: str, user: Optional[str] = None) -> Dict[str, Any]:
    """Store (or change) one decision. Does not rebuild — the caller does."""
    from app.phantom.models import PhMergeDecision
    if decision not in (MERGE, DISTINCT) or not _ANCHOR.match(anchor_a) or not _ANCHOR.match(anchor_b) or anchor_a == anchor_b:
        raise ValueError("decision must be 'merge' or 'distinct' between two different projects")
    a, b = pair_key(anchor_a, anchor_b)
    row = db.query(PhMergeDecision).filter(PhMergeDecision.anchor_a == a, PhMergeDecision.anchor_b == b).first()
    if row:
        row.decision, row.decided_by = decision, user
    else:
        db.add(PhMergeDecision(anchor_a=a, anchor_b=b, decision=decision, decided_by=user))
    db.commit()
    return {"a": a, "b": b, "decision": decision}
