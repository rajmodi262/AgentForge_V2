/**
 * Phantom Hunter — Workbench
 *
 * Two jobs a person does with the tracker:
 *   Score a list   paste or upload anyone's project list; each row is matched to a tracked
 *                  project and gets its reality score, grid position and weakest assumption.
 *   Review merges  pairs the resolver kept apart because it was unsure. A person decides;
 *                  the decision is stored and applied on every rebuild.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import { PhantomNav, PageHead, Stat, H, Chip, card, mono } from '../components/phantomUi';
import { colors, radii } from '../styles/tokens';
import { bench, fmtMW, pct, scoreColor, GRID_COLORS, type ImportResult, type MergeCandidate } from '../services/phantom';

const SAMPLE = `name,developer,city,capacity_mw
KUL2,Vantage Data Centers,Cyberjaya,256
JHB1,AirTrunk,Johor,150
Chandanvelly campus,CtrlS,Hyderabad,600
Mega campus,Unknown Developer,Nagpur,500`;

function ImportPanel() {
  const nav = useNavigate();
  const [csv, setCsv] = useState(SAMPLE);
  const [res, setRes] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const run = async () => {
    setBusy(true); setErr('');
    try { setRes(await bench.importCsv(csv)); } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  };
  const file = (f?: File) => f && f.text().then(setCsv);
  return (
    <div style={{ ...card, marginBottom: 16 }}>
      <H note="name, developer, city / location, country, MW — any order, extra columns ignored">Score a project list</H>
      <textarea value={csv} onChange={(e) => setCsv(e.target.value)} rows={6} aria-label="CSV to score" spellCheck={false}
        style={{ width: '100%', boxSizing: 'border-box', fontFamily: mono, fontSize: 12.5, padding: 10, background: colors.bgInput, color: colors.text, border: `1px solid ${colors.border}`, borderRadius: radii.md, resize: 'vertical' }} />
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
        <button onClick={run} disabled={busy} style={{ padding: '0.55rem 1.1rem', borderRadius: radii.md, border: 'none', background: 'linear-gradient(135deg,#7c3aed,#06b6d4)', color: '#fff', fontWeight: 700, cursor: busy ? 'wait' : 'pointer', fontFamily: 'inherit' }}>{busy ? 'Matching…' : 'Score this list'}</button>
        <label style={{ fontSize: 13, color: colors.secondary, cursor: 'pointer' }}>or upload a CSV<input type="file" accept=".csv,text/csv" onChange={(e) => file(e.target.files?.[0])} style={{ display: 'none' }} /></label>
        {err && <span style={{ color: colors.error, fontSize: 13 }}>{err}</span>}
      </div>
      {res && (
        <>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '16px 0 10px' }}>
            <Stat label="ROWS MATCHED" value={`${res.summary.matched} / ${res.summary.rows}`} sub="to a project we track" color="#22d3ee" />
            <Stat label="ANNOUNCED IN YOUR LIST" value={fmtMW(res.summary.announced_mw)} sub={`${fmtMW(res.summary.matched_mw)} of it matched`} />
            <Stat label="REALITY-WEIGHTED (MATCHED)" value={fmtMW(res.summary.reality_mw)} sub={res.summary.matched_mw ? `${pct(res.summary.reality_mw / res.summary.matched_mw)} of matched capacity` : 'nothing matched'} color={colors.emerald} />
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead><tr style={{ color: colors.textDim, fontSize: 11, textAlign: 'left', fontFamily: mono }}>
                {['ROW', 'YOUR PROJECT', 'MATCHED TO', 'REALITY', 'GRID', 'WEAKEST ASSUMPTION'].map((h) => <th key={h} style={{ padding: '6px 8px', borderBottom: `1px solid ${colors.border}` }}>{h}</th>)}
              </tr></thead>
              <tbody>
                {res.rows.map((r) => (
                  <tr key={r.row} style={{ borderBottom: `1px solid ${colors.border}`, cursor: r.project_id ? 'pointer' : 'default' }} onClick={() => r.project_id && nav(`/phantom/${r.project_id}`)}>
                    <td style={{ padding: 8, fontFamily: mono, color: colors.textDim }}>{r.row}</td>
                    <td style={{ padding: 8 }}><b>{r.name}</b><div style={{ fontSize: 11.5, color: colors.textDim }}>{[r.developer, r.city, r.capacity_mw && fmtMW(r.capacity_mw)].filter(Boolean).join(' · ')}</div></td>
                    <td style={{ padding: 8 }}>{r.matched ? <>{r.project}<div style={{ fontSize: 11, color: colors.textDim }}>{pct(r.confidence)} alike · {r.why.join('; ')}</div></> : <span style={{ color: colors.textDim }}>not tracked{r.in_scope === false ? ' (outside India / Malaysia)' : ''}</span>}</td>
                    <td style={{ padding: 8, fontFamily: mono, color: r.matched ? scoreColor(r.reality_score || 0) : colors.textDark }}>{r.matched ? pct(r.reality_score) : '—'}</td>
                    <td style={{ padding: 8 }}>{r.grid_position ? <Chip color={GRID_COLORS[r.grid_position]}>{r.grid_position.replace(/_/g, ' ').toLowerCase()}</Chip> : '—'}</td>
                    <td style={{ padding: 8, fontSize: 12, color: colors.textDim, maxWidth: 340 }}>{r.weakest_assumption || (r.matched ? '' : 'We have no public evidence for this row. A hunt or an investigation is the next step.')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Side({ p }: { p: MergeCandidate['a'] }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontWeight: 600, fontSize: 13.5 }}>{p.name}</div>
      <div style={{ fontSize: 12, color: colors.textDim, marginTop: 2 }}>{[p.developer, p.city, fmtMW(p.capacity_mw)].filter(Boolean).join(' · ')}</div>
      <div style={{ fontSize: 11.5, color: colors.textDim }}>{p.n_sources} source{p.n_sources === 1 ? '' : 's'} · first seen {p.first_seen || '—'} · <span style={{ color: scoreColor(p.reality_score) }}>{pct(p.reality_score)}</span></div>
    </div>
  );
}

function MergePanel() {
  const [data, setData] = useState<Awaited<ReturnType<typeof bench.candidates>> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState('');
  const load = () => bench.candidates().then(setData).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const decide = async (c: MergeCandidate, d: 'merge' | 'distinct') => {
    setBusy(c.a.anchor + c.b.anchor);
    try { await bench.decide(c.a.anchor, c.b.anchor, d); await load(); } catch (e) { setErr((e as Error).message); }
    setBusy(null);
  };
  return (
    <div style={card}>
      <H note="the resolver kept these apart because it was not sure — a person decides">Merge review</H>
      {err && <div style={{ color: colors.error, fontSize: 13, marginBottom: 8 }}>{err}</div>}
      {!data && !err && <div style={{ color: colors.textMuted, fontSize: 13 }}>Loading candidates…</div>}
      {data && (
        <>
          <div style={{ fontSize: 13, color: colors.textMuted, marginBottom: 12 }}>
            {data.candidates.length} undecided pairs. The {data.candidates.filter((c) => c.score >= 0.8).length} most alike may count <b style={{ color: '#fff' }}>{fmtMW(data.double_counted_mw)}</b> twice. {data.decided.length} decided so far. {data.note}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {data.candidates.slice(0, 25).map((c) => {
              const key = c.a.anchor + c.b.anchor;
              return (
                <div key={key} style={{ border: `1px solid ${c.score >= 0.8 ? 'rgba(245,158,11,0.45)' : colors.border}`, borderRadius: 12, padding: 12 }}>
                  <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Side p={c.a} />
                    <div style={{ fontFamily: mono, fontSize: 12, color: c.score >= 0.8 ? colors.amber : colors.textMuted, textAlign: 'center' }}>{pct(c.score)}<br /><span style={{ fontSize: 10, color: colors.textDim }}>alike</span></div>
                    <Side p={c.b} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>{c.reasons.map((r) => <Chip key={r} color={c.kind === 'cross_developer' && r.startsWith('different') ? colors.amber : colors.textMuted}>{r}</Chip>)}</div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button disabled={!!busy} onClick={() => decide(c, 'merge')} style={{ padding: '6px 12px', borderRadius: 8, border: 'none', cursor: busy ? 'wait' : 'pointer', background: 'rgba(16,185,129,0.25)', color: '#fff', fontFamily: 'inherit', fontSize: 12.5 }}>{busy === key ? 'Rebuilding…' : 'Same project'}</button>
                      <button disabled={!!busy} onClick={() => decide(c, 'distinct')} style={{ padding: '6px 12px', borderRadius: 8, border: `1px solid ${colors.border}`, cursor: busy ? 'wait' : 'pointer', background: 'transparent', color: colors.textMuted, fontFamily: 'inherit', fontSize: 12.5 }}>Different</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default function PhantomWorkbench() {
  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <PhantomNav />
        <PageHead kicker="WORKBENCH" title="Bring your list. Settle the doubts.">
          Paste any project list to see which rows are real, or decide the pairs the resolver was unsure about. Merge decisions are stored and applied on every rebuild; nothing is guessed.
        </PageHead>
        <ImportPanel />
        <MergePanel />
      </div>
    </DashboardLayout>
  );
}
