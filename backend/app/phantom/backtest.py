"""Backtest calibration — does a 75% reality score mean 75%?

Without outcome labels the layer priors were stated assumptions. This replays history:

1. For each CUTOFF (mid-2022 … mid-2025) take every mention published on or before it and
   resolve + score the projects exactly as the system would have then
   (`score.reality(..., now=cutoff)`): nothing published later is visible.
2. Read the outcome from what verified evidence shows AFTER the cutoff (regular hunt +
   Firecrawl outcome scout): progressed = verified BUILDING or LIVE evidence.
3. Compare prediction with outcome three ways:
     calibration  reliability table + Brier score (is "70%" right 70% of the time?)
     ranking      AUC (does a higher score mean a likelier project?)
     baselines    always the base rate · a flat 35% (the Bernstein figure) · the evidence
                  layer alone — so the score has to beat simpler rules, not just exist.

Several cutoffs multiply the test cases, but a project scored at three cutoffs is not three
independent projects, so every confidence interval is a bootstrap that resamples PROJECTS.

Honest limits, printed with the numbers:
  * "not progressed" is absence of evidence, not proof of failure → observed rates are a lower bound;
  * later cutoffs have had less time to progress;
  * the score is tested hardest as a FILTER (calling phantoms). There are few high-scoring
    projects that were not already under construction, so its power to pick winners early is
    reported separately and is still weakly tested.

    python -m app.phantom.backtest
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.phantom import score as S
from app.phantom.targeted import CUTOFF

PROGRESS = {"BUILDING", "LIVE"}
NEGATIVE = {"CANCELLED", "DELAYED"}
CUTOFFS = [datetime(y, 6, 30, tzinfo=timezone.utc) for y in (2022, 2023, 2024, 2025)]
SCOPE = ("India", "Malaysia")
PHANTOM_CALL, LIKELY_CALL = 0.45, 0.60   # same bands the product shows


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _key(c: Dict[str, Any]) -> str:
    return str(min(str(i) for i in c["mention_ids"]))


def rows_at(mentions: List[Dict[str, Any]], cutoff: datetime, now_clusters: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Score every project as of `cutoff`, then read its outcome from evidence published after it."""
    from app.phantom.resolve import resolve
    before = [m for m in mentions if m["published"] and m["published"] <= cutoff]
    then = resolve([dict(m) for m in before])
    now = now_clusters if now_clusters is not None else resolve([dict(m) for m in mentions])
    owner = {mid: c for c in now for mid in c["mention_ids"]}
    rows = []
    for c in then:
        cur = next((owner[i] for i in c["mention_ids"] if i in owner), None)
        if cur is None or c["country"] not in SCOPE:
            continue
        # scored with the STATED priors, exactly as designed; `adj` keeps the adjustments so the same
        # case can be re-scored under any other prior table without replaying history
        p_then, br = S.reality(c, now=cutoff, priors=S.PRIOR_ASSUMED)
        stage_then = S.stage_of(c["events"])
        cancelled = any(b["term"] == "Cancelled" for b in br)
        adj = sum(b["delta"] for b in br if b.get("delta") is not None)
        later = [e for e in cur["events"] if _aware(e.get("published")) and _aware(e["published"]) > cutoff]
        layers_later = {e["layer"] for e in later}
        stage_now = S.stage_of(cur["events"])
        progressed = bool(layers_later & PROGRESS) or (stage_then >= 4 and stage_now >= 4)
        if layers_later & {"CANCELLED"}:
            progressed = False
        rows.append({"name": c["name"], "project": _key(cur), "developer": c["developer"], "country": c["country"],
                     "cutoff": cutoff.date().isoformat(), "reality_score": round(p_then, 3),
                     "stage_then": S.LAYERS[stage_then], "stage_now": S.LAYERS[stage_now], "progressed": progressed,
                     "prior_only": S.PRIOR_ASSUMED[stage_then], "adj": adj, "cancelled_then": cancelled, "n_sources_then": len(c["article_ids"]),
                     "news_after_cutoff": len({e["article_id"] for e in later}),
                     "negative_after": sorted(layers_later & NEGATIVE)})
    return rows


# ───────────────────────── metrics ─────────────────────────

def brier(pairs: List[Tuple[float, bool]]) -> Optional[float]:
    return sum((s - y) ** 2 for s, y in pairs) / len(pairs) if pairs else None


