import { useState, type FormEvent } from 'react';
import './PlanForm.scss';

const EXAMPLES = [
  '下周一开始的双人深圳 3 天 2 晚，非自驾，偏舒适，不含大交通',
  '北京 4 天 3 晚，想看故宫和长城，预算 5000，喜欢历史',
  '成都 3 天，主要想吃美食和看熊猫，节奏慢一点',
];

export function PlanForm({
  loading,
  onSubmit,
}: {
  loading: boolean;
  onSubmit: (prompt: string) => void;
}) {
  const [prompt, setPrompt] = useState(EXAMPLES[0]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || loading) return;
    onSubmit(text);
  }

  return (
    <section className="card composer">
      <h2>说说你的旅行计划</h2>
      <form onSubmit={handleSubmit}>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={5}
          placeholder="例如：下周一深圳 3 天 2 晚，双人，非自驾，偏舒适……"
          disabled={loading}
        />
        <div className="examples">
          {EXAMPLES.map((example) => (
            <button
              type="button"
              key={example}
              onClick={() => setPrompt(example)}
              disabled={loading}
            >
              {example}
            </button>
          ))}
        </div>
        <button className="primary" type="submit" disabled={loading || !prompt.trim()}>
          {loading ? '正在规划…' : '生成攻略'}
        </button>
      </form>
    </section>
  );
}
