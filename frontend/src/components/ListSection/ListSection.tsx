import './ListSection.scss';

export function ListSection({
  title,
  items,
}: {
  title: string;
  items: { name: string; meta?: string }[];
}) {
  if (items.length === 0) return null;

  return (
    <div className="section">
      <h4>{title}</h4>
      <ul>
        {items.map((item, index) => (
          <li key={`${item.name}-${index}`}>
            <span className="item-name">{item.name}</span>
            {item.meta ? <span className="item-meta">{item.meta}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
