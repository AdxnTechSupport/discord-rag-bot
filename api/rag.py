"""RAG pipeline: embed query → vector search → grounded LLM answer."""

import logging
import os
import time

from google import genai
from google.genai import types

from .db import vector_search

log = logging.getLogger(__name__)

EMBED_MODEL = "gemini-embedding-001"
LLM_MODEL = "llama-3.3-70b-versatile"

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


def embed_text(text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    """Embed a single string."""
    result = _get_client().models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return result.embeddings[0].values


def embed_batch(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed a list of strings in one API call."""
    result = _get_client().models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return [e.values for e in result.embeddings]


def _build_prompt(question: str, chunks: list[dict]) -> str:
    context_blocks = "\n\n".join(
        f"[{i + 1}] (source: {c['source']})\n{c['text']}"
        for i, c in enumerate(chunks)
    )

    system = (
        "You are a helpful assistant for the PM Accelerator AI engineering internship program.\n"
        "Rules you MUST follow:\n"
        "1. Answer ONLY from the numbered context blocks provided below. Never use outside knowledge.\n"
        "2. If the answer is not in the context, say exactly: "
        "\"I don't have information about that in my knowledge base.\"\n"
        "3. Always mention which source document your answer comes from, e.g. \"According to [source.pdf]...\"\n"
        "4. Keep answers concise — under 300 words unless a list is genuinely needed.\n"
        "5. Format your answer using Discord markdown: "
        "bold key terms with **text**, use • for bullet lists.\n"
        "6. Cite context blocks inline with [1], [2], etc.\n"
    )

    return (
        f"{system}\n\n"
        f"CONTEXT:\n{context_blocks}\n\n"
        f"QUESTION: {question}\n\n"
        "ANSWER:"
    )


async def answer_question(question: str) -> tuple[str, list[str], int]:
    """
    Runs the full RAG pipeline.
    Returns (answer, sources, chunks_used).
    """
    t0 = time.monotonic()

    query_embedding = embed_text(question, task_type="RETRIEVAL_QUERY")
    chunks = await vector_search(query_embedding, top_k=5)

    if not chunks:
        log.warning("No chunks retrieved for question: %s", question)
        return ("I don't have information about that in my knowledge base.", [], 0)

    prompt = _build_prompt(question, chunks)
    prompt_token_estimate = len(prompt.split())
    log.info("LLM call: model=%s prompt_tokens_est=%d", LLM_MODEL, prompt_token_estimate)

    llm_start = time.monotonic()

    from groq import Groq
    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    chat = groq_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = chat.choices[0].message.content.strip()

    llm_ms = int((time.monotonic() - llm_start) * 1000)
    total_ms = int((time.monotonic() - t0) * 1000)

    sources = list(dict.fromkeys(c["source"] for c in chunks))
    log.info(
        "RAG complete: answer_len=%d sources=%s llm_ms=%d total_ms=%d",
        len(answer), sources, llm_ms, total_ms,
    )

    return answer, sources, len(chunks)
