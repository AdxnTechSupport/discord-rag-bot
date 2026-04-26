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

## Setup

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd discord-rag-bot
cp .env.example .env
```

Open `.env` and fill in every value (see sections below for how to get each one).

---

### 2. MongoDB Atlas — create cluster and enable Vector Search

1. Go to [cloud.mongodb.com](https://cloud.mongodb.com) and create a **free M0 cluster**.
2. Under **Security → Database Access**, create a user with read/write privileges.
3. Under **Security → Network Access**, add `0.0.0.0/0` (allow all IPs) or your specific IP.
4. Click **Connect → Drivers** and copy the connection string into `MONGODB_URI` in `.env`.
   - Replace `<password>` with your database user's password.

---

### 3. Google AI Studio API key

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Click **Create API Key**.
3. Paste the key into `GOOGLE_API_KEY` in `.env`.

---

### 4. Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications).
2. Click **New Application**, give it a name.
3. Navigate to **Bot** → click **Add Bot**.
4. Under **Token**, click **Reset Token** and copy it into `DISCORD_TOKEN` in `.env`.
5. Enable **Server Members Intent** and **Message Content Intent** under Privileged Gateway Intents.
6. Navigate to **OAuth2 → General** and copy your **Client ID**.
7. Get your server's Guild ID: In Discord, enable Developer Mode (**Settings → Advanced**), then right-click your server and click **Copy Server ID**. Paste into `DISCORD_GUILD_ID` in `.env`.

**Invite the bot to your server** — replace `CLIENT_ID` with your actual client ID:

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot+applications.commands&permissions=18432
```

Permissions needed: **Send Messages** (2048) + **Use Slash Commands** (2147483648) + **Embed Links** (16384).

---

### 5. Add your documents

Place your `.txt` or `.pdf` files into `ingest/docs/`. The ingest script supports both formats.

---

### 6. Run the ingestion script

```bash
pip install -r requirements.txt
python -m ingest.ingest
```

This will:
- Chunk all documents in `ingest/docs/`
- Embed each chunk with `text-embedding-004`
- Store everything in MongoDB

---

### 7. Create the Atlas Vector Search index

After ingestion, you **must** create a vector search index in Atlas before queries will work.

1. In Atlas, go to your cluster → **Atlas Search** → **Create Search Index**.
2. Choose **JSON Editor**.
3. Select your database (`pm_accelerator_rag`) and collection (`chunks`).
4. Set the index name to exactly: `vector_index`
5. Paste this JSON:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 768,
      "similarity": "cosine"
    }
  ]
}
```

6. Click **Create Index** and wait for it to become **Active** (usually 1–2 minutes).

---

### 8. Run locally with Docker Compose

```bash
docker compose up --build
```

- API server: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Bot connects to Discord automatically

To run the services in the background:

```bash
docker compose up --build -d
docker compose logs -f
```

---

## Usage

In your Discord server, type:

```
/ask question: What is the PM Accelerator program?
```

The bot will respond with a formatted embed containing the answer and cited sources.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `DISCORD_GUILD_ID` | Yes | Discord server (guild) ID |
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `MONGODB_DB_NAME` | No | Database name (default: `pm_accelerator_rag`) |
| `MONGODB_COLLECTION_NAME` | No | Collection name (default: `chunks`) |
| `GOOGLE_API_KEY` | Yes | Google AI Studio key for embeddings + Gemini |
| `AZURE_OPENAI_ENDPOINT` | No | Optional: Azure AI Foundry endpoint for DeepSeek |
| `AZURE_OPENAI_API_KEY` | No | Optional: Azure OpenAI key |
| `API_BASE_URL` | No | RAG API URL (default: `http://api:8000`) |

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
