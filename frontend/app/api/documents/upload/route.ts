import { NextRequest, NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers.get("content-type");
    if (!contentType?.startsWith("multipart/form-data") || !request.body) {
      return NextResponse.json({ detail: "É necessário selecionar um ficheiro PDF" }, { status: 400 });
    }
    const response = await fetch(backendUrl("/api/v1/documents/upload"), {
      method: "POST",
      headers: { "content-type": contentType },
      body: request.body,
      duplex: "half",
      signal: AbortSignal.timeout(120000),
    } as RequestInit & { duplex: "half" });
    return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "Serviço de carregamento indisponível" }, { status: 502 });
  }
}
