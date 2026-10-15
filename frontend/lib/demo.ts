import { DocumentRecord } from "@/lib/documents";

export const DEMO_FILENAMES = [
  "reportmind-demo-project-alpha.pdf",
  "reportmind-demo-project-beta.pdf",
];

export const DEMO_AGENT_OBJECTIVE = "Cria uma comparação concisa e baseada em evidências entre o Projeto Alpha e o Projeto Beta. Indica os objetivos, orçamentos, datas de entrega, tecnologias e públicos-alvo exatos. Identifica qual tem o maior orçamento. Não infiras a duração dos projetos; apresenta apenas as datas indicadas nos documentos.";
export const DEMO_REPORT_BRIEF = "Cria um relatório executivo em português que compare o Projeto Alpha e o Projeto Beta com base nos factos exatos dos documentos: objetivo, orçamento, data de entrega, tecnologia e público-alvo. Identifica qual tem o maior orçamento. Não infiras a duração dos projetos; apresenta apenas as datas indicadas.";

export function demoDocuments(documents: DocumentRecord[]): DocumentRecord[] {
  return DEMO_FILENAMES
    .map((filename) => documents.find((document) => document.original_filename === filename))
    .filter((document): document is DocumentRecord => Boolean(document));
}
