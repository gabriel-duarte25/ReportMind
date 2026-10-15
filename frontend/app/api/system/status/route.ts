import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET() {
  try { const baseUrl = process.env.BACKEND_INTERNAL_URL; if (!baseUrl) throw new Error("BACKEND_INTERNAL_URL is missing"); const response = await fetch(`${baseUrl}/api/v1/system/status`, { cache: "no-store", signal: AbortSignal.timeout(5000) }); if (!response.ok) throw new Error(`Backend returned ${response.status}`); return NextResponse.json(await response.json(), { headers: { "Cache-Control": "no-store" } }); }
  catch { return NextResponse.json({ status: "degraded", service: "reportmind-backend", database: "unavailable" }, { status: 503, headers: { "Cache-Control": "no-store" } }); }
}
