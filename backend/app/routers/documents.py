"""Upload documents and ask questions about them."""

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.deps import TeamScope, get_scope
from app.models import Document
from app.ratelimit import ask_limiter
from app.schemas import AskIn, AskOut, DocumentOut, SourceOut
from app.services import audit, rag
from app.services.chunking import ALLOWED_EXTENSIONS
from app.services.ingest import EmptyDocument, ingest
from app.services.llm import LLMError, LLMNotConfigured

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile = File(...), scope: TeamScope = Depends(get_scope)) -> Document:
    filename = file.filename or "upload.txt"
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Allowed file types: {', '.join(ALLOWED_EXTENSIONS)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 5 MB")

    try:
        document = ingest(scope.db, team_id=scope.team_id, user_id=scope.user.id, filename=filename, data=data)
    except EmptyDocument:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file has no readable text. Scanned PDFs need OCR first.")
    except Exception:
        scope.db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not read text from this file")
    scope.db.commit()
    return document


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(scope: TeamScope = Depends(get_scope)) -> list[Document]:
    return list(scope.db.scalars(scope.select(Document).order_by(Document.id.desc())))


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, scope: TeamScope = Depends(get_scope)) -> Response:
    scope.db.delete(scope.get(Document, document_id))
    scope.db.commit()
    return Response(status_code=204)


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, scope: TeamScope = Depends(get_scope)) -> AskOut:
    ask_limiter.check(f"user:{scope.user.id}")
    try:
        text, hits, refused, raw = rag.answer(scope.db, scope.team_id, body.question)
    except LLMError as exc:
        audit.log(scope.db, team_id=scope.team_id, user_id=scope.user.id, action="ask",
                  input_text=body.question, output=str(exc), status="failed")
        scope.db.commit()
        if isinstance(exc, LLMNotConfigured):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "AI is not set up on this server. The admin needs to add LLM_API_KEY.")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The AI service failed: {exc}")

    audit.log(scope.db, team_id=scope.team_id, user_id=scope.user.id, action="ask",
              input_text=body.question, output=raw or text, status="refused" if refused else "ok")
    scope.db.commit()

    # One source per document, keeping the best score.
    best: dict[int, SourceOut] = {}
    for hit in hits:
        doc_id = hit.chunk.document_id
        if doc_id not in best or hit.similarity > best[doc_id].similarity:
            best[doc_id] = SourceOut(document_id=doc_id, filename=hit.filename, similarity=round(hit.similarity, 3))
    return AskOut(answer=text, sources=list(best.values()), refused=refused)
