from app.document_processing.chunking import chunk_segments
from app.document_processing.cleaning import clean_text
from app.document_processing.sections import SectionSegment, detect_heading


def test_cleaning_preserves_paragraphs_and_source_language():
    assert clean_text("Uma  linha\ncontinua aqui.\n\nOutro\tparágrafo.") == "Uma linha continua aqui.\n\nOutro parágrafo."
    assert clean_text("Results\nValue 1    Value 2") == "Results\nValue 1 Value 2"


def test_portuguese_and_english_section_headings():
    assert detect_heading("2. Metodologia") == "Metodologia"
    assert detect_heading("III. RESULTS") == "Results"
    assert detect_heading("This sentence discusses results.") is None


def test_chunks_follow_sentence_boundaries_and_overlap():
    segments = [SectionSegment(1, "Introduction", "Alpha line is here. Beta line is here. Gamma line is here. Delta line is here.")]
    chunks = chunk_segments(segments, size=48, overlap_chars=15)
    assert len(chunks) >= 2
    assert chunks[0].text.endswith("Beta line is here.")
    assert chunks[1].text.startswith("Beta line is here.")
    assert all(chunk.character_count <= 48 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
