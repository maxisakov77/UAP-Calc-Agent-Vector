import json
import os
import uuid
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from openai import OpenAI

client: Optional[OpenAI] = None
index: Optional[faiss.IndexFlatIP] = None  # Inner-product (cosine on normalized vecs)
metadata: list[dict] = []  # parallel array: {id, filename, chunk_index, text}

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536  # text-embedding-3-small dimension
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200

_persist_dir: str = ""


def _meta_path() -> Path:
    return Path(_persist_dir) / "metadata.json"


def _index_path() -> Path:
    return Path(_persist_dir) / "faiss.index"


def _save():
    """Persist FAISS index and metadata to disk."""
    Path(_persist_dir).mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(_index_path()))
    with open(_meta_path(), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)


def init():
    global client, index, metadata, _persist_dir
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    _persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./vector_data")
    Path(_persist_dir).mkdir(parents=True, exist_ok=True)

    if _index_path().exists() and _meta_path().exists():
        index = faiss.read_index(str(_index_path()))
        with open(_meta_path(), "r", encoding="utf-8") as f:
            metadata = json.load(f)
    else:
        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        metadata = []


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def embed_texts(texts: list[str]) -> np.ndarray:
    """Get embeddings from OpenAI, returned as L2-normalized numpy array."""
    resp = client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
    vecs = np.array([d.embedding for d in resp.data], dtype=np.float32)
    faiss.normalize_L2(vecs)
    return vecs


def ingest_document(text: str, filename: str) -> int:
    """Chunk, embed, and store a document. Returns chunk count."""
    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)

    for i, chunk in enumerate(chunks):
        metadata.append({
            "id": str(uuid.uuid4()),
            "filename": filename,
            "chunk_index": i,
            "text": chunk,
        })

    index.add(embeddings)
    _save()
    return len(chunks)


def retrieve(query: str, n_results: int = 5) -> list[dict]:
    """Retrieve the most relevant chunks for a query."""
    if index.ntotal == 0:
        return []

    query_vec = embed_texts([query])
    k = min(n_results, index.ntotal)
    distances, indices = index.search(query_vec, k)

    hits: list[dict] = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        m = metadata[idx]
        hits.append({"text": m["text"], "filename": m["filename"], "distance": float(1 - dist)})
    return hits


def get_document_count() -> int:
    """Return total number of stored chunks."""
    return index.ntotal if index else 0


def list_documents() -> list[str]:
    """Return unique filenames in the store."""
    return sorted({m["filename"] for m in metadata})


def delete_document(filename: str) -> int:
    """Delete all chunks for a given filename. Returns deleted count.
    Rebuilds the FAISS index since flat indexes don't support removal."""
    global index, metadata

    keep = [m for m in metadata if m["filename"] != filename]
    deleted = len(metadata) - len(keep)
    if deleted == 0:
        return 0

    metadata = keep

    # Rebuild index from remaining metadata
    new_index = faiss.IndexFlatIP(EMBEDDING_DIM)
    if metadata:
        texts = [m["text"] for m in metadata]
        vecs = embed_texts(texts)
        new_index.add(vecs)
    index = new_index
    _save()
    return deleted
