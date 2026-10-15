import pymupdf
from fastapi.testclient import TestClient

from app.main import app


def test_report_pdf_export_preserves_structure_and_paginates():
    rows = "\n".join(f"| Clube {index} | País {index} | Informação {index} |" for index in range(1, 55))
    content = (
        "# Relatório Comparativo\n\n"
        "## Dados principais\n\n"
        "| Clube | País | Informação |\n|---|---|---|\n"
        f"{rows}\n\n"
        "## Conclusão\n\nInformação confirmada através das fontes selecionadas."
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/reports/export/pdf", json={"title": "Relatório Comparativo", "content": content})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="relatorio-comparativo.pdf"'
    assert response.content.startswith(b"%PDF")
    document = pymupdf.open(stream=response.content, filetype="pdf")
    assert document.page_count >= 2
    text = "\n".join(page.get_text() for page in document).replace("ﬁ", "fi")
    assert "Relatório Comparativo" in text
    assert "Clube 54" in text
    assert "Informação confirmada" in text
    assert "Página 1 de" in document[0].get_text()
    assert f"Página {document.page_count} de {document.page_count}" in document[-1].get_text()
