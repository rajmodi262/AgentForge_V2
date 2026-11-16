/**
 * Phantom Hunter — Time machine
 *
 * Two ways to travel:
 *   History  drag (or play) from 2019 to today and watch projects appear and climb the
 *            evidence ladder — or sit at ANNOUNCED for years.
 *   Replay   stand at a backtest cutoff, see what the score predicted using only the news
 *            published by then, then reveal what actually happened.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import RealityGlobe, { type GlobeItem } from '../components/RealityGlobe';
import { PhantomNav, PageHead, H, Chip, card, mono, display, Loading, Fail } from '../components/phantomUi';
import { colors } from '../styles/tokens';
import { lab, fmtMW, pct, scoreColor, STAGE_COLORS, type Backtest, type BacktestCase, type Timeline, type TimelineProject } from '../services/phantom';

const LADDER = ['ANNOUNCED', 'SITE', 'APPROVED', 'POWER', 'BUILDING', 'LIVE'];
const DAY = 86400000;
const START = Date.parse('2019-01-01');
const iso = (t: number) => new Date(t).toISOString().slice(0, 10);
const nice = (t: number) => new Date(t).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });

function stageAt(p: TimelineProject, t: number): number {
  let s = 0;
  for (const e of p.events) if (Date.parse(e.date) <= t) s = Math.max(s, LADDER.indexOf(e.layer));
  return s;
}

/** Spread projects that share a city, once, so bars stay put while time moves. */
function spread(ps: TimelineProject[]): TimelineProject[] {
  const seen: Record<string, number> = {};
  return ps.filter((p) => p.lat != null && p.lon != null).map((p) => {
    const k = `${p.lat},${p.lon}`; const n = (seen[k] = (seen[k] || 0) + 1) - 1;
    const a = n * 2.4, d = n ? 0.25 + 0.12 * Math.sqrt(n) : 0;
    return { ...p, lat: p.lat! + Math.sin(a) * d, lon: p.lon! + Math.cos(a) * d };
  });
}

