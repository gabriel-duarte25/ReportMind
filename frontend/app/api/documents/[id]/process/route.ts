import { forwardJson } from "@/lib/backend";

type Context = { params: Promise<{ id: string }> };

export async function POST(_request: Request, { params }: Context) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) return Response.json({ detail: "Identificador de documento inválido" }, { status: 400 });
  return forwardJson(`/api/v1/documents/${id}/process`, { method: "POST" });
}
