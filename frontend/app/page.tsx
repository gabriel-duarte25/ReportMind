"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Bot, CheckCircle2, Clock3, FileOutput, FileText, Files, Layers3, PlayCircle, Search, SearchCheck } from "lucide-react";
import { SystemStatus } from "@/components/system-status";
import { DocumentRecord, LibraryStats, formatDate, formatFileSize } from "@/lib/documents";
import { DEMO_FILENAMES } from "@/lib/demo";

export default function Dashboard() {
  const [documents, setDocuments] = useState<DocumentRecord[] | null>(null);
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([fetch("/api/documents", { cache: "no-store" }), fetch("/api/documents/stats", { cache: "no-store" })])
      .then(async ([documentsResponse, statsResponse]) => {
        if (!documentsResponse.ok || !statsResponse.ok) throw new Error("Não foi possível carregar o painel");
        return [await documentsResponse.json() as DocumentRecord[], await statsResponse.json() as LibraryStats] as const;
      })
      .then(([data, totals]) => { if (active) { setDocuments(data); setStats(totals); } })
      .catch(() => { if (active) setLoadError(true); });
    return () => { active = false; };
  }, []);

  const metrics = [
    { label: "Documentos", value: stats === null ? "—" : String(stats.document_count), icon: Files },
    { label: "Páginas analisadas", value: stats === null ? "—" : String(stats.page_count), icon: FileText },
    { label: "Fragmentos", value: stats === null ? "—" : String(stats.chunk_count), icon: Layers3 },
    { label: "Descobertas da IA", value: "0", icon: SearchCheck },
  ];

  const demoReady = documents !== null && DEMO_FILENAMES.every((filename) => documents.some((document) => document.original_filename === filename && document.status === "ready" && document.indexing_status === "indexed"));
  const pipeline = [
    { label: "Biblioteca de PDFs", detail: "Carregar e guardar", icon: Files },
    { label: "Processamento", detail: "Páginas e fragmentos", icon: Layers3 },
    { label: "Pesquisa híbrida", detail: "Vetores + BM25", icon: Search },
    { label: "Agente de documentos", detail: "Ferramentas autónomas", icon: Bot },
    { label: "Relatórios", detail: "Resultado fundamentado", icon: FileOutput },
  ];
  const demos = [
    { step: "01", title: "Vê o agente em ação", description: "Mostra o Llama a usar a pesquisa híbrida como ferramenta e a consultar evidências.", href: "/document-agent?demo=1", action: "Executar demonstração do agente", icon: Bot, duration: "2 min" },
    { step: "02", title: "Gerar um relatório", description: "Deixa o agente pesquisar os dois PDFs e criar um relatório para descarregar.", href: "/reports?demo=1", action: "Executar demonstração do relatório", icon: FileOutput, duration: "2 min" },
  ];

  return <div className="min-h-screen">
    <header className="flex h-16 items-center justify-between border-b border-line bg-panel-deep px-5 sm:px-8 lg:h-[72px] lg:px-10"><div className="text-xs font-medium text-muted-soft">Espaço de trabalho <span className="mx-2 text-muted-faint">/</span><span className="text-secondary">Painel</span></div><SystemStatus /></header>
    <div className="mx-auto max-w-[1450px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
      <div className="mb-10"><p className="mb-2 text-xs font-semibold uppercase tracking-[.18em] text-accent">Visão geral</p><h1 className="text-3xl font-bold tracking-tight text-ink sm:text-[36px]">Olá, bem-vindo ao ReportMind</h1><p className="mt-2 text-sm text-muted sm:text-base">Pesquisa, analisa e transforma os teus documentos em conhecimento.</p></div>
      <section aria-label="Métricas gerais" className="flex flex-wrap justify-between gap-x-12 gap-y-10">{metrics.map(({ label, value, icon: Icon }) => <div key={label} className="min-w-[150px] flex-1"><div className="flex items-center gap-3"><Icon size={21} strokeWidth={1.7} className="text-accent" /><div className="text-3xl font-semibold leading-none tracking-tight text-ink">{value}</div></div><div className="mt-2 text-xs text-muted-soft">{label}</div></div>)}</section>
      <section className="mt-14"><div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-base font-semibold text-ink">Fluxo documental</h2><p className="mt-1 text-xs text-muted-soft">Do PDF ao relatório fundamentado, num único processo.</p></div><div className={`inline-flex items-center gap-2 text-[11px] font-semibold ${demoReady ? "text-emerald-300" : "text-muted-soft"}`}>{demoReady ? <CheckCircle2 size={13} /> : <Clock3 size={13} />}{documents === null ? "A verificar demonstração" : demoReady ? "Alpha + Beta prontos" : "A preparar demonstração"}</div></div>
        <ol className="relative mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-5 lg:gap-8 before:absolute before:left-5 before:top-5 before:hidden before:h-px before:w-[calc(100%-2.5rem)] before:bg-line lg:before:block">{pipeline.map(({ label, detail, icon: Icon }, index) => <li key={label} className="relative flex gap-4 lg:block"><div className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-blue-line bg-surface text-accent"><Icon size={17} /></div><div className="pt-0.5 lg:mt-4"><span className="text-[10px] font-semibold tracking-wider text-muted-faint">0{index + 1}</span><div className="mt-1 text-xs font-semibold text-secondary">{label}</div><div className="mt-1 text-[11px] text-muted-soft">{detail}</div></div></li>)}</ol>
      </section>
      <div className="mt-10 grid gap-10 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,.65fr)]">
      <section><div className="mb-4 flex items-end justify-between gap-4"><div><h2 className="text-base font-semibold text-ink">Documentos recentes</h2><p className="mt-1 text-xs text-muted-soft">Os últimos ficheiros adicionados à biblioteca.</p></div><Link href="/documents" className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:text-white">Ver todos <ArrowRight size={13} /></Link></div><div className="border-t border-line">
        {loadError ? <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 px-5 text-center text-sm text-muted"><span>Não foi possível carregar os documentos.</span><button onClick={() => window.location.reload()} className="font-semibold text-accent">Tentar novamente</button></div> : documents === null ? <div className="flex min-h-[220px] items-center justify-center text-sm text-muted-soft">A carregar documentos...</div> : documents.length === 0 ? <div className="flex min-h-[280px] flex-col items-center justify-center px-5 py-12 text-center"><div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-line bg-panel-soft text-muted-soft"><FileText size={25} strokeWidth={1.5} /></div><h3 className="text-sm font-semibold text-ink">Ainda não foram carregados documentos.</h3><p className="mt-2 max-w-sm text-xs leading-5 text-muted-soft">Quando existirem documentos, serão apresentados aqui.</p><Link href="/documents" className="mt-5 inline-flex items-center gap-1 text-xs font-semibold text-accent">Ir para Documentos <ArrowRight size={14} /></Link></div> : <div className="divide-y divide-line-soft">{documents.slice(0, 5).map((document) => <Link key={document.id} href="/documents" className="flex items-center justify-between gap-4 px-6 py-4 hover:bg-panel-soft"><div className="flex min-w-0 items-center gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-soft text-rose-300"><FileText size={17} /></div><div className="min-w-0"><div className="truncate text-sm font-semibold text-ink">{document.original_filename}</div><div className="mt-0.5 text-xs text-muted-soft">PDF · {formatFileSize(document.file_size)}</div></div></div><div className="shrink-0 text-xs text-muted-soft">{formatDate(document.uploaded_at)}</div></Link>)}</div>}
      </div></section>
      <section><div className="mb-4"><h2 className="text-base font-semibold text-ink">Demonstrações</h2><p className="mt-1 text-xs text-muted-soft">Dois percursos rápidos para explorar o produto.</p></div><div className="border-t border-line">{demos.map(({ step, title, description, href, action, icon: Icon, duration }) => <Link key={step} href={href} className="group flex gap-4 border-b border-line py-5"><Icon size={18} className="mt-0.5 shrink-0 text-accent" /><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold text-ink">{title}</h3><span className="shrink-0 text-[10px] text-muted-soft">{duration}</span></div><p className="mt-1.5 text-xs leading-5 text-muted">{description}</p><div className="mt-2 inline-flex items-center gap-1.5 text-[11px] font-semibold text-accent">{action}<PlayCircle size={12} className="transition-transform group-hover:translate-x-0.5" /></div></div></Link>)}</div></section>
      </div>
    </div>
  </div>;
}
