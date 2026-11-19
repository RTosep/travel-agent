import type { PlanEvent } from '../types';

const PHASE_LABELS: Partial<Record<PlanEvent['type'], string>> = {
  run_started: '准备中',
  plan_start: '正在制定研究计划',
  plan_done: '研究计划完成',
  resolve_start: '正在检索景点、天气、酒店',
  resolve_done: '资料检索完成',
  draft_start: '正在撰写行程草稿',
  draft_done: '草稿完成',
  reflect_start: '正在反思行程',
  reflect_done: '反思完成',
  revise_start: '正在修订行程',
  revise_done: '修订完成',
  done: '行程生成完成',
  error: '生成失败',
};

/** 从事件流里取最近一个「阶段事件」，得到当前在做什么。 */
export function currentPhase(events: PlanEvent[]): string {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const label = PHASE_LABELS[events[index].type];
    if (label) return label;
  }
  return '准备中';
}
