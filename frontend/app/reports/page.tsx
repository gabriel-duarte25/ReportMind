"use client";

import { FormEvent, ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, Bot, Check, CheckCircle2, ChevronDown, Download, FileDown, FileOutput, FileText, LoaderCircle, Sparkles } from "lucide-react";
import { AgentStep } from "@/lib/agent";
import { DocumentRecord, errorMessage } from "@/lib/documents";
import { GeneratedReport } from "@/lib/reports";
import { DEMO_REPORT_BRIEF, demoDocuments } from "@/lib/demo";

const MAX_DOCUMENTS = 10;
const DEFAULT_BRIEF = DEMO_REPORT_BRIEF;

function inlineText(value: string): ReactNode[] {
  return value.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index} className="font-semibold text-ink">{part.slice(2, -2)}</strong>
      : part,
  );
}

function ReportPreview({ content }: { content: string }) {
  return <div className="space-y-3 text-sm leading-7 text-secondary-soft">{content.split("\n").map((raw, index) => {
    const line = raw.trim();
    if (!line) return <div key={index} className="h-1" />;
    if (line.startsWith("# ")) return <h1 key={index} className="border-b border-blue-line pb-4 text-2xl font-bold tracking-tight text-ink">{inlineText(line.slice(2))}</h1>;
    if (line.startsWith("## ")) return <h2 key={index} className="pt-4 text-lg font-bold text-ink">{inlineText(line.slice(3))}</h2>;
    if (line.startsWith("### ")) return <h3 key={index} className="pt-2 text-base font-semibold text-ink">{inlineText(line.slice(4))}</h3>;
    if (/^[-*]\s/.test(line)) return <div key={index} className="flex gap-3 pl-2"><span className="mt-[11px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" /><p>{inlineText(line.slice(2))}</p></div>;
    const numbered = line.match(/^(\d+)\.\s+(.+)$/);
    if (numbered) return <div key={index} className="flex gap-3 pl-2"><span className="font-semibold text-accent">{numbered[1]}.</span><p>{inlineText(numbered[2])}</p></div>;
    return <p key={index}>{inlineText(line)}</p>;
  })}</div>;
}

function toolLabel(step: AgentStep): string {
  const query = typeof step.input.query === "string" ? `“${step.input.query}”` : "";
  const labels: Record<string, string> = {
    list_documents: "listar_documentos",
    search_documents: "pesquisar_documentos",
    get_document_info: "obter_informação_documento",
    get_document_content: "obter_conteúdo_documento",
    get_chunk: "obter_fragmento",
  };
  return `${labels[step.tool] ?? step.tool}(${query})`;
}

