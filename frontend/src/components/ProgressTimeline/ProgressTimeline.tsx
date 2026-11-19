import { useEffect, useRef } from 'react';
import type { PlanEvent } from '../../types';
import './ProgressTimeline.scss';

const ICONS: Record<PlanEvent['type'], string> = {
  run_started: '📁',
  plan_start: '🧠',
  plan_done: '📋',
  resolve_start: '🔎',
  resolve_done: '🧩',
  agent_start: '▶️',
  tool_call: '🔧',
  tool_result: '✅',
  agent_result: '📦',
  agent_retry: '🔁',
  draft_start: '✍️',
  draft_done: '📝',
  reflect_start: '🪞',
  reflect_done: '🔍',
  revise_start: '🛠️',
  revise_done: '✅',
  done: '🎉',
  error: '⚠️',
};

export function ProgressTimeline({ events }: { events: PlanEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [events.length]);

  return (
    <section className="card timeline">
      <ol>
        {events.map((event, index) => (
          <li key={index} className={`event event-${event.type}`}>
            <span className="event-icon">{ICONS[event.type]}</span>
            <div className="event-body">
              {event.agent ? <span className="event-agent">{event.agent}</span> : null}
              <span className="event-message">{event.message ?? event.type}</span>
            </div>
          </li>
        ))}
      </ol>

      <div ref={bottomRef} />
    </section>
  );
}
