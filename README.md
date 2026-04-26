# PM Accelerator Discord RAG Bot

A Discord slash-command bot that answers questions about PM Accelerator program documentation using Retrieval-Augmented Generation (RAG). It embeds queries with Google's `text-embedding-004`, retrieves relevant chunks from MongoDB Atlas Vector Search, and generates grounded answers with Groq

---

## Architecture

```
Discord User
    │  /ask <question>
    ▼
discord.py Bot  ──HTTP──▶  FastAPI RAG Server
                               │
                     ┌─────────┴──────────┐
                     ▼                    ▼
            Google Gemini           MongoDB Atlas
         (embed + generate)       (vector search)
```

---

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- MongoDB Atlas account (free tier works)
- Google AI Studio API key (free tier works)
- Discord developer account

---


## Project Structure

```
discord-rag-bot/
├── api/
│   ├── main.py          # FastAPI app, /query and /health endpoints
│   ├── rag.py           # Embed → vector search → LLM pipeline
│   ├── db.py            # Motor async MongoDB client + vector search
│   └── models.py        # Pydantic request/response schemas
├── bot/
│   ├── main.py          # discord.py bot with /ask slash command
│   └── api_client.py    # Async httpx client for the RAG API
├── ingest/
│   ├── ingest.py        # One-time ingestion script
│   └── docs/            # Place your .txt and .pdf files here
├── .env.example
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.bot
└── requirements.txt
```
