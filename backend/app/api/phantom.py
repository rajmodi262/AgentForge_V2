"""Phantom Hunter API.

Reads are public (the data is public news); anything that spends LLM time or
changes data (hunt, rebuild, debate, ask) requires a logged-in user.
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database import get_db
from app.models.db_models import User
from app.phantom.models import PhAnomaly, PhArticle, PhEvidence, PhMention, PhProject, PhRun
from app.phantom.score import LAYERS

router = APIRouter(prefix="/phantom", tags=["Phantom Hunter"])


def _uuid(v):
    try:
        return UUID(str(v))
    except (ValueError, TypeError):
        return None


def _project_row(p: PhProject) -> dict:
    return {
        "id": str(p.id), "name": p.name, "developer": p.developer, "city": p.city, "state": p.state, "country": p.country,
        "lat": p.lat, "lon": p.lon, "capacity_mw": p.capacity_mw, "capacity_basis": p.capacity_basis,
        "target_year": p.target_year, "power_partner": p.power_partner, "ai_density": p.ai_density,
        "stage": p.stage, "stage_name": LAYERS[p.stage or 0], "reality_score": p.reality_score,
        "reality_mw": round((p.capacity_mw or 0) * (p.reality_score or 0), 1),
        "weakest_assumption": p.weakest_assumption, "n_sources": p.n_sources,
        "call_segments": p.call_segments, "has_debate": bool(p.debate),
        "last_seen": p.last_seen.isoformat() if p.last_seen else None,
        "grid_position": (p.power or {}).get("grid_position", "NO_EVIDENCE"), "grid_label": (p.power or {}).get("grid_label"),
        "power": {k: v for k, v in (p.power or {}).items() if k != "facts"},
    }


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    projects = db.query(PhProject).all()
    by_country = defaultdict(lambda: {"projects": 0, "announced_mw": 0.0, "reality_mw": 0.0, "with_capacity": 0})
    by_state = defaultdict(lambda: {"projects": 0, "announced_mw": 0.0, "reality_mw": 0.0})
    for p in projects:
        for bucket, key in ((by_country, p.country or "Unknown"), (by_state, f"{p.state or p.city or 'Place not stated'}, {p.country or '?'}")):
            b = bucket[key]
            b["projects"] += 1
            if p.capacity_mw:
                b["announced_mw"] += p.capacity_mw
                b["reality_mw"] += p.capacity_mw * (p.reality_score or 0)
                if "with_capacity" in b:
                    b["with_capacity"] += 1
    arts = Counter(k for (k,) in db.query(PhArticle.text_kind).all())
    rel = db.query(PhArticle).filter(PhArticle.relevant == True).count()  # noqa: E712
    done = db.query(PhArticle).filter(PhArticle.extracted == True).count()  # noqa: E712
    from app.phantom.evaluate import claim_tally
    ok_claims, n_claims = claim_tally(v for (v,) in db.query(PhMention.verification).all())
    n_mentions = db.query(PhMention).count()
    anomalies = Counter(k for (k,) in db.query(PhAnomaly.kind).all())
    return {
        "projects": len(projects),
        "announced_mw": round(sum(p.capacity_mw or 0 for p in projects), 1),
        "reality_mw": round(sum((p.capacity_mw or 0) * (p.reality_score or 0) for p in projects), 1),
        "by_country": {k: {**v, "announced_mw": round(v["announced_mw"], 1), "reality_mw": round(v["reality_mw"], 1)} for k, v in by_country.items()},
        "by_state": sorted(({"place": k, **{kk: round(vv, 1) if isinstance(vv, float) else vv for kk, vv in v.items()}} for k, v in by_state.items()),
                           key=lambda x: -x["announced_mw"])[:15],
        "stages": {LAYERS[i]: sum(1 for p in projects if (p.stage or 0) == i) for i in range(6)},
        "articles": {"total": sum(arts.values()), "full_text": arts.get("full", 0), "headline_only": arts.get("summary", 0),
                     "relevant": rel, "extracted": done},
        "mentions": n_mentions,
        "claims": n_claims,
        "claims_verified_pct": round(100 * ok_claims / n_claims, 1) if n_claims else None,
        "anomalies": dict(anomalies),
    }


@router.get("/projects")
def list_projects(country: Optional[str] = None, min_score: float = 0.0, segment: Optional[str] = None,
                  sort: str = Query("reality_mw", pattern="^(reality_mw|capacity_mw|reality_score|priority|name)$"),
                  limit: int = Query(200, le=1000), db: Session = Depends(get_db)):
    q = db.query(PhProject)
    if country:
        q = q.filter(PhProject.country == country)
    rows = [_project_row(p) for p in q.all() if (p.reality_score or 0) >= min_score]
    if sort == "priority" and segment:
        rows.sort(key=lambda r: -((r["call_segments"] or {}).get(segment, {}).get("priority", 0)))
    elif sort == "name":
        rows.sort(key=lambda r: r["name"].lower())
    else:
        rows.sort(key=lambda r: -(r.get(sort) or 0))
    return {"total": len(rows), "projects": rows[:limit]}


@router.get("/who-to-call")
def who_to_call(segment: str = Query("power", pattern="^(power|electrical|cooling)$"), limit: int = 10, db: Session = Depends(get_db)):
    rows = []
    for p in db.query(PhProject).all():
        seg = (p.call_segments or {}).get(segment)
        if seg and seg["priority"] > 0:
            rows.append({**_project_row(p), "priority": seg["priority"], "reasons": seg["reasons"]})
    rows.sort(key=lambda r: -r["priority"])
    return {"segment": segment, "projects": rows[:limit]}


@router.get("/power")
def power(country: Optional[str] = None, db: Session = Depends(get_db)):
    """Power forensics for the portfolio: grid position (secured vs unsecured), on-site generation,
    cooling and procurement signals — plus the projects behind each number."""
    from app.phantom import power as P
    q = db.query(PhProject)
    if country:
        q = q.filter(PhProject.country == country)
    ps = q.all()
    head = P.headline([{"capacity_mw": p.capacity_mw, "stage": p.stage, "power": p.power} for p in ps])
    rows = sorted((_project_row(p) for p in ps), key=lambda r: -(r["capacity_mw"] or 0))
    by_pos = {k: [r for r in rows if r["grid_position"] == k][:25] for k in P.GRID_POSITIONS}
    return {"headline": head, "labels": P.GRID_LABEL, "secured_positions": sorted(P.SECURED), "projects_by_position": by_pos,
            "note": "NO_EVIDENCE means nothing was found in public sources — not proof that no agreement exists."}


@router.get("/merge-candidates")
def merge_candidates(limit: int = Query(40, le=200), db: Session = Depends(get_db)):
    """Pairs of projects that look like the same site but were kept apart — for a person to settle."""
    from app.phantom import merge as M
    decided = M.load_decisions(db)
    projects = M.projects_for_review(db)
    cands = M.candidates(projects, decided, limit)
    by_anchor = {p["anchor"]: p for p in projects if p["anchor"]}
    history = [{"a": by_anchor.get(a, {"anchor": a, "name": "(merged away)"}), "b": by_anchor.get(b, {"anchor": b, "name": "(merged away)"}), "decision": d}
               for (a, b), d in decided.items()]
    return {"candidates": cands, "decided": history, "double_counted_mw": round(sum(c["double_counted_mw"] or 0 for c in cands if c["score"] >= 0.8), 1),
            "note": "A merge is applied on the next rebuild and can be changed at any time."}


class MergeBody(BaseModel):
    a: str = Field(..., min_length=32, max_length=40)
    b: str = Field(..., min_length=32, max_length=40)
    decision: str = Field(..., pattern="^(merge|distinct)$")


@router.post("/merge-decisions")
async def merge_decision(body: MergeBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Record one human decision and rebuild, so the tracker reflects it straight away."""
    from app.phantom import merge as M
    from app.phantom.pipeline import rebuild_projects
    try:
        saved = M.decide(db, body.a, body.b, body.decision, getattr(user, "email", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    res = await asyncio.to_thread(rebuild_projects) if body.decision == M.MERGE else None
    return {**saved, "rebuilt": res}


class ImportBody(BaseModel):
    csv: str = Field(..., min_length=5, max_length=2_000_000)


@router.post("/import")
def import_list(body: ImportBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Score someone else's project list: match each row to a tracked project and return its reality layer."""
    from app.phantom import importer as I
    try:
        rows = I.parse(body.csv)
    except (ValueError, Exception) as e:   # malformed CSV is the caller's problem, not a 500
        raise HTTPException(400, f"Could not read the CSV: {e}")
    return I.match(rows, I.tracked_from_db(db))


@router.get("/model")
def model(db: Session = Depends(get_db)):
    """Everything the what-if panel needs to re-score the whole portfolio in the browser:
    the prior table (stated and fitted), every adjustment weight, and which adjustments apply to each project.
    score = sigmoid(logit(prior[stage]) + sum(weights[term])) — the same formula as score.reality."""
    from app.phantom import score as S
    by_label = {v.lower(): k for k, v in S.WEIGHT_LABELS.items()}

    def key(b):
        if b.get("key"):
            return b["key"]
        t = (b.get("term") or "").lower()          # rows scored before terms carried keys
        if t.startswith("evidence layer"):
            return "prior"
        if "independent sources" in t:
            return "multi_source"
        if t.startswith("named power partner"):
            return "power_partner"
        if t.startswith("gone quiet"):
            return "gone_quiet"
        return by_label.get(t, t.replace(" ", "_").replace("-", "_"))

    rows = []
    for p in db.query(PhProject).all():
        terms = [key(b) for b in p.score_breakdown or []]
        rows.append({"id": str(p.id), "name": p.name, "developer": p.developer, "country": p.country, "state": p.state,
                     "capacity_mw": p.capacity_mw, "stage": p.stage or 0, "cancelled": "cancelled" in terms,
                     "terms": [t for t in terms if t in S.WEIGHTS], "score": p.reality_score})
    return {"layers": LAYERS, "priors": {"stated": [S.PRIOR_ASSUMED[i] for i in range(6)], "active": [S.PRIOR[i] for i in range(6)],
                                         "fitted": [S.CALIBRATION["priors"][i] for i in range(6)] if S.CALIBRATION else None},
            "calibration": {k: v for k, v in (S.CALIBRATION or {}).items() if k in ("cases", "projects", "cutoffs", "fitted_on", "shrink", "layers")} or None,
            "weights": S.WEIGHTS, "weight_labels": S.WEIGHT_LABELS, "projects": rows}


@router.get("/timeline")
def timeline(db: Session = Depends(get_db)):
    """Every project with the date it was first reported and the date each evidence layer was first verified —
    enough for the browser to redraw the map as of any day."""
    first: dict = {}
    for e in db.query(PhEvidence).all():
        if e.event_date and e.layer in LAYERS:
            k = (e.project_id, e.layer)
            if k not in first or e.event_date < first[k]:
                first[k] = e.event_date
    rows, dates = [], []
    for p in db.query(PhProject).all():
        ev = sorted(({"layer": l, "date": d.date().isoformat()} for (pid, l), d in first.items() if pid == p.id), key=lambda x: x["date"])
        start = p.first_seen.date().isoformat() if p.first_seen else (ev[0]["date"] if ev else None)
        if not start:
            continue
        dates.append(start)
        rows.append({"id": str(p.id), "name": p.name, "developer": p.developer, "country": p.country, "city": p.city, "lat": p.lat, "lon": p.lon,
                     "capacity_mw": p.capacity_mw, "first_seen": start, "events": ev, "stage": p.stage or 0, "reality_score": p.reality_score,
                     "grid_position": (p.power or {}).get("grid_position", "NO_EVIDENCE")})
    return {"projects": rows, "from": min(dates) if dates else None, "to": max((e["date"] for r in rows for e in r["events"]), default=None),
            "undated": db.query(PhProject).count() - len(rows)}


@router.get("/backtest")
def backtest():
    """The cached calibration backtest (python -m app.phantom.backtest --cache): cases, reliability tables, baselines, fitted priors."""
    import json
    from app.phantom.backtest import CACHE_FILE
    if not CACHE_FILE.exists():
        raise HTTPException(404, "No backtest has been cached yet — run: python -m app.phantom.backtest --cache")
    return json.loads(CACHE_FILE.read_text(encoding="utf-8"))


@router.get("/developers")
def developers(min_projects: int = Query(1, ge=1), limit: int = Query(50, le=300), db: Session = Depends(get_db)):
    """Track record per developer: how much of what they announced reached construction, and how fast."""
    from app.phantom.track import JUDGE_AFTER_MONTHS, MIN_JUDGED, from_db
    rows = [r for r in from_db(db) if r["projects"] >= min_projects]
    return {"developers": rows[:limit], "total": len(rows),
            "note": f"build_rate counts only projects first seen {JUDGE_AFTER_MONTHS}+ months ago and needs {MIN_JUDGED}+ of them."}


@router.get("/signals")
def signals(limit: int = Query(15, le=50), db: Session = Depends(get_db)):
    """Latest verified evidence across all projects — the 'what changed' feed."""
    rows = (db.query(PhEvidence, PhProject, PhArticle)
            .join(PhProject, PhEvidence.project_id == PhProject.id)
            .join(PhArticle, PhEvidence.article_id == PhArticle.id)
            .order_by(PhEvidence.event_date.desc().nullslast()).limit(limit * 3).all())
    seen, out = set(), []
    for e, p, a in rows:
        key = (p.id, e.layer)
        if key in seen:
            continue
        seen.add(key)
        out.append({"project_id": str(p.id), "project": p.name, "layer": e.layer, "quote": (e.quote or "")[:220],
                    "date": e.event_date.isoformat() if e.event_date else None, "source": a.source, "url": a.url,
                    "reality_score": p.reality_score, "country": p.country})
        if len(out) >= limit:
            break
    anomalies = [{"project_id": str(p.id), "project": p.name, "kind": an.kind, "severity": an.severity, "message": an.message}
                 for an, p in db.query(PhAnomaly, PhProject).join(PhProject, PhAnomaly.project_id == PhProject.id).all()]
    order = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda x: order.get(x["severity"], 3))
    return {"signals": out, "anomalies": anomalies[:limit]}


@router.get("/projects/{project_id}")
def project_detail(project_id: UUID, db: Session = Depends(get_db)):
    p = db.query(PhProject).filter(PhProject.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    ev = db.query(PhEvidence).filter(PhEvidence.project_id == p.id).all()
    arts = {a.id: a for a in db.query(PhArticle).filter(PhArticle.id.in_({e.article_id for e in ev} | {m.article_id for m in p.mentions})).all()}

    def art(aid):
        a = arts.get(aid)
        return {"url": a.url, "title": a.title, "source": a.source, "published": a.published_at.isoformat() if a and a.published_at else None,
                "text_kind": a.text_kind} if a else None

    order = {l: i for i, l in enumerate(LAYERS)}
    evidence = sorted(({"layer": e.layer, "detail": e.detail, "quote": e.quote, "date": e.event_date.isoformat() if e.event_date else None,
                        "article": art(e.article_id)} for e in ev), key=lambda x: (order.get(x["layer"], 9), x["date"] or ""))
    return {
        **_project_row(p),
        "score_breakdown": p.score_breakdown, "debate": p.debate,
        "power_facts": [{**f, "article": art(_uuid(f.get("article_id")))} for f in (p.power or {}).get("facts", [])],
        "evidence": evidence,
        "anomalies": [{"kind": a.kind, "severity": a.severity, "message": a.message, "details": a.details} for a in p.anomalies],
        "mentions": [{"article": art(m.article_id), "verified_ratio": m.verified_ratio, "verification": m.verification, "data": m.data}
                     for m in p.mentions],
        "ladder": [{"layer": l, "reached": (p.stage or 0) >= i and any(e["layer"] == l for e in evidence) or (p.stage or 0) > i,
                    "verified": any(e["layer"] == l for e in evidence)} for i, l in enumerate(LAYERS)],
    }


@router.post("/projects/{project_id}/debate")
async def debate(project_id: UUID, refresh: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.phantom.debate import run_debate
    p = db.query(PhProject).filter(PhProject.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    if p.debate and not refresh:
        return p.debate
    detail = project_detail(project_id, db)
    if not detail["evidence"]:
        raise HTTPException(400, "No verified evidence to debate yet")
    result = await run_debate(detail, [{**e, "event_date": e["date"]} for e in detail["evidence"]])
    p.debate = result
    db.commit()
    return result


class AskBody(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@router.post("/ask")
async def ask(body: AskBody, user: User = Depends(get_current_user)):
    from app.phantom.chat import ask as run_ask
    return await run_ask(body.question)


class HuntBody(BaseModel):
    region: str = Field("malaysia", pattern="^(malaysia|india|singapore|indonesia)$")
    max_rounds: int = Field(2, ge=1, le=3)


@router.post("/hunt")
async def start_hunt(body: HuntBody, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.phantom.pipeline import run_hunt
    if db.query(PhRun).filter(PhRun.status == "running").count():
        raise HTTPException(409, "A hunt is already running")
    run = PhRun(region=body.region, status="running", stats={}, log=[])
    db.add(run)
    db.commit()
    background.add_task(run_hunt, str(run.id), body.region, body.max_rounds)
    return {"run_id": str(run.id), "websocket_url": f"/api/v1/ws/hunt-{run.id}"}


@router.post("/projects/{project_id}/investigate")
async def investigate(project_id: UUID, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Send the Investigator after this project's weakest assumption. Streams its steps over the websocket."""
    from app.phantom.investigate import run as run_investigation
    if not db.query(PhProject).filter(PhProject.id == project_id).first():
        raise HTTPException(404, "Project not found")
    if db.query(PhRun).filter(PhRun.status == "running").count():
        raise HTTPException(409, "A hunt or investigation is already running")
    run = PhRun(region=f"investigate:{project_id}", status="running", stats={}, log=[])
    db.add(run)
    db.commit()
    background.add_task(run_investigation, str(run.id), str(project_id))
    return {"run_id": str(run.id), "websocket_url": f"/api/v1/ws/hunt-{run.id}"}


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    r = db.query(PhRun).filter(PhRun.id == run_id).first()
    if not r:
        raise HTTPException(404, "Run not found")
    return {"id": str(r.id), "region": r.region, "status": r.status, "stats": r.stats, "log": r.log,
            "started_at": r.started_at.isoformat() if r.started_at else None, "finished_at": r.finished_at.isoformat() if r.finished_at else None}


@router.post("/rebuild")
async def rebuild(user: User = Depends(get_current_user)):
    from app.phantom.pipeline import rebuild_projects
    return await asyncio.to_thread(rebuild_projects)


# ─── Business exports: the dashboard's data as Excel / CSV (Sheets, Power BI) ───

BOM = chr(0xFEFF)  # lets Excel open UTF-8 CSVs (₹, en dashes) correctly
EXPORT_TABLES = ("projects", "who_to_call", "evidence", "anomalies", "score_terms", "articles")


@router.get("/export.xlsx")
def export_xlsx(db: Session = Depends(get_db)):
    """Formatted workbook: KPI summary, filterable tables, live SUMIFS analysis, native charts."""
    from app.phantom.export import build_xlsx, tables
    return Response(build_xlsx(tables(db)), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="PhantomHunter.xlsx"'})


@router.get("/export/{table}.csv")
def export_csv(table: str, db: Session = Depends(get_db)):
    """One star-schema table as UTF-8 CSV — imports directly into Google Sheets or Power BI."""
    if table not in EXPORT_TABLES:
        raise HTTPException(404, f"Unknown table. Choose one of: {', '.join(EXPORT_TABLES)}")
    from app.phantom.export import tables, to_csv
    return Response(BOM + to_csv(tables(db)[table]), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="phantom_{table}.csv"'})
