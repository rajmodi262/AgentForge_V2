"""Developer track records: who builds what they announce, and how fast?

Two developers can announce the same 500 MW. One has broken ground on every campus it
ever named; the other has a shelf of press releases. For a supplier deciding whom to call,
that history is the cheapest signal there is — and FSX's own chart makes the same point
("time-to-power varies widely by region and developer").

Per developer, from the resolved projects and their verified evidence:

    projects / announced_mw      everything tracked
    live, building               how many reached each stage
    judged, built_of_judged      projects first seen 24+ months ago, and how many of THOSE show
                                 verified construction or operation — a recent announcement
                                 cannot count against anyone
    build_rate                   built_of_judged / judged (None under 3 judged projects)
    months_to_ground             median months from first report to first verified
                                 construction evidence, where both dates are known
    secured_mw                   capacity with a secured grid position (power.SECURED)

Descriptive on purpose. The backtest tried "has built 2+ other projects" as a score
adjustment: the 6 cases it could test were encouraging (4 progressed, against a 13% base
rate) and far too few to tune a weight on, so the record is shown, not scored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Optional

JUDGE_AFTER_MONTHS = 24
MIN_JUDGED = 3
BUILT = {"BUILDING", "LIVE"}


def _aware(d: Optional[datetime]) -> Optional[datetime]:
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _months(a: datetime, b: datetime) -> float:
    return (b - a).days / 30.44


def track_records(projects: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """projects: [{developer, country, capacity_mw, stage, reality_score, first_seen, secured,
    evidence: [{layer, date}]}] → one row per developer, biggest pipeline first."""
    now = now or datetime.now(timezone.utc)
    by_dev: Dict[str, List[Dict[str, Any]]] = {}
    for p in projects:
        if p.get("developer"):
            by_dev.setdefault(p["developer"], []).append(p)
    out = []
    for dev, ps in by_dev.items():
        judged = [p for p in ps if _aware(p.get("first_seen")) and _months(_aware(p["first_seen"]), now) >= JUDGE_AFTER_MONTHS]
        built = [p for p in judged if (p.get("stage") or 0) >= 4]
        waits = []
        for p in ps:
            first = _aware(p.get("first_seen"))
            ground = min((_aware(e["date"]) for e in p.get("evidence") or [] if e.get("layer") in BUILT and e.get("date")), default=None)
            if first and ground and _months(first, ground) >= 1:     # first reported before construction, so the wait is real
                waits.append(_months(first, ground))
        mw = lambda rows: round(sum(p.get("capacity_mw") or 0 for p in rows), 1)  # noqa: E731
        out.append({
            "developer": dev, "countries": ", ".join(sorted({p["country"] for p in ps if p.get("country")})),
            "projects": len(ps), "announced_mw": mw(ps),
            "reality_mw": round(sum((p.get("capacity_mw") or 0) * (p.get("reality_score") or 0) for p in ps), 1),
            "live": sum(1 for p in ps if (p.get("stage") or 0) == 5), "building": sum(1 for p in ps if (p.get("stage") or 0) == 4),
            "pre_construction": sum(1 for p in ps if (p.get("stage") or 0) < 4),
            "live_mw": mw([p for p in ps if (p.get("stage") or 0) == 5]),
            "secured_mw": mw([p for p in ps if p.get("secured")]),
            "judged": len(judged), "built_of_judged": len(built),
            "build_rate": round(len(built) / len(judged), 3) if len(judged) >= MIN_JUDGED else None,
            "months_to_ground": round(median(waits), 1) if waits else None, "timed_projects": len(waits),
        })
    out.sort(key=lambda r: (-r["announced_mw"], -r["projects"], r["developer"]))
    return out


def from_db(db) -> List[Dict[str, Any]]:
    from app.phantom.models import PhEvidence, PhProject
    ev: Dict[Any, List[Dict[str, Any]]] = {}
    for e in db.query(PhEvidence).all():
        ev.setdefault(e.project_id, []).append({"layer": e.layer, "date": e.event_date})
    return track_records([{
        "developer": p.developer, "country": p.country, "capacity_mw": p.capacity_mw, "stage": p.stage, "reality_score": p.reality_score,
        "first_seen": p.first_seen, "secured": bool((p.power or {}).get("secured")), "evidence": ev.get(p.id, []),
    } for p in db.query(PhProject).all()])
