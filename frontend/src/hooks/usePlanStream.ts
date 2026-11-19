import { useCallback, useRef, useState } from 'react';
import { streamPlan } from '../api';
import type { PlanEvent, TripPlan } from '../types';

export function usePlanStream() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<PlanEvent[]>([]);
  const [trip, setTrip] = useState<TripPlan | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const inFlight = useRef(false);

  const start = useCallback(async (prompt: string) => {
    const text = prompt.trim();
    if (!text || inFlight.current) return;

    inFlight.current = true;
    setLoading(true);
    setError(null);
    setEvents([]);
    setTrip(null);
    setRunId(null);

    let finished = false;

    try {
      await streamPlan(text, (event) => {
        setEvents((prev) => [...prev, event]);

        if (event.type === 'run_started' && event.run_id) {
          setRunId(event.run_id);
        }
        if (event.type === 'done' && event.data) {
          setTrip(event.data as TripPlan);
          finished = true;
        }
        if (event.type === 'error') {
          setError(event.message ?? '生成失败');
          finished = true;
        }
      });

      if (!finished) {
        setError('连接意外中断，请重试。');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);

  return { loading, error, events, trip, runId, start };
}