export default function ReportsPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [instructions, setInstructions] = useState(DEFAULT_BRIEF);
  const [report, setReport] = useState<GeneratedReport | null>(null);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        const demoItems = demoDocuments(indexed);
        setDocuments(indexed);
        setSelectedIds(demoItems.length === 2 ? demoItems.map((item) => item.id) : indexed.slice(0, 2).map((item) => item.id));
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Não foi possível carregar os documentos"); })
      .finally(() => { if (active) setLoadingDocuments(false); });
    return () => { active = false; };
  }, []);

  function toggleDocument(id: number) {
    if (generating) return;
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < MAX_DOCUMENTS ? [...current, id] : current);
    setReport(null);
    setError(null);
  }

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (generating || selectedIds.length === 0 || instructions.trim().length < 2) return;
    setGenerating(true);
    setReport(null);
    setError(null);
    try {
      const response = await fetch("/api/reports/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: selectedIds, instructions: instructions.trim() }),
      });
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "O agente não conseguiu gerar o relatório"));
      setReport(await response.json() as GeneratedReport);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "O agente não conseguiu gerar o relatório");
    } finally {
      setGenerating(false);
    }
  }

  function downloadReport() {
    if (!report) return;
    const filename = `${report.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "reportmind-report"}.md`;
    const url = URL.createObjectURL(new Blob([report.content], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function downloadPdf() {
    if (!report || exportingPdf) return;
    setExportingPdf(true);
    setError(null);
    try {
      const response = await fetch("/api/reports/export/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: report.title, content: report.content }),
      });
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "Não foi possível gerar o PDF"));
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "reportmind-report.pdf";
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível gerar o PDF");
    } finally {
      setExportingPdf(false);
    }
  }

  return <div className="min-h-screen">
    <header className="flex h-16 items-center justify-between border-b border-line bg-panel-deep px-5 sm:px-8 lg:h-[72px] lg:px-10"><div className="text-xs font-medium text-muted-soft">Espaço de trabalho <span className="mx-2 text-muted-faint">/</span><span className="text-secondary">Estúdio de Relatórios</span></div><span className="inline-flex items-center gap-2 rounded-full border border-blue-line bg-blue-soft px-3 py-1 text-[11px] font-semibold text-accent"><Sparkles size={12} /> COMPOSITOR DO AGENTE</span></header>
    <div className="mx-auto max-w-[1450px] px-5 py-7 sm:px-8 lg:px-10 lg:py-8">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-bold tracking-tight text-ink sm:text-[36px]">Estúdio de Relatórios</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">Cria um relatório cuidado a partir dos PDFs selecionados. O agente pesquisa primeiro e depois redige um documento claro com evidências sem duplicações.</p></div><div className="hidden items-center gap-2 text-xs text-muted-soft sm:flex"><BookOpen size={15} className="text-accent" /> Pronto para exportar em PDF</div></div>

      <div className="grid items-start gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <form onSubmit={(event) => void generate(event)} className="rounded-2xl border border-line bg-panel shadow-card xl:sticky xl:top-6">
          <div className="border-b border-line-soft px-5 py-4"><div className="flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-navy text-xs font-bold text-white">1</span><div><h2 className="text-sm font-semibold text-ink">Configuração do relatório</h2><p className="mt-0.5 text-[11px] text-muted-soft">Escolhe as evidências e define o resultado pretendido.</p></div></div></div>
          <div className="p-5"><div className="flex items-center justify-between gap-3"><div><h3 className="text-xs font-semibold text-secondary">PDFs de origem</h3><p className="mt-1 text-[11px] text-muted-soft">{selectedIds.length} selecionado{selectedIds.length === 1 ? "" : "s"}</p></div>{documents.length > 0 && <div className="flex gap-3 text-[11px]"><button type="button" disabled={generating} onClick={() => setSelectedIds(documents.slice(0, MAX_DOCUMENTS).map((item) => item.id))} className="font-semibold text-accent hover:underline disabled:opacity-50">Todos</button><button type="button" disabled={generating || !selectedIds.length} onClick={() => setSelectedIds([])} className="font-semibold text-muted hover:text-secondary disabled:opacity-50">Limpar</button></div>}</div>
            {loadingDocuments ? <div className="mt-3 flex items-center gap-2 rounded-xl border border-line bg-panel-deep px-3 py-4 text-xs text-muted"><LoaderCircle size={14} className="animate-spin" /> A carregar PDFs...</div> : documents.length ? <div className="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1">{documents.map((item) => { const selected = selectedIds.includes(item.id); return <button key={item.id} type="button" disabled={generating || (!selected && selectedIds.length >= MAX_DOCUMENTS)} onClick={() => toggleDocument(item.id)} className={`flex w-full min-w-0 items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors disabled:opacity-50 ${selected ? "border-blue-line bg-blue-soft" : "border-line bg-panel-deep hover:border-blue-line"}`}><span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selected ? "border-accent bg-accent text-white" : "border-line text-transparent"}`}><Check size={12} /></span><FileText size={15} className={selected ? "text-accent" : "text-muted-soft"} /><span className="min-w-0"><span className="block truncate text-xs font-semibold text-secondary">{item.original_filename}</span><span className="mt-0.5 block text-[10px] text-muted-soft">{item.page_count ?? 0} páginas · {item.indexed_chunk_count} fragmentos</span></span></button>; })}</div> : <p className="mt-3 rounded-xl border border-line bg-panel-deep px-3 py-4 text-xs leading-5 text-muted-soft">Não existem PDFs indexados. Prepara os documentos em <Link href="/documents" className="font-semibold text-accent">Documentos</Link>.</p>}
            <div className="my-5 border-t border-line-soft" />
            <div className="flex items-center justify-between gap-3"><label htmlFor="report-brief" className="text-xs font-semibold text-secondary">Instruções do relatório</label><button type="button" disabled={generating} onClick={() => setInstructions(DEMO_REPORT_BRIEF)} className="text-[11px] font-semibold text-accent hover:underline disabled:opacity-50">Carregar instruções de demonstração</button></div>
            <textarea id="report-brief" value={instructions} onChange={(event) => setInstructions(event.target.value)} disabled={generating} maxLength={2000} rows={8} className="mt-3 w-full resize-y rounded-xl border border-line bg-panel-deep px-3.5 py-3 text-xs leading-5 text-ink placeholder:text-muted-soft outline-none focus:border-accent disabled:opacity-60" />
            <div className="mt-2 text-right text-[10px] text-muted-soft">{instructions.length}/2000</div>
            <button type="submit" disabled={generating || !selectedIds.length || instructions.trim().length < 2} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-navy px-5 py-3 text-sm font-semibold text-white shadow-primary transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50">{generating ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}{generating ? "A pesquisar e a redigir..." : "Criar relatório"}</button>
            {error && <div role="alert" className="mt-4 rounded-xl border border-red-line bg-red-soft px-3 py-3 text-xs leading-5 text-rose-200">{error}</div>}
          </div>
        </form>

        <div className="min-w-0">
          <section className="overflow-hidden rounded-2xl border border-line bg-panel shadow-card">
            <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-line-soft bg-panel-deep px-5 py-3"><div className="flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-soft text-accent"><FileOutput size={16} /></span><div><div className="text-xs font-semibold text-secondary">Área do relatório</div><div className="text-[10px] text-muted-soft">{report ? `${report.model} · ${report.iterations} iterações` : "À espera das instruções"}</div></div></div>{report && <div className="flex flex-wrap items-center gap-2"><button type="button" onClick={downloadReport} className="inline-flex items-center gap-2 rounded-lg border border-line bg-panel px-3 py-2 text-xs font-semibold text-secondary hover:border-blue-line"><Download size={14} /> Markdown</button><button type="button" onClick={() => void downloadPdf()} disabled={exportingPdf} className="inline-flex items-center gap-2 rounded-lg bg-navy px-3 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-60">{exportingPdf ? <LoaderCircle size={14} className="animate-spin" /> : <FileDown size={14} />} {exportingPdf ? "A gerar PDF..." : "Descarregar PDF"}</button></div>}</div>
            {generating ? <div role="status" className="min-h-[650px] px-7 py-10 sm:px-12"><div className="mx-auto max-w-3xl"><div className="mb-10 flex items-center gap-3 rounded-xl border border-blue-line bg-blue-soft px-4 py-3 text-sm font-semibold text-secondary"><LoaderCircle size={17} className="animate-spin text-accent" /> O agente está a pesquisar os PDFs selecionados</div><div className="space-y-6 opacity-60"><div className="h-8 w-2/3 animate-pulse rounded bg-panel-soft" /><div className="h-px bg-line" /><div className="h-4 w-full animate-pulse rounded bg-panel-soft" /><div className="h-4 w-11/12 animate-pulse rounded bg-panel-soft" /><div className="h-4 w-4/5 animate-pulse rounded bg-panel-soft" /><div className="pt-5"><div className="h-6 w-1/3 animate-pulse rounded bg-panel-soft" /></div><div className="h-4 w-full animate-pulse rounded bg-panel-soft" /><div className="h-4 w-3/4 animate-pulse rounded bg-panel-soft" /></div></div></div> : report ? <article className="min-h-[650px] bg-[linear-gradient(90deg,rgba(37,111,232,.08)_1px,transparent_1px)] bg-[size:32px_32px] px-6 py-9 sm:px-12 sm:py-12"><div className="mx-auto max-w-3xl rounded-sm border border-line bg-panel-deep px-6 py-9 shadow-2xl sm:px-10 sm:py-12"><ReportPreview content={report.content} /></div></article> : <div className="flex min-h-[650px] flex-col items-center justify-center px-6 text-center"><div className="flex h-20 w-20 items-center justify-center rounded-3xl border border-blue-line bg-blue-soft text-accent"><FileOutput size={34} strokeWidth={1.4} /></div><h2 className="mt-6 text-xl font-semibold text-ink">O teu relatório será apresentado aqui</h2><p className="mt-2 max-w-md text-sm leading-6 text-muted">Escolhe os documentos de origem, ajusta as instruções e deixa o agente pesquisar antes de redigir.</p><div className="mt-7 flex items-center gap-2 text-[11px] text-muted-soft"><Bot size={14} className="text-accent" /> Pesquisa do agente <span className="text-muted-faint">→</span> Evidências <span className="text-muted-faint">→</span> Relatório</div></div>}
          </section>

          {report && <div className="mt-6 grid gap-6 lg:grid-cols-2"><section className="rounded-2xl border border-line bg-panel p-5 shadow-card"><div className="flex items-center justify-between"><div><h2 className="text-sm font-semibold text-ink">Anexo de evidências</h2><p className="mt-1 text-xs text-muted-soft">{report.sources.length} fragmentos consultados</p></div><BookOpen size={17} className="text-accent" /></div><div className="mt-4 space-y-2">{report.sources.map((source) => <details key={source.chunk_id} className="group rounded-xl border border-line bg-panel-deep p-3"><summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-xs"><span className="min-w-0 truncate font-semibold text-secondary">{source.document_name} · p. {source.page_start}</span><ChevronDown size={14} className="shrink-0 text-muted-soft transition-transform group-open:rotate-180" /></summary><p className="mt-3 hidden whitespace-pre-wrap border-t border-line-soft pt-3 text-xs leading-6 text-secondary-soft group-open:block">{source.text}</p></details>)}</div></section>
            <section className="rounded-2xl border border-line bg-panel p-5 shadow-card"><div className="flex items-center justify-between"><div><h2 className="text-sm font-semibold text-ink">Registo de produção</h2><p className="mt-1 text-xs text-muted-soft">Ações observáveis do agente</p></div><span className="rounded-full bg-green-soft px-2.5 py-1 text-[10px] font-semibold text-emerald-300">CONCLUÍDO</span></div><ol className="mt-5 space-y-3">{report.steps.map((step, index) => <li key={`${step.tool}-${index}`} className="flex gap-3"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-soft text-[10px] font-bold text-accent">{index + 1}</span><div className="min-w-0"><div className="truncate font-mono text-[11px] font-semibold text-accent">{toolLabel(step)}</div><p className="mt-1 text-[11px] leading-5 text-muted">{step.summary}</p></div></li>)}<li className="flex items-center gap-3 border-t border-line-soft pt-3 text-xs font-semibold text-secondary"><CheckCircle2 size={20} className="text-emerald-300" /> Relatório criado a partir de {report.sources.length} fragmentos de evidência</li></ol></section></div>}
        </div>
      </div>
    </div>
  </div>;
}
