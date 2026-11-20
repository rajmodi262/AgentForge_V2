"""Investigator: one agent, one project, one question — "is the weakest assumption still true?"

The hunt casts a wide net. The investigator goes after the single missing piece of evidence
that would move one project's score most (score.weakest_assumption), and stops on its own:

    observe   what is the weakest assumption now, and what has already been tried?
    decide    which search would settle it — and if the last one found nothing, how to
              widen it (drop the place, then try the developer's own wording)
    act       search the free news feeds, read what is relevant (robots.txt respected),
              extract and verify with the same pipeline as everything else, re-score
    stop      the score moved (found it), the assumption changed, or the budget is spent

Every step is recorded as {step, thought, action, result}, so the trace reads like an
analyst's notes. The decisions are rules, deliberately: cheap, repeatable, explainable.
The reading is the LLM and the verifier, exactly as in the hunt — nothing here can add a
claim the verifier would reject.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_STEPS = 4
MAX_READ = 6         # articles read per step: keeps one investigation to a few minutes on a laptop model

# what to search for, per missing piece of evidence (the weakest assumption's wording)
ANGLES = [
    ("power", "power is secured", ["{dev} {place} data centre power supply agreement", "{dev} {place} data centre electricity substation MW"]),
    ("BUILDING", "construction has started", ["{dev} {place} data centre construction begins", "{dev} {place} data centre groundbreaking"]),
    ("LIVE", "operational", ["{dev} {place} data centre opens operational", "{dev} {place} data centre inaugurated"]),
    ("land", "land or a site", ["{dev} {place} data centre land acres", "{dev} {place} data centre site acquired"]),
    ("permit", "permits or government approval", ["{dev} {place} data centre approval cabinet", "{dev} {place} data centre clearance"]),
    ("source", "uncorroborated", ["{dev} {name} data centre", "{dev} {place} data centre MW"]),
    ("headline", "headlines", ["{dev} {name} data centre", "{dev} {place} data centre"]),
]


def plan(weakest: str, dev: str, place: str, name: str, tried: List[str], last_found: Optional[int]) -> Optional[Dict[str, str]]:
    """The next search, or None when every sensible query has been tried."""
    w = (weakest or "").lower()
    angle = next((a for a in ANGLES if a[1].lower() in w), ANGLES[5])
    widen = last_found == 0
    for template in angle[2]:
        for where in ([place, ""] if place else [""]):
            if widen and where and any(place in t for t in tried):
                continue                                  # the place-specific query found nothing: drop the place
            q = " ".join(template.format(dev=dev or "", place=where, name=name).split())
            if q and q not in tried:
                why = f"not yet proven: {angle[1]}"
                if widen:
                    why += "; the last search found nothing new, so widening it"
                return {"angle": angle[0], "query": q, "why": why}
    return None


async def _search_and_read(query: str, region: str) -> Dict[str, Any]:
    from app.phantom.extract import extract_article
    from app.phantom.models import PhArticle
    from app.phantom.sources import fetch_all, is_relevant, search
    from app.phantom.store import save_articles, save_mentions
    from app.database import SessionLocal
    items = await search([query], region, feeds=("bing", "google"))
    keep = [i for i in items if is_relevant(i.title, i.summary)][:MAX_READ * 2]
    fetched = await fetch_all(keep, concurrency=4)
    saved = await asyncio.to_thread(save_articles, fetched)
    urls = [a.item.url for a in fetched]
    db = SessionLocal()
    try:
        todo = [(a.id, a.title, a.text, a.published_at) for a in db.query(PhArticle).filter(PhArticle.url.in_(urls), PhArticle.extracted == False,  # noqa: E712
                                                                                             PhArticle.relevant == True).limit(MAX_READ).all()]  # noqa: E712
    finally:
        db.close()
    mentions = 0
    for aid, title, text, pub in todo:
        try:
            r = await extract_article(title, text or "", str(pub) if pub else None, region)
            mentions += await asyncio.to_thread(save_mentions, aid, r["mentions"], r["meta"].get("model") or "")
        except Exception as e:  # one bad article never stops the investigation
            logger.warning(f"[investigate] extract failed: {e!r}")
    return {"results": len(items), "relevant": len(keep), "new_articles": saved["new"], "read": len(todo), "mentions": mentions}


def _snapshot(db, anchor: str) -> Optional[Dict[str, Any]]:
    """The project that now owns the anchor mention (ids can change when projects merge)."""
    from app.phantom.models import PhEvidence, PhMention, PhProject
    m = db.query(PhMention).filter(PhMention.id == anchor).first()
    p = db.query(PhProject).filter(PhProject.id == m.project_id).first() if m and m.project_id else None
    if not p:
        return None
    return {"id": str(p.id), "name": p.name, "developer": p.developer, "city": p.city, "state": p.state, "country": p.country,
            "score": p.reality_score, "stage": p.stage, "weakest": p.weakest_assumption, "n_sources": p.n_sources,
            "grid_position": (p.power or {}).get("grid_position", "NO_EVIDENCE"),
            "evidence": db.query(PhEvidence).filter(PhEvidence.project_id == p.id).count()}


async def investigate(project_id: str, emit=None, max_steps: int = MAX_STEPS) -> Dict[str, Any]:
    """Run one investigation. `emit(dict)` (optional) receives every trace step as it happens."""
    from app.database import SessionLocal
    from app.phantom.models import PhMention
    from app.phantom.pipeline import rebuild_projects

    async def say(step: Dict[str, Any]):
        trace.append(step)
        if emit:
            await emit(step)

    db = SessionLocal()
    try:
        anchor = min((str(i) for (i,) in db.query(PhMention.id).filter(PhMention.project_id == project_id).all()), default=None)
        start = _snapshot(db, anchor) if anchor else None
    finally:
        db.close()
    if not start:
        raise ValueError("project not found")
    trace: List[Dict[str, Any]] = []
    region = "malaysia" if start["country"] == "Malaysia" else "india"
    place = start["city"] or start["state"] or ""
    cur, tried, last_found, stop = start, [], None, "budget"
    await say({"step": 0, "thought": f"Starting on {start['name']}: {round((start['score'] or 0) * 100)}% real, {start['evidence']} verified evidence items.",
               "action": "read the weakest assumption", "result": start["weakest"]})
    for step in range(1, max_steps + 1):
        nxt = plan(cur["weakest"], cur["developer"] or "", place, cur["name"], tried, last_found)
        if not nxt:
            stop = "exhausted"
            await say({"step": step, "thought": "Every sensible search for this assumption has been tried.", "action": "stop", "result": None})
            break
        tried.append(nxt["query"])
        await say({"step": step, "thought": nxt["why"].capitalize() + ".", "action": f'search: "{nxt["query"]}"', "result": None})
        try:
            got = await _search_and_read(nxt["query"], region)
        except Exception as e:
            await say({"step": step, "thought": "The search failed; trying the next angle.", "action": "error", "result": str(e)[:200]})
            last_found = 0
            continue
        last_found = got["new_articles"]
        if got["mentions"]:
            await asyncio.to_thread(rebuild_projects)
            db = SessionLocal()
            try:
                after = _snapshot(db, anchor) or cur
            finally:
                db.close()
        else:
            after = cur
        moved = round((after["score"] or 0) - (cur["score"] or 0), 3)
        await say({"step": step, "thought": (f"Score moved {'+' if moved > 0 else ''}{round(moved * 100)} points." if moved else
                                             "Nothing new about this project." if not got["mentions"] else "New mentions, but the score did not move."),
                   "action": "read and verify", "result": got | {"score_after": after["score"], "weakest_after": after["weakest"]}})
        if moved or after["weakest"] != cur["weakest"]:
            cur, stop = after, "found"
            break
        cur = after
    out = {"project_id": cur["id"], "name": start["name"], "before": start, "after": cur, "stop": stop, "steps": len(tried), "trace": trace,
           "finished": datetime.now(timezone.utc).isoformat()}
    return out


async def run(run_id: str, project_id: str) -> None:
    """Background entry point: stream the trace to the websocket and store the result on the run."""
    from app.database import SessionLocal
    from app.phantom.models import PhRun
    from app.services.websocket_manager import ws_manager
    channel = f"hunt-{run_id}"

    async def emit(step):
        await ws_manager.broadcast(channel, {"type": "investigator_step", "agent": "Investigator", **step,
                                             "content": f"{step['thought']} → {step['action']}"})
    try:
        res = await investigate(project_id, emit)
        status, stats, log = "completed", {k: v for k, v in res.items() if k != "trace"}, res["trace"]
    except Exception as e:
        logger.exception("[investigate] failed")
        status, stats, log = "failed", {"error": str(e)}, []
    db = SessionLocal()
    try:
        r = db.query(PhRun).filter(PhRun.id == run_id).first()
        if r:
            r.status, r.stats, r.log, r.finished_at = status, stats, log, datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
    await ws_manager.broadcast(channel, {"type": "hunt_finished", "status": status, "stats": stats})
