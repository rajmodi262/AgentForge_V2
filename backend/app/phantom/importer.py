"""Import mode: bring your own project list, get the reality layer on top.

A tracker with thousands of projects (a client's, or FSX's own) is the asset; this is the
layer that says which rows are real. Each uploaded row is matched to a project we track
(same rules as the merge queue: developer, place, size, name) and returned with its reality
score, grid position, weakest assumption and evidence count. A row we cannot match is
reported as such, with the announced-layer prior — never silently scored as if we knew it.

    rows: CSV with a header; recognised columns (any case): name / project, developer,
          city / location, country, capacity_mw / mw
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

from app.phantom import merge as M
from app.phantom.geo import resolve_place

MAX_ROWS = 2000
ALIASES = {"name": ("name", "project", "project_name", "facility"), "developer": ("developer", "operator", "company", "owner"),
           "city": ("city", "location", "place", "site", "state"), "country": ("country",), "capacity_mw": ("capacity_mw", "mw", "capacity", "it_mw")}


def parse(text: str) -> List[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = {k.strip().lower(): k for k in (reader.fieldnames or [])}
    pick = {f: next((cols[a] for a in names if a in cols), None) for f, names in ALIASES.items()}
    if not pick["name"]:
        raise ValueError("the CSV needs a 'name' (or 'project') column")
    out = []
    for i, r in enumerate(reader):
        if i >= MAX_ROWS:
            raise ValueError(f"at most {MAX_ROWS} rows per upload")
        get = lambda f: (r.get(pick[f]) or "").strip() if pick[f] else ""  # noqa: E731
        try:
            mw = float(get("capacity_mw").replace(",", "")) if get("capacity_mw") else None
        except ValueError:
            mw = None
        if get("name"):
            out.append({"row": i + 2, "name": get("name"), "developer": get("developer") or None, "city": get("city") or None,
                        "country": get("country") or None, "capacity_mw": mw})
    return out


def match(rows: List[Dict[str, Any]], tracked: List[Dict[str, Any]]) -> Dict[str, Any]:
    """tracked: merge.projects_for_review rows plus grid_position / weakest_assumption / reality_score."""
    from app.phantom.geo import PLACES, infer_country
    out = []
    for r in rows:
        place = resolve_place(r["city"], r["name"])
        country = r["country"] or (PLACES[place][1] if place else infer_country(r["name"], r["city"]))
        q = {**r, "anchor": f"row{r['row']}", "city": place, "country": country}
        sims = [(M.similarity(q, t), t) for t in tracked if t.get("country") == country]
        # a row that names its developer is only ever matched to that developer's projects
        sims = [(s, t) for s, t in sims if s and (not r["developer"] or s["kind"] == "same_developer")]
        # a facility code ("JHB1") outranks everything else when the tracker has that exact site
        from app.phantom.resolve import facility_code
        code = facility_code(r["name"])
        coded = [(s, t) for s, t in sims if code and facility_code(t["name"]) == code]
        sim, t = max(coded or sims, key=lambda x: x[0]["score"], default=(None, None))
        if sim:
            out.append({**r, "matched": True, "confidence": sim["score"], "why": sim["reasons"], "project_id": t["id"], "project": t["name"],
                        "reality_score": t["reality_score"], "stage": t["stage"], "grid_position": t.get("grid_position"),
                        "weakest_assumption": t.get("weakest_assumption"), "n_sources": t.get("n_sources")})
        else:
            out.append({**r, "matched": False, "why": ["no tracked project with the same developer, place and size"],
                        "country_guess": country, "in_scope": (country in {c["country"] for c in __import__("app.phantom.sources", fromlist=["REGIONS"]).REGIONS.values()}) if country else None})
    m = [x for x in out if x["matched"]]
    cap = lambda xs: sum(x["capacity_mw"] or 0 for x in xs)  # noqa: E731
    return {"rows": out, "summary": {"rows": len(out), "matched": len(m), "unmatched": len(out) - len(m),
                                     "announced_mw": cap(out), "matched_mw": cap(m),
                                     "reality_mw": round(sum((x["capacity_mw"] or 0) * (x["reality_score"] or 0) for x in m), 1)}}


def tracked_from_db(db) -> List[Dict[str, Any]]:
    from app.phantom.models import PhProject
    extra = {str(p.id): p for p in db.query(PhProject).all()}
    return [{**t, "grid_position": (extra[t["id"]].power or {}).get("grid_position", "NO_EVIDENCE"),
             "weakest_assumption": extra[t["id"]].weakest_assumption} for t in M.projects_for_review(db)]
