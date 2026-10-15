import { forwardJson } from "@/lib/backend";

export async function GET() {
  return forwardJson("/api/v1/agent/conversations", { cache: "no-store" });
}
