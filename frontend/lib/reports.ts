import { AgentSource, AgentStep } from "@/lib/agent";

export type GeneratedReport = {
  title: string;
  content: string;
  model: string;
  iterations: number;
  steps: AgentStep[];
  sources: AgentSource[];
};
