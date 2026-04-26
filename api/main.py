"""FastAPI RAG server: /query, /health, /api/feedback, /api/stats, /api/ingest."""

import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["MONGODB_URI", "GOOGLE_API_KEY"]
missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    sys.exit(f"Missing required environment variables: {', '.join(missing)}")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .db import get_stats, log_feedback, log_query, ping, store_chunks, vector_search
from .models import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    StatsResponse,
)
from .rag import answer_question, embed_batch, embed_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(title="PM Accelerator RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = await ping()
    return HealthResponse(
        status="ok",
        db="connected" if db_ok else "unreachable",
    )


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    t0 = time.monotonic()
    log.info("Incoming /query: question=%r", req.question)
    try:
        answer, sources, chunks_used = await answer_question(req.question)
    except Exception as exc:
        log.exception("RAG pipeline error")
        raise HTTPException(status_code=500, detail="RAG pipeline failed") from exc

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "Response: answer_len=%d sources=%s chunks=%d elapsed_ms=%d",
        len(answer),
        sources,
        chunks_used,
        elapsed_ms,
    )
    await log_query(req.question, answer, sources)
    return QueryResponse(answer=answer, sources=sources, chunks_used=chunks_used)


@app.post("/api/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest) -> FeedbackResponse:
    log.info(
        "Feedback received: message_id=%s user_id=%s rating=%s",
        req.message_id,
        req.user_id,
        req.rating,
    )
    try:
        await log_feedback(req.message_id, req.user_id, req.query, req.rating)
    except Exception as exc:
        log.exception("Failed to store feedback")
        raise HTTPException(status_code=500, detail="Failed to store feedback") from exc
    return FeedbackResponse(ok=True)


@app.get("/api/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    try:
        data = await get_stats()
    except Exception as exc:
        log.exception("Failed to fetch stats")
        raise HTTPException(status_code=500, detail="Failed to fetch stats") from exc
    return StatsResponse(**data)


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest) -> IngestResponse:
    """Chunk, embed, and store a new text snippet without re-running the full ingest script."""
    log.info("Inline ingest: source=%s text_len=%d", req.source, len(req.text))
    chunks = _splitter.split_text(req.text)
    if not chunks:
        return IngestResponse(chunks_added=0, source=req.source)

    try:
        embeddings = embed_batch(chunks, task_type="RETRIEVAL_DOCUMENT")
    except Exception as exc:
        log.exception("Embedding failed during inline ingest")
        raise HTTPException(status_code=500, detail="Embedding failed") from exc

    records = [
        {
            "text": text,
            "embedding": embedding,
            "source": req.source,
            "chunk_index": i,
        }
        for i, (text, embedding) in enumerate(zip(chunks, embeddings))
    ]

    try:
        await store_chunks(records)
    except Exception as exc:
        log.exception("Failed to store chunks during inline ingest")
        raise HTTPException(status_code=500, detail="Storage failed") from exc

    log.info("Inline ingest complete: source=%s chunks_added=%d", req.source, len(records))
    return IngestResponse(chunks_added=len(records), source=req.source)
