import type { PlanEvent } from '../types';
import { readSSEStream } from '../utils/sse';
import { readError } from './client';

/**
 * 用 fetch 读取 SSE 流（POST 请求，便于传较长 prompt）。
 * 每收到一个事件就回调一次 onEvent。
 */
export async function streamPlan(
  prompt: string,
  onEvent: (event: PlanEvent) => void,
): Promise<void> {
  const response = await fetch('/api/plan/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok || !response.body) {
    throw new Error(await readError(response));
  }

  await readSSEStream(response.body, onEvent);
}
