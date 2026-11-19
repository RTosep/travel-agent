import type { Budget } from '../../types';
import './BudgetBar.scss';

export function BudgetBar({ budget }: { budget: Budget }) {
  const items: [string, number][] = [];
  if (budget.total != null) items.push(['总预算', budget.total]);
  if (budget.transport != null) items.push(['交通', budget.transport]);
  if (budget.hotel != null) items.push(['住宿', budget.hotel]);
  if (budget.meals != null) items.push(['餐饮', budget.meals]);
  if (budget.tickets != null) items.push(['门票', budget.tickets]);
  if (budget.other != null) items.push(['其他', budget.other]);

  if (items.length === 0) return null;

  return (
    <div className="budget">
      {items.map(([label, value]) => (
        <span key={label}>
          {label} {value} {budget.currency}
        </span>
      ))}
    </div>
  );
}
