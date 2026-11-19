import type { TripPlan } from '../../types';
import { BudgetBar } from '../BudgetBar/BudgetBar';
import { DayCard } from '../DayCard/DayCard';
import './TripPlanView.scss';

export function TripPlanView({ trip }: { trip: TripPlan }) {
  return (
    <section className="trip">
      <header className="card trip-head">
        <h2>{trip.title}</h2>
        <div className="trip-meta">
          {trip.destination ? <span>📍 {trip.destination}</span> : null}
          {trip.start_date || trip.end_date ? (
            <span>
              📅 {trip.start_date ?? '?'} ~ {trip.end_date ?? '?'}
            </span>
          ) : null}
        </div>
        {trip.summary ? <p className="trip-summary">{trip.summary}</p> : null}
        {trip.budget ? <BudgetBar budget={trip.budget} /> : null}
      </header>

      {trip.days.length === 0 ? (
        <p className="card empty">这次没有生成每日安排，换个描述再试试？</p>
      ) : (
        trip.days.map((day) => <DayCard key={day.day} day={day} />)
      )}
    </section>
  );
}
