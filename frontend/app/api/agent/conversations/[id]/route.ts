import { forwardJson } from "@/lib/backend";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return forwardJson(`/api/v1/agent/conversations/${id}`, { cache: "no-store" });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return forwardJson(`/api/v1/agent/conversations/${id}`, { method: "DELETE" });
}
