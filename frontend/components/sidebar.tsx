"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, BrainCircuit, FileText, LayoutDashboard, ShieldCheck } from "lucide-react";

const navigation = [
  { label: "Painel", href: "/", icon: LayoutDashboard },
  { label: "Documentos", href: "/documents", icon: FileText },
  { label: "Agente de Documentos", href: "/document-agent", icon: Bot },
  { label: "Relatórios", href: "/reports", icon: ShieldCheck },
];

export function Sidebar() {
  const pathname = usePathname();
  return <aside className="border-b border-line bg-panel-deep lg:fixed lg:inset-y-0 lg:left-0 lg:z-20 lg:w-[224px] lg:border-b-0 lg:border-r">
    <div className="flex h-16 items-center gap-3 px-5 lg:h-[88px] lg:px-6"><div className="flex h-8 w-8 items-center justify-center rounded-lg bg-navy text-white"><BrainCircuit size={18} strokeWidth={1.9} /></div><div className="text-[17px] font-bold tracking-tight text-ink">ReportMind</div></div>
    <nav aria-label="Navegação principal" className="flex gap-1 overflow-x-auto px-3 pb-3 lg:block lg:space-y-1 lg:px-3 lg:pb-0">{navigation.map(({ label, href, icon: Icon }) => { const active = pathname === href; return <Link key={href} href={href} aria-current={active ? "page" : undefined} className={`flex shrink-0 items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors lg:w-full ${active ? "bg-blue-soft font-semibold text-ink" : "font-medium text-muted hover:bg-panel-soft hover:text-ink"}`}><Icon size={17} strokeWidth={active ? 2.1 : 1.8} className={active ? "text-accent" : ""} /><span>{label}</span></Link>; })}</nav>
  </aside>;
}
