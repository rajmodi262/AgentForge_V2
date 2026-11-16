/**
 * Phantom Hunter — the power dossier of one project.
 *
 * A one-line diagram (supplier → connection → campus, with anything generated on site),
 * coloured by grid position, then every power fact with the sentence it came from.
 */
import { colors } from '../styles/tokens';
import { card, mono, H, Chip } from './phantomUi';
import { fmtMW, GRID_COLORS, type GridPosition, type PowerBrief, type PowerFact } from '../services/phantom';

const FIELD_LABEL: Record<string, string> = {
  grid: 'Grid position', utility: 'Supplier', grid_kv: 'Voltage (kV)', grid_mva: 'Contracted MVA', substation: 'Substation', onsite: 'On-site generation',
  renewable: 'Renewable procurement', cooling: 'Cooling', rack_kw: 'Rack density (kW)', pue: 'PUE', water: 'Water', contractor: 'Contractor', equipment: 'Equipment', financier: 'Financier / investor',
};

function Node({ x, title, lines, color, dashed }: { x: number; title: string; lines: string[]; color: string; dashed?: boolean }) {
  return (
    <g transform={`translate(${x} 18)`}>
      <rect width={190} height={78} rx={12} fill={`${color}14`} stroke={color} strokeDasharray={dashed ? '5 4' : undefined} />
      <text x={14} y={22} fontSize="10" fill={color} fontFamily="JetBrains Mono" letterSpacing="1.5">{title}</text>
      {lines.slice(0, 3).map((l, i) => <text key={i} x={14} y={42 + i * 15} fontSize="12" fill={i === 0 ? '#fff' : '#94a3b8'}>{l.length > 26 ? `${l.slice(0, 25)}…` : l}</text>)}
    </g>
  );
}

export default function PowerCard({ power, facts, capacityMw, partner }: { power?: Partial<PowerBrief>; facts?: PowerFact[]; capacityMw: number | null; partner: string | null }) {
  const pos = (power?.grid_position || 'NO_EVIDENCE') as GridPosition;
  const c = GRID_COLORS[pos];
  const known = pos !== 'NO_EVIDENCE';
  const supplier = power?.utilities?.[0] || partner;
  const conn = [power?.grid_kv && `${power.grid_kv} kV`, power?.grid_mva && `${power.grid_mva} MVA`].filter(Boolean) as string[];
  const connLines = [...conn, power?.substation ? `${power.substation} substation` : ''].filter(Boolean);
  const campus = [fmtMW(capacityMw), ...(power?.onsite?.length ? [`on site: ${power.onsite.join(', ')}`] : []), ...(power?.cooling?.length ? [power.cooling.slice(0, 2).join(', ')] : [])];
  const list = facts || [];
  const wire = known ? c : '#475569';
  return (
    <div style={{ ...card, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
        <H note="what the sources say about power, cooling and who is building it">⚡ Power dossier</H>
        <Chip color={c}>{power?.grid_label || 'No public evidence of power'}</Chip>
      </div>
      <svg viewBox="0 0 760 116" style={{ width: '100%', display: 'block' }} role="img" aria-label="Power path: supplier, connection, campus">
        <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill={wire} /></marker></defs>
        <Node x={4} title="SUPPLIER" lines={supplier ? [supplier, ...(power?.utilities || []).slice(1, 3)] : ['not named', 'in public sources']} color={supplier ? '#22d3ee' : '#475569'} dashed={!supplier} />
        <line x1={198} y1={57} x2={280} y2={57} stroke={wire} strokeWidth={2} strokeDasharray={power?.secured ? undefined : '6 5'} markerEnd="url(#arr)" />
        <Node x={285} title="CONNECTION" lines={connLines.length ? connLines : ['no detail published']} color={connLines.length ? '#c4b5fd' : '#475569'} dashed={!connLines.length} />
        <line x1={479} y1={57} x2={561} y2={57} stroke={wire} strokeWidth={2} strokeDasharray={power?.secured ? undefined : '6 5'} markerEnd="url(#arr)" />
        <Node x={566} title="CAMPUS" lines={campus} color={c} />
        <text x={239} y={48} textAnchor="middle" fontSize="9.5" fill="#64748b" fontFamily="JetBrains Mono">{power?.secured ? 'secured' : 'not evidenced'}</text>
      </svg>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '10px 0 4px' }}>
        {(power?.renewable || []).map((x) => <Chip key={x} color="#10b981" title="Renewable procurement">{x}</Chip>)}
        {power?.rack_kw && <Chip color="#60a5fa">{power.rack_kw} kW per rack</Chip>}
        {power?.pue && <Chip color="#60a5fa">PUE {power.pue}</Chip>}
        {(power?.water || []).map((x) => <Chip key={x} color="#60a5fa">{x}</Chip>)}
        {(power?.contractors || []).map((x) => <Chip key={x} color="#f59e0b" title="Contractor">🏗 {x}</Chip>)}
        {(power?.financiers || []).map((x) => <Chip key={x} color="#e879f9" title="Financier / investor">💰 {x}</Chip>)}
      </div>
      {list.length === 0 ? (
        <div style={{ color: colors.textDim, fontSize: 13, marginTop: 8 }}>
          The sources say nothing specific about this project&apos;s power. That is not proof it has none: supply agreements are often never announced. It is the first thing a filing would settle.
        </div>
      ) : (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 9 }}>
          {list.map((f, i) => (
            <div key={i} style={{ borderLeft: `3px solid ${f.planned ? colors.textDark : '#22d3ee'}`, paddingLeft: 12 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontFamily: mono, fontSize: 10.5, color: colors.textDim, letterSpacing: '0.08em' }}>{(FIELD_LABEL[f.field] || f.field).toUpperCase()}</span>
                <b style={{ fontSize: 13 }}>{String(f.value)}</b>
                {f.planned && <Chip title="Stated as a plan or design intent, not as done">planned</Chip>}
              </div>
              <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 3, lineHeight: 1.5 }}>“{f.quote}”</div>
              {f.article && <a href={f.article.url} target="_blank" rel="noreferrer" style={{ fontSize: 11.5, color: colors.secondary }}>{f.article.source} — {f.article.title.slice(0, 80)} ↗</a>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
