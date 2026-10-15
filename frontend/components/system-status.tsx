"use client";
import { useEffect, useState } from "react";
type Status = "loading" | "operational" | "degraded";
export function SystemStatus() {
  const [status, setStatus] = useState<Status>("loading");
  useEffect(() => { let active = true; async function check() { try { const response = await fetch("/api/system/status", { cache: "no-store" }); const data = await response.json(); if (active) setStatus(response.ok && data.status === "operational" && data.database === "connected" ? "operational" : "degraded"); } catch { if (active) setStatus("degraded"); } } void check(); return () => { active = false; }; }, []);
  const healthy = status === "operational";
  return <div role="status" className="flex items-center gap-2.5 text-xs font-medium text-muted"><span className={`h-2 w-2 rounded-full ${healthy ? "bg-green-soft0" : status === "loading" ? "bg-amber-400" : "bg-red-soft0"}`} /><span>{healthy ? "Sistema operacional" : status === "loading" ? "A verificar sistema" : "Sistema indisponível"}</span></div>;
}
