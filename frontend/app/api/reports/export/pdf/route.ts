import { backendUrl } from "@/lib/backend";

export async function POST(request: Request) {
  try {
    const response = await fetch(backendUrl("/api/v1/reports/export/pdf"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    });
    const body = await response.arrayBuffer();
    return new Response(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/pdf",
        "Content-Disposition": response.headers.get("Content-Disposition") ?? 'attachment; filename="reportmind-report.pdf"',
      },
    });
  } catch {
    return Response.json({ detail: "Não foi possível gerar o PDF" }, { status: 502 });
  }
}
