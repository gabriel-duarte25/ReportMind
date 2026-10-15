import type { Metadata } from "next";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";
export const metadata: Metadata = { title: "ReportMind", description: "Inteligência de relatórios com IA" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt"><body><div className="min-h-screen lg:flex"><Sidebar /><main className="min-w-0 flex-1 lg:ml-[224px]">{children}</main></div></body></html>;
}
