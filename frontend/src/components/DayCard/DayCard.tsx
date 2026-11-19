import type { DayPlan } from '../../types';
import {
  attractionMeta,
  formatWeather,
  hotelMeta,
  mealMeta,
  routeMeta,
} from '../../utils/format';
import { ListSection } from '../ListSection/ListSection';
import './DayCard.scss';

export function DayCard({ day }: { day: DayPlan }) {
  return (
    <article className="card day-card">
      <div className="day-head">
        <span className="day-badge">D{day.day}</span>
        <div>
          <h3>{day.title ?? `第 ${day.day} 天`}</h3>
          {day.date ? <span className="muted">{day.date}</span> : null}
        </div>
      </div>

      {day.weather ? <p className="weather">🌤 {formatWeather(day.weather)}</p> : null}

      <ListSection
        title="景点"
        items={day.attractions.map((item) => ({
          name: item.name,
          meta: attractionMeta(item),
        }))}
      />

      <ListSection
        title="餐饮"
        items={day.meals.map((item) => ({ name: item.name, meta: mealMeta(item) }))}
      />

      {day.hotel ? (
        <div className="section">
          <h4>住宿</h4>
          <p className="single">
            {day.hotel.name}
            {hotelMeta(day.hotel) ? ` · ${hotelMeta(day.hotel)}` : ''}
          </p>
        </div>
      ) : null}

      <ListSection
        title="交通"
        items={day.routes.map((route) => ({
          name: `${route.origin.name} → ${route.destination.name}`,
          meta: routeMeta(route),
        }))}
      />

      {day.notes.length > 0 ? (
        <div className="section">
          <h4>备注</h4>
          <ul>
            {day.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}
