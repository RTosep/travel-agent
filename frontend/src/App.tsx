import { ErrorBanner } from './components/ErrorBanner/ErrorBanner';
import { Header } from './components/Header/Header';
import { PlanForm } from './components/PlanForm/PlanForm';
import { ThinkingPanel } from './components/ThinkingPanel/ThinkingPanel';
import { TripPlanView } from './components/TripPlanView/TripPlanView';
import { usePlanStream } from './hooks/usePlanStream';
import './App.scss';

export default function App() {
  const { loading, error, events, trip, runId, start } = usePlanStream();

  return (
    <div className="app">
      <Header />

      <main className="layout">
        <PlanForm loading={loading} onSubmit={start} />

        {events.length > 0 || loading ? (
          <ThinkingPanel events={events} loading={loading} runId={runId} />
        ) : null}

        {error ? <ErrorBanner message={error} /> : null}

        {trip ? <TripPlanView trip={trip} /> : null}
      </main>
    </div>
  );
}
