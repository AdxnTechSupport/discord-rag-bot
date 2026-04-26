"""Pydantic request/response models for the RAG API."""

from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    chunks_used: int


class HealthResponse(BaseModel):
    status: str
    db: str


class FeedbackRequest(BaseModel):
    message_id: str
    user_id: str
    query: str
    rating: Literal["positive", "negative"]


class FeedbackResponse(BaseModel):
    ok: bool


class StatsResponse(BaseModel):
    total_queries: int
    total_feedback: int
    positive_feedback: int
    negative_feedback: int


class IngestRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)


class IngestResponse(BaseModel):
    chunks_added: int
    source: str
