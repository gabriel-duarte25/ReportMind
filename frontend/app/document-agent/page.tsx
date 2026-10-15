"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bot, Check, ChevronDown, FileText, LoaderCircle, MessageSquarePlus, Quote, Send, ShieldAlert, Sparkles, Trash2, Wrench, X } from "lucide-react";
import { AgentConversationDetail, AgentConversationSummary, AgentResult, AgentSource } from "@/lib/agent";
import { DocumentRecord, errorMessage } from "@/lib/documents";
import { DEMO_AGENT_OBJECTIVE, demoDocuments } from "@/lib/demo";

const MAX_DOCUMENTS = 10;
const RISK_ANALYSIS_OBJECTIVE = "Analisa todos os documentos selecionados e identifica riscos, contradições, lacunas e requisitos problemáticos. Classifica a gravidade e recomenda ações concretas.";

type ChatExchange = {
  id: number;
  question: string;
  result?: AgentResult;
  error?: string;
};

function toolLabel(step: AgentResult["steps"][number]): string {
  const query = typeof step.input.query === "string" ? `“${step.input.query}”` : "";
  const id = step.input.document_id ?? step.input.chunk_id;
  const labels: Record<string, string> = {
    list_documents: "listar_documentos",
    search_documents: "pesquisar_documentos",
    get_document_info: "obter_informação_documento",
    get_document_content: "obter_conteúdo_documento",
    get_chunk: "obter_fragmento",
  };
  return `${labels[step.tool] ?? step.tool}(${query || (id ? String(id) : "")})`;
}

function CitedAnswer({ result, onSelect }: { result: AgentResult; onSelect: (source: AgentSource) => void }) {
  const sourceById = new Map(result.sources.map((source) => [source.chunk_id, source]));
  const sourceNumber = new Map(result.sources.map((source, index) => [source.chunk_id, index + 1]));
  const parts = result.answer.split(/(\[chunk:\d+\])/g);

  return <p className="whitespace-pre-wrap break-words">{parts.map((part, index): ReactNode => {
    const match = part.match(/^\[chunk:(\d+)\]$/);
    if (!match) return part;
    const chunkId = Number(match[1]);
    const source = sourceById.get(chunkId);
    if (!source) return null;
    const number = sourceNumber.get(chunkId);
    return <button key={`${chunkId}-${index}`} type="button" onClick={() => onSelect(source)} aria-label={`Abrir fonte ${number}: ${source.document_name}, página ${source.page_start}`} className="mx-0.5 inline-flex min-w-5 -translate-y-px items-center justify-center rounded bg-blue-soft px-1.5 py-0.5 text-[10px] font-bold leading-4 text-accent transition-colors hover:bg-navy hover:text-white focus-visible:outline-offset-1">{number}</button>;
  })}</p>;
}

