"""Store a document: extract text, chunk it, embed the chunks, save everything.

Used by the upload endpoint and by the demo workspace setup.
"""

from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.services.chunking import chunk_text, extract_text
from app.services.embeddings import embed_texts


class EmptyDocument(ValueError):
    pass


def ingest(db: Session, *, team_id: int, user_id: int, filename: str, data: bytes) -> Document:
    pieces = chunk_text(extract_text(filename, data))
    if not pieces:
        raise EmptyDocument("The file has no readable text")

    document = Document(team_id=team_id, filename=filename, uploaded_by=user_id, chunk_count=len(pieces))
    db.add(document)
    db.flush()  # gives the document its id
    for position, (piece, vector) in enumerate(zip(pieces, embed_texts(pieces))):
        db.add(Chunk(team_id=team_id, document_id=document.id, position=position, text=piece, embedding=vector))
    return document
