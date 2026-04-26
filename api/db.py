"""Async MongoDB client, vector search, and persistence helpers."""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import motor.motor_asyncio

log = logging.getLogger(__name__)

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None


def get_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGODB_URI"])
    return _client


def get_collection(name: str | None = None):
    client = get_client()
    db = client[os.environ.get("MONGODB_DB_NAME", "pm_accelerator_rag")]
    col_name = name or os.environ.get("MONGODB_COLLECTION_NAME", "chunks")
    return db[col_name]


async def ping() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception:
        return False


async def vector_search(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    collection = get_collection()
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 50,
                "limit": top_k,
            }
        },
        {
            "$project": {
                "_id": 0,
                "text": 1,
                "source": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=top_k)
    log.info(
        "vector_search: retrieved %d chunks, sources=%s",
        len(results),
        [c["source"] for c in results],
    )
    return results


async def store_chunks(records: list[dict[str, Any]]) -> None:
    collection = get_collection()
    if records:
        await collection.insert_many(records)
        log.info("store_chunks: inserted %d records", len(records))


async def log_query(question: str, answer: str, sources: list[str]) -> None:
    logs = get_collection("query_logs")
    try:
        await logs.insert_one({
            "question": question,
            "answer": answer,
            "sources": sources,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as exc:
        log.error("Failed to log query: %s", exc)


async def log_feedback(
    message_id: str,
    user_id: str,
    query: str,
    rating: str,
) -> None:
    col = get_collection("feedback_logs")
    await col.insert_one({
        "message_id": message_id,
        "user_id": user_id,
        "query": query,
        "rating": rating,
        "timestamp": datetime.now(timezone.utc),
    })
    log.info("Feedback stored: message_id=%s rating=%s", message_id, rating)


async def get_stats() -> dict[str, int]:
    query_logs = get_collection("query_logs")
    feedback_logs = get_collection("feedback_logs")

    total_queries = await query_logs.count_documents({})
    total_feedback = await feedback_logs.count_documents({})
    positive = await feedback_logs.count_documents({"rating": "positive"})
    negative = await feedback_logs.count_documents({"rating": "negative"})

    return {
        "total_queries": total_queries,
        "total_feedback": total_feedback,
        "positive_feedback": positive,
        "negative_feedback": negative,
    }