def auc(pairs: List[Tuple[float, bool]]) -> Optional[float]:
    """P(a progressed project outscored one that did not); ties count half. None if one class is empty."""
    pos, neg = [s for s, y in pairs if y], [s for s, y in pairs if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def bootstrap(rows: List[Dict[str, Any]], stat: Callable[[List[Dict[str, Any]]], Optional[float]], n: int = 1000, seed: int = 7) -> Optional[Tuple[float, float]]:
    """95% interval, resampling whole projects (a project seen at 3 cutoffs moves together)."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r["project"], []).append(r)
    keys = list(groups)
    if len(keys) < 8:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in groups[k]]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    if len(vals) < n // 2:
        return None
    vals.sort()
    return round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)


def evaluate(rows: List[Dict[str, Any]], ci: bool = True) -> Dict[str, Any]:
    if not rows:
        return {"n": 0}
    pairs = lambda rs, f="reality_score": [(r[f], r["progressed"]) for r in rs]  # noqa: E731
    base = sum(r["progressed"] for r in rows) / len(rows)
    b_model = brier(pairs(rows))
    baselines = {"base_rate": base * (1 - base), "flat_35": brier([(0.35, r["progressed"]) for r in rows]),
                 "stage_only": brier(pairs(rows, "prior_only"))}
    table = S.calibrate(rows, {r["name"] + r["cutoff"]: r["progressed"] for r in rows}, key=lambda r: r["name"] + r["cutoff"])["table"]
    phantom = [r for r in rows if r["reality_score"] < PHANTOM_CALL]
    likely = [r for r in rows if r["reality_score"] >= LIKELY_CALL]
    out = {
        "n": len(rows), "projects": len({r["project"] for r in rows}), "base_rate": round(base, 3),
        "brier": round(b_model, 4), "auc": None if auc(pairs(rows)) is None else round(auc(pairs(rows)), 3),
        "baselines": {k: round(v, 4) for k, v in baselines.items()},
        "skill_vs_base_rate": round(1 - b_model / baselines["base_rate"], 3) if baselines["base_rate"] else None,
        "skill_vs_stage_only": round(1 - b_model / baselines["stage_only"], 3) if baselines["stage_only"] else None,
        "auc_stage_only": None if auc(pairs(rows, "prior_only")) is None else round(auc(pairs(rows, "prior_only")), 3),
        "table": table,
        "phantom_calls": {"n": len(phantom), "right": sum(not r["progressed"] for r in phantom),
                          "accuracy": round(sum(not r["progressed"] for r in phantom) / len(phantom), 3) if phantom else None},
        "likely_calls": {"n": len(likely), "right": sum(r["progressed"] for r in likely),
                         "accuracy": round(sum(r["progressed"] for r in likely) / len(likely), 3) if likely else None},
    }
    if ci:
        out["brier_ci"] = bootstrap(rows, lambda rs: brier(pairs(rs)))
        out["auc_ci"] = bootstrap(rows, lambda rs: auc(pairs(rs)))
    return out


def fitted_priors(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What the outcomes say each layer's prior should be (Laplace-smoothed), next to the stated assumption."""
    out = []
    for i, layer in enumerate(S.LAYERS):
        rs = [r for r in rows if r["stage_then"] == layer]
        k = sum(r["progressed"] for r in rs)
        out.append({"layer": layer, "assumed": S.PRIOR_ASSUMED[i], "n": len(rs), "progressed": k,
                    "observed": round(k / len(rs), 3) if rs else None, "fitted": round((k + 1) / (len(rs) + 2), 3) if rs else None})
    return out


# ───────────────────────── re-fitting the priors ─────────────────────────

SHRINK = 20          # pseudo-cases pulling each fitted prior towards the stated assumption
MATURE_YEARS = 2     # fit only on cutoffs old enough for a project to have broken ground
MIN_FIT_CASES = 40


def rescore(rows: List[Dict[str, Any]], priors: Dict[int, float]) -> List[Dict[str, Any]]:
    """The same cases under another prior table: logit(prior[layer]) + the recorded adjustments."""
    out = []
    for r in rows:
        i = S.LAYERS.index(r["stage_then"])
        score = 0.03 if r.get("cancelled_then") else S.sigmoid(S.logit(priors[i]) + r.get("adj", 0.0))
        out.append({**r, "reality_score": round(score, 3), "prior_only": priors[i]})
    return out


def fit(rows: List[Dict[str, Any]], shrink: int = SHRINK) -> Dict[int, float]:
    """Prior per layer = (progressed + shrink × assumed) / (cases + shrink), then forced to rise with the ladder.

    The shrinkage matters twice over: thin layers (ten POWER cases) must not swing the prior, and
    "no verified progress" under-counts real progress, so the data alone would be too pessimistic."""
    out, floor = {}, 0.0
    for i, layer in enumerate(S.LAYERS):
        rs = [r for r in rows if r["stage_then"] == layer]
        v = (sum(r["progressed"] for r in rs) + shrink * S.PRIOR_ASSUMED[i]) / (len(rs) + shrink)
        floor = max(floor, v)
        out[i] = round(min(0.99, floor), 3)
    return out


def cross_validate(rows: List[Dict[str, Any]], folds: int = 5, seed: int = 7) -> List[Dict[str, Any]]:
    """Out-of-sample scores: each project is scored with priors fitted on the OTHER projects only."""
    keys = sorted({r["project"] for r in rows})
    random.Random(seed).shuffle(keys)
    fold_of = {k: i % folds for i, k in enumerate(keys)}
    out = []
    for f in range(folds):
        train = [r for r in rows if fold_of[r["project"]] != f]
        test = [r for r in rows if fold_of[r["project"]] == f]
        out += rescore(test, fit(train))
    return out


def mature(rows: List[Dict[str, Any]], latest: datetime) -> List[Dict[str, Any]]:
    return [r for r in rows if (latest - datetime.fromisoformat(r["cutoff"]).replace(tzinfo=timezone.utc)).days >= 365 * MATURE_YEARS]


CACHE_FILE = S.CALIBRATION_FILE.with_name("backtest_cache.json")


def cache(res: Dict[str, Any]) -> Dict[str, Any]:
    """What the Calibration Lab and the Time Machine in the UI read: every case, both scorings, all the tables.
    Written to a file because replaying four cutoffs takes far longer than a page load."""
    import json
    import uuid
    fitted = res.get("fitted") or S.PRIOR_ASSUMED
    rows = []
    for r in rescore(res["pooled_rows"], fitted):
        stated = next(x for x in res["pooled_rows"] if x["project"] == r["project"] and x["cutoff"] == r["cutoff"])
        rows.append({"project_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"phantom:{r['project']}")), "name": r["name"], "developer": r["developer"],
                     "country": r["country"], "cutoff": r["cutoff"], "stage_then": r["stage_then"], "stage_now": r["stage_now"],
                     "progressed": r["progressed"], "score_stated": stated["reality_score"], "score_fitted": r["reality_score"],
                     "news_after": r["news_after_cutoff"], "sources_then": r["n_sources_then"]})
    keep = ("pooled", "pooled_pre_construction", "assumed_mature", "assumed_mature_pre", "cv", "cv_pre", "recent_assumed_pre", "recent_fitted_pre",
            "by_cutoff", "by_cutoff_pre_construction", "fitted_priors", "fit_cases", "fit_cutoffs", "cutoffs")
    out = {"generated": datetime.now(timezone.utc).isoformat(), "rows": rows, "fitted": {str(k): v for k, v in fitted.items()},
           "assumed": {str(k): v for k, v in S.PRIOR_ASSUMED.items()}, "shrink": SHRINK, "mature_years": MATURE_YEARS,
           "bands": {"phantom": PHANTOM_CALL, "likely": LIKELY_CALL}, **{k: res.get(k) for k in keep}}
    CACHE_FILE.write_text(json.dumps(out, default=str), encoding="utf-8")
    return out


def calibration(res: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The file score.py loads: fitted priors plus where they came from."""
    if not res.get("fitted"):
        return None
    return {"priors": {str(k): v for k, v in res["fitted"].items()}, "assumed": {str(k): v for k, v in S.PRIOR_ASSUMED.items()},
            "layers": res["fitted_priors"], "cases": res["fit_cases"]["n"], "projects": res["fit_cases"]["projects"],
            "cutoffs": res["fit_cutoffs"], "shrink": SHRINK, "fitted_on": datetime.now(timezone.utc).date().isoformat(),
            "method": "Beta-binomial shrinkage towards the stated priors, monotone in the evidence ladder; "
                      "outcome = verified BUILDING or LIVE evidence after the cutoff"}


def run(mentions: List[Dict[str, Any]] = None, cutoffs: Optional[List[datetime]] = None) -> Dict[str, Any]:
    from app.phantom.resolve import resolve
    if mentions is None:
        from app.database import SessionLocal
        from app.phantom.pipeline import _load_mentions
        db = SessionLocal()
        try:
            mentions = _load_mentions(db)
        finally:
            db.close()
    for m in mentions:
        m["published"] = _aware(m.get("published"))
    now = resolve([dict(m) for m in mentions])
    cutoffs = cutoffs or CUTOFFS
    per_cutoff = {c.date().isoformat(): rows_at(mentions, c, now) for c in cutoffs}
    pooled = [r for rs in per_cutoff.values() for r in rs]
    early = [r for r in pooled if r["stage_then"] not in PROGRESS]
    main = per_cutoff.get(CUTOFF.date().isoformat(), [])        # the single cutoff reported before: kept for continuity
    main_early = [r for r in main if r["stage_then"] not in PROGRESS]
    out = {
        "cutoff": CUTOFF.date().isoformat(), "cutoffs": list(per_cutoff), "rows": main, "pooled_rows": pooled,
        "all": S.calibrate(main, {r["name"]: r["progressed"] for r in main}),
        "pre_construction": S.calibrate(main_early, {r["name"]: r["progressed"] for r in main_early}),
        "with_news_after": sum(1 for r in main if r["news_after_cutoff"]),
        "pooled": evaluate(pooled), "pooled_pre_construction": evaluate(early),
        "by_cutoff": {k: evaluate(v, ci=False) for k, v in per_cutoff.items()},
        "by_cutoff_pre_construction": {k: evaluate([r for r in v if r["stage_then"] not in PROGRESS], ci=False) for k, v in per_cutoff.items()},
        "fitted_priors": fitted_priors(pooled),
    }
    # Re-fit the priors on cutoffs old enough to judge, and test the fit on projects it never saw
    latest = max((m["published"] for m in mentions if m["published"]), default=datetime.now(timezone.utc))
    fit_rows = mature(pooled, latest)
    out["fit_cutoffs"] = sorted({r["cutoff"] for r in fit_rows})
    out["fit_cases"] = {"n": len(fit_rows), "projects": len({r["project"] for r in fit_rows})}
    if len(fit_rows) >= MIN_FIT_CASES:
        cv = cross_validate(fit_rows)
        pre = lambda rs: [r for r in rs if r["stage_then"] not in PROGRESS]  # noqa: E731
        out["fitted"] = fit(fit_rows)
        out["fitted_priors"] = [{**f, "fitted": out["fitted"][i]} for i, f in enumerate(fitted_priors(fit_rows))]
        out["assumed_mature"] = evaluate(fit_rows)
        out["assumed_mature_pre"] = evaluate(pre(fit_rows))
        out["cv"] = evaluate(cv)
        out["cv_pre"] = evaluate(pre(cv))
        recent = [r for r in pooled if r not in fit_rows]
        out["recent_fitted_pre"] = evaluate(pre(rescore(recent, out["fitted"])), ci=False)
        out["recent_assumed_pre"] = evaluate(pre(recent), ci=False)
    return out


# ───────────────────────── report section ─────────────────────────

def _ci(v) -> str:
    return f" (95% CI {v[0]:.3f}–{v[1]:.3f})" if v else ""


def _pct(x) -> str:
    return "—" if x is None else f"{x:.0%}"


def section(res: Dict[str, Any] = None) -> List[str]:
    res = res or run()
    p = res["pooled"]
    if not p.get("n"):
        return ["", "## 6. Calibration backtest", "", "_Not enough projects older than the cutoffs yet._"]

    def reliability(r):
        return ["| Predicted score | Cases | Mean predicted | Observed progressed |", "|---|---|---|---|",
                *[f"| {t['bucket']} | {t['n']} | {t['predicted']:.0%} | {t['observed']:.0%} |" for t in r["table"]]]

    def versus(rows):
        """rows: [(label, evaluation)] — one line per predictor, plus the shared baselines of the first."""
        b = rows[0][1]["baselines"]
        fmt = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
        return ["| Predictor | Brier (lower is better) | AUC (ranking; 0.5 = coin flip) |", "|---|---|---|",
                *[f"| **{label}** | **{r['brier']:.4f}**{_ci(r.get('brier_ci'))} | **{fmt(r['auc'])}**{_ci(r.get('auc_ci'))} |" for label, r in rows],
                f"| Evidence layer alone (stated prior, no adjustments) | {b['stage_only']:.4f} | {fmt(rows[0][1]['auc_stage_only'])} |",
                f"| Flat 35% for every project (Bernstein's pipeline figure) | {b['flat_35']:.4f} | 0.500 |",
                f"| Always the base rate ({rows[0][1]['base_rate']:.0%}) — only knowable with hindsight | {b['base_rate']:.4f} | 0.500 |"]

    head = [
        "", "## 6. Calibration backtest: does the score mean what it says?", "",
        f"History is replayed at **{len(res['cutoffs'])} cutoffs** ({', '.join(res['cutoffs'])}). At each one, every project known by then is "
        "scored using **only the evidence published up to that date**, and the prediction is compared with what verified evidence shows "
        "afterwards (regular hunt + Firecrawl outcome scout). *Progressed* = verified BUILDING or LIVE evidence; otherwise not progressed.", "",
        f"**{p['n']} project-cutoff cases from {p['projects']} distinct projects.** A project scored at several cutoffs is not several independent "
        "projects, so every confidence interval is a bootstrap that resamples whole projects.",
    ]
    if not res.get("fitted"):
        e = res["pooled_pre_construction"]
        return head + ["", f"Too few mature cases to re-fit the priors yet ({res['fit_cases']['n']}).", "",
                       *versus([("Reality score (stated priors)", e)]), "", *reliability(e)]

    am, cv, ap, cp = res["assumed_mature"], res["cv"], res["assumed_mature_pre"], res["cv_pre"]
    ph = cp["phantom_calls"]
    lk_a, lk_c = ap["likely_calls"], cp["likely_calls"]
    cut_rows = []
    for k in res["cutoffs"]:
        a, b = res["by_cutoff"][k], res["by_cutoff_pre_construction"][k]
        if a.get("n"):
            cut_rows.append(f"| {k} | {a['n']} | {a['base_rate']:.0%} | {a['brier']:.4f} | {a['baselines']['base_rate']:.4f} | "
                            f"{'—' if a['auc'] is None else a['auc']} | {b.get('n', 0)} | {_pct(b.get('base_rate'))} | {b.get('brier', '—')} |")
    ra, rf = res["recent_assumed_pre"], res["recent_fitted_pre"]
    live = "**The scorer now runs on the fitted priors** (`app/phantom/calibration.json`)." if S.CALIBRATION else \
        "The fitted priors are computed here but not applied (run `python -m app.phantom.backtest --fit`)."
    return head + [
        "",
        "### 6.1 What the outcomes did to the priors", "",
        f"Fitting uses the cutoffs old enough for a project to have broken ground ({', '.join(res['fit_cutoffs'])}; at least {MATURE_YEARS} years of follow-up): "
        f"{res['fit_cases']['n']} cases from {res['fit_cases']['projects']} projects.", "",
        "| Layer when scored | Stated prior | Cases | Progressed | Observed | Fitted prior |", "|---|---|---|---|---|---|",
        *[f"| {f['layer']} | {f['assumed']:.0%} | {f['n']} | {f['progressed']} | {_pct(f['observed'])} | **{f['fitted']:.1%}** |" for f in res["fitted_priors"]], "",
        f"*Fitted* = (progressed + {SHRINK} × stated prior) / (cases + {SHRINK}), then forced to rise with the ladder. The {SHRINK} pseudo-cases mean a layer "
        f"needs about {SHRINK} real cases before the data outweighs the assumption — so the well-populated ANNOUNCED layer moves a lot and the thin "
        "layers barely move. It also offsets a known bias: *no verified progress* under-counts real progress.", "",
        live, "",
        "### 6.2 The fair test: projects NOT yet under construction when scored", "",
        f"{cp['n']} cases from {cp['projects']} projects; {cp['base_rate']:.0%} went on to verified construction or operation. "
        "The fitted score is **cross-validated**: each project is scored with priors fitted on the *other* projects only (5 folds).", "",
        *versus([("Reality score, fitted priors (out of sample)", cp), ("Reality score, stated priors (as first built)", ap)]), "",
        "Fitted, out of sample:", "", *reliability(cp), "", "Stated priors:", "", *reliability(ap), "",
        "**What this does and does not show.**", "",
        f"* **Its phantom calls are right, but no more often than chance.** Of {ph['n']} cases the fitted score called phantom risk (below {PHANTOM_CALL:.0%}), "
        f"{ph['right']} ({_pct(ph['accuracy'])}) showed no verified progress — against **{_pct(1 - cp['base_rate'])} for every pre-construction project**. "
        "Calling everything a phantom would do as well.",
        f"* **Before construction it does not rank projects.** Out-of-sample AUC is {cp['auc'] if cp['auc'] is not None else '—'}{_ci(cp.get('auc_ci'))}; "
        f"Brier {cp['brier']:.4f} against {cp['baselines']['flat_35']:.4f} for a flat 35% and {cp['baselines']['base_rate']:.4f} for the base rate. "
        "The news evidence available before ground is broken does not separate the projects that will be built from those that will not.",
        f"* **It cannot pick winners early.** With the stated priors {lk_a['n']} pre-construction case(s) scored {LIKELY_CALL:.0%} or more and "
        f"{lk_a['right']} progressed; with fitted priors {lk_c['n']} do.",
        "* **Where it does work:** once evidence of construction or operation exists, the score is well calibrated (§6.3) — useful for sizing the real "
        "pipeline, not for predicting it. Predicting needs pre-construction evidence the news does not carry: filings, supply agreements, clearances.",
        "* *Not progressed* means no verified evidence was found, which is weaker than proof of failure, so observed rates are a lower bound.", "",
        "### 6.3 All projects, including those already under construction", "",
        f"{cv['n']} cases; base rate {cv['base_rate']:.0%}. This flatters any model — a project already being built when scored is an easy call — "
        "and is shown for completeness.", "",
        *versus([("Reality score, fitted priors (out of sample)", cv), ("Reality score, stated priors", am)]), "", *reliability(cv), "",
        "### 6.4 By cutoff (stated priors)", "",
        "| Cutoff | Cases | Progressed | Brier | Brier of base rate | AUC | Pre-construction cases | Progressed | Pre-construction Brier |",
        "|---|---|---|---|---|---|---|---|---|",
        *cut_rows, "",
        f"The latest cutoff has had under {MATURE_YEARS} years to progress, so it is excluded from fitting. Scored anyway as a short-horizon check on "
        f"{rf.get('n', 0)} pre-construction projects: Brier {ra.get('brier', '—')} with stated priors, **{rf.get('brier', '—')}** with fitted "
        f"(base rate {_pct(rf.get('base_rate'))}; these projects overlap with the fitting set, so this is not an independent test).", "",
        "### 6.5 What would make this conclusive", "",
        "* **More outcomes.** The next scout should chase 2019–2023 announcements specifically, to reach a few hundred independent projects.",
        "* **Stronger pre-construction evidence.** News rarely separates serious projects from talk before ground is broken; filings do "
        "(supply agreements, environmental clearances, land registrations). That is where the next data source should come from.",
        "* **Per-developer track records** (see `analytics/ANALYSIS.md`) as a prior, once enough developers have five or more judged projects.",
    ]


def main():
    import json
    import sys
    res = run()
    if "--fit" in sys.argv:
        cal = calibration(res)
        if not cal:
            print(f"not enough mature cases to fit ({res['fit_cases']['n']} < {MIN_FIT_CASES})")
            return
        S.CALIBRATION_FILE.write_text(json.dumps(cal, indent=2), encoding="utf-8")
        cache(res)
        print("wrote", S.CALIBRATION_FILE.name, cal["priors"], f"({cal['cases']} cases, {cal['projects']} projects)")
        print("now run:  python -c \"from app.phantom.pipeline import rebuild_projects; print(rebuild_projects())\"")
        return
    if "--cache" in sys.argv:
        print("wrote", CACHE_FILE.name, len(cache(res)["rows"]), "cases")
    if "--rows" in sys.argv:
        for r in sorted(res["pooled_rows"], key=lambda r: (r["cutoff"], -r["reality_score"])):
            print(f"{r['cutoff']} {r['reality_score']:.2f} {r['stage_then']:9} -> {r['stage_now']:9} {'Y' if r['progressed'] else '.'} news={r['news_after_cutoff']:2} {r['name'][:60]}")
    for k in ("pooled", "pooled_pre_construction", "assumed_mature_pre", "cv_pre"):
        if res.get(k):
            print(k, {kk: vv for kk, vv in res[k].items() if kk != "table"})
    print("fitted", res.get("fitted"))


if __name__ == "__main__":
    main()
