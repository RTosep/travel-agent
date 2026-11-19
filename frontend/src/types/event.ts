export type PlanEventType =
  | 'run_started'
  | 'plan_start'
  | 'plan_done'
  | 'resolve_start'
  | 'resolve_done'
  | 'agent_start'
  | 'tool_call'
  | 'tool_result'
  | 'agent_result'
  | 'agent_retry'
  | 'draft_start'
  | 'draft_done'
  | 'reflect_start'
  | 'reflect_done'
  | 'revise_start'
  | 'revise_done'
  | 'done'
  | 'error';

export interface PlanEvent {
  type: PlanEventType;
  agent?: string;
  message?: string;
  run_id?: string;
  data?: unknown;
}
