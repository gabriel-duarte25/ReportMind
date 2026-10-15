import { forwardJson } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  return forwardJson("/api/v1/documents/stats");
}
