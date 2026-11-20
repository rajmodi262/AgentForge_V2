/**
 * Phantom Hunter — Ctrl+K command bar and the 90-second guided tour.
 *
 * Command bar: jump to any project (name, developer, city) or view, or ask the tracker a
 * question and read the cited answer in place.
 * Tour: walks a first-time reviewer through every view with one sentence each, then stops.
 * Its step lives in sessionStorage so it survives the page changes it causes.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { colors } from '../styles/tokens';
import { phantom, fmtMW, scoreColor, type ChatAnswer, type PhProject } from '../services/phantom';

const mono = "'JetBrains Mono', monospace";
const VIEWS = [
  { path: '/phantom', label: 'Overview', hint: 'announced vs real, the globe, who to call' },
  { path: '/phantom/power', label: 'Power', hint: 'secured vs unsecured grid position' },
  { path: '/phantom/time', label: 'Time machine', hint: 'replay 2019 → today, or replay a prediction' },
  { path: '/phantom/what-if', label: 'What-if', hint: 'move the priors and weights' },
  { path: '/phantom/calibration', label: 'Calibration lab', hint: 'was the score right?' },
  { path: '/phantom/workbench', label: 'Workbench', hint: 'score a list · review merges' },
];

let cache: PhProject[] | null = null;   // one fetch per page load, shared by every command bar

export function CommandBar() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [items, setItems] = useState<PhProject[]>(cache || []);
  const [sel, setSel] = useState(0);
  const [answer, setAnswer] = useState<ChatAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  useEffect(() => {
    if (!open) return;
    setQ(''); setAnswer(null); setSel(0);
    setTimeout(() => input.current?.focus(), 0);
    if (!cache) phantom.projects('?limit=1000').then((r) => { cache = r.projects; setItems(r.projects); }).catch(() => undefined);
  }, [open]);

  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    const views = VIEWS.filter((v) => !t || v.label.toLowerCase().includes(t)).map((v) => ({ kind: 'view' as const, key: v.path, label: v.label, sub: v.hint, go: () => nav(v.path) }));
    const projects = t.length < 2 ? [] : items.filter((p) => [p.name, p.developer, p.city, p.state, p.country].some((x) => (x || '').toLowerCase().includes(t)))
      .sort((a, b) => (b.capacity_mw || 0) - (a.capacity_mw || 0)).slice(0, 8)
      .map((p) => ({ kind: 'project' as const, key: p.id, label: p.name, sub: `${[p.developer, p.city || p.country].filter(Boolean).join(' · ')} · ${fmtMW(p.capacity_mw)}`, score: p.reality_score, go: () => nav(`/phantom/${p.id}`) }));
    const askIt = t.length >= 3 ? [{ kind: 'ask' as const, key: 'ask', label: `Ask the tracker: “${q.trim()}”`, sub: 'answered from verified evidence, with sources', go: () => undefined }] : [];
    return [...projects, ...views, ...askIt];
  }, [q, items, nav]);

  const run = async (i: number) => {
    const r = results[i];
    if (!r) return;
    if (r.kind === 'ask') {
      setAsking(true); setAnswer(null);
      try { setAnswer(await phantom.ask(q.trim())); } catch (e) { setAnswer({ answer: `Error: ${(e as Error).message}`, sources: [] }); }
      setAsking(false);
      return;
    }
    r.go(); setOpen(false);
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} title="Search projects and views, or ask a question (Ctrl+K)"
        style={{ padding: '8px 12px', borderRadius: 10, border: `1px solid ${colors.border}`, background: 'transparent', color: colors.textMuted, cursor: 'pointer', fontSize: 12.5, fontFamily: 'inherit' }}>
        🔍 Search <span style={{ fontFamily: mono, fontSize: 10.5, border: `1px solid ${colors.border}`, borderRadius: 5, padding: '1px 5px', marginLeft: 4 }}>Ctrl K</span>
      </button>
    );
  }
  return (
    <div role="dialog" aria-modal="true" aria-label="Command bar" onClick={() => setOpen(false)}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(5,4,11,0.6)', backdropFilter: 'blur(6px)', display: 'flex', justifyContent: 'center', paddingTop: '12vh' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(640px, calc(100vw - 32px))', maxHeight: '70vh', display: 'flex', flexDirection: 'column', background: '#100c1f', border: '1px solid rgba(196,181,253,0.3)', borderRadius: 16, boxShadow: '0 30px 80px rgba(0,0,0,0.6)', overflow: 'hidden' }}>
        <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setSel(0); setAnswer(null); }} placeholder="Project, developer, city, view — or a question"
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(results.length - 1, s + 1)); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
            if (e.key === 'Enter') run(sel);
          }}
          style={{ padding: '16px 18px', fontSize: 16, background: 'transparent', border: 'none', borderBottom: `1px solid ${colors.border}`, color: '#fff', outline: 'none', fontFamily: 'inherit' }} />
        <div role="listbox" style={{ overflowY: 'auto', padding: 6 }}>
          {results.map((r, i) => (
            <div key={r.key} role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => run(i)}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 10, cursor: 'pointer', background: i === sel ? 'rgba(124,58,237,0.22)' : 'transparent' }}>
              <span style={{ fontFamily: mono, fontSize: 10, color: colors.textDim, width: 54 }}>{r.kind.toUpperCase()}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</div>
                <div style={{ fontSize: 11.5, color: colors.textDim }}>{r.sub}</div>
              </span>
              {'score' in r && <span style={{ fontFamily: mono, fontSize: 12, color: scoreColor(r.score) }}>{Math.round(r.score * 100)}%</span>}
            </div>
          ))}
          {!results.length && <div style={{ padding: 14, color: colors.textDim, fontSize: 13 }}>Nothing matches.</div>}
          {(asking || answer) && (
            <div style={{ margin: 8, padding: 12, borderRadius: 12, border: `1px solid ${colors.border}`, fontSize: 13.5, lineHeight: 1.6 }}>
              {asking ? <span style={{ color: colors.textMuted }}>Reading the evidence…</span> : (
                <>
                  <div>{answer!.answer}</div>
                  {answer!.sources.map((s) => (
                    <div key={s.id} onClick={() => { nav(`/phantom/${s.project_id}`); setOpen(false); }} style={{ fontSize: 12, color: colors.secondary, cursor: 'pointer', marginTop: 4 }}>[{s.id}] {s.name}</div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ───────────── guided tour ─────────────
const TOUR = [
  { path: '/phantom', ms: 15000, title: 'Announced is not real', text: 'Every bar on the globe is a data centre someone announced. The solid part is how much of it the evidence says will be built.' },
  { path: '/phantom/power', ms: 15000, title: 'Power decides it', text: 'Only a small share of announced capacity has a secured grid position. Click a position to see the projects behind it.' },
  { path: '/phantom/time', ms: 15000, title: 'Watch it happen', text: 'Press play: projects appear when first reported and climb only when verified evidence is published. Most never leave the first rung.' },
  { path: '/phantom/what-if', ms: 15000, title: 'Argue with the model', text: 'Six starting probabilities and ten named adjustments. Move any of them and every project is re-scored instantly.' },
  { path: '/phantom/calibration', ms: 15000, title: 'Was it right?', text: 'History replayed: what the score said with only the news of the day, against what happened. It sizes the real pipeline well; it cannot yet predict before construction.' },
  { path: '/phantom/workbench', ms: 15000, title: 'Bring your own list', text: 'Paste any project list to see which rows are real, and settle the duplicates the resolver was unsure about.' },
];
const KEY = 'phantomTourStep';

function readStep(): number | null {
  try { const v = sessionStorage.getItem(KEY); return v == null ? null : Number(v); } catch { return null; }
}
function writeStep(v: number | null) {
  try { if (v == null) sessionStorage.removeItem(KEY); else sessionStorage.setItem(KEY, String(v)); } catch { /* private mode: the tour just stops */ }
}

