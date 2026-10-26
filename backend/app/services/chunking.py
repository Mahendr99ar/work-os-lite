"""Read an uploaded file and split it into overlapping chunks."""

import io

from pypdf import PdfReader

# Roughly 1 token = 0.75 English words, so 375 words is about 500 tokens.
CHUNK_WORDS = 375
OVERLAP_WORDS = 50

ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")


def chunk_text(text: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    """Split text into windows of `size` words.

    Each window repeats the last `overlap` words of the one before it, so a
    sentence cut at a boundary still appears whole in one of the two chunks.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    words = text.split()
    if not words:
        return []
    chunks = []
    step = size - overlap
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
    return chunks
