/**
 * Phantom Hunter — What-if
 *
 * The score is six starting probabilities and ten named adjustments. Nothing is hidden,
 * so nothing stops you moving them: every slider re-scores all projects in the browser
 * with the scorer's own formula —
 *
 *     score = sigmoid( logit(prior[layer]) + Σ weights[adjustment] )
 *
 * — and the page shows how the headline number and individual projects move.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import { PhantomNav, PageHead, Stat, H, Slider, card, mono, Loading, Fail } from '../components/phantomUi';
import { colors } from '../styles/tokens';
import { lab, fmtMW, pct, scoreColor, STAGE_COLORS, type ModelProject, type ScoreModel } from '../services/phantom';

const logit = (p: number) => Math.log(p / (1 - p));
const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
const clampP = (p: number) => Math.min(0.995, Math.max(0.005, p));

function rescore(p: ModelProject, priors: number[], weights: Record<string, number>): number {
  if (p.cancelled) return 0.03;
  return sigmoid(logit(clampP(priors[p.stage])) + p.terms.reduce((a, t) => a + (weights[t] || 0), 0));
}

export default function PhantomWhatIf() {
  const nav = useNavigate();
  const [m, setM] = useState<ScoreModel | null>(null);
  const [err, setErr] = useState('');
  const [priors, setPriors] = useState<number[]>([]);
  const [weights, setWeights] = useState<Record<string, number>>({});

  useEffect(() => { lab.model().then((x) => { setM(x); setPriors(x.priors.active); setWeights(x.weights); }).catch((e) => setErr(e.message)); }, []);

  const r = useMemo(() => {
    if (!m || !priors.length) return null;
    // the baseline is recomputed too (stored scores are rounded), so "no change" reads exactly zero
    const rows = m.projects.map((p) => ({ ...p, score: rescore(p, m.priors.active, m.weights), now: rescore(p, priors, weights) }));
    const capped = rows.filter((p) => p.capacity_mw);
    const sum = (f: (p: typeof rows[number]) => number) => capped.reduce((a, p) => a + f(p), 0);
    const announced = sum((p) => p.capacity_mw!);
    const base = sum((p) => p.capacity_mw! * p.score), now = sum((p) => p.capacity_mw! * p.now);
    const byStage = m.layers.map((l, i) => {
      const ps = capped.filter((p) => p.stage === i);
      return { layer: l, n: rows.filter((p) => p.stage === i).length, announced: ps.reduce((a, p) => a + p.capacity_mw!, 0), base: ps.reduce((a, p) => a + p.capacity_mw! * p.score, 0), now: ps.reduce((a, p) => a + p.capacity_mw! * p.now, 0) };
    });
    const movers = capped.map((p) => ({ ...p, dmw: p.capacity_mw! * (p.now - p.score) })).filter((p) => Math.abs(p.dmw) >= 0.5).sort((a, b) => Math.abs(b.dmw) - Math.abs(a.dmw)).slice(0, 12);
    const bands = (f: (p: typeof rows[number]) => number) => ({ likely: rows.filter((p) => f(p) >= 0.7).length, risk: rows.filter((p) => f(p) >= 0.45 && f(p) < 0.7).length, phantom: rows.filter((p) => f(p) < 0.45).length });
    return { announced, base, now, byStage, movers, was: bands((p) => p.score), is: bands((p) => p.now) };
  }, [m, priors, weights]);

  if (err) return <DashboardLayout><PhantomNav /><Fail msg={err} /></DashboardLayout>;
  if (!m || !r) return <DashboardLayout><PhantomNav /><Loading what="the scoring model" /></DashboardLayout>;

  const changed = priors.some((p, i) => Math.abs(p - m.priors.active[i]) > 1e-9) || Object.keys(weights).some((k) => Math.abs(weights[k] - m.weights[k]) > 1e-9);
  const delta = r.now - r.base;
  const maxStage = Math.max(1, ...r.byStage.map((s) => s.announced));
  const presets: [string, () => void][] = [
    ['Fitted (current)', () => { setPriors(m.priors.active); setWeights(m.weights); }],
    ['Stated assumptions', () => { setPriors(m.priors.stated); setWeights(m.weights); }],
    ['Bernstein: flat 35%', () => { setPriors(m.layers.map((_, i) => (i >= 4 ? m.priors.active[i] : 0.35))); setWeights(Object.fromEntries(Object.keys(m.weights).map((k) => [k, 0]))); }],
    ['Sceptic', () => { setPriors(m.priors.active.map((p, i) => (i < 4 ? p * 0.6 : p))); setWeights({ ...m.weights, single_source: -0.8, gone_quiet: -1.0, target_passed: -1.0 }); }],
    ['Optimist', () => { setPriors(m.priors.active.map((p, i) => (i < 4 ? Math.min(0.9, p * 1.6) : p))); setWeights({ ...m.weights, single_source: 0, headline_only: 0 }); }],
  ];

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <PhantomNav />
        <PageHead kicker="WHAT-IF" title="Argue with the model">
          The score is six starting probabilities and ten named adjustments, added in log-odds. Move any of them and all {m.projects.length} projects are re-scored here, instantly, with the scorer's own formula.
          {m.calibration && <> The starting probabilities currently in use were fitted on {m.calibration.cases} back-tested cases from {m.calibration.projects} projects.</>}
        </PageHead>

        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
          <Stat label="ANNOUNCED" value={fmtMW(r.announced)} sub="does not move" />
          <Stat label="REALITY-WEIGHTED, YOUR SETTINGS" value={fmtMW(r.now)} sub={`${pct(r.now / r.announced)} of announced`} color={changed ? colors.amber : colors.emerald} />
          <Stat label="CHANGE FROM THE CURRENT MODEL" value={`${delta >= 0 ? '+' : '−'}${fmtMW(Math.abs(delta))}`} sub={changed ? `was ${fmtMW(r.base)} (${pct(r.base / r.announced)})` : 'move a slider or pick a preset'} color={Math.abs(delta) < 1 ? colors.textMuted : delta > 0 ? colors.emerald : '#f43f5e'} />
          <Stat label="PROJECTS LIKELY · AT RISK · PHANTOM" value={`${r.is.likely} · ${r.is.risk} · ${r.is.phantom}`} sub={`was ${r.was.likely} · ${r.was.risk} · ${r.was.phantom}`} color="#c4b5fd" />
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
          <span style={{ fontSize: 12.5, color: colors.textDim }}>Presets</span>
          {presets.map(([label, fn]) => (
            <button key={label} onClick={fn} style={{ padding: '6px 12px', borderRadius: 20, cursor: 'pointer', fontSize: 12.5, fontFamily: 'inherit', border: `1px solid ${colors.borderLight}`, background: 'rgba(255,255,255,0.04)', color: '#fff' }}>{label}</button>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.25fr)', gap: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={card}>
              <H note="chance a project at this layer reaches construction">Starting probability by evidence layer</H>
              {m.layers.map((l, i) => (
                <Slider key={l} label={l} value={priors[i]} base={m.priors.active[i]} min={0.01} max={0.99} step={0.01} format={(v) => `${Math.round(v * 100)}%`}
                  onChange={(v) => setPriors((ps) => ps.map((x, j) => (j === i ? v : x)))} />
              ))}
              <div style={{ fontSize: 11.5, color: colors.textDim, lineHeight: 1.6 }}>
                Stated assumptions: {m.priors.stated.map((p) => `${Math.round(p * 100)}%`).join(' · ')}.{m.priors.fitted && <> Fitted from outcomes: {m.priors.fitted.map((p) => `${(p * 100).toFixed(p < 0.3 ? 1 : 0)}%`).join(' · ')}.</>}
              </div>
            </div>
            <div style={card}>
              <H note="log-odds; negative lowers the score">Adjustments</H>
              {Object.keys(m.weights).map((k) => (
                <Slider key={k} label={`${m.weight_labels[k] || k} · ${m.projects.filter((p) => p.terms.includes(k)).length} projects`} value={weights[k]} base={m.weights[k]} min={-1.5} max={1.5} step={0.05}
                  format={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`} onChange={(v) => setWeights((w) => ({ ...w, [k]: v }))} />
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={card}>
              <H note="ghost = announced · line = current model · solid = your settings">Reality-weighted capacity by evidence layer</H>
              {r.byStage.map((s) => (
                <div key={s.layer} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                    <span style={{ fontFamily: mono, fontSize: 11, color: STAGE_COLORS[s.layer] }}>{s.layer} <span style={{ color: colors.textDim }}>· {s.n}</span></span>
                    <span style={{ fontFamily: mono, color: colors.textMuted }}>{fmtMW(s.now)} <span style={{ color: colors.textDim }}>/ {fmtMW(s.announced)}</span></span>
                  </div>
                  <div style={{ position: 'relative', height: 14, marginTop: 4, width: `${Math.max(2, (100 * s.announced) / maxStage)}%`, background: 'rgba(196,181,253,0.13)', borderRadius: 4 }}>
                    <div style={{ position: 'absolute', inset: 0, width: `${s.announced ? (100 * s.now) / s.announced : 0}%`, background: STAGE_COLORS[s.layer], borderRadius: 4, transition: 'width .12s linear', opacity: 0.9 }} />
                    <div title="current model" style={{ position: 'absolute', top: -3, bottom: -3, left: `${s.announced ? (100 * s.base) / s.announced : 0}%`, width: 2, background: '#fff' }} />
                  </div>
                </div>
              ))}
            </div>
            <div style={card}>
              <H note="largest change in reality-weighted MW">Projects that move most</H>
              {r.movers.length === 0 && <div style={{ color: colors.textDim, fontSize: 13 }}>Nothing has moved yet. Try the “Sceptic” preset, or drag ANNOUNCED.</div>}
              {r.movers.map((p) => (
                <div key={p.id} onClick={() => nav(`/phantom/${p.id}`)} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderBottom: `1px solid ${colors.border}`, cursor: 'pointer', fontSize: 12.5 }}>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                  <span style={{ fontFamily: mono, color: colors.textDim }}>{fmtMW(p.capacity_mw)}</span>
                  <span style={{ fontFamily: mono, color: scoreColor(p.score), width: 34, textAlign: 'right' }}>{pct(p.score)}</span>
                  <span style={{ color: colors.textDark }}>→</span>
                  <span style={{ fontFamily: mono, color: scoreColor(p.now), width: 34 }}>{pct(p.now)}</span>
                  <span style={{ fontFamily: mono, width: 78, textAlign: 'right', color: p.dmw > 0 ? colors.emerald : '#f43f5e' }}>{p.dmw > 0 ? '+' : '−'}{fmtMW(Math.abs(p.dmw))}</span>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 12, color: colors.textDim, lineHeight: 1.6 }}>
              Nothing here is saved or changes the tracker. To see which settings the evidence supports, open the Calibration lab: it replays history and scores each choice against what happened.
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
