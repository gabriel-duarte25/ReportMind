export type AgentStep = {
  tool: string;
  input: Record<string, unknown>;
  summary: string;
};

export type AgentSource = {
  score: number | null;
  chunk_id: number;
  document_id: number;
  document_name: string;
  text: string;
  section: string | null;
  page_start: number;
  page_end: number;
};

export type AgentResult = {
  answer: string;
  model: string;
  iterations: number;
  steps: AgentStep[];
  sources: AgentSource[];
  conversation_id?: number | null;
};

export type AgentConversationSummary = {
  id: number;
  title: string;
  document_ids: number[];
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type AgentConversationDetail = AgentConversationSummary & {
  messages: Array<{
    id: number;
    question: string;
    answer: string;
    model: string;
    iterations: number;
    steps: AgentStep[];
    sources: AgentSource[];
    created_at: string;
  }>;
};
