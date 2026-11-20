/**
 * Phantom Hunter — the Investigator on one project: start it, watch each step arrive.
 */
import { useEffect, useRef, useState } from 'react';
import { colors, radii } from '../styles/tokens';
import { card, mono, H } from './phantomUi';
import { bench, pct, WS_BASE, type TraceStep } from '../services/phantom';

export default function InvestigatorCard({ projectId, weakest, onDone }: { projectId: string; weakest: string | null; onDone: () => void }) {
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'failed'>('idle');
  const [err, setErr] = useState('');
  const ws = useRef<WebSocket | null>(null);
  useEffect(() => () => ws.current?.close(), []);

  const start = async () => {
    setErr(''); setSteps([]); setStatus('running');
    try {
      const r = await bench.investigate(projectId);
      const sock = new WebSocket(`${WS_BASE}${r.websocket_url}`);
      ws.current = sock;
      sock.onmessage = (ev) => {
        const d = JSON.parse(ev.data);
        for (const e of d.type === 'catchup' ? d.events : [d]) {
          if (e.type === 'investigator_step') setSteps((s) => [...s, e as TraceStep]);
          if (e.type === 'hunt_finished') { setStatus(e.status === 'completed' ? 'done' : 'failed'); sock.close(); onDone(); }
        }
      };
    } catch (e) { setErr((e as Error).message); setStatus('idle'); }
  };

  return (
    <div style={{ ...card, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <H note="one agent goes after this project's weakest assumption, then stops on its own">🔎 Investigator</H>
        <button onClick={start} disabled={status === 'running'} style={{ padding: '0.45rem 0.9rem', borderRadius: radii.md, border: 'none', background: status === 'running' ? 'rgba(255,255,255,0.06)' : 'linear-gradient(135deg,#7c3aed,#06b6d4)', color: '#fff', cursor: status === 'running' ? 'wait' : 'pointer', fontWeight: 600, fontFamily: 'inherit' }}>
          {status === 'running' ? 'Investigating…' : steps.length ? '↻ Investigate again' : '▶ Investigate'}
        </button>
      </div>
      {status === 'idle' && !steps.length && <div style={{ fontSize: 13, color: colors.textDim }}>It will try to settle: <i>{weakest || 'the weakest assumption'}</i>. Free news search, the same extractor and verifier as the hunt; a few minutes on the local model.</div>}
      {err && <div style={{ color: colors.error, fontSize: 13 }}>{err}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 6 }}>
        {steps.map((s, i) => {
          const r = s.result as Record<string, number | string> | string | null;
          return (
            <div key={i} style={{ borderLeft: `3px solid ${s.action === 'stop' ? colors.textDark : s.action.startsWith('search') ? '#a78bfa' : '#22d3ee'}`, paddingLeft: 12 }}>
              <div style={{ fontSize: 13 }}><span style={{ fontFamily: mono, fontSize: 11, color: colors.textDim }}>STEP {s.step}</span> {s.thought}</div>
              <div style={{ fontFamily: mono, fontSize: 12, color: colors.secondary, marginTop: 2 }}>{s.action}</div>
              {r && typeof r === 'object' && (
                <div style={{ fontSize: 11.5, color: colors.textDim, marginTop: 2 }}>
                  {r.results} results · {r.new_articles} new articles · {r.read} read · {r.mentions} verified mentions{r.score_after != null && <> · score now <b style={{ color: '#fff' }}>{pct(Number(r.score_after))}</b></>}
                </div>
              )}
              {typeof r === 'string' && <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{r}</div>}
            </div>
          );
        })}
        {status === 'running' && <div style={{ fontSize: 12, color: colors.textDim }}>working…</div>}
        {status === 'failed' && <div style={{ fontSize: 12, color: colors.error }}>The investigation failed — see the server log.</div>}
      </div>
    </div>
  );
}
