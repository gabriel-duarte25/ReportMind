import { forwardJson } from "@/lib/backend";

export async function POST(request: Request) {
  return forwardJson("/api/v1/agent/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
    signal: AbortSignal.timeout(300000),
  });
}
