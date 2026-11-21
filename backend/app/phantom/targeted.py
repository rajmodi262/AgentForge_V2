"""Targeted Firecrawl scouting — three jobs beyond the general hunt.

    python -m app.phantom.targeted gaps        # recall gaps: sites the recall check says we missed
    python -m app.phantom.targeted official    # official sources: approvals, clearances, utility & investment notices
    python -m app.phantom.targeted outcomes    # what happened to projects first seen before the backtest cutoff
    python -m app.phantom.targeted filings     # exchange / clearance / regulator filings for the fair-test projects

Each job writes search queries, runs them through Firecrawl search, reads the hits
(direct fetch first, Firecrawl fallback, robots.txt respected) and stores them as normal
articles (feed = gaps | official | outcomes). The extractor and verifier then treat them
exactly like any other source: nothing is trusted because of where it came from.

Credit budget per job: PHANTOM_FIRECRAWL_BUDGET (or --budget N). Jobs can run in
parallel; set PHANTOM_FIRECRAWL_INTERVAL so their combined rate stays under the plan limit.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from app.phantom import firecrawl
from app.phantom.sources import fetch_all, is_relevant, search
from app.phantom.store import save_articles

CUTOFF = datetime(2024, 6, 30, tzinfo=timezone.utc)   # backtest: score as of this date, outcome after it
ROOT = Path(__file__).resolve().parents[3]

# Official / primary domains: governments, investment agencies, utilities, regulators, exchanges
OFFICIAL = {
    "india": ["pib.gov.in", "parivesh.nic.in", "investindia.gov.in", "maharashtra.gov.in", "telangana.gov.in",
              "tn.gov.in", "up.gov.in", "ap.gov.in", "mahadiscom.in", "bseindia.com", "nseindia.com"],
    "malaysia": ["mida.gov.my", "tnb.com.my", "johor.gov.my", "investselangor.my", "iskandarmalaysia.com.my",
                 "bursamalaysia.com", "mdec.my"],
}
OFFICIAL_TOPICS = {
    "india": ["data centre approved state cabinet MW", "data centre policy approval investment data center",
              "data center environmental clearance MW", "data centre land allotment acres", "data centre power supply MW substation"],
    "malaysia": ["data centre approved investment MW", "data centre electricity supply agreement MW",
                 "data centre green lane approval", "data centre land acquisition acres Johor", "data centre MIDA approved projects"],
}


def _q(developer, project, place) -> str:
    """Short search query: developer + project + place, without parentheses or repeated words."""
    import re as _re
    words, seen = [], set()
    for w in _re.sub(r"\([^)]*\)", " ", f"{developer or ''} {project or ''} {place or ''} data centre").split():
        k = w.lower().strip(",.")
        if k and k not in seen:
            seen.add(k)
            words.append(w)
    return " ".join(words)


def gap_queries() -> Dict[str, List[str]]:
    from app.phantom.recall import load_reference, match, projects_from_db
    rows = match(load_reference(), projects_from_db())
    out: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        if r["pipeline"] and r["verdict"] in ("missing", "other_site", "place_unknown"):
            region = "india" if r["country"] == "India" else "malaysia"
            out[region].append(_q(r["developer"], r["project"], r["city"]))
    out["india"] += ["Kolkata data centre MW hyperscale", "New Town Kolkata data centre campus", "West Bengal data centre MW investment"]
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def official_queries() -> Dict[str, List[str]]:
    return {region: [f"{topic} site:{dom}" for dom in doms[:4] for topic in OFFICIAL_TOPICS[region][:2]]
            + [f"{topic} site:{doms[i % len(doms)]}" for i, topic in enumerate(OFFICIAL_TOPICS[region][2:], start=4)]
            for region, doms in OFFICIAL.items()}


def outcome_projects() -> List[Dict]:
    from app.database import SessionLocal
    from app.phantom.models import PhProject
    db = SessionLocal()
    try:
        return [{"id": str(p.id), "name": p.name, "developer": p.developer, "city": p.city, "state": p.state, "country": p.country}
                for p in db.query(PhProject).filter(PhProject.first_seen <= CUTOFF).all()]
    finally:
        db.close()


def outcome_queries() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = defaultdict(list)
    for p in outcome_projects():
        region = "india" if p["country"] == "India" else "malaysia"
        where = p["city"] or p["state"] or ""
        out[region].append(_q(p["developer"], p["name"], where))
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


# ── Filings: pre-construction evidence for the backtest's fair-test projects ──
# News rarely separates real projects from talk before ground is broken (PHANTOM_EVAL §6.2);
# exchange disclosures, clearances and regulator orders might. Every fair-test project is
# searched the same way, whatever its outcome, and only up to the last fitting cutoff:
# the backtest still ignores anything published after each cutoff.
FILINGS = {
    "india": ["bseindia.com", "nseindia.com", "parivesh.nic.in", "environmentclearance.nic.in"],
    "malaysia": ["bursamalaysia.com", "mida.gov.my", "st.gov.my", "tnb.com.my"],
    "singapore": ["sgx.com", "edb.gov.sg", "imda.gov.sg"],
    "indonesia": ["idx.co.id", "bkpm.go.id", "investindonesia.go.id"],
}
FILINGS_TBS = f"cdr:1,cd_min:1/1/2018,cd_max:{CUTOFF.month}/{CUTOFF.day}/{CUTOFF.year}"


def filings_projects() -> List[Dict]:
    """The projects the fair test scores: not yet under construction at a cutoff used for fitting."""
    from app.phantom import backtest as B
    res = B.run()
    out: Dict[str, Dict] = {}
    for r in res["pooled_rows"]:
        if r["stage_then"] not in B.PROGRESS and r["cutoff"] in res["fit_cutoffs"]:
            out.setdefault(r["project"], {"name": r["name"], "developer": r["developer"], "country": r["country"]})
    return list(out.values())


def filings_queries(projects: List[Dict] = None) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = defaultdict(list)
    for p in filings_projects() if projects is None else projects:
        region = (p["country"] or "").lower()
        if region in FILINGS:
            sites = " OR ".join(f"site:{d}" for d in FILINGS[region])
            out[region].append(f"{_q(p['developer'], p['name'], None)} ({sites})")
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s/.-]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?[\s/.,-]+(\d{4})\b"
                   r"|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b"
                   r"|\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b", re.I)


def date_in_text(text: str, today: datetime = None) -> datetime | None:
    """A filing's date when the search result has none: the LATEST explicit date in its opening.
    Taking the latest errs late, so a filing can only drop out of a cutoff, never leak into one early.
    Numeric dates are read day-first (Indian, Malaysian and Singapore style)."""
    today = today or datetime.now(timezone.utc)
    found = []
    for m in _DATE.finditer(text[:2000]):
        try:
            if m.group(3):
                d = datetime.strptime(f"{m.group(1)} {m.group(2)[:3]} {m.group(3)}", "%d %b %Y")
            elif m.group(6):
                d = datetime.strptime(f"{m.group(5)} {m.group(4)[:3]} {m.group(6)}", "%d %b %Y")
            else:
                d = datetime(int(m.group(9)), int(m.group(8)), int(m.group(7)))
        except ValueError:
            continue
        d = d.replace(tzinfo=timezone.utc)
        if d <= today:
            found.append(d)
    return max(found) if found else None


async def _search_filings(qs: List[str], region: str) -> list:
    import httpx
    from app.phantom.sources import HEADERS, REGIONS
    items, seen = [], set()
    async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for q in qs:
            for it in await firecrawl.search(client, q, REGIONS[region]["country"], tbs=FILINGS_TBS):
                if it.url not in seen:
                    seen.add(it.url)
                    items.append(it)
    return items


HISTORY_YEARS = range(2019, 2024)


def history_queries() -> Dict[str, List[str]]:
    """Older announcements (2019–2023), so the backtest has more projects old enough to judge.
    Free feeds only: Google News takes a date range (`after:` / `before:`); Bing gets the year as a word."""
    from collections import Counter
    from app.database import SessionLocal
    from app.phantom.models import PhProject
    from app.phantom.sources import REGIONS
    db = SessionLocal()
    try:
        seen = Counter((p.country, p.developer) for p in db.query(PhProject).all() if p.developer)
    finally:
        db.close()
    out: Dict[str, List[str]] = {}
    for region, cfg in REGIONS.items():
        devs = list(dict.fromkeys([d for (c, d), _ in seen.most_common() if c == cfg["country"]][:22] + cfg["developers"]))
        qs = []
        for y in HISTORY_YEARS:
            span = f"after:{y}-01-01 before:{y}-12-31"
            qs += [f"{d} data centre {span}" for d in devs]
            qs += [f"data centre {pl} MW {span}" for pl in cfg["places"]]
            qs += [f"{d} data centre {cfg['country']} {y}" for d in devs[:12]]          # Bing: full text where the publisher allows it
            qs += [f"hyperscale data centre {pl} {y} MW" for pl in cfg["places"][:5]]
        out[region] = list(dict.fromkeys(qs))
    return out


async def _search_free(qs: List[str], region: str, chunk: int = 10, pause: float = 2.0) -> list:
    """Dated queries go to Google News, the rest to Bing News; in small paced batches so neither feed throttles us."""
    items, seen = [], set()
    for feed, group in (("google", [q for q in qs if "after:" in q]), ("bing", [q for q in qs if "after:" not in q])):
        for i in range(0, len(group), chunk):
            for it in await search(group[i:i + chunk], region, feeds=(feed,)):
                if it.url not in seen:
                    seen.add(it.url)
                    items.append(it)
            await asyncio.sleep(pause)
    return items


JOBS = {"gaps": gap_queries, "official": official_queries, "outcomes": outcome_queries, "history": history_queries,
        "filings": filings_queries}


async def run(job: str, budget: int) -> Dict:
    queries = JOBS[job]()
    firecrawl.reset_budget(budget)
    stats = {"job": job, "queries": sum(len(v) for v in queries.values()), "found": 0, "relevant": 0, "full_text": 0, "new": 0}
    for region, qs in queries.items():
        try:
            if job == "history":
                items = await _search_free(qs, region)
            elif job == "filings":
                items = await _search_filings(qs, region)
            else:
                items = await search(qs, region, feeds=("firecrawl",))
        except firecrawl.BudgetExceeded:
            items = []
        items = [replace(i, feed=job) for i in items]
        stats["found"] += len(items)
        # read only what can matter: the headline/snippet already looks like data-centre project news
        keep = [i for i in items if is_relevant(i.title, i.summary) or job in ("official", "filings")]
        fetched = await fetch_all(keep, concurrency=3)
        if job == "filings":  # undated filings get the date they state; still none → kept, but outside the backtest
            fetched = [a if a.item.published_at else replace(a, item=replace(a.item, published_at=date_in_text(a.text))) for a in fetched]
            stats["dated"] = sum(1 for a in fetched if a.item.published_at)
        saved = await asyncio.to_thread(save_articles, fetched)
        stats["relevant"] += sum(1 for a in fetched if is_relevant(a.item.title, a.text))
        stats["full_text"] += sum(1 for a in fetched if a.text_kind == "full")
        stats["new"] += saved["new"]
    b = firecrawl.budget()
    stats.update(credits=b.spent, calls=b.calls)
    (ROOT / f"phantom_targeted_{job}.json").write_text(json.dumps({**stats, "queries_by_region": queries}, indent=2, default=str), encoding="utf-8")
    return stats


def main(argv: List[str]) -> None:
    job = next((a for a in argv if a in JOBS), None)
    if not job:
        sys.exit(f"usage: python -m app.phantom.targeted {'|'.join(JOBS)} [--budget N] [--dry-run]")
    if "--dry-run" in argv:
        for region, qs in JOBS[job]().items():
            print(f"{region}: {len(qs)} queries")
            for q in qs[:8]:
                print("  ", q)
        return
    if job != "history" and not firecrawl.enabled():
        sys.exit("FIRECRAWL_API_KEY is not set in backend/.env")
    budget = int(argv[argv.index("--budget") + 1]) if "--budget" in argv else 120
    print(asyncio.run(run(job, budget)))


if __name__ == "__main__":
    main(sys.argv[1:])