export default function PhantomTime() {
  const nav = useNavigate();
  const [tl, setTl] = useState<Timeline | null>(null);
  const [bt, setBt] = useState<Backtest | null>(null);
  const [err, setErr] = useState('');
  const [mode, setMode] = useState<'history' | 'replay'>('history');
  const [t, setT] = useState(START);
  const [playing, setPlaying] = useState(false);
  const [cutoff, setCutoff] = useState('');
  const [revealed, setRevealed] = useState(false);
  const end = useRef(Date.now());

  useEffect(() => {
    lab.timeline().then((x) => { setTl(x); setT(START); }).catch((e) => setErr(e.message));
    lab.backtest().then((b) => { setBt(b); setCutoff(b.fit_cutoffs[b.fit_cutoffs.length - 1] || b.cutoffs[0]); }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setT((x) => { const n = x + 21 * DAY; if (n >= end.current) { setPlaying(false); return end.current; } return n; }), 60);
    return () => clearInterval(id);
  }, [playing]);

  const all = useMemo(() => (tl ? spread(tl.projects) : []), [tl]);
  const now = mode === 'replay' && cutoff ? Date.parse(cutoff) : t;
  const known = useMemo(() => all.filter((p) => Date.parse(p.first_seen) <= now), [all, now]);
  const cases = useMemo(() => {
    const m: Record<string, BacktestCase> = {};
    if (bt) for (const r of bt.rows) if (r.cutoff === cutoff) m[r.project_id] = r;
    return m;
  }, [bt, cutoff]);

  const items: (GlobeItem & { _stage: number })[] = useMemo(() => known.map((p) => {
    const s = stageAt(p, now);
    return { id: p.id, name: p.name, lat: p.lat, lon: p.lon, capacity_mw: p.capacity_mw, reality_score: cases[p.id]?.score_fitted ?? p.reality_score, stage_name: LADDER[s], city: p.city, country: p.country, _stage: s };
  }), [known, now, cases]);
  const shown = mode === 'replay' ? items.filter((i) => cases[i.id]) : items;

  const stats = useMemo(() => {
    const mw = (ps: TimelineProject[]) => ps.reduce((a, p) => a + (p.capacity_mw || 0), 0);
    return { n: known.length, announced: mw(known), built: mw(known.filter((p) => stageAt(p, now) >= 4)), builtNow: mw(known.filter((p) => p.stage >= 4)) };
  }, [known, now]);

  // quarterly series for the strip under the slider
  const series = useMemo(() => {
    const out: { t: number; n: number; built: number }[] = [];
    for (let q = START; q <= end.current; q += 91 * DAY) {
      const k = all.filter((p) => Date.parse(p.first_seen) <= q);
      out.push({ t: q, n: k.length, built: k.filter((p) => stageAt(p, q) >= 4).length });
    }
    return out;
  }, [all]);
  const maxN = Math.max(1, ...series.map((s) => s.n));

  const replayRows = useMemo(() => Object.values(cases).sort((a, b) => b.score_fitted - a.score_fitted), [cases]);
  const pre = replayRows.filter((r) => r.stage_then !== 'BUILDING' && r.stage_then !== 'LIVE');
  const calledPhantom = pre.filter((r) => r.score_fitted < (bt?.bands.phantom ?? 0.45));
  const rightPhantom = calledPhantom.filter((r) => !r.progressed).length;

  const look = mode === 'history'
    ? { colorOf: (p: GlobeItem) => STAGE_COLORS[p.stage_name || 'ANNOUNCED'], fillOf: (p: GlobeItem) => 0.12 + 0.88 * (LADDER.indexOf(p.stage_name || 'ANNOUNCED') / 5),
        detailOf: (p: GlobeItem) => `${p.stage_name} as of ${nice(now)}`,
        legend: <>bar height = announced MW · fill and colour = how far up the evidence ladder <b style={{ color: '#fff' }}>on that date</b></> }
    : revealed
      ? { colorOf: (p: GlobeItem) => (cases[p.id]?.progressed ? '#10b981' : '#f43f5e'), fillOf: (p: GlobeItem) => (cases[p.id]?.progressed ? 1 : 0.1),
          detailOf: (p: GlobeItem) => `${cases[p.id]?.progressed ? 'progressed' : 'no verified progress'} · was scored ${pct(cases[p.id]?.score_fitted)}`,
          legend: <><span style={{ color: '#10b981' }}>■</span> reached construction or operation &nbsp; <span style={{ color: '#f43f5e' }}>■</span> no verified progress since</> }
      : { colorOf: (p: GlobeItem) => scoreColor(p.reality_score), fillOf: (p: GlobeItem) => p.reality_score,
          detailOf: (p: GlobeItem) => `scored ${pct(p.reality_score)} on ${cutoff}`,
          legend: <>fill and colour = the reality score <b style={{ color: '#fff' }}>as it stood on {cutoff}</b>, from news published by then</> };

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <PhantomNav />
        <PageHead kicker="TIME MACHINE" title={mode === 'history' ? `The pipeline as of ${nice(t)}` : `What the score said on ${cutoff}`}>
          {mode === 'history'
            ? 'Drag the date or press play. Projects appear when first reported and climb the ladder only when verified evidence is published. Most never leave the bottom rung.'
            : 'The backtest, made visible: every project is scored with only the news published by the cutoff. Then reveal what the following years showed.'}
        </PageHead>
        {err && <Fail msg={err} />}
        {!tl && !err && <Loading what="the timeline" />}

        {tl && (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              {(['history', 'replay'] as const).map((m) => (
                <button key={m} onClick={() => { setMode(m); setPlaying(false); setRevealed(false); }} aria-pressed={mode === m}
                  style={{ padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontSize: 13, fontFamily: 'inherit', border: `1px solid ${mode === m ? colors.secondary : colors.border}`, background: mode === m ? 'rgba(6,182,212,0.15)' : 'transparent', color: mode === m ? '#fff' : colors.textMuted }}>
                  {m === 'history' ? '⏱ History' : '🎯 Prediction replay'}
                </button>
              ))}
              {mode === 'replay' && bt && (
                <>
                  <span style={{ color: colors.textDim, fontSize: 12.5, marginLeft: 8 }}>cutoff</span>
                  {bt.cutoffs.map((c) => (
                    <button key={c} onClick={() => { setCutoff(c); setRevealed(false); }} style={{ padding: '5px 10px', borderRadius: 8, cursor: 'pointer', fontFamily: mono, fontSize: 12, border: `1px solid ${cutoff === c ? '#c4b5fd' : colors.border}`, background: cutoff === c ? 'rgba(124,58,237,0.2)' : 'transparent', color: cutoff === c ? '#fff' : colors.textMuted }}>{c.slice(0, 7)}</button>
                  ))}
                  <button onClick={() => setRevealed((r) => !r)} style={{ marginLeft: 'auto', padding: '8px 16px', borderRadius: 10, border: 'none', cursor: 'pointer', fontWeight: 700, fontFamily: 'inherit', color: '#fff', background: revealed ? 'rgba(255,255,255,0.08)' : 'linear-gradient(135deg,#7c3aed,#06b6d4)' }}>
                    {revealed ? '↩ Back to the prediction' : '▶ Reveal what happened'}
                  </button>
                </>
              )}
              {mode === 'replay' && !bt && <span style={{ color: colors.textDim, fontSize: 12.5 }}>No cached backtest — run <code>python -m app.phantom.backtest --cache</code>.</span>}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.55fr) minmax(0, 1fr)', gap: 16, marginBottom: 16 }}>
              <div style={card}>
                <RealityGlobe projects={shown} onPick={(id) => nav(`/phantom/${id}`)} height={480} look={look} />
                {mode === 'history' && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <button onClick={() => { if (t >= end.current) setT(START); setPlaying((p) => !p); }} aria-label={playing ? 'Pause' : 'Play'}
                        style={{ width: 40, height: 40, borderRadius: '50%', border: 'none', cursor: 'pointer', color: '#fff', fontSize: 15, background: 'linear-gradient(135deg,#7c3aed,#06b6d4)', flexShrink: 0 }}>{playing ? '❚❚' : '▶'}</button>
                      <div style={{ flex: 1 }}>
                        <svg viewBox={`0 0 ${series.length} 30`} preserveAspectRatio="none" style={{ width: '100%', height: 34, display: 'block' }} aria-hidden>
                          {series.map((s, i) => (
                            <g key={i} opacity={s.t <= t ? 1 : 0.25}>
                              <rect x={i + 0.12} width={0.76} y={30 - (30 * s.n) / maxN} height={(30 * s.n) / maxN} fill="#4c3b9e" />
                              <rect x={i + 0.12} width={0.76} y={30 - (30 * s.built) / maxN} height={(30 * s.built) / maxN} fill="#10b981" />
                            </g>
                          ))}
                        </svg>
                        <input type="range" aria-label="Date" min={START} max={end.current} step={7 * DAY} value={t} onChange={(e) => { setPlaying(false); setT(Number(e.target.value)); }} style={{ width: '100%', accentColor: '#7c3aed', cursor: 'pointer' }} />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: mono, fontSize: 10.5, color: colors.textDim }}>
                          <span>2019</span><span><span style={{ color: '#7b68d6' }}>■</span> projects known &nbsp;<span style={{ color: '#10b981' }}>■</span> building or live</span><span>today</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {mode === 'history' ? (
                  <>
                    <div style={card}>
                      <div style={{ fontFamily: mono, fontSize: 11, color: colors.textMuted, letterSpacing: '0.12em' }}>KNOWN BY {iso(t)}</div>
                      <div style={{ fontFamily: display, fontSize: '2.2rem', fontWeight: 700, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>{stats.n} <span style={{ fontSize: 14, color: colors.textMuted, fontWeight: 400 }}>projects · {fmtMW(stats.announced)}</span></div>
                      <div style={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden', background: 'rgba(196,181,253,0.14)', marginTop: 12 }}>
                        <div style={{ width: `${stats.announced ? (100 * stats.built) / stats.announced : 0}%`, background: '#10b981', transition: 'width .2s' }} />
                        <div style={{ width: `${stats.announced ? (100 * Math.max(0, stats.builtNow - stats.built)) / stats.announced : 0}%`, background: 'rgba(16,185,129,0.3)', transition: 'width .2s' }} />
                      </div>
                      <div style={{ fontSize: 12.5, color: colors.textMuted, marginTop: 8, lineHeight: 1.6 }}>
                        <b style={{ color: '#10b981' }}>{fmtMW(stats.built)}</b> building or live on that date.<br />
                        <b style={{ color: '#6ee7b7' }}>{fmtMW(stats.builtNow)}</b> of the same projects are building or live today.<br />
                        <b style={{ color: '#c4b5fd' }}>{fmtMW(stats.announced - stats.builtNow)}</b> still has no verified construction.
                      </div>
                    </div>
                    <div style={card}>
                      <H note="on the selected date">Where they stood</H>
                      {LADDER.map((l, i) => {
                        const n = items.filter((x) => x._stage === i).length;
                        return (
                          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                            <div style={{ width: 92, fontFamily: mono, fontSize: 10.5, color: STAGE_COLORS[l] }}>{l}</div>
                            <div style={{ flex: 1, height: 12, background: 'rgba(255,255,255,0.04)', borderRadius: 4 }}>
                              <div style={{ width: `${items.length ? (100 * n) / items.length : 0}%`, height: '100%', background: STAGE_COLORS[l], borderRadius: 4, transition: 'width .2s' }} />
                            </div>
                            <div style={{ width: 28, textAlign: 'right', fontFamily: mono, fontSize: 12 }}>{n}</div>
                          </div>
                        );
                      })}
                      <div style={{ fontSize: 11.5, color: colors.textDim, marginTop: 8 }}>{tl.undated} projects have no dated source and are left out of the timeline.</div>
                    </div>
                  </>
                ) : (
                  <div style={card}>
                    <H note={`${replayRows.length} projects known by ${cutoff}`}>{revealed ? 'What happened' : 'What the score predicted'}</H>
                    {revealed && pre.length > 0 && (
                      <div style={{ padding: 10, borderRadius: 10, border: '1px solid rgba(34,211,238,0.35)', background: 'rgba(34,211,238,0.07)', fontSize: 13, marginBottom: 12, lineHeight: 1.55 }}>
                        Of <b>{calledPhantom.length}</b> pre-construction projects called phantom risk, <b style={{ color: '#22d3ee' }}>{rightPhantom}</b> showed no verified progress ({pct(calledPhantom.length ? rightPhantom / calledPhantom.length : null)}).
                        <span style={{ color: colors.textDim }}> No progress means none was found in public sources.</span>
                      </div>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 470, overflowY: 'auto', paddingRight: 4 }}>
                      {replayRows.map((r) => {
                        const hit = revealed && ((r.score_fitted >= 0.5) === r.progressed);
                        return (
                          <div key={r.project_id} onClick={() => nav(`/phantom/${r.project_id}`)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 9px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${colors.border}` }}>
                            <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 700, width: 38, color: scoreColor(r.score_fitted) }}>{pct(r.score_fitted)}</span>
                            <span style={{ flex: 1, fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
                            <Chip color={STAGE_COLORS[r.stage_then]}>{r.stage_then}</Chip>
                            {revealed && <span title={r.progressed ? `now ${r.stage_now}` : 'no verified progress'} style={{ fontSize: 13, width: 16, textAlign: 'center', color: r.progressed ? '#10b981' : '#f43f5e' }}>{r.progressed ? '▲' : '·'}</span>}
                            {revealed && <span style={{ fontFamily: mono, fontSize: 10, color: hit ? '#10b981' : colors.textDark, width: 30 }}>{hit ? 'right' : 'miss'}</span>}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
