import { NextResponse } from "next/server";

export function backendUrl(path: string): string {
  const base = process.env.BACKEND_INTERNAL_URL;
  if (!base) throw new Error("BACKEND_INTERNAL_URL não está definido");
  return `${base}${path}`;
}

export async function forwardJson(path: string, init?: RequestInit): Promise<NextResponse> {
  try {
    const response = await fetch(backendUrl(path), { ...init, cache: "no-store", signal: init?.signal ?? AbortSignal.timeout(30000) });
    if (response.status === 204) return new NextResponse(null, { status: 204 });
    return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "Backend indisponível" }, { status: 502 });
  }
}
