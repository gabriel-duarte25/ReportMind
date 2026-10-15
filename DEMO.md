# ReportMind presentation guide

This walkthrough uses the automatically prepared **Project Alpha** and **Project Beta** PDFs. Start the stack and wait until the dashboard shows **Alpha + Beta ready**.

```sh
docker compose up -d --build
```

Open `http://localhost:3000` (or the port configured in `FRONTEND_PORT`). The two dashboard cards open each agent experience with the demo documents selected and a prepared objective.

## Demo 1 — Autonomous Document Agent (about 2 minutes)

1. Open **Watch the agent work**.
2. Submit the prepared comparison objective.
3. While it runs, explain that Llama decides which tools to call.
4. Show **Agent activity**, especially `search_documents` and `get_document_info` when selected.
5. Expand the evidence chunks beside the final answer.

Talking point: RAG is not exposed as a separate product feature. It is the agent's `search_documents` tool. The agent decides when retrieval is necessary, Hybrid Search finds evidence in the selected PDFs, and the results return to the agent.

Expected comparison:

- Alpha: internal API, Python/FastAPI, internal teams.
- Beta: customer portal, Node.js/React, external customers.
- Alpha has the larger budget; the exact delivery dates are reported without inferring project duration.

## Demo 2 — Autonomous report generation (about 2 minutes)

1. Open **Generate a report**.
2. Submit the prepared executive report brief.
3. Show the formatted report and the activity trace.
4. Expand one evidence source.
5. Use the Markdown and PDF download buttons to demonstrate export.

Talking point: report generation reuses the same agent and retrieval tools, then produces a structured Markdown deliverable grounded in the inspected chunks.

## Before presenting

```sh
docker compose ps
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/v1/llm/status
```

Ollama generation is local and may take several seconds on CPU. Run each prompt once before the presentation so the model is warm.
