/**
 * Phantom Hunter — shared building blocks for the control-room pages
 * (tab bar, cards, stat tiles, bars, sliders). One place, so every page reads the same.
 */
import { useNavigate, useLocation } from 'react-router-dom';
import { colors, radii } from '../styles/tokens';

export const mono = "'JetBrains Mono', monospace";
export const display = "'Space Grotesk', sans-serif";
export const card: React.CSSProperties = { background: colors.bgCard, border: `1px solid ${colors.border}`, borderRadius: radii.lg, padding: '1.25rem' };

const TABS = [
  { path: '/phantom', label: 'Overview', hint: 'Announced vs real' },
  { path: '/phantom/power', label: 'Power', hint: 'Who has a grid position' },
  { path: '/phantom/time', label: 'Time machine', hint: 'Replay 2019 → today' },
  { path: '/phantom/what-if', label: 'What-if', hint: 'Argue with the model' },
  { path: '/phantom/calibration', label: 'Calibration lab', hint: 'Was the score right?' },
];

export function PhantomNav() {
  const nav = useNavigate();
  const { pathname } = useLocation();
  return (
    <div role="tablist" aria-label="Phantom Hunter views" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18, padding: 5, borderRadius: 14, border: `1px solid ${colors.border}`, background: 'rgba(255,255,255,0.02)', width: 'fit-content', maxWidth: '100%' }}>
      {TABS.map((t) => {
        const on = pathname === t.path;
        return (
          <button key={t.path} role="tab" aria-selected={on} title={t.hint} onClick={() => nav(t.path)}
            style={{ padding: '8px 14px', borderRadius: 10, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              color: on ? '#fff' : colors.textMuted, background: on ? 'linear-gradient(135deg, rgba(124,58,237,0.55), rgba(6,182,212,0.35))' : 'transparent',
              boxShadow: on ? '0 0 0 1px rgba(196,181,253,0.35), 0 6px 20px rgba(124,58,237,0.25)' : 'none', transition: 'all .18s ease' }}>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export function PageHead({ kicker, title, children }: { kicker: string; title: string; children?: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontFamily: mono, fontSize: 11, letterSpacing: '0.2em', color: colors.secondary }}>{kicker}</div>
      <h1 style={{ margin: '6px 0 4px', fontSize: '1.9rem', fontFamily: display }}>{title}</h1>
      {children && <div style={{ color: colors.textMuted, fontSize: 14, maxWidth: 760, lineHeight: 1.55 }}>{children}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ ...card, flex: 1, minWidth: 170 }}>
      <div style={{ fontSize: 11, letterSpacing: '0.12em', color: colors.textMuted, fontFamily: mono }}>{label}</div>
      <div style={{ fontSize: '1.9rem', fontWeight: 700, color: color || colors.white, marginTop: 6, fontFamily: display, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: colors.textDim, marginTop: 4, lineHeight: 1.45 }}>{sub}</div>}
    </div>
  );
}

export const H = ({ children, note }: { children: React.ReactNode; note?: string }) => (
  <div style={{ fontWeight: 600, marginBottom: 12 }}>{children}{note && <span style={{ fontSize: 11.5, color: colors.textDim, fontWeight: 400 }}> — {note}</span>}</div>
);

export function Chip({ children, color = colors.textMuted, title }: { children: React.ReactNode; color?: string; title?: string }) {
  return <span title={title} style={{ fontFamily: mono, fontSize: 10.5, color, border: `1px solid ${color}66`, background: `${color}14`, borderRadius: 6, padding: '2px 7px', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>{children}</span>;
}

/** A labelled range input that shows its value and how far it has moved from a reference. */
export function Slider({ label, value, min, max, step, base, onChange, format }: { label: string; value: number; min: number; max: number; step: number; base: number; onChange: (v: number) => void; format: (v: number) => string }) {
  const moved = Math.abs(value - base) > step / 2;
  return (
    <label style={{ display: 'block', marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 3 }}>
        <span style={{ color: moved ? '#fff' : colors.textMuted }}>{label}</span>
        <span style={{ fontFamily: mono, color: moved ? colors.amber : colors.textMuted }}>{format(value)}{moved && <span style={{ color: colors.textDim }}> (was {format(base)})</span>}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: moved ? '#f59e0b' : '#7c3aed', cursor: 'pointer' }} />
    </label>
  );
}

export const Loading = ({ what }: { what: string }) => <div style={{ ...card, color: colors.textMuted }}>Loading {what}…</div>;
export const Fail = ({ msg }: { msg: string }) => <div style={{ ...card, borderColor: colors.error, color: colors.error }}>{msg}</div>;
