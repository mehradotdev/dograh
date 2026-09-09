export type PocCall = {
  id: number;
  created_at: string;
  engine: string;
  models: string;
  language: string;
  caller: string;
  duration_seconds: number;
  outcome: string;
  ticket_number: string | null;
  estimated_cost_usd: number | null;
  normalized_list_cost_usd: number | null;
  actual_billed_estimate_usd: number | null;
  first_response_latency_ms: number | null;
};

export type PocCallList = { items: PocCall[]; total: number };

export type PocCallDetail = PocCall & {
  asterisk_call_id: string | null;
  caller_number: string | null;
  caller_e164: string | null;
  wfms_mobile: string | null;
  runtime_configuration: Record<string, unknown>;
  initial_context: Record<string, unknown>;
  gathered_context: Record<string, unknown>;
  usage_info: Record<string, unknown>;
  cost_info: Record<string, unknown>;
  logs: unknown;
  transcript_url: string | null;
  dograh_recording_url: string | null;
  recording_available: boolean;
};
