/**
 * Phantom Hunter — Power
 *
 * The question the market argues about: how much of the pipeline has a grid position?
 * One split bar (secured vs not), the six grid positions as a clickable filter, the
 * supplier-facing signals (who has no utility named, who wants liquid cooling), and the
 * projects behind every number.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import { PhantomNav, PageHead, Stat, H, Chip, card, mono, Loading, Fail } from '../components/phantomUi';
import { colors } from '../styles/tokens';
import { lab, fmtMW, pct, GRID_COLORS, GRID_ORDER, type GridPosition, type PowerView, type Share } from '../services/phantom';
import { ScorePill, StagePill } from './PhantomHunter';

const SIGNALS: { key: keyof PowerView['headline']; label: string; who: string; color: string }[] = [
  { key: 'no_utility_named', label: 'No power supplier named', who: 'Open door for utilities and IPPs', color: '#f43f5e' },
  { key: 'renewable_signal', label: 'Renewable procurement mentioned', who: 'PPA, green tariff, CRESS, open access', color: '#10b981' },
  { key: 'liquid_cooling_signal', label: 'Liquid cooling signalled', who: 'Direct-to-chip, immersion, rear-door', color: '#22d3ee' },
  { key: 'btm_signal', label: 'On-site generation', who: 'Gas, fuel cells, solar, batteries, SMR', color: '#f59e0b' },
  { key: 'low_water_signal', label: 'Low-water design', who: 'Waterless, closed loop, reclaimed water', color: '#60a5fa' },
];

export default function PhantomPower() {
  const nav = useNavigate();
  const [country, setCountry] = useState('');
  const [view, setView] = useState<PowerView | null>(null);
  const [err, setErr] = useState('');
  const [pos, setPos] = useState<GridPosition>('AGREEMENT');

  useEffect(() => { setView(null); lab.power(country).then(setView).catch((e) => setErr(e.message)); }, [country]);

  const h = view?.headline;
  const rows = useMemo(() => view?.projects_by_position[pos] || [], [view, pos]);

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <PhantomNav />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
          <PageHead kicker="POWER FORENSICS" title="Who actually has power?">
            A data centre is a power project with servers attached. Every project's verified sentences are read for its grid position, supplier, connection, cooling and who builds and funds it. Rules only, and every fact keeps its quote.
          </PageHead>
          <select value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country" style={{ background: colors.bgInput, color: colors.text, border: `1px solid ${colors.border}`, borderRadius: 8, padding: '6px 10px', marginBottom: 14 }}>
            <option value="">All countries</option><option>India</option><option>Malaysia</option><option>Singapore</option><option>Indonesia</option>
          </select>
        </div>
        {err && <Fail msg={err} />}
        {!view && !err && <Loading what="power forensics" />}

        {h && view && (
          <>
            {/* The split */}
            <div style={{ ...card, marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
                <div>
                  <span style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: '2.6rem', fontWeight: 700, color: '#22d3ee' }}>{pct(h.secured_share)}</span>
                  <span style={{ fontSize: 15, color: colors.textMuted, marginLeft: 10 }}>of {fmtMW(h.announced_mw)} announced has a secured grid position</span>
                </div>
                <div style={{ fontSize: 12.5, color: colors.textDim, maxWidth: 420, textAlign: 'right' }}>Secured = operating, or a verified supply agreement. “No public evidence” is not proof there is no agreement, so this is a floor.</div>
              </div>
              <div role="img" aria-label="Capacity by grid position" style={{ display: 'flex', height: 26, borderRadius: 8, overflow: 'hidden', marginTop: 14, background: 'rgba(255,255,255,0.04)' }}>
                {GRID_ORDER.filter((k) => h.grid[k].mw > 0).map((k) => (
                  <div key={k} onClick={() => setPos(k)} title={`${view.labels[k]} · ${fmtMW(h.grid[k].mw)} · ${h.grid[k].projects} projects`}
                    style={{ width: `${(100 * h.grid[k].mw) / h.announced_mw}%`, background: GRID_COLORS[k], opacity: pos === k ? 1 : 0.55, cursor: 'pointer', transition: 'opacity .15s' }} />
                ))}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8, marginTop: 12 }}>
                {GRID_ORDER.filter((k) => h.grid[k].projects > 0).map((k) => (
                  <button key={k} onClick={() => setPos(k)} aria-pressed={pos === k}
                    style={{ textAlign: 'left', padding: '10px 12px', borderRadius: 10, cursor: 'pointer', fontFamily: 'inherit', color: '#fff',
                      border: `1px solid ${pos === k ? GRID_COLORS[k] : colors.border}`, background: pos === k ? `${GRID_COLORS[k]}1c` : 'transparent' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5 }}>
                      <span style={{ width: 9, height: 9, borderRadius: 3, background: GRID_COLORS[k], flexShrink: 0 }} />{view.labels[k]}
                    </div>
                    <div style={{ fontFamily: mono, fontSize: 15, marginTop: 5 }}>{fmtMW(h.grid[k].mw)} <span style={{ color: colors.textDim, fontSize: 11.5 }}>· {h.grid[k].projects} projects</span></div>
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
              <Stat label="NOT YET OPERATING" value={fmtMW(h.pipeline_mw)} sub="where a supplier can still win" />
              <Stat label="…WITH A SIGNED GRID AGREEMENT" value={fmtMW(h.pipeline_secured.mw)} sub={`${pct(h.pipeline_secured.share)} of that pipeline · ${h.pipeline_secured.projects} projects`} color="#22d3ee" />
              <Stat label="PROJECTS WITH ANY POWER FACT" value={`${h.with_any_fact} / ${h.projects}`} sub="what public news states at all" color="#c4b5fd" />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.5fr)', gap: 16, marginBottom: 16 }}>
              {/* Signals */}
              <div style={card}>
                <H note="share of capacity not yet operating">Supplier signals</H>
                {SIGNALS.map((s) => {
                  const v = h[s.key] as Share;
                  return (
                    <div key={s.key} style={{ marginBottom: 14 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                        <span>{s.label}</span><span style={{ fontFamily: mono, color: s.color }}>{fmtMW(v.mw)} · {pct(v.share)}</span>
                      </div>
                      <div style={{ height: 7, background: 'rgba(255,255,255,0.05)', borderRadius: 4, margin: '5px 0 3px' }}>
                        <div style={{ width: `${Math.min(100, 100 * (v.share || 0))}%`, height: '100%', background: s.color, borderRadius: 4, transition: 'width .4s ease' }} />
                      </div>
                      <div style={{ fontSize: 11.5, color: colors.textDim }}>{s.who} · {v.projects} projects</div>
                    </div>
                  );
                })}
                <div style={{ fontSize: 11.5, color: colors.textDim, borderTop: `1px solid ${colors.border}`, paddingTop: 10, lineHeight: 1.6 }}>
                  How often the news states each detail: supplier {h.coverage.utilities} · voltage {h.coverage.grid_kv} · MVA {h.coverage.grid_mva} · substation {h.coverage.substation} · cooling {h.coverage.cooling} · contractor {h.coverage.contractors} · financier {h.coverage.financiers}.
                </div>
              </div>

              {/* Projects in the selected position */}
              <div style={card}>
                <H note={`${rows.length} shown, largest first`}><span style={{ color: GRID_COLORS[pos] }}>■</span> {view.labels[pos]}</H>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 520, overflowY: 'auto', paddingRight: 4 }}>
                  {rows.length === 0 && <div style={{ color: colors.textDim, fontSize: 13 }}>No projects in this position.</div>}
                  {rows.map((p) => {
                    const pw = p.power || {};
                    const conn = [pw.grid_kv && `${pw.grid_kv} kV`, pw.grid_mva && `${pw.grid_mva} MVA`, pw.substation && `${pw.substation} substation`].filter(Boolean).join(' · ');
                    return (
                      <div key={p.id} onClick={() => nav(`/phantom/${p.id}`)} style={{ padding: '10px 12px', borderRadius: 10, border: `1px solid ${colors.border}`, cursor: 'pointer' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                          <div style={{ fontWeight: 600, fontSize: 13.5 }}>{p.name}</div>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}><StagePill stage={p.stage_name} /><ScorePill s={p.reality_score} /></div>
                        </div>
                        <div style={{ fontSize: 12, color: colors.textDim, marginTop: 3 }}>{fmtMW(p.capacity_mw)} · {p.city || p.state || p.country}</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 7 }}>
                          {(pw.utilities || []).map((u) => <Chip key={u} color="#22d3ee" title="Power supplier named">⚡ {u}</Chip>)}
                          {conn && <Chip color="#c4b5fd" title="Grid connection">{conn}</Chip>}
                          {(pw.onsite || []).map((u) => <Chip key={u} color="#f59e0b" title="On-site generation">{u}</Chip>)}
                          {(pw.cooling || []).slice(0, 2).map((u) => <Chip key={u} color="#60a5fa" title="Cooling">{u}</Chip>)}
                          {(pw.renewable || []).slice(0, 2).map((u) => <Chip key={u} color="#10b981" title="Renewable procurement">{u}</Chip>)}
                          {!pw.n_facts && <span style={{ fontSize: 11.5, color: colors.textDark }}>no power detail in the sources</span>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            <div style={{ fontSize: 12, color: colors.textDim }}>{view.note}</div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
