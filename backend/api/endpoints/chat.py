"""
RAG chatbot endpoint - replaces Supabase chat-document edge function.
Uses document chunks + embeddings for context-aware Q&A.
"""

import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db, get_current_user
from db.models import DocumentChunk, DocumentProcessing

logger = structlog.get_logger()
router = APIRouter()


class ChatRequest(BaseModel):
    document_id: str
    message: str
    conversation_history: Optional[list] = None


@router.post("/chat")
async def chat_with_document(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Chat with a document using RAG (Retrieval-Augmented Generation)."""
    # Fetch document
    doc_stmt = select(DocumentProcessing).where(
        DocumentProcessing.id == uuid.UUID(req.document_id)
    )
    doc = (await db.execute(doc_stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Fetch relevant chunks
    chunk_stmt = select(DocumentChunk).where(
        DocumentChunk.document_id == doc.id
    ).order_by(DocumentChunk.chunk_index)
    chunks = (await db.execute(chunk_stmt)).scalars().all()

    if not chunks:
        raise HTTPException(status_code=400, detail="No document chunks available for chat")

    # Build context from chunks (simple approach - semantic search can be added later)
    context = "\n\n".join(c.content for c in chunks[:5])  # Top 5 chunks

    # Build conversation
    history = req.conversation_history or []
    history.append({"role": "user", "content": req.message})

    # Call LLM
    from llm.llm_engines.llm_registry import LLMRegistry
    llm = LLMRegistry()

    system_prompt = f"""You are a helpful assistant that answers questions about an engineering document.
Use ONLY the following document context to answer. If the answer is not in the context, say so.

DOCUMENT: {doc.file_name}
CONTEXT:
{context}"""

    try:
        response = await llm.chat_async(
            system_prompt=system_prompt,
            messages=history,
        )

        return {
            "response": response,
            "document_id": str(doc.id),
        }
    except Exception as e:
        logger.error("chat_failed", doc_id=str(doc.id), error=str(e))
        raise HTTPException(status_code=500, detail="Chat processing failed")
