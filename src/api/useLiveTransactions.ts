import { useEffect, useRef, useState } from 'react';
import { api } from './client';
import { tokenStore } from './tokenStore';
import type { LiveEvent, LiveItem, LiveResponse } from './types';

const WS_BASE = (import.meta.env.VITE_WS_URL as string | undefined) ?? '/api/v1/ws/live';

export function useLiveTransactions(max = 100) {
  const [items, setItems] = useState<LiveItem[]>([]);
  const cursor = useRef(0);

  async function resync() {
    const after = cursor.current;
    const res = await api.get<LiveResponse>('/transactions/live', {
      params: after ? { after_seq: after } : { limit: max },
    });
    const fresh = res.data.items.filter((i) => i.seq > cursor.current);
    if (fresh.length) {
      cursor.current = Math.max(cursor.current, ...fresh.map((i) => i.seq));
      setItems((prev) => [...fresh.sort((a, b) => b.seq - a.seq), ...prev].slice(0, max));
    } else if (!after) {
      // first load with no after_seq returns newest-first window
      const initial = res.data.items;
      if (initial.length) cursor.current = Math.max(...initial.map((i) => i.seq));
      setItems(initial.slice(0, max));
    }
  }

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;

    void resync();

    function connect() {
      const token = tokenStore.getAccess();
      const url = `${WS_BASE}${WS_BASE.includes('?') ? '&' : '?'}token=${token ?? ''}`;
      ws = new WebSocket(url);
      ws.onopen = () => { void resync(); };
      ws.onmessage = (e) => {
        const ev = JSON.parse(e.data) as LiveEvent & { type?: string };
        if ((ev as { type?: string }).type === 'connected') return;
        if ((ev as { type?: string }).type === 'resync') { void resync(); return; }
        if (typeof ev.seq !== 'number' || ev.seq <= cursor.current) return;
        cursor.current = ev.seq;
        const item: LiveItem = {
          seq: ev.seq, transaction_id: ev.transaction_id, bank: ev.bank ?? '',
          type: ev.type ?? '', amount: ev.amount ?? 0, fraud_score: ev.fraud_score,
          typology: ev.typology, status: ev.status, surfaced_at: ev.surfaced_at,
        };
        setItems((prev) => [item, ...prev].slice(0, max));
      };
      ws.onclose = () => {
        if (!closed) setTimeout(connect, 1000);  // reconnect → resync on next open
      };
    }
    connect();

    return () => { closed = true; ws?.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [max]);

  return { items };
}
