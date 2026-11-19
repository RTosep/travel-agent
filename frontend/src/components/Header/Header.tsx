import './Header.scss';

export function Header() {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">✈</span>
        <div>
          <h1>Travel Agent</h1>
          <p>多 Agent 旅行规划 · 景点 / 天气 / 酒店 / 路线 / 预算</p>
        </div>
      </div>
    </header>
  );
}
