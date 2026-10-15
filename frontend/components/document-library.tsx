"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpRight, Bot, CloudUpload, FileText, FolderOpen, Info, LoaderCircle, Search, Trash2, UploadCloud, X } from "lucide-react";
import { DocumentRecord, documentStatusLabel, errorMessage, formatDate, formatFileSize } from "@/lib/documents";
import { DocumentProcessingPanel } from "@/components/document-processing-panel";
import { DocumentIndexingPanel } from "@/components/document-indexing-panel";

async function responseError(response: Response, fallback: string): Promise<string> {
  try { return errorMessage(await response.json(), fallback); } catch { return fallback; }
}

function StatusPill({ status }: { status: DocumentRecord["status"] }) {
  const tone = status === "failed" ? "bg-red-soft text-rose-200" : status === "ready" ? "bg-green-soft text-emerald-300" : "bg-blue-soft text-blue-200";
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ${tone}`}>{documentStatusLabel(status)}</span>;
}

function DetailDialog({ document, onClose, onUpdated }: { document: DocumentRecord; onClose: () => void; onUpdated: () => void }) {
  const fields = [
    ["Nome do ficheiro", document.original_filename],
    ["Tipo de ficheiro", "PDF"],
    ["Tamanho", formatFileSize(document.file_size)],
    ["Estado", documentStatusLabel(document.status)],
    ["Número de páginas", document.page_count === null ? "Não disponível" : String(document.page_count)],
    ["Data de carregamento", formatDate(document.uploaded_at)],
  ];
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div role="dialog" aria-modal="true" aria-label="Detalhes do documento" className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-panel p-6 shadow-2xl sm:p-8">
      <div className="flex items-start justify-between gap-4"><div className="flex min-w-0 items-center gap-3"><div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-soft text-accent"><FileText size={23} /></div><div className="min-w-0"><div className="text-xs font-semibold uppercase tracking-widest text-muted-soft">Detalhes do documento</div><h2 className="mt-1 truncate text-xl font-semibold text-ink">{document.original_filename}</h2></div></div><button onClick={onClose} aria-label="Fechar detalhes" className="rounded-lg p-2 text-muted-soft hover:bg-panel-soft"><X size={19} /></button></div>
      <div className="mt-8 grid gap-x-8 gap-y-5 border-y border-line-soft py-6 sm:grid-cols-2">{fields.map(([label, value]) => <div key={label}><div className="text-xs font-medium text-muted-soft">{label}</div><div className="mt-1 break-words text-sm font-semibold text-secondary">{value}</div></div>)}</div>
      <DocumentProcessingPanel document={document} onUpdated={onUpdated} />
      {document.status === "ready" && <DocumentIndexingPanel document={document} onUpdated={onUpdated} />}
      {document.status === "ready" && document.indexing_status === "indexed" && <Link href={`/document-agent?document_id=${document.id}`} onClick={onClose} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-xs font-semibold text-white shadow-primary transition-colors hover:bg-blue-600"><Bot size={15} />Abrir no Agente de Documentos</Link>}
    </div>
  </div>;
}

export function DocumentLibrary({ maxUploadSizeMb }: { maxUploadSizeMb: number }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadName, setUploadName] = useState("");
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [selected, setSelected] = useState<DocumentRecord | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DocumentRecord | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [search, setSearch] = useState("");

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/documents", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseError(response, "Não foi possível carregar os documentos"));
      setDocuments(await response.json());
      setMessage((current) => current?.kind === "error" ? null : current);
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Não foi possível carregar os documentos" });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  function upload(file: File) {
    if (uploading) return;
    if (file.size > maxUploadSizeMb * 1024 * 1024) {
      setMessage({ kind: "error", text: `O PDF excede o limite de ${maxUploadSizeMb} MB.` });
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setMessage(null);
    setUploadName(file.name);
    setProgress(0);
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents/upload");
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100)); };
    xhr.onload = () => {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
      let payload: unknown = null;
      try { payload = JSON.parse(xhr.responseText); } catch { /* Keep fallback message. */ }
      if (xhr.status === 201) { setProgress(100); setMessage({ kind: "success", text: `${file.name} foi carregado com sucesso.` }); void refresh(); }
      else setMessage({ kind: "error", text: errorMessage(payload, "O carregamento falhou. Tenta novamente.") });
    };
    xhr.onerror = () => { setUploading(false); setMessage({ kind: "error", text: "O carregamento falhou. Verifica a ligação e tenta novamente." }); };
    xhr.send(form);
  }

  async function viewDetails(id: number) {
    try {
      const response = await fetch(`/api/documents/${id}`, { cache: "no-store" });
      if (!response.ok) throw new Error(await responseError(response, "Não foi possível carregar os detalhes do documento"));
      setSelected(await response.json());
    } catch (error) { setMessage({ kind: "error", text: error instanceof Error ? error.message : "Não foi possível carregar os detalhes do documento" }); }
  }

  async function confirmDelete() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      const response = await fetch(`/api/documents/${deleteTarget.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseError(response, "Não foi possível eliminar o documento"));
      setSelected(null);
      setDeleteTarget(null);
      setMessage({ kind: "success", text: "Documento eliminado com sucesso." });
      await refresh();
    } catch (error) { setMessage({ kind: "error", text: error instanceof Error ? error.message : "Não foi possível eliminar o documento" }); }
    finally { setDeleting(false); }
  }

  const visible = documents.filter((document) => document.original_filename.toLowerCase().includes(search.toLowerCase()));

  return <div className="min-h-screen">
    <header className="flex h-16 items-center justify-between border-b border-line bg-panel-deep px-5 sm:px-8 lg:h-[72px] lg:px-10"><div className="text-xs font-medium text-muted-soft">Espaço de trabalho <span className="mx-2 text-muted-faint">/</span><span className="text-secondary">Documentos</span></div><div className="text-xs font-medium text-muted-soft">Biblioteca de Documentos</div></header>
    <div className="mx-auto max-w-[1450px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4"><div><div className="mb-3 inline-flex items-center gap-2 rounded-full border border-blue-line bg-blue-soft px-3 py-1 text-[11px] font-semibold text-accent"><FolderOpen size={12} /> BIBLIOTECA DE DOCUMENTOS</div><h1 className="text-3xl font-bold tracking-tight text-ink sm:text-[36px]">Documentos</h1><p className="mt-2 text-sm text-muted">Um espaço central para os teus relatórios e ficheiros de origem.</p></div><button onClick={() => inputRef.current?.click()} disabled={uploading} className="inline-flex items-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-sm font-semibold text-white shadow-primary transition-colors hover:bg-blue-600 disabled:opacity-50"><CloudUpload size={17} />Carregar documento</button></div>
      <input ref={inputRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload(file); }} />
      {message && <div role="alert" className={`mb-5 flex items-center justify-between gap-4 rounded-xl border px-4 py-3 text-sm ${message.kind === "success" ? "border-green-line bg-green-soft text-emerald-200" : "border-red-line bg-red-soft text-rose-100"}`}><span>{message.text}</span><button onClick={() => setMessage(null)} aria-label="Fechar mensagem"><X size={17} /></button></div>}
      <div onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { event.preventDefault(); if (event.currentTarget === event.target) setDragging(false); }} onDrop={(event) => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file) upload(file); }} className={`rounded-2xl border-2 border-dashed bg-panel px-6 py-8 text-center transition-colors ${dragging ? "border-accent bg-blue-soft" : "border-line hover:border-accent"}`}><div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-soft text-accent"><UploadCloud size={23} /></div><div className="text-sm font-semibold text-ink">Arrasta e larga um PDF aqui</div><div className="mt-1 text-xs text-muted-soft">ou <button onClick={() => inputRef.current?.click()} className="font-semibold text-accent hover:underline">procurar nos teus ficheiros</button></div><div className="mt-3 text-[11px] text-muted-soft">Apenas ficheiros PDF · Até {maxUploadSizeMb} MB</div></div>
      {uploading && <div aria-live="polite" className="mt-4 rounded-xl border border-line bg-panel p-4"><div className="mb-2 flex items-center justify-between gap-3 text-xs"><span className="truncate font-semibold text-secondary">A carregar {uploadName}</span><span className="text-muted">{progress === 100 ? "A guardar documento..." : `${progress}%`}</span></div><div className="h-2 overflow-hidden rounded-full bg-panel-soft"><div className="h-full rounded-full bg-accent transition-all" style={{ width: `${progress}%` }} /></div></div>}
      <section className="mt-8 overflow-hidden rounded-2xl border border-line bg-panel shadow-card"><div className="flex flex-wrap items-center justify-between gap-4 border-b border-line-soft px-5 py-5 sm:px-6"><div><h2 className="text-base font-semibold text-ink">Os teus documentos</h2><p className="mt-1 text-xs text-muted-soft">{loading ? "A carregar documentos..." : `${documents.length} documento${documents.length === 1 ? "" : "s"} na biblioteca`}</p></div><div className="relative"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-soft" /><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Pesquisar documentos" placeholder="Pesquisar documentos" className="w-full rounded-lg border border-line bg-panel-deep py-2 pl-9 pr-3 text-xs text-secondary placeholder:text-muted-soft outline-none focus:border-accent sm:w-52" /></div></div>
        {loading ? <div className="flex min-h-[240px] items-center justify-center gap-2 text-sm text-muted-soft"><LoaderCircle size={17} className="animate-spin" /> A carregar documentos</div> : documents.length === 0 ? <div className="flex min-h-[280px] flex-col items-center justify-center px-5 py-12 text-center"><div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-panel-soft text-muted-soft"><FileText size={26} strokeWidth={1.5} /></div><div className="text-sm font-semibold text-ink">Ainda não foram carregados documentos.</div><p className="mt-2 max-w-sm text-xs leading-5 text-muted-soft">Carrega o primeiro PDF para começar a construir a biblioteca.</p></div> : visible.length === 0 ? <div className="py-16 text-center text-sm text-muted">Nenhum documento corresponde à pesquisa.</div> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left"><thead className="bg-panel-soft text-[11px] font-semibold uppercase tracking-wider text-muted-soft"><tr><th className="px-6 py-3 font-semibold">Nome</th><th className="px-4 py-3 font-semibold">Tipo</th><th className="px-4 py-3 font-semibold">Tamanho</th><th className="px-4 py-3 font-semibold">Páginas</th><th className="px-4 py-3 font-semibold">Estado</th><th className="px-4 py-3 font-semibold">Carregado em</th><th className="px-4 py-3 text-right font-semibold">Ações</th></tr></thead><tbody>{visible.map((document) => <tr key={document.id} className="border-t border-line-soft text-xs text-secondary-soft"><td className="max-w-[260px] px-6 py-4"><div className="flex items-center gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-soft text-rose-300"><FileText size={18} /></div><span className="truncate font-semibold text-ink" title={document.original_filename}>{document.original_filename}</span></div></td><td className="px-4 py-4">PDF</td><td className="px-4 py-4">{formatFileSize(document.file_size)}</td><td className="px-4 py-4">{document.page_count ?? "—"}</td><td className="px-4 py-4"><StatusPill status={document.status} /></td><td className="whitespace-nowrap px-4 py-4">{formatDate(document.uploaded_at)}</td><td className="whitespace-nowrap px-4 py-4 text-right"><button onClick={() => void viewDetails(document.id)} className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 font-semibold text-accent hover:bg-blue-soft"><Info size={14} />Ver detalhes</button><button onClick={() => setDeleteTarget(document)} className="ml-1 inline-flex items-center gap-1 rounded-md px-2 py-1.5 font-semibold text-muted hover:bg-red-soft hover:text-rose-300"><Trash2 size={14} />Eliminar</button></td></tr>)}</tbody></table></div>}
      </section>
      <div className="mt-5 flex items-center gap-2 text-xs text-muted-soft"><ArrowUpRight size={13} /> A análise documental está disponível através do Agente de Documentos.</div>
    </div>
    {selected && <DetailDialog document={selected} onClose={() => setSelected(null)} onUpdated={() => { void refresh(); void viewDetails(selected.id); }} />}
    {deleteTarget && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4" role="presentation"><div role="alertdialog" aria-modal="true" aria-label="Eliminar documento" className="w-full max-w-md rounded-2xl bg-panel p-6 shadow-2xl"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-soft text-rose-300"><Trash2 size={21} /></div><h2 className="mt-5 text-lg font-semibold text-ink">Eliminar documento?</h2><p className="mt-2 text-sm leading-6 text-muted">Esta ação irá eliminar permanentemente <strong className="font-semibold text-secondary">{deleteTarget.original_filename}</strong> e o ficheiro guardado.</p><div className="mt-6 flex justify-end gap-3"><button onClick={() => setDeleteTarget(null)} disabled={deleting} className="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-secondary-soft">Cancelar</button><button onClick={() => void confirmDelete()} disabled={deleting} className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{deleting ? "A eliminar..." : "Eliminar documento"}</button></div></div></div>}
  </div>;
}
