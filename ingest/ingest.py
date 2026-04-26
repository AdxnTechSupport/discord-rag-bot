"""
One-time ingestion script: loads docs from ingest/docs/, chunks them,
embeds with Google text-embedding-004, and stores in MongoDB Atlas.

Run from project root:
    python -m ingest.ingest
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["MONGODB_URI", "GOOGLE_API_KEY"]
missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    sys.exit(f"Missing required environment variables: {', '.join(missing)}")

import pymongo
from google import genai
from google.genai import types
from langchain_text_splitters import RecursiveCharacterTextSplitter

_genai_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.getenv("MONGODB_DB_NAME", "pm_accelerator_rag")
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION_NAME", "chunks")
DOCS_DIR = Path(__file__).parent / "docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBED_MODEL = "gemini-embedding-001"
BATCH_SIZE = 20


def load_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return load_txt(path)
    if suffix == ".pdf":
        return load_pdf(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def embed_batch(texts: list[str]) -> list[list[float]]:
    result = _genai_client.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return [e.values for e in result.embeddings]


def ingest():
    if not DOCS_DIR.exists():
        sys.exit(f"Docs directory not found: {DOCS_DIR}")

    doc_files = [
        p for p in DOCS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".txt", ".pdf"}
    ]
    if not doc_files:
        sys.exit(f"No .txt or .pdf files found in {DOCS_DIR}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    client = pymongo.MongoClient(MONGODB_URI)
    db = client[DB_NAME]

    print(f"Dropping and recreating collection '{COLLECTION_NAME}' …")
    db.drop_collection(COLLECTION_NAME)
    collection = db[COLLECTION_NAME]

    total_chunks = 0
    # summary: filename -> (chunk_count, list_of_chunk_lengths)
    summary: dict[str, tuple[int, list[int]]] = {}

    for doc_path in sorted(doc_files):
        print(f"\nProcessing: {doc_path.name}")
        try:
            raw_text = load_document(doc_path)
        except Exception as exc:
            print(f"  ERROR loading {doc_path.name}: {exc}")
            continue

        chunks = splitter.split_text(raw_text)
        print(f"  Split into {len(chunks)} chunks")

        records = []
        chunk_lengths: list[int] = []
        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[batch_start : batch_start + BATCH_SIZE]
            try:
                embeddings = embed_batch(batch)
            except Exception as exc:
                print(f"  ERROR embedding batch at index {batch_start}: {exc}")
                continue

            for i, (text, embedding) in enumerate(zip(batch, embeddings)):
                records.append({
                    "text": text,
                    "embedding": embedding,
                    "source": doc_path.name,
                    "chunk_index": batch_start + i,
                })
                chunk_lengths.append(len(text))

            print(f"  Embedded chunks {batch_start}–{batch_start + len(batch) - 1}")

        if records:
            collection.insert_many(records)
            print(f"  Inserted {len(records)} chunks for '{doc_path.name}'")
            summary[doc_path.name] = (len(records), chunk_lengths)
            total_chunks += len(records)

    client.close()

    print("\n" + "=" * 72)
    print(f"{'INGESTION SUMMARY':^72}")
    print("=" * 72)
    col_w = max((len(n) for n in summary), default=20)
    col_w = max(col_w, 20)
    header = f"  {'Document':<{col_w}}  {'Chunks':>8}  {'Avg chars':>10}  {'Total chars':>12}"
    print(header)
    print("-" * 72)
    for source, (count, lengths) in summary.items():
        avg = int(sum(lengths) / len(lengths)) if lengths else 0
        total_chars = sum(lengths)
        print(f"  {source:<{col_w}}  {count:>8}  {avg:>10}  {total_chars:>12,}")
    print("-" * 72)
    print(f"  {'TOTAL':<{col_w}}  {total_chunks:>8}")
    print("=" * 72)

    print("""
=== Atlas Vector Search Index ===
In your MongoDB Atlas cluster, navigate to:
  Atlas Search → Create Search Index → JSON Editor

Collection: {db}.{col}
Index name: vector_index

Paste this JSON config:
{{
  "fields": [
    {{
      "type": "vector",
      "path": "embedding",
      "numDimensions": 768,
      "similarity": "cosine"
    }}
  ]
}}
""".format(db=DB_NAME, col=COLLECTION_NAME))


if __name__ == "__main__":
    ingest()
