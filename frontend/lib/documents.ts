export type DocumentRecord = {
  id: number;
  original_filename: string;
  stored_filename: string;
  file_type: string;
  file_size: number;
  storage_path: string;
  status: "uploaded" | "processing" | "ready" | "failed";
  page_count: number | null;
  processing_error: string | null;
  indexing_status: "not_indexed" | "indexing" | "indexed" | "index_failed";
  indexing_error: string | null;
  indexed_chunk_count: number;
  embedding_model: string | null;
  indexed_at: string | null;
  uploaded_at: string;
  updated_at: string;
};

export type DocumentPageRecord = {
  id: number;
  document_id: number;
  page_number: number;
  raw_text: string;
  cleaned_text: string;
  character_count: number;
  word_count: number;
};

export type DocumentChunkRecord = {
  id: number;
  document_id: number;
  page_id: number;
  text: string;
  page_start: number;
  page_end: number;
  section: string | null;
  chunk_index: number;
  character_count: number;
  word_count: number;
  created_at: string;
};

export type ProcessingStatus = {
  document_id: number;
  status: DocumentRecord["status"];
  page_count: number;
  word_count: number;
  chunk_count: number;
  sections_detected: number;
  processing_error: string | null;
  updated_at: string;
};

export type LibraryStats = {
  document_count: number;
  page_count: number;
  chunk_count: number;
};

export type IndexingStatus = {
  document_id: number;
  indexing_status: DocumentRecord["indexing_status"];
  chunk_count: number;
  indexed_vector_count: number;
  embedding_model: string | null;
  indexing_error: string | null;
  indexed_at: string | null;
};

export type SemanticSearchResult = {
  score: number;
  chunk_id: number;
  document_id: number;
  document_name: string;
  text: string;
  section: string | null;
  page_start: number;
  page_end: number;
};

export type SemanticSearchResponse = {
  query: string;
  results: SemanticSearchResult[];
};

export type DocumentAnswer = {
  documents: { id: number; name: string }[];
  question: string;
  answer: string;
  model: string;
  answered: boolean;
  sources: (SemanticSearchResult & { supporting_quote: string })[];
};

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("pt-PT", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

export function documentStatusLabel(status: DocumentRecord["status"]): string {
  return { uploaded: "Carregado", processing: "A processar", ready: "Pronto", failed: "Falhou" }[status];
}

export function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
    const translations: Record<string, string> = {
      "Document not found": "Documento não encontrado",
      "Document is not ready": "O documento ainda não está pronto",
      "Document is not indexed": "O documento ainda não está indexado",
      "Ollama is unavailable": "O Ollama está indisponível",
      "Configured Ollama model is not installed": "O modelo Ollama configurado não está instalado",
      "Agent could not retrieve evidence from the selected documents": "O agente não encontrou evidências nos documentos selecionados",
      "Agent did not produce a final answer": "O agente não produziu uma resposta final",
    };
    return translations[payload.detail] ?? payload.detail;
  }
  return fallback;
}
