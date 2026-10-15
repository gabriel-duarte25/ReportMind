import { DocumentLibrary } from "@/components/document-library";

export const metadata = { title: "Documentos · ReportMind" };
export const dynamic = "force-dynamic";

export default function DocumentsPage() {
  const maxUploadSizeMb = Number(process.env.MAX_UPLOAD_SIZE_MB ?? "25");
  return <DocumentLibrary maxUploadSizeMb={maxUploadSizeMb} />;
}
