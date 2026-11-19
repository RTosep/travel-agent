import { useState } from 'react';
import type { PlanEvent } from '../../types';
import { currentPhase } from '../../utils/phase';
import { ProgressTimeline } from '../ProgressTimeline/ProgressTimeline';
import './ThinkingPanel.scss';

export function ThinkingPanel({
  events,
  loading,
  runId,
}: {
  events: PlanEvent[];
  loading: boolean;
  runId: string | null;
}) {
  const [open, setOpen] = useState(false);
  const phase = currentPhase(events);
  const failed = events.some((event) => event.type === 'error');

  return (
    <section className="thinking">
      <div className="card thinking-bar">
        <div className="thinking-status">
          {loading ? (
            <span className="spinner" />
          ) : (
            <span className={failed ? 'thinking-failed' : 'thinking-check'}>
              {failed ? '!' : '✓'}
            </span>
          )}
          <div>
            <strong>{phase}</strong>
            <span className="thinking-meta">
              {events.length} 步{runId ? ` · ${runId}` : ''}
            </span>
          </div>
        </div>

        <button
          type="button"
          className="thinking-toggle"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
        >
          {open ? '收起思考详情' : '思考详情'}
          <span className={`chevron${open ? ' open' : ''}`}>▾</span>
        </button>
      </div>

      {open ? <ProgressTimeline events={events} /> : null}
    </section>
  );
}
