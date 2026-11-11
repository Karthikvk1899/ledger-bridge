import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Side = { event_id: string; amount_minor: number; currency: string };
type RecordView = { correlation_id: string; status: 'pending' | 'matched' | 'mismatched'; expected: Side | null; actual: Side | null };
export async function lookup(id: string): Promise<RecordView> {
  const response = await fetch(`/v1/reconciliations/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(response.status === 404 ? 'No reconciliation found' : `Request failed (${response.status})`);
  return response.json() as Promise<RecordView>;
}
export function App() {
  const [id, setId] = useState('');
  const [record, setRecord] = useState<RecordView | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function search(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError(''); setRecord(null);
    try { setRecord(await lookup(id.trim())); } catch (err) { setError(err instanceof Error ? err.message : 'Unknown error'); }
    finally { setLoading(false); }
  }
  return <main><header><span className="eyebrow">OPEN SOURCE · EVENT RECONCILIATION</span><h1>Ledger Bridge</h1><p>Trace two independent event streams to one verifiable outcome.</p></header>
    <form onSubmit={search}><label htmlFor="id">Correlation ID</label><div className="search"><input id="id" value={id} onChange={e => setId(e.target.value)} maxLength={128} required placeholder="trade-1001" /><button disabled={loading}>{loading ? 'Checking…' : 'Inspect'}</button></div></form>
    {error && <p role="alert" className="error">{error}</p>}
    {record && <section aria-label="Reconciliation result"><div className="result-head"><h2>{record.correlation_id}</h2><span className={`badge ${record.status}`}>{record.status}</span></div><div className="grid">{(['expected', 'actual'] as const).map(side => <article key={side}><h3>{side}</h3>{record[side] ? <><strong>{record[side].amount_minor} <small>minor units · {record[side].currency}</small></strong><p>Event ID: {record[side].event_id}</p></> : <p>Awaiting event</p>}</article>)}</div></section>}
    <footer>Deterministic outcomes · At least once delivery · Seven day retention</footer></main>;
}
if (document.getElementById('root')) createRoot(document.getElementById('root')!).render(<App />);
