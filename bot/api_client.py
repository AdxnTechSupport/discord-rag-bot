"""Async HTTP client for communicating with the FastAPI RAG backend."""

import os
from typing import Any

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
TIMEOUT = 30.0


async def query_rag(question: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
        response = await client.post("/query", json={"question": question})
        response.raise_for_status()
        return response.json()


async def post_feedback(
    message_id: str,
    user_id: str,
    query: str,
    rating: str,
) -> None:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0) as client:
        response = await client.post(
            "/api/feedback",
            json={
                "message_id": message_id,
                "user_id": user_id,
                "query": query,
                "rating": rating,
            },
        )
        response.raise_for_status()


async def get_stats() -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0) as client:
        response = await client.get("/api/stats")
        response.raise_for_status()
        return response.json()


async def check_health() -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=5.0) as client:
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()
