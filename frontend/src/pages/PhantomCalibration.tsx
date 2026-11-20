/**
 * Phantom Hunter — Calibration lab
 *
 * "Does a 70% score mean 70%?" History is replayed at several cutoffs: each project is
 * scored with only the news published by then, and compared with what happened after.
 * This page shows the result without flattering it: the reliability diagram, the score
 * against three simpler rules, where it works (ruling projects out) and where it does
 * not yet (picking winners early), and how the starting probabilities were re-fitted.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import { PhantomNav, PageHead, H, Chip, card, mono, display, Loading, Fail } from '../components/phantomUi';
import { colors } from '../styles/tokens';
import { lab, fmtMW, pct, scoreColor, STAGE_COLORS, type Backtest, type DeveloperRow, type Evaluation } from '../services/phantom';

type Subset = 'pre' | 'all';
type Scoring = 'fitted' | 'stated';
const BUILT = new Set(['BUILDING', 'LIVE']);

function Toggle<T extends string>({ value, set, options }: { value: T; set: (v: T) => void; options: [T, string][] }) {
  return (
    <div style={{ display: 'inline-flex', border: `1px solid ${colors.border}`, borderRadius: 10, overflow: 'hidden' }}>
      {options.map(([k, label]) => (
        <button key={k} onClick={() => set(k)} aria-pressed={value === k} style={{ padding: '7px 12px', border: 'none', cursor: 'pointer', fontSize: 12.5, fontFamily: 'inherit', color: value === k ? '#fff' : colors.textMuted, background: value === k ? 'rgba(124,58,237,0.35)' : 'transparent' }}>{label}</button>
      ))}
    </div>
  );
}

function ReliabilityChart({ e, picked, pick }: { e: Evaluation; picked: number | null; pick: (i: number | null) => void }) {
  const S = 300, P = 38, x = (v: number) => P + v * (S - P - 12), y = (v: number) => S - P - v * (S - P - 12);
  const maxN = Math.max(1, ...e.table.map((t) => t.n));
  return (
    <svg viewBox={`0 0 ${S} ${S}`} style={{ width: '100%', maxWidth: 380, display: 'block' }} role="img" aria-label="Reliability diagram: predicted score against observed rate">
      {[0, 0.25, 0.5, 0.75, 1].map((v) => (
        <g key={v}>
          <line x1={x(0)} x2={x(1)} y1={y(v)} y2={y(v)} stroke="rgba(255,255,255,0.06)" />
          <line y1={y(0)} y2={y(1)} x1={x(v)} x2={x(v)} stroke="rgba(255,255,255,0.06)" />
          <text x={x(0) - 6} y={y(v) + 3} textAnchor="end" fontSize="9" fill="#64748b" fontFamily="JetBrains Mono">{Math.round(v * 100)}</text>
          <text x={x(v)} y={y(0) + 13} textAnchor="middle" fontSize="9" fill="#64748b" fontFamily="JetBrains Mono">{Math.round(v * 100)}</text>
        </g>
      ))}
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#c4b5fd" strokeDasharray="4 4" opacity={0.6} />
      <text x={x(0.99)} y={y(0.9)} textAnchor="end" fontSize="9" fill="#c4b5fd">perfectly calibrated</text>
      <line x1={x(0)} x2={x(1)} y1={y(e.base_rate)} y2={y(e.base_rate)} stroke="#f59e0b" strokeDasharray="2 3" opacity={0.7} />
      <text x={x(0.99)} y={y(e.base_rate) - 4} textAnchor="end" fontSize="9" fill="#f59e0b">base rate {Math.round(e.base_rate * 100)}%</text>
      <polyline fill="none" stroke="rgba(34,211,238,0.5)" strokeWidth={1.5} points={e.table.map((t) => `${x(t.predicted)},${y(t.observed)}`).join(' ')} />
      {e.table.map((t, i) => (
        <g key={t.bucket} onClick={() => pick(picked === i ? null : i)} style={{ cursor: 'pointer' }}>
          <circle cx={x(t.predicted)} cy={y(t.observed)} r={5 + 11 * Math.sqrt(t.n / maxN)} fill={picked === i ? '#22d3ee' : 'rgba(34,211,238,0.35)'} stroke="#22d3ee" />
          <text x={x(t.predicted)} y={y(t.observed) + 3} textAnchor="middle" fontSize="9" fill="#fff" fontFamily="JetBrains Mono" style={{ pointerEvents: 'none' }}>{t.n}</text>
        </g>
      ))}
      <text x={(x(0) + x(1)) / 2} y={S - 4} textAnchor="middle" fontSize="10" fill="#94a3b8">predicted score (%)</text>
      <text transform={`translate(10 ${(y(0) + y(1)) / 2}) rotate(-90)`} textAnchor="middle" fontSize="10" fill="#94a3b8">actually progressed (%)</text>
    </svg>
  );
}

export default function PhantomCalibration() {
  const nav = useNavigate();
  const [bt, setBt] = useState<Backtest | null>(null);
  const [devs, setDevs] = useState<DeveloperRow[]>([]);
  const [err, setErr] = useState('');
  const [subset, setSubset] = useState<Subset>('pre');
  const [scoring, setScoring] = useState<Scoring>('fitted');
  const [picked, setPicked] = useState<number | null>(null);

  useEffect(() => {
    lab.backtest().then(setBt).catch((e) => setErr(e.message));
    lab.developers(3).then((r) => setDevs(r.developers)).catch(() => undefined);
  }, []);
  useEffect(() => setPicked(null), [subset, scoring]);

  const e: Evaluation | null = bt ? (subset === 'pre' ? (scoring === 'fitted' ? bt.cv_pre : bt.assumed_mature_pre) : (scoring === 'fitted' ? bt.cv : bt.assumed_mature)) : null;
  const cases = useMemo(() => {
    if (!bt || picked == null || !e) return [];
    const lo = Number(e.table[picked].bucket.split('-')[0]) / 100;
    return bt.rows.filter((r) => bt.fit_cutoffs.includes(r.cutoff) && (subset === 'all' || !BUILT.has(r.stage_then)))
      .filter((r) => { const s = scoring === 'fitted' ? r.score_fitted : r.score_stated; return Math.min(4, Math.floor(s * 5)) === Math.round(lo * 5); })
      .sort((a, b) => Number(b.progressed) - Number(a.progressed));
  }, [bt, picked, e, subset, scoring]);

  if (err) return <DashboardLayout><PhantomNav /><Fail msg={err} /></DashboardLayout>;
  if (!bt || !e) return <DashboardLayout><PhantomNav /><Loading what="the backtest" /></DashboardLayout>;

  const bars: [string, number, string, string][] = [
    ['Reality score', e.brier, '#22d3ee', scoring === 'fitted' ? 'fitted priors, scored out of sample' : 'stated priors, as first built'],
    ['Evidence layer alone', e.baselines.stage_only, '#a78bfa', 'the prior with no adjustments'],
    ['Flat 35% for every project', e.baselines.flat_35, '#f59e0b', "Bernstein's pipeline figure"],
    ['Always the base rate', e.baselines.base_rate, '#64748b', 'only knowable with hindsight'],
  ];
  const maxB = Math.max(...bars.map((b) => b[1]));
  const beatsBase = e.brier < e.baselines.base_rate;
  const aucWeak = e.auc_ci ? e.auc_ci[0] <= 0.5 : true;

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <PhantomNav />
        <PageHead kicker="CALIBRATION LAB" title="Was the score right?">
          History is replayed at {bt.cutoffs.length} cutoffs. At each one, every project known by then is scored using only the news published up to that date, then compared with what verified evidence shows afterwards. {bt.pooled.n} cases from {bt.pooled.projects} projects; intervals resample whole projects.
        </PageHead>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
          <Toggle<Subset> value={subset} set={setSubset} options={[['pre', 'Not yet under construction (the fair test)'], ['all', 'All projects']]} />
          <Toggle<Scoring> value={scoring} set={setScoring} options={[['fitted', 'Fitted priors, out of sample'], ['stated', 'Stated priors']]} />
          <span style={{ fontSize: 12.5, color: colors.textDim }}>{e.n} cases · {e.projects} projects · {pct(e.base_rate)} progressed</span>
        </div>

        {/* Verdict */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14, marginBottom: 16 }}>
          {(() => {
            // the fair bar: how often a project in this set showed no progress anyway
            const chance = 1 - e.base_rate, lift = (e.phantom_calls.accuracy ?? 0) - chance, good = lift > 0.03;
            const c = good ? colors.emerald : colors.amber;
            return (
              <div style={{ ...card, borderColor: `${c}66`, background: `${c}0d` }}>
                <div style={{ fontFamily: mono, fontSize: 11, color: c, letterSpacing: '0.12em' }}>{good ? '✓' : '≈'} PHANTOM CALLS</div>
                <div style={{ fontFamily: display, fontSize: '2.1rem', fontWeight: 700, marginTop: 4 }}>{pct(e.phantom_calls.accuracy)} <span style={{ fontSize: '1rem', color: colors.textDim, fontWeight: 400 }}>vs {pct(chance)} by chance</span></div>
                <div style={{ fontSize: 13, color: colors.textMuted, lineHeight: 1.55 }}>of {e.phantom_calls.n} projects called phantom risk showed no verified progress — but {pct(chance)} of every project in this set showed none. {good ? 'Better than calling them all phantoms.' : 'No better than calling them all phantoms.'}</div>
              </div>
            );
          })()}
          <div style={{ ...card, borderColor: 'rgba(245,158,11,0.4)', background: 'rgba(245,158,11,0.05)' }}>
            <div style={{ fontFamily: mono, fontSize: 11, color: colors.amber, letterSpacing: '0.12em' }}>⚠ AS A FORECAST OF WINNERS</div>
            <div style={{ fontFamily: display, fontSize: '2.1rem', fontWeight: 700, marginTop: 4 }}>{e.likely_calls.n ? `${e.likely_calls.right} of ${e.likely_calls.n}` : 'untested'}</div>
            <div style={{ fontSize: 13, color: colors.textMuted, lineHeight: 1.55 }}>
              {e.likely_calls.n ? `projects scored ${pct(bt.bands.likely)} or more went on to progress.` : `No project in this set scored ${pct(bt.bands.likely)} or more.`}
              {subset === 'pre' && ' Too few to say high scores mean anything before ground is broken.'}
            </div>
          </div>
          <div style={{ ...card, borderColor: aucWeak ? 'rgba(244,63,94,0.4)' : colors.border }}>
            <div style={{ fontFamily: mono, fontSize: 11, color: aucWeak ? '#f43f5e' : colors.secondary, letterSpacing: '0.12em' }}>RANKING (AUC)</div>
            <div style={{ fontFamily: display, fontSize: '2.1rem', fontWeight: 700, marginTop: 4 }}>{e.auc == null ? '—' : e.auc.toFixed(2)}</div>
            <div style={{ fontSize: 13, color: colors.textMuted, lineHeight: 1.55 }}>
              0.5 is a coin flip, 1.0 is perfect.{e.auc_ci && <> 95% interval {e.auc_ci[0].toFixed(2)}–{e.auc_ci[1].toFixed(2)}.</>}
              {aucWeak ? ' The interval includes a coin flip.' : ''} Evidence layer alone: {e.auc_stage_only == null ? '—' : e.auc_stage_only.toFixed(2)}.
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.15fr)', gap: 16, marginBottom: 16 }}>
          <div style={card}>
            <H note="click a dot to see its projects">Reliability</H>
            <ReliabilityChart e={e} picked={picked} pick={setPicked} />
            <div style={{ fontSize: 11.5, color: colors.textDim, lineHeight: 1.6, marginTop: 6 }}>
              Each dot is a score band; the number is how many cases. On the dashed line, a score means what it says. “Progressed” is verified construction or operation; no progress means none was found, so observed rates are a lower bound.
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={card}>
              <H note="Brier score — lower is better">Against simpler rules</H>
              {bars.map(([label, v, c, note]) => (
                <div key={label} style={{ marginBottom: 11 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>{label} <span style={{ color: colors.textDim, fontSize: 11.5 }}>· {note}</span></span>
                    <span style={{ fontFamily: mono, color: c }}>{v.toFixed(4)}</span>
                  </div>
                  <div style={{ height: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 4, marginTop: 4 }}><div style={{ width: `${(100 * v) / maxB}%`, height: '100%', background: c, borderRadius: 4, transition: 'width .3s' }} /></div>
                </div>
              ))}
              <div style={{ fontSize: 12.5, color: colors.textMuted, lineHeight: 1.6 }}>
                {e.brier < e.baselines.flat_35 ? 'Beats a flat 35% and ' : 'Does not beat a flat 35% and '}
                {e.brier < e.baselines.stage_only ? 'the evidence layer alone' : 'does not beat the evidence layer alone'}
                {beatsBase ? ', and beats the hindsight base rate.' : ' — but not the base rate, a number nobody has in advance.'}
                {e.brier_ci && <span style={{ color: colors.textDim }}> 95% interval {e.brier_ci[0].toFixed(3)}–{e.brier_ci[1].toFixed(3)}.</span>}
              </div>
            </div>
            <div style={card}>
              <H note={picked == null ? 'pick a dot on the chart' : `${cases.length} cases`}>{picked == null ? 'Projects in a score band' : `Scored ${e.table[picked].bucket}`}</H>
              {picked == null && <div style={{ color: colors.textDim, fontSize: 13 }}>Click any dot to list the projects behind it, and whether each one progressed.</div>}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 230, overflowY: 'auto' }}>
                {cases.map((r) => (
                  <div key={r.project_id + r.cutoff} onClick={() => nav(`/phantom/${r.project_id}`)} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12.5, cursor: 'pointer', padding: '5px 0', borderBottom: `1px solid ${colors.border}` }}>
                    <span style={{ color: r.progressed ? '#10b981' : '#f43f5e', width: 14 }}>{r.progressed ? '▲' : '·'}</span>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
                    <span style={{ fontFamily: mono, fontSize: 11, color: colors.textDim }}>{r.cutoff.slice(0, 7)}</span>
                    <Chip color={STAGE_COLORS[r.stage_then]}>{r.stage_then}</Chip>
                    <span style={{ fontFamily: mono, color: scoreColor(scoring === 'fitted' ? r.score_fitted : r.score_stated), width: 34, textAlign: 'right' }}>{pct(scoring === 'fitted' ? r.score_fitted : r.score_stated)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Re-fit */}
        <div style={{ ...card, marginBottom: 16 }}>
          <H note={`fitted on ${bt.fit_cases.n} cases from ${bt.fit_cases.projects} projects, cutoffs with ${bt.mature_years}+ years of follow-up`}>What the outcomes did to the starting probabilities</H>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
            {bt.fitted_priors.map((f) => {
              const moved = Math.abs(f.fitted - f.assumed) >= 0.02;
              return (
                <div key={f.layer} style={{ padding: 12, borderRadius: 12, border: `1px solid ${moved ? `${STAGE_COLORS[f.layer]}88` : colors.border}` }}>
                  <div style={{ fontFamily: mono, fontSize: 11, color: STAGE_COLORS[f.layer] }}>{f.layer}</div>
                  <div style={{ fontFamily: display, fontSize: '1.5rem', fontWeight: 700, marginTop: 4 }}>
                    <span style={{ color: colors.textDim, fontSize: '1rem', fontWeight: 400, textDecoration: moved ? 'line-through' : 'none' }}>{pct(f.assumed)}</span>
                    {moved && <> → {pct(f.fitted, f.fitted < 0.3 ? 1 : 0)}</>}
                  </div>
                  <div style={{ fontSize: 11.5, color: colors.textDim, marginTop: 3 }}>{f.n ? `${f.progressed} of ${f.n} progressed` : 'no cases yet'}</div>
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: 12, color: colors.textDim, marginTop: 10, lineHeight: 1.6 }}>
            Fitted = (progressed + {bt.shrink} × stated) / (cases + {bt.shrink}), kept rising with the ladder. A layer needs about {bt.shrink} real cases before the data outweighs the assumption, so the well-populated ANNOUNCED layer moved and the thin ones barely did.
          </div>
        </div>

        {/* Developers */}
        <div style={card}>
          <H note="developers with 3+ projects · build rate judges only projects first reported 24+ months ago">Developer track records</H>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: colors.textDim, fontSize: 11, textAlign: 'left', fontFamily: mono }}>
                  {['DEVELOPER', 'PROJECTS', 'ANNOUNCED', 'LIVE', 'BUILDING', 'JUDGED', 'BUILD RATE', 'MONTHS TO GROUND', 'SECURED GRID'].map((h) => <th key={h} style={{ padding: '6px 8px', borderBottom: `1px solid ${colors.border}` }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {devs.map((d) => (
                  <tr key={d.developer} style={{ borderBottom: `1px solid ${colors.border}` }}>
                    <td style={{ padding: 8, fontWeight: 600 }}>{d.developer} <span style={{ color: colors.textDim, fontWeight: 400, fontSize: 11.5 }}>{d.countries}</span></td>
                    <td style={{ padding: 8, fontFamily: mono }}>{d.projects}</td>
                    <td style={{ padding: 8, fontFamily: mono }}>{fmtMW(d.announced_mw)}</td>
                    <td style={{ padding: 8, fontFamily: mono, color: colors.emerald }}>{d.live || '—'}</td>
                    <td style={{ padding: 8, fontFamily: mono, color: '#22d3ee' }}>{d.building || '—'}</td>
                    <td style={{ padding: 8, fontFamily: mono, color: colors.textMuted }}>{d.judged ? `${d.built_of_judged} / ${d.judged}` : '—'}</td>
                    <td style={{ padding: 8 }}>
                      {d.build_rate == null ? <span style={{ color: colors.textDark }}>too few</span> : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 70, height: 7, background: 'rgba(255,255,255,0.06)', borderRadius: 4 }}><div style={{ width: `${100 * d.build_rate}%`, height: '100%', borderRadius: 4, background: scoreColor(d.build_rate) }} /></div>
                          <span style={{ fontFamily: mono, color: scoreColor(d.build_rate) }}>{pct(d.build_rate)}</span>
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 8, fontFamily: mono, color: colors.textMuted }}>{d.months_to_ground ?? '—'}</td>
                    <td style={{ padding: 8, fontFamily: mono, color: colors.textMuted }}>{d.secured_mw ? fmtMW(d.secured_mw) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 12, color: colors.textDim, marginTop: 10, lineHeight: 1.6 }}>
            Shown, not scored: “has built two or more other projects” could be tested on only 6 back-tested cases (4 progressed, against a 13% base rate). Encouraging, and far too few to tune a weight on.
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
