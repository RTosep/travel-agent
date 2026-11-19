import './ErrorBanner.scss';

export function ErrorBanner({ message }: { message: string }) {
  return (
    <section className="card error">
      <strong>生成失败</strong>
      <p>{message}</p>
    </section>
  );
}
