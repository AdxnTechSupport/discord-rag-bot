# PM Accelerator Discord RAG Bot — Complete Setup Guide

---

## 1. Create a Discord Application and Bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** and give it a name (e.g. "PM Accelerator FAQ Bot")
3. Navigate to **Bot** in the left sidebar → click **Add Bot** → confirm
4. Under **Token**, click **Reset Token**, copy it — this is your `DISCORD_TOKEN`
5. Scroll down to **Privileged Gateway Intents** and enable:
   - **Server Members Intent**
   - **Message Content Intent** ← required for reading message context
6. Click **Save Changes**

### Enable Required Permissions

Navigate to **OAuth2 → URL Generator**. Under Scopes check:
- `bot`
- `applications.commands`

Under Bot Permissions check:
- Send Messages
- Use Slash Commands
- Add Reactions
- Embed Links
- Read Message History

Copy the generated URL and paste it into your browser to invite the bot to your server.

### Get Your Server (Guild) ID

1. In Discord, open **User Settings → Advanced** and enable **Developer Mode**
2. Right-click your server icon in the sidebar → **Copy Server ID**
3. Paste this into `DISCORD_GUILD_ID` in your `.env`

---

## 2. Create a MongoDB Atlas Free Cluster

1. Go to [cloud.mongodb.com](https://cloud.mongodb.com) and create a free account
2. Click **Build a Database** → choose **M0 Free** → select a cloud region → click **Create**
3. Under **Security → Database Access**, click **Add New Database User**:
   - Authentication: Username/Password
   - Role: **Read and Write to Any Database**
   - Save the username and password
4. Under **Security → Network Access**, click **Add IP Address** → **Allow Access from Anywhere** (`0.0.0.0/0`)
5. Under **Database → Connect**, click **Connect** → **Drivers**:
   - Select Python, any version
   - Copy the connection string and replace `<password>` with your password
   - Paste into `MONGODB_URI` in your `.env`

---

## 3. Create the Vector Search Index

After running the ingest script (step 7), you must create the vector index:

1. In Atlas, click your cluster → **Atlas Search** tab
2. Click **Create Search Index**
3. Choose **JSON Editor** (not the Visual Editor)
4. Select your database (`pm_accelerator_rag`) and collection (`chunks`)
5. Set the **Index Name** to exactly: `vector_index`
6. Paste this JSON:

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

7. Click **Create Search Index** and wait ~1–2 minutes for status to become **Active**

---

## 4. Get a Google AI Studio API Key (Free, No Credit Card)

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with a Google account
3. Click **Create API Key** → select or create a project
4. Copy the key → paste into `GOOGLE_API_KEY` in your `.env`

This key gives access to:
- `models/text-embedding-004` — for embeddings
- `gemini-1.5-flash` — for answer generation

---

## 5. Configure Your Environment

```bash
cd discord-rag-bot
cp .env.example .env
```

Open `.env` and fill in every variable:

```
DISCORD_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_server_id_here
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=pm_accelerator_rag
MONGODB_COLLECTION_NAME=chunks
GOOGLE_API_KEY=your_google_api_key_here
API_BASE_URL=http://api:8000
```

---

## 6. Add Your Documents

Place your `.txt` or `.pdf` files into `ingest/docs/`. The bot will answer questions based only on these files.

Recommended documents for PM Accelerator:
- `ai_bootcamp_journey.pdf` — AI Bootcamp Journey & Learning Path
- `training_for_ai_interns.pdf` — Training For AI Engineer Interns
- `intern_faq.txt` — Intern FAQ

---

## 7. Run the Ingest Script

```bash
pip install -r requirements.txt
python -m ingest.ingest
```

This will:
- Chunk all documents in `ingest/docs/` (500-char chunks, 50-char overlap)
- Embed each chunk using Google `text-embedding-004`
- Store everything in MongoDB
- Print a summary table of chunks per document

After it finishes, go back to step 3 to create the vector index.

---

## 8. Run the Bot with Docker Compose

```bash
docker compose up --build
```

The bot service waits for the API to pass its health check before starting.

To run in the background:
```bash
docker compose up --build -d
docker compose logs -f        # stream all logs
docker compose logs -f api    # API logs only
docker compose logs -f bot    # Bot logs only
```

To stop:
```bash
docker compose down
```

---

## 9. Use the Bot

In your Discord server, use these slash commands:

| Command | Description |
|---|---|
| `/ask <question>` | Ask a question about the program |
| `/help` | Show what the bot does and how to use it |
| `/stats` | View usage statistics and feedback counts |

After each `/ask` response, react with 👍 or 👎 to record feedback.

---

## 10. Run the RAG Evaluator

```bash
python -m ingest.evaluate
```

This runs 5 test questions through the full pipeline (embed → vector search → LLM) and checks whether the answers contain expected keywords. Results are printed as a report with pass/fail per question.

---

## 11. Add Knowledge Without Re-Ingesting

Send a POST request to the running API to add new content on-the-fly:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "New policy text here...", "source": "policy_update.txt"}'
```

---

## Architecture Overview

```
Discord User
    │  /ask <question>
    ▼
discord.py Bot  ──HTTP──▶  FastAPI RAG Server (port 8000)
                               │
                     ┌─────────┴──────────┐
                     ▼                    ▼
            Google Gemini           MongoDB Atlas
       text-embedding-004         vector_index (cosine)
       gemini-1.5-flash           query_logs
                                  feedback_logs
```

## Troubleshooting

**Bot slash commands don't appear in Discord**
→ Commands are registered to your specific guild. Wait up to 1 minute after startup, or restart the bot.

**`$vectorSearch` returns 0 results**
→ The vector index may not be Active yet. Check in Atlas Search. Also confirm the index name is exactly `vector_index`.

**`Missing required environment variables`**
→ Make sure `.env` is in the `discord-rag-bot/` directory and all values are filled in.

**API health check fails on bot startup**
→ The API container may still be starting. The `depends_on: condition: service_healthy` in docker-compose will retry automatically.
