"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Layers3, LoaderCircle, Play, RotateCw } from "lucide-react";
import { DocumentChunkRecord, DocumentPageRecord, DocumentRecord, ProcessingStatus, errorMessage } from "@/lib/documents";

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "Não foi possível carregar os dados de processamento"));
  return response.json() as Promise<T>;
}

export function DocumentProcessingPanel({ document, onUpdated }: { document: DocumentRecord; onUpdated: () => void }) {
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [pages, setPages] = useState<DocumentPageRecord[]>([]);
  const [chunks, setChunks] = useState<DocumentChunkRecord[]>([]);
  const [selectedPage, setSelectedPage] = useState(1);
  const [showRaw, setShowRaw] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;
  const statusRef = useRef<DocumentRecord["status"]>(document.status);

  const loadDerived = useCallback(async () => {
    const [nextPages, nextChunks] = await Promise.all([
      readJson<DocumentPageRecord[]>(`/api/documents/${document.id}/pages`),
      readJson<DocumentChunkRecord[]>(`/api/documents/${document.id}/chunks`),
    ]);
    setPages(nextPages);
    setChunks(nextChunks);
    if (nextPages.length > 0) setSelectedPage((current) => nextPages.some((page) => page.page_number === current) ? current : nextPages[0].page_number);
  }, [document.id]);

  const readStatus = useCallback(async () => {
    const next = await readJson<ProcessingStatus>(`/api/documents/${document.id}/processing-status`);
    const previousStatus = statusRef.current;
    statusRef.current = next.status;
    setStatus(next);
    if (previousStatus === "processing" && next.status !== "processing") onUpdatedRef.current();
    if (next.status === "ready") await loadDerived();
    return next;
  }, [document.id, loadDerived]);

  useEffect(() => {
    let active = true;
    void readStatus().catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Não foi possível carregar o estado do processamento"); });
    return () => { active = false; };
  }, [readStatus]);

  useEffect(() => {
    if (status?.status !== "processing") return;
    const timer = window.setInterval(() => {
      void readStatus().catch((cause) => setError(cause instanceof Error ? cause.message : "Não foi possível verificar o estado do processamento"));
    }, 1200);
    return () => window.clearInterval(timer);
  }, [readStatus, status?.status]);

  async function startProcessing() {
    if (starting || status?.status === "processing") return;
    setStarting(true);
    setError(null);
    try {
      const response = await fetch(`/api/documents/${document.id}/process`, { method: "POST" });
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "Não foi possível iniciar o processamento"));
      statusRef.current = "processing";
      setStatus((current) => ({
        document_id: document.id,
        status: "processing",
        page_count: current?.page_count ?? 0,
        word_count: current?.word_count ?? 0,
        chunk_count: current?.chunk_count ?? 0,
        sections_detected: current?.sections_detected ?? 0,
        processing_error: null,
        updated_at: new Date().toISOString(),
      }));
      onUpdatedRef.current();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível iniciar o processamento");
    } finally {
      setStarting(false);
    }
  }

  const currentStatus = status?.status ?? document.status;
  const page = pages.find((item) => item.page_number === selectedPage);
  const counts = [
    { label: "Páginas", value: status?.page_count ?? 0, icon: FileText },
    { label: "Palavras", value: status?.word_count ?? 0, icon: FileText },
    { label: "Fragmentos", value: status?.chunk_count ?? 0, icon: Layers3 },
    { label: "Secções", value: status?.sections_detected ?? 0, icon: Layers3 },
  ];

  return <section className="mt-7" aria-label="Processamento do documento">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h3 className="text-sm font-semibold text-ink">Processamento do documento</h3><p className="mt-1 text-xs text-muted-soft">Extrai o texto das páginas e organiza-o em fragmentos legíveis.</p></div>
      <button onClick={() => void startProcessing()} disabled={starting || currentStatus === "processing"} className="inline-flex items-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-xs font-semibold text-white shadow-primary transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60">
        {starting || currentStatus === "processing" ? <LoaderCircle size={15} className="animate-spin" /> : currentStatus === "ready" ? <RotateCw size={15} /> : <Play size={15} />}
        {starting || currentStatus === "processing" ? "A processar..." : currentStatus === "ready" ? "Reprocessar documento" : "Processar documento"}
      </button>
    </div>
    {currentStatus === "processing" && <div role="status" className="mt-4 rounded-xl border border-blue-line bg-blue-soft px-4 py-3 text-xs text-blue-200"><LoaderCircle size={14} className="mr-2 inline animate-spin" />A extrair páginas e a preparar fragmentos. Este processo pode demorar um pouco.</div>}
    {currentStatus === "failed" && <div role="alert" className="mt-4 rounded-xl border border-red-line bg-red-soft px-4 py-3 text-xs text-rose-200">{status?.processing_error ?? document.processing_error ?? "O processamento falhou."} Podes tentar novamente.</div>}
    {error && <div role="alert" className="mt-4 rounded-xl border border-red-line bg-red-soft px-4 py-3 text-xs text-rose-200">{error}</div>}
    <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">{counts.map(({ label, value, icon: Icon }) => <div key={label} className="rounded-xl border border-line bg-panel-soft p-3"><div className="flex items-center justify-between text-muted-soft"><span className="text-[11px] font-medium">{label}</span><Icon size={14} /></div><div className="mt-2 text-lg font-semibold text-ink">{value.toLocaleString()}</div></div>)}</div>
    {pages.length > 0 && <div className="mt-6 rounded-xl border border-line bg-panel-soft">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3"><div><h4 className="text-xs font-semibold text-ink">Conteúdo extraído</h4><p className="mt-0.5 text-[11px] text-muted-soft">Texto obtido de cada página do PDF</p></div><div className="flex items-center gap-2"><label className="text-[11px] text-muted-soft" htmlFor="document-page">Página</label><select id="document-page" value={selectedPage} onChange={(event) => setSelectedPage(Number(event.target.value))} className="rounded-md border border-line bg-panel px-2 py-1 text-xs text-secondary">{pages.map((item) => <option key={item.id} value={item.page_number}>{item.page_number}</option>)}</select><button onClick={() => setShowRaw((value) => !value)} className="rounded-md border border-blue-line bg-blue-soft px-2 py-1 text-[11px] font-semibold text-accent transition-colors hover:bg-navy hover:text-white">{showRaw ? "Texto tratado" : "Texto original"}</button></div></div>
      <div className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words px-4 py-4 text-xs leading-6 text-secondary-soft">{page ? (showRaw ? page.raw_text : page.cleaned_text) || "Não existe texto selecionável nesta página." : "Nenhuma página selecionada."}</div>
    </div>}
    {currentStatus === "ready" && pages.length === 0 && <p className="mt-5 rounded-xl border border-line bg-panel-soft p-4 text-xs text-muted-soft">Não foram encontradas páginas neste PDF.</p>}
    {currentStatus === "ready" && pages.length > 0 && chunks.length === 0 && <p className="mt-5 rounded-xl border border-line bg-panel-soft p-4 text-xs text-muted-soft">Não foi encontrado texto selecionável. Este PDF pode conter imagens digitalizadas.</p>}
    {chunks.length > 0 && <div className="mt-6"><h4 className="text-xs font-semibold text-ink">Fragmentos de texto</h4><p className="mt-1 text-[11px] text-muted-soft">Segmentos estruturados com páginas de origem e etiquetas de secção</p><div className="mt-3 max-h-96 space-y-3 overflow-y-auto">{chunks.map((chunk) => <article key={chunk.id} className="rounded-xl border border-line bg-panel-soft p-4"><div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-medium text-muted-soft"><span>Fragmento {chunk.chunk_index + 1}{chunk.section ? ` · ${chunk.section}` : ""}</span><span>Página {chunk.page_start}{chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ""}</span></div><p className="mt-3 whitespace-pre-wrap break-words text-xs leading-6 text-secondary-soft">{chunk.text}</p></article>)}</div></div>}
  </section>;
}
