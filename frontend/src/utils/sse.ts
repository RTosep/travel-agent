import type { PlanEvent } from '../types';

/**
 * 解析一个 SSE 消息块（形如 `event: xxx\ndata: {...}`）。
 * 心跳 `: ping` 没有 data，返回 null。
 */
export function parseSSEChunk(chunk: string): PlanEvent | null {
  const data = chunk
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('\n');

  if (!data) return null;

  try {
    return JSON.parse(data) as PlanEvent;
  } catch {
    return null;
  }
}

/**
 * 逐块读取 SSE 流，按空行切分消息并回调。
 */
export async function readSSEStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: PlanEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const chunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const event = parseSSEChunk(chunk);
      if (event) onEvent(event);

      boundary = buffer.indexOf('\n\n');
    }
  }
}