export default function DocumentAgentPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [objective, setObjective] = useState("");
  const [exchanges, setExchanges] = useState<ChatExchange[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSource, setActiveSource] = useState<AgentSource | null>(null);
  const [conversations, setConversations] = useState<AgentConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const conversationEndRef = useRef<HTMLDivElement>(null);

  const refreshConversations = async () => {
    try {
      const response = await fetch("/api/agent/conversations", { cache: "no-store" });
      if (response.ok) setConversations(await response.json() as AgentConversationSummary[]);
    } catch { /* The agent remains usable if history cannot be loaded. */ }
  };

  useEffect(() => { void refreshConversations(); }, []);

  useEffect(() => {
    if (!activeSource) return;
    function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape") setActiveSource(null); }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [activeSource]);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [exchanges, running]);

  useEffect(() => {
    let active = true;
    fetch("/api/documents", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "Não foi possível carregar os documentos"));
        return response.json() as Promise<DocumentRecord[]>;
      })
      .then((items) => {
        if (!active) return;
        const indexed = items.filter((item) => item.status === "ready" && item.indexing_status === "indexed");
        const params = new URLSearchParams(window.location.search);
        const demo = params.get("demo") === "1";
        const requested = Number(params.get("document_id"));
        const demoItems = demoDocuments(indexed);
        setDocuments(indexed);
        setSelectedIds(demo && demoItems.length === 2 ? demoItems.map((item) => item.id) : indexed.some((item) => item.id === requested) ? [requested] : indexed[0] ? [indexed[0].id] : []);
        if (demo) setObjective(DEMO_AGENT_OBJECTIVE);
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Não foi possível carregar os documentos"); })
      .finally(() => { if (active) setLoadingDocuments(false); });
    return () => { active = false; };
  }, []);

  function toggleDocument(documentId: number) {
    if (running) return;
    setSelectedIds((current) => current.includes(documentId)
      ? current.filter((id) => id !== documentId)
      : current.length < MAX_DOCUMENTS ? [...current, documentId] : current);
    setExchanges([]);
    setConversationId(null);
    setError(null);
  }

  function startConversation() {
    if (running) return;
    setConversationId(null);
    setExchanges([]);
    setObjective("");
    setError(null);
  }

  async function openConversation(id: number) {
    if (running || loadingConversation) return;
    setLoadingConversation(true);
    setError(null);
    try {
      const response = await fetch(`/api/agent/conversations/${id}`, { cache: "no-store" });
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "Não foi possível abrir a conversa"));
      const conversation = await response.json() as AgentConversationDetail;
      setConversationId(conversation.id);
      setSelectedIds(conversation.document_ids);
      setExchanges(conversation.messages.map((message) => ({
        id: message.id,
        question: message.question,
        result: {
          answer: message.answer,
          model: message.model,
          iterations: message.iterations,
          steps: message.steps,
          sources: message.sources,
          conversation_id: conversation.id,
        },
      })));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível abrir a conversa");
    } finally {
      setLoadingConversation(false);
    }
  }

  async function deleteConversation(id: number) {
    if (running) return;
    try {
      const response = await fetch(`/api/agent/conversations/${id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Não foi possível eliminar a conversa");
      if (conversationId === id) startConversation();
      await refreshConversations();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível eliminar a conversa");
    }
  }

  async function executeAgent(question: string, analysisMode: "standard" | "risk_review" = "standard") {
    if (running || selectedIds.length === 0 || question.trim().length < 2) return;
    question = question.trim();
    const exchangeId = Date.now();
    const history = exchanges
      .filter((exchange): exchange is ChatExchange & { result: AgentResult } => Boolean(exchange.result))
      .slice(-6)
      .map((exchange) => ({ question: exchange.question, answer: exchange.result.answer }));
    setRunning(true);
    setObjective("");
    setExchanges((current) => [...current, { id: exchangeId, question }]);
    try {
      const response = await fetch("/api/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: selectedIds, objective: question, history, conversation_id: conversationId, analysis_mode: analysisMode }),
      });
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "O agente não conseguiu concluir a tarefa"));
      const result = await response.json() as AgentResult;
      if (result.conversation_id) setConversationId(result.conversation_id);
      setExchanges((current) => current.map((exchange) => exchange.id === exchangeId ? { ...exchange, result } : exchange));
      await refreshConversations();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "O agente não conseguiu concluir a tarefa";
      setExchanges((current) => current.map((exchange) => exchange.id === exchangeId ? { ...exchange, error: message } : exchange));
    } finally {
      setRunning(false);
    }
  }

  function runAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void executeAgent(objective);
  }

  return <div className="min-h-screen">
    <header className="flex h-16 items-center justify-between border-b border-line bg-panel-deep px-5 sm:px-8 lg:h-[72px] lg:px-10"><div className="text-xs font-medium text-muted-soft">Espaço de trabalho <span className="mx-2 text-muted-faint">/</span><span className="text-secondary">Agente de Documentos</span></div><span className="inline-flex items-center gap-2 text-xs text-muted-soft"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Agente local</span></header>
    <div className="mx-auto max-w-[1080px] px-5 py-7 sm:px-8 lg:px-10 lg:py-8">
      <div className="mb-6"><div className="mb-3 inline-flex items-center gap-2 rounded-full border border-blue-line bg-blue-soft px-3 py-1 text-[11px] font-semibold text-accent"><Bot size={12} /> AGENTE DE DOCUMENTOS</div><h1 className="text-3xl font-bold tracking-tight text-ink sm:text-[36px]">Pergunta ao agente</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">Escreve em português e em linguagem natural. O agente decide quando pesquisar os PDFs selecionados e mostra as ferramentas e evidências usadas em cada resposta.</p></div>

      <section className="mb-6" aria-label="Conversas guardadas"><div className="mb-3 flex items-center justify-between gap-4"><div><h2 className="text-xs font-semibold text-secondary">Conversas guardadas</h2><p className="mt-1 text-[11px] text-muted-soft">Continua uma conversa anterior ou começa uma nova.</p></div><button type="button" onClick={startConversation} disabled={running} className="inline-flex items-center gap-2 text-xs font-semibold text-accent hover:text-white disabled:opacity-50"><MessageSquarePlus size={15} /> Nova conversa</button></div>{conversations.length > 0 ? <div className="flex gap-2 overflow-x-auto pb-1">{conversations.map((conversation) => <div key={conversation.id} className={`flex shrink-0 items-center rounded-lg border ${conversationId === conversation.id ? "border-blue-line bg-blue-soft" : "border-line bg-panel-deep"}`}><button type="button" onClick={() => void openConversation(conversation.id)} disabled={running || loadingConversation} className="max-w-[230px] px-3 py-2 text-left disabled:opacity-50"><div className="truncate text-xs font-semibold text-secondary">{conversation.title}</div><div className="mt-0.5 text-[10px] text-muted-soft">{conversation.message_count} mensage{conversation.message_count === 1 ? "m" : "ns"}</div></button><button type="button" onClick={() => void deleteConversation(conversation.id)} disabled={running} aria-label={`Eliminar conversa ${conversation.title}`} className="mr-1 rounded-md p-2 text-muted-faint hover:bg-red-soft hover:text-rose-300 disabled:opacity-50"><Trash2 size={13} /></button></div>)}</div> : <p className="text-xs text-muted-soft">As conversas concluídas aparecerão aqui.</p>}</section>

      <section className="mb-4 border-b border-line pb-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xs font-semibold text-secondary">Documentos da conversa</h2><p className="mt-1 text-[11px] text-muted-soft">{selectedIds.length} documento{selectedIds.length === 1 ? " indexado selecionado" : "s indexados selecionados"}</p></div>{documents.length > 0 && <div className="flex gap-3 text-xs"><button type="button" disabled={running || conversationId !== null} onClick={() => { setSelectedIds(documents.slice(0, MAX_DOCUMENTS).map((document) => document.id)); setExchanges([]); setConversationId(null); }} className="font-semibold text-accent hover:underline disabled:opacity-50">Selecionar todos</button><button type="button" disabled={running || selectedIds.length === 0 || conversationId !== null} onClick={() => { setSelectedIds([]); setExchanges([]); setConversationId(null); }} className="font-semibold text-muted hover:text-secondary disabled:opacity-50">Limpar</button></div>}</div>
        {loadingDocuments ? <div className="mt-3 flex items-center gap-2 text-sm text-muted"><LoaderCircle size={15} className="animate-spin" /> A carregar documentos...</div> : documents.length ? <div className="mt-3 flex gap-2 overflow-x-auto pb-1">{documents.map((document) => { const selected = selectedIds.includes(document.id); return <button key={document.id} type="button" disabled={running || conversationId !== null || (!selected && selectedIds.length >= MAX_DOCUMENTS)} onClick={() => toggleDocument(document.id)} aria-pressed={selected} className={`inline-flex max-w-[280px] shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-xs transition-colors disabled:opacity-50 ${selected ? "border-blue-line bg-blue-soft font-semibold text-secondary" : "border-line text-muted hover:border-blue-line"}`}><span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${selected ? "bg-accent text-white" : "border border-line text-transparent"}`}><Check size={10} /></span><span className="truncate">{document.original_filename}</span></button>; })}</div> : <p className="mt-3 text-sm text-muted-soft">Não existem PDFs indexados. Prepara os documentos em <Link href="/documents" className="font-semibold text-accent hover:underline">Documentos</Link>.</p>}
      </section>

      <section className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-amber-400/20 bg-amber-soft px-4 py-3" aria-label="Análise de riscos"><div className="flex min-w-0 items-center gap-3"><ShieldAlert size={19} className="shrink-0 text-amber-300" /><div><h2 className="text-xs font-semibold text-secondary">Análise de riscos e contradições</h2><p className="mt-0.5 text-[11px] text-muted-soft">Revê todos os documentos e apresenta alertas priorizados com evidências.</p></div></div><button type="button" onClick={() => void executeAgent(RISK_ANALYSIS_OBJECTIVE, "risk_review")} disabled={running || selectedIds.length === 0} className="shrink-0 rounded-lg bg-amber-400 px-3.5 py-2 text-xs font-semibold text-slate-950 transition-colors hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-50">{running ? "A analisar..." : "Analisar riscos"}</button></section>

      {error && <div role="alert" className="mb-4 rounded-xl border border-red-line bg-red-soft px-4 py-3 text-sm text-rose-200">{error}</div>}

      <section aria-label="Conversa com o agente" className="overflow-hidden rounded-2xl border border-line bg-panel shadow-card">
        <div className="max-h-[62vh] min-h-[430px] overflow-y-auto px-4 py-6 sm:px-7">
          {exchanges.length === 0 && <div className="flex min-h-[360px] flex-col items-center justify-center px-4 text-center"><div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-soft text-accent"><Sparkles size={24} /></div><h2 className="mt-5 text-base font-semibold text-ink">Inicia uma conversa sobre os teus documentos</h2><p className="mt-2 max-w-md text-sm leading-6 text-muted">Pede uma comparação, um facto específico ou uma análise. A pesquisa só é executada quando o agente escolhe essa ferramenta.</p><button type="button" onClick={() => setObjective(DEMO_AGENT_OBJECTIVE)} className="mt-5 text-xs font-semibold text-accent hover:underline">Inserir pergunta de demonstração</button></div>}

          <div className="space-y-7">{exchanges.map((exchange) => <div key={exchange.id} className="space-y-5">
            <div className="flex justify-end"><div className="max-w-[82%]"><div className="mb-1.5 text-right text-[10px] font-semibold uppercase tracking-wider text-muted-soft">Tu</div><div className="rounded-2xl rounded-br-md bg-navy px-4 py-3 text-sm leading-6 text-white shadow-primary">{exchange.question}</div></div></div>

            {!exchange.result && !exchange.error && <div className="flex items-start gap-3" role="status"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-soft text-accent"><Bot size={16} /></div><div className="rounded-2xl rounded-tl-md border border-blue-line bg-blue-soft px-4 py-3"><div className="flex items-center gap-2 text-sm font-semibold text-secondary"><LoaderCircle size={15} className="animate-spin text-accent" /> A analisar o teu pedido</div><div className="mt-2 flex items-center gap-1.5"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent [animation-delay:150ms]" /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent [animation-delay:300ms]" /><span className="ml-2 text-[11px] text-muted-soft">A escolher ferramentas e a consultar evidências...</span></div></div></div>}

            {exchange.error && <div className="flex items-start gap-3"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-soft text-rose-300"><Bot size={16} /></div><div className="rounded-2xl rounded-tl-md border border-red-line bg-red-soft px-4 py-3 text-sm text-rose-200">{exchange.error}</div></div>}

            {exchange.result && <div className="flex items-start gap-3"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-soft text-accent"><Bot size={16} /></div><div className="min-w-0 flex-1"><div className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted-soft">Agente ReportMind <span>·</span><span className="normal-case tracking-normal">{exchange.result.model}</span></div><div className="text-sm leading-7 text-secondary-soft"><CitedAnswer result={exchange.result} onSelect={setActiveSource} /></div>
              {exchange.result.sources.length > 0 && <div className="mt-4"><div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-soft"><Quote size={11} /> Evidências utilizadas</div><div className="flex flex-wrap gap-2">{exchange.result.sources.map((source, index) => <button key={source.chunk_id} type="button" onClick={() => setActiveSource(source)} className="inline-flex max-w-full items-center gap-2 rounded-full border border-line px-2.5 py-1.5 text-[11px] text-muted transition-colors hover:border-blue-line hover:text-secondary"><span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-blue-soft text-[9px] font-bold text-accent">{index + 1}</span><span className="max-w-[220px] truncate">{source.document_name}</span><span className="shrink-0 text-muted-faint">p. {source.page_start}</span></button>)}</div></div>}
              <div className="mt-4 flex flex-wrap gap-2"><details className="group rounded-lg border border-line bg-panel-deep"><summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[11px] font-semibold text-secondary"><Wrench size={13} className="text-accent" /> {exchange.result.steps.length} ações do agente <ChevronDown size={13} className="transition-transform group-open:rotate-180" /></summary><ol className="max-w-2xl space-y-3 border-t border-line-soft px-3 py-3">{exchange.result.steps.map((step, index) => <li key={`${step.tool}-${index}`} className="flex gap-2"><span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-green-soft text-emerald-300"><Check size={9} /></span><div><div className="break-all font-mono text-[10px] font-semibold text-accent">{toolLabel(step)}</div><p className="mt-0.5 text-[11px] leading-5 text-muted">{step.summary}</p></div></li>)}</ol></details>
                {exchange.result.sources.length > 0 && <button type="button" onClick={() => setActiveSource(exchange.result!.sources[0])} className="inline-flex items-center gap-2 rounded-lg border border-line bg-panel-deep px-3 py-2 text-[11px] font-semibold text-secondary transition-colors hover:border-blue-line"><FileText size={13} className="text-accent" /> Consultar {exchange.result.sources.length} fonte{exchange.result.sources.length === 1 ? "" : "s"}</button>}
              </div>
            </div></div>}
          </div>)}</div>
          <div ref={conversationEndRef} />
        </div>

        <form onSubmit={(event) => void runAgent(event)} className="border-t border-line bg-panel-deep p-3 sm:p-4"><div className="rounded-xl border border-line bg-panel px-3 py-2 focus-within:border-accent"><textarea id="agent-objective" value={objective} onChange={(event) => setObjective(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) event.currentTarget.form?.requestSubmit(); }} disabled={running} maxLength={2000} rows={2} placeholder="Pergunta ao agente sobre os documentos selecionados..." className="w-full resize-none bg-transparent px-1 py-1 text-sm leading-6 text-ink placeholder:text-muted-soft outline-none disabled:opacity-60" /><div className="mt-2 flex items-center justify-between gap-3 border-t border-line-soft pt-2"><div className="flex items-center gap-3"><span className="text-[10px] text-muted-soft">{objective.length}/2000</span><button type="button" disabled={running} onClick={() => setObjective(DEMO_AGENT_OBJECTIVE)} className="text-[10px] font-semibold text-accent hover:underline disabled:opacity-50">Pergunta de demonstração</button></div><button type="submit" aria-label="Enviar ao agente" disabled={running || selectedIds.length === 0 || objective.trim().length < 2} className="flex h-9 w-9 items-center justify-center rounded-lg bg-navy text-white shadow-primary transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50">{running ? <LoaderCircle size={16} className="animate-spin" /> : <Send size={16} />}</button></div></div><p className="mt-2 text-center text-[10px] text-muted-soft">O agente mantém o contexto desta conversa · ⌘/Ctrl + Enter para enviar</p></form>
      </section>
    </div>
    {activeSource && <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-950/60 p-3 sm:p-5" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setActiveSource(null); }}><aside role="dialog" aria-modal="true" aria-label="Evidência documental" className="max-h-[88vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-line bg-panel p-5 shadow-2xl sm:p-6"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.16em] text-accent"><Quote size={12} /> Evidência documental</div><h2 className="mt-3 truncate text-base font-semibold text-ink">{activeSource.document_name}</h2><p className="mt-1 text-xs text-muted-soft">Página {activeSource.page_start}{activeSource.page_end !== activeSource.page_start ? `–${activeSource.page_end}` : ""}{activeSource.section ? ` · ${activeSource.section}` : ""}</p></div><button type="button" onClick={() => setActiveSource(null)} aria-label="Fechar evidência" className="rounded-lg p-2 text-muted-soft transition-colors hover:bg-panel-soft hover:text-ink"><X size={18} /></button></div><blockquote className="mt-6 border-l-2 border-accent pl-4 text-sm leading-7 text-secondary-soft">{activeSource.text}</blockquote><div className="mt-6 flex items-center justify-between border-t border-line-soft pt-4 text-[10px] text-muted-faint"><span>Fragmento #{activeSource.chunk_id}</span>{activeSource.score !== null && <span>Relevância {(activeSource.score * 100).toFixed(0)}%</span>}</div></aside></div>}
  </div>;
}