export function Tour() {
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [step, setStep] = useState<number | null>(readStep);
  const s = step != null ? TOUR[step] : null;

  useEffect(() => {
    if (!s) return;
    if (pathname !== s.path) { nav(s.path); return; }
    const id = setTimeout(() => {
      const next = step! + 1 < TOUR.length ? step! + 1 : null;
      writeStep(next); setStep(next);
      if (next != null) nav(TOUR[next].path);
    }, s.ms);
    return () => clearTimeout(id);
  }, [s, step, pathname, nav]);

  const stop = () => { writeStep(null); setStep(null); };
  if (!s) {
    return (
      <button onClick={() => { writeStep(0); setStep(0); }} title="A 90-second walk through every view"
        style={{ padding: '8px 12px', borderRadius: 10, border: `1px solid ${colors.border}`, background: 'transparent', color: colors.textMuted, cursor: 'pointer', fontSize: 12.5, fontFamily: 'inherit' }}>▶ Tour</button>
    );
  }
  return (
    <div role="status" aria-live="polite" style={{ position: 'fixed', left: '50%', bottom: 24, transform: 'translateX(-50%)', zIndex: 900, width: 'min(560px, calc(100vw - 32px))', padding: '14px 16px', borderRadius: 14, background: 'rgba(16,12,31,0.96)', border: '1px solid rgba(196,181,253,0.4)', boxShadow: '0 20px 60px rgba(0,0,0,0.55)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <div style={{ fontFamily: mono, fontSize: 11, color: colors.secondary, letterSpacing: '0.12em' }}>TOUR {step! + 1} / {TOUR.length}</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {step! + 1 < TOUR.length && <button onClick={() => { const n = step! + 1; writeStep(n); setStep(n); nav(TOUR[n].path); }} style={{ padding: '4px 10px', borderRadius: 8, border: `1px solid ${colors.border}`, background: 'transparent', color: '#fff', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12 }}>Next →</button>}
          <button onClick={stop} style={{ padding: '4px 10px', borderRadius: 8, border: 'none', background: 'rgba(255,255,255,0.08)', color: colors.textMuted, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12 }}>End tour</button>
        </div>
      </div>
      <div style={{ fontWeight: 700, fontSize: 15, marginTop: 6 }}>{s.title}</div>
      <div style={{ fontSize: 13.5, color: colors.textMuted, marginTop: 4, lineHeight: 1.55 }}>{s.text}</div>
      <div style={{ height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, marginTop: 10, overflow: 'hidden' }}>
        <div key={step} style={{ height: '100%', background: 'linear-gradient(90deg,#7c3aed,#06b6d4)', animation: `tourbar ${s.ms}ms linear forwards` }} />
      </div>
      <style>{'@keyframes tourbar { from { width: 0 } to { width: 100% } } @media (prefers-reduced-motion: reduce) { [style*="tourbar"] { animation: none !important; width: 100% } }'}</style>
    </div>
  );
}
