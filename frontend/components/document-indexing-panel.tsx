"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Database, LoaderCircle, RotateCw, Sparkles } from "lucide-react";
import { DocumentRecord, IndexingStatus, errorMessage } from "@/lib/documents";

export function DocumentIndexingPanel({ document, onUpdated }: { document: DocumentRecord; onUpdated: () => void }) {
  const [status, setStatus] = useState<IndexingStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const statusRef = useRef(document.indexing_status);
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;

  const refresh = useCallback(async () => {
    const response = await fetch(`/api/documents/${document.id}/indexing-status`, { cache: "no-store" });
    if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "Não foi possível carregar o estado da indexação"));
    const next = await response.json() as IndexingStatus;
    const previous = statusRef.current;
    statusRef.current = next.indexing_status;
    setStatus(next);
    if (previous === "indexing" && next.indexing_status !== "indexing") onUpdatedRef.current();
  }, [document.id]);

  useEffect(() => {
    let active = true;
    void refresh().catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Não foi possível carregar o estado da indexação"); });
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    if (status?.indexing_status !== "indexing") return;
    const timer = window.setInterval(() => {
      void refresh().catch((cause) => setError(cause instanceof Error ? cause.message : "Não foi possível verificar o estado da indexação"));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [refresh, status?.indexing_status]);

  async function startIndexing() {
    if (starting || status?.indexing_status === "indexing") return;
    setStarting(true);
    setError(null);
    try {
      const response = await fetch(`/api/documents/${document.id}/index`, { method: "POST" });
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null), "Não foi possível iniciar a indexação"));
      statusRef.current = "indexing";
      setStatus((current) => ({
        document_id: document.id,
        indexing_status: "indexing",
        chunk_count: current?.chunk_count ?? 0,
        indexed_vector_count: 0,
        embedding_model: null,
        indexing_error: null,
        indexed_at: null,
      }));
      onUpdatedRef.current();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível iniciar a indexação");
    } finally {
      setStarting(false);
    }
  }

  const state = status?.indexing_status ?? document.indexing_status;
  const label = state === "indexed" ? "Indexado" : state === "indexing" ? "A indexar" : state === "index_failed" ? "A indexação falhou" : "Não indexado";

  return <section className="mt-7 border-t border-line-soft pt-7" aria-label="Indexação semântica">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h3 className="text-sm font-semibold text-ink">Indexação semântica</h3><p className="mt-1 text-xs text-muted-soft">Cria embeddings locais para os fragmentos de texto deste documento.</p></div>
      <button onClick={() => void startIndexing()} disabled={starting || state === "indexing" || (status?.chunk_count ?? 0) === 0} className="inline-flex items-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-xs font-semibold text-white shadow-primary transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60">
        {starting || state === "indexing" ? <LoaderCircle size={15} className="animate-spin" /> : state === "indexed" ? <RotateCw size={15} /> : <Sparkles size={15} />}
        {starting || state === "indexing" ? "A indexar..." : state === "indexed" ? "Reindexar documento" : "Indexar documento"}
      </button>
    </div>
    <div className="mt-5 grid gap-3 sm:grid-cols-3">
      <div className="rounded-xl border border-line bg-panel-soft p-3"><div className="text-[11px] text-muted-soft">Estado da indexação</div><div className="mt-2 text-sm font-semibold text-ink">{label}</div></div>
      <div className="rounded-xl border border-line bg-panel-soft p-3"><div className="text-[11px] text-muted-soft">Fragmentos de texto</div><div className="mt-2 text-sm font-semibold text-ink">{status?.chunk_count ?? "—"}</div></div>
      <div className="rounded-xl border border-line bg-panel-soft p-3"><div className="text-[11px] text-muted-soft">Vetores indexados</div><div className="mt-2 flex items-center gap-2 text-sm font-semibold text-ink"><Database size={14} className="text-accent" />{status?.indexed_vector_count ?? document.indexed_chunk_count}</div></div>
    </div>
    <p className="mt-3 text-xs text-muted-soft">Modelo de embeddings: <span className="font-medium text-secondary">{status?.embedding_model ?? document.embedding_model ?? "Ainda não indexado"}</span></p>
    {state === "indexing" && <p role="status" className="mt-4 rounded-xl border border-blue-line bg-blue-soft px-4 py-3 text-xs text-blue-200"><LoaderCircle size={14} className="mr-2 inline animate-spin" />A criar vetores. A primeira execução pode transferir o modelo local.</p>}
    {state === "index_failed" && <p role="alert" className="mt-4 rounded-xl border border-red-line bg-red-soft px-4 py-3 text-xs text-rose-200">{status?.indexing_error ?? document.indexing_error ?? "A indexação falhou."} Podes tentar novamente.</p>}
    {status?.chunk_count === 0 && <p className="mt-4 text-xs text-muted-soft">Este documento não tem fragmentos de texto selecionáveis para indexar.</p>}
    {error && <p role="alert" className="mt-4 rounded-xl border border-red-line bg-red-soft px-4 py-3 text-xs text-rose-200">{error}</p>}
  </section>;
}
