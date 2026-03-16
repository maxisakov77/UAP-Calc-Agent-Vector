"""
NYC UAP / 485-x development strategy backend.
Uses Pinecone RAG + GPT multi-agent orchestration to evaluate zoning, site context, and developer-oriented scenarios.
"""

import os
import io
import json
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from pydantic import BaseModel

from engine.engine import context_engine
from engine.helpers import helper_sanitize_input, helper_moderate_content, get_embedding
from property_models import (
    BlockLotsResponse,
    PropertyContext,
    PropertyContextRequest,
    PropertySearchResponse,
    ValidatedLotInfo,
)
from property_service import property_service
from property_store import delete_property_context, fetch_property_context, upsert_property_context

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ── Configuration ───────────────────────────────────────────────────────

GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gpt-5.4")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "und1")
NAMESPACE_CONTEXT = os.getenv("NAMESPACE_CONTEXT", "ContextLibrary")
NAMESPACE_KNOWLEDGE = os.getenv("NAMESPACE_KNOWLEDGE", "KnowledgeStore")
NAMESPACE_PROPERTY = os.getenv("NAMESPACE_PROPERTY", "PropertyContextStore")
DEFAULT_CORS_ALLOW_ORIGINS = ("http://localhost:3000", "http://localhost:3001")


def _get_csv_env(name: str, default: tuple[str, ...]) -> list[str]:
    raw_value = os.getenv(name, "")
    if not raw_value.strip():
        return list(default)
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    return values or list(default)


CORS_ALLOW_ORIGINS = _get_csv_env("CORS_ALLOW_ORIGINS", DEFAULT_CORS_ALLOW_ORIGINS)

# ── Global clients (initialized on startup) ────────────────────────────

openai_client: OpenAI | None = None
pinecone_client: Pinecone | None = None
active_index_name: str = PINECONE_INDEX  # mutable — switched via API
_template_store: dict = {}  # stores uploaded underwriting template bytes

# Per-agent tunable settings
agent_settings: dict = {
    "librarian": {
        "top_k": 3,
        "description": "Retrieves semantic blueprints from the ContextLibrary to guide the Writer.",
    },
    "researcher": {
        "top_k": 60,
        "temperature": 0.1,
        "description": "Queries the KnowledgeStore and synthesizes facts with citations.",
    },
    "writer": {
        "temperature": 0.1,
        "description": "Combines research with the blueprint to generate the final response.",
    },
    "summarizer": {
        "temperature": 0.1,
        "max_length": 2000,
        "description": "Condenses large outputs to stay within token limits.",
    },
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global openai_client, pinecone_client, active_index_name

    openai_key = os.getenv("OPENAI_API_KEY", "")
    pinecone_key = os.getenv("PINECONE_API_KEY", "")

    if not openai_key:
        logging.error("OPENAI_API_KEY not set!")
    if not pinecone_key:
        logging.error("PINECONE_API_KEY not set!")

    openai_client = OpenAI(api_key=openai_key)
    pinecone_client = Pinecone(api_key=pinecone_key)

    # Verify Pinecone index exists; auto-switch if the configured one is gone
    try:
        idx = pinecone_client.Index(active_index_name)
        stats = idx.describe_index_stats()
        total_vectors = stats.get("total_vector_count", 0)
        logging.info(f"✅ Pinecone connected: index={active_index_name}, vectors={total_vectors}")
    except Exception as e:
        logging.warning(f"Configured index '{active_index_name}' not reachable: {e}")
        # Try to fall back to the first available index
        try:
            available = pinecone_client.list_indexes()
            if available:
                first = available[0].name
                active_index_name = first
                idx = pinecone_client.Index(active_index_name)
                stats = idx.describe_index_stats()
                total_vectors = stats.get("total_vector_count", 0)
                logging.info(f"✅ Auto-switched to index '{active_index_name}', vectors={total_vectors}")
            else:
                logging.warning("No Pinecone indexes available")
        except Exception as e2:
            logging.error(f"Failed to auto-switch index: {e2}")

    logging.info(f"✅ MAS Backend ready — model={GENERATION_MODEL}, embedding={EMBEDDING_MODEL}")
    yield


app = FastAPI(title="UAP 485-x NYC Development Expert API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    use_rag: bool = True


class ChatResponse(BaseModel):
    reply: str
    sources: list[dict]


def _get_index():
    return pinecone_client.Index(active_index_name)


def _get_active_property_context() -> PropertyContext | None:
    try:
        return fetch_property_context(_get_index(), NAMESPACE_PROPERTY)
    except Exception as exc:
        logging.warning(f"Failed to load active property context: {exc}")
        return None


# ── Agent Settings ──────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    """Return current agent settings."""
    return {"settings": agent_settings}


@app.put("/api/settings")
async def update_settings(req: dict):
    """Update agent settings. Accepts partial updates per agent."""
    ALLOWED_KEYS = {
        "librarian": {"top_k": (int, 1, 20)},
        "researcher": {"top_k": (int, 1, 100), "temperature": (float, 0.0, 2.0)},
        "writer": {"temperature": (float, 0.0, 2.0)},
        "summarizer": {"temperature": (float, 0.0, 2.0), "max_length": (int, 100, 10000)},
    }
    settings_input = req.get("settings", {})
    for agent_name, params in settings_input.items():
        if agent_name not in ALLOWED_KEYS:
            continue
        for key, value in params.items():
            if key not in ALLOWED_KEYS[agent_name]:
                continue
            expected_type, min_val, max_val = ALLOWED_KEYS[agent_name][key]
            try:
                casted = expected_type(value)
                casted = max(min_val, min(max_val, casted))
                agent_settings[agent_name][key] = casted
            except (ValueError, TypeError):
                continue
    logging.info(f"Agent settings updated: {agent_settings}")
    return {"settings": agent_settings}


# ── Pinecone Index Management ───────────────────────────────────────────

class CreateIndexRequest(BaseModel):
    name: str
    dimension: int = 3072
    metric: str = "cosine"
    cloud: str = "aws"
    region: str = "us-east-1"


class SwitchIndexRequest(BaseModel):
    name: str


@app.get("/api/indexes")
async def list_indexes():
    """List all Pinecone indexes in the account."""
    try:
        indexes = pinecone_client.list_indexes()
        result = []
        for idx_model in indexes:
            status = idx_model.status
            result.append({
                "name": idx_model.name,
                "dimension": idx_model.dimension,
                "metric": idx_model.metric,
                "host": idx_model.host,
                "ready": status["ready"] if status else False,
                "state": status["state"] if status else "Unknown",
            })
        return {"indexes": result, "active": active_index_name}
    except Exception as e:
        logging.error(f"Failed to list indexes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/indexes/active")
async def get_active_index():
    """Return the currently active Pinecone index with stats."""
    try:
        idx = pinecone_client.Index(active_index_name)
        stats = idx.describe_index_stats()
        ns = stats.get("namespaces", {})
        return {
            "name": active_index_name,
            "total_vectors": stats.get("total_vector_count", 0),
            "dimension": stats.get("dimension", 0),
            "namespaces": {
                k: {"vector_count": v.get("vector_count", 0)}
                for k, v in ns.items()
            },
        }
    except Exception as e:
        logging.error(f"Failed to get active index stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/indexes")
async def create_index(req: CreateIndexRequest):
    """Create a new Pinecone serverless index."""
    try:
        pinecone_client.create_index(
            name=req.name,
            dimension=req.dimension,
            metric=req.metric,
            spec=ServerlessSpec(cloud=req.cloud, region=req.region),
        )
        logging.info(f"Created Pinecone index: {req.name}")
        return {"created": req.name}
    except Exception as e:
        logging.error(f"Failed to create index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/indexes/{index_name}")
async def delete_index(index_name: str):
    """Delete a Pinecone index."""
    if index_name == active_index_name:
        raise HTTPException(status_code=400, detail="Cannot delete the currently active index. Switch to another first.")
    try:
        pinecone_client.delete_index(name=index_name)
        logging.info(f"Deleted Pinecone index: {index_name}")
        return {"deleted": index_name}
    except Exception as e:
        logging.error(f"Failed to delete index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/indexes/switch")
async def switch_index(req: SwitchIndexRequest):
    """Switch the active Pinecone index used for chat and uploads."""
    global active_index_name
    # Verify the index exists and is ready
    try:
        info = pinecone_client.describe_index(req.name)
        status = info.status
        if not status["ready"]:
            raise HTTPException(status_code=400, detail=f"Index '{req.name}' is not ready")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Index '{req.name}' not found: {e}")

    active_index_name = req.name
    logging.info(f"Switched active index to: {active_index_name}")
    return {"active": active_index_name}


# ── Live Property Context ───────────────────────────────────────────────

@app.get("/api/property/search-address", response_model=PropertySearchResponse)
async def search_property_address(q: str = Query("", description="NYC address or 10-digit BBL")):
    try:
        results = await property_service.search_address(q)
        return PropertySearchResponse(results=results, query=q)
    except Exception as exc:
        logging.error(f"Property address search failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Address search failed: {exc}")


@app.get("/api/property/validate-lot", response_model=ValidatedLotInfo)
async def validate_property_lot(bbl: str = Query(..., description="10-digit BBL")):
    try:
        result = await property_service.validate_lot(bbl)
        return ValidatedLotInfo(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logging.error(f"Property lot validation failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Lot validation failed: {exc}")


@app.get("/api/property/block-lots", response_model=BlockLotsResponse)
async def get_property_block_lots(
    borough: int = Query(..., ge=1, le=5, description="Borough code (1-5)"),
    block: int = Query(..., gt=0, description="Tax block"),
):
    try:
        result = await property_service.get_block_lots(borough, block)
        return BlockLotsResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logging.error(f"Property block lookup failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Block lot lookup failed: {exc}")


@app.put("/api/property/context", response_model=PropertyContext)
async def set_property_context(req: PropertyContextRequest):
    try:
        context = await property_service.build_property_context(req.primary_bbl, req.adjacent_bbls)
        embedding = get_embedding(context.property_brief, client=openai_client, embedding_model=EMBEDDING_MODEL)
        upsert_property_context(_get_index(), NAMESPACE_PROPERTY, embedding, context)
        logging.info(f"Stored active property context for index '{active_index_name}': {context.primary_bbl}")
        return context
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logging.error(f"Set property context failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Property context update failed: {exc}")


@app.get("/api/property/context", response_model=PropertyContext | None)
async def get_property_context():
    try:
        return _get_active_property_context()
    except Exception as exc:
        logging.error(f"Get property context failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Property context lookup failed: {exc}")


@app.delete("/api/property/context")
async def clear_property_context():
    try:
        delete_property_context(_get_index(), NAMESPACE_PROPERTY)
        logging.info(f"Cleared active property context for index '{active_index_name}'")
        return {"cleared": True}
    except Exception as exc:
        logging.error(f"Clear property context failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Property context clear failed: {exc}")


# ── Blueprint Management (ContextLibrary) ───────────────────────────────

class CreateBlueprintRequest(BaseModel):
    subject: str
    instructions: str


@app.get("/api/blueprints")
async def list_blueprints():
    """List all blueprints in the ContextLibrary namespace."""
    try:
        idx = pinecone_client.Index(active_index_name)
        stats = idx.describe_index_stats()
        dim = stats.get("dimension", 3072) or 3072
        # Fetch all vectors in ContextLibrary using a zero-vector query
        # (Pinecone doesn't have a "list" — we query with a dummy and high top_k)
        dummy_vec = [0.0] * int(dim)
        results = idx.query(
            vector=dummy_vec,
            top_k=100,
            namespace=NAMESPACE_CONTEXT,
            include_metadata=True,
        )
        blueprints = []
        for m in results.get("matches", []):
            meta = m.get("metadata", {})
            blueprints.append({
                "id": m["id"],
                "subject": meta.get("subject", "Unknown"),
                "instructions": meta.get("text", ""),
            })
        return {"blueprints": blueprints}
    except Exception as e:
        logging.error(f"Failed to list blueprints: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/blueprints")
async def create_blueprint(req: CreateBlueprintRequest):
    """Create a new blueprint in the ContextLibrary namespace."""
    if not req.subject.strip() or not req.instructions.strip():
        raise HTTPException(status_code=400, detail="Subject and instructions are required")

    try:
        idx = pinecone_client.Index(active_index_name)
        # Embed the subject so the Librarian can match it semantically
        embedding = get_embedding(req.subject.strip(), client=openai_client, embedding_model=EMBEDDING_MODEL)
        vec_id = f"blueprint__{req.subject.strip().lower().replace(' ', '_')}"
        idx.upsert(
            vectors=[{
                "id": vec_id,
                "values": embedding,
                "metadata": {
                    "text": req.instructions.strip(),
                    "subject": req.subject.strip(),
                    "source": "blueprint",
                },
            }],
            namespace=NAMESPACE_CONTEXT,
        )
        logging.info(f"Created blueprint: {req.subject}")
        return {"id": vec_id, "subject": req.subject.strip()}
    except Exception as e:
        logging.error(f"Failed to create blueprint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class GenerateBlueprintRequest(BaseModel):
    subject: str


@app.post("/api/blueprints/generate")
async def generate_blueprint(req: GenerateBlueprintRequest):
    """Use AI to generate blueprint instructions for a subject, then store it."""
    subject = req.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")

    try:
        # Generate instructions via GPT
        system_prompt = (
            "You are writing blueprint instructions for an AI Writer that is exclusively focused on "
            "NYC UAP / 485-x building development strategy. Given a subject domain, produce instructions "
            "for how the Writer should format, structure, and tone responses inside that NYC development context.\n\n"
            "Include: developer-first tone, response structure, terminology guidance, profitability framing, "
            "assumption handling, and how to cite source-grounded constraints.\n\n"
            "Be specific and practical. Output ONLY the instructions, no preamble."
        )
        response = openai_client.chat.completions.create(
            model=GENERATION_MODEL,
            temperature=0.4,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Generate blueprint instructions for the subject: {subject}"},
            ],
        )
        instructions = response.choices[0].message.content.strip()

        # Upsert into Pinecone ContextLibrary
        idx = pinecone_client.Index(active_index_name)
        embedding = get_embedding(subject, client=openai_client, embedding_model=EMBEDDING_MODEL)
        vec_id = f"blueprint__{subject.lower().replace(' ', '_')}"
        idx.upsert(
            vectors=[{
                "id": vec_id,
                "values": embedding,
                "metadata": {
                    "text": instructions,
                    "subject": subject,
                    "source": "blueprint",
                },
            }],
            namespace=NAMESPACE_CONTEXT,
        )
        logging.info(f"AI-generated blueprint for '{subject}'")
        return {"id": vec_id, "subject": subject, "instructions": instructions}
    except Exception as e:
        logging.error(f"Failed to generate blueprint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/blueprints/{blueprint_id:path}")
async def delete_blueprint(blueprint_id: str):
    """Delete a blueprint from the ContextLibrary namespace."""
    try:
        idx = pinecone_client.Index(active_index_name)
        idx.delete(ids=[blueprint_id], namespace=NAMESPACE_CONTEXT)
        logging.info(f"Deleted blueprint: {blueprint_id}")
        return {"deleted": blueprint_id}
    except Exception as e:
        logging.error(f"Failed to delete blueprint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Routes ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    try:
        idx = pinecone_client.Index(active_index_name)
        stats = idx.describe_index_stats()
        total = stats.get("total_vector_count", 0)
    except Exception:
        total = 0
    return {"status": "ok", "documents": total, "active_index": active_index_name}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Extract the last user message as the goal
    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user":
            last_user_msg = m.content
            break

    if not last_user_msg:
        raise HTTPException(status_code=400, detail="No user message found")

    # Sanitize and moderate input
    try:
        sanitized = helper_sanitize_input(last_user_msg)
        helper_moderate_content(sanitized, openai_client)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    property_context = _get_active_property_context()

    # Run the Multi-Agent System pipeline
    try:
        result, trace = context_engine(
            goal=sanitized,
            client=openai_client,
            pc=pinecone_client,
            index_name=active_index_name,
            generation_model=GENERATION_MODEL,
            embedding_model=EMBEDDING_MODEL,
            namespace_context=NAMESPACE_CONTEXT,
            namespace_knowledge=NAMESPACE_KNOWLEDGE,
            agent_settings=agent_settings,
            property_context=property_context.model_dump() if property_context else None,
        )
    except Exception as e:
        logging.error(f"Context engine error: {e}")
        raise HTTPException(status_code=500, detail="Engine processing failed")

    if result is None:
        return ChatResponse(
            reply=f"I wasn't able to find a complete answer. Trace: {trace.status}",
            sources=[],
        )

    # Extract final text and sources from the MAS output
    if isinstance(result, str):
        reply_text = result
        sources = []
    elif isinstance(result, dict):
        reply_text = result.get("answer_with_sources", result.get("summary", str(result)))
        sources = result.get("sources", [])
    else:
        reply_text = str(result)
        sources = []

    # Format sources for the frontend contract
    formatted_sources = []
    for s in sources[:10]:
        if isinstance(s, dict):
            formatted_sources.append({
                "filename": s.get("source", "Pinecone"),
                "distance": round(1 - s.get("score", 0), 4),
            })

    return ChatResponse(reply=reply_text, sources=formatted_sources)


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload any document and upsert its chunks into Pinecone KnowledgeStore."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    ext = os.path.splitext(file.filename)[1].lower()

    # Extract text based on file type
    text = _extract_text(content, ext, file.filename)

    if len(text.strip()) == 0:
        raise HTTPException(status_code=400, detail="File is empty or could not be parsed")

    # Chunk the text
    chunks = _chunk_text(text, chunk_size=800, overlap=200)
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks generated")

    # Upsert into Pinecone
    idx = pinecone_client.Index(active_index_name)
    vectors = []
    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk, client=openai_client, embedding_model=EMBEDDING_MODEL)
        vec_id = f"{file.filename}__chunk_{i}"
        vectors.append({
            "id": vec_id,
            "values": embedding,
            "metadata": {"text": chunk, "source": file.filename, "chunk_index": i},
        })

    # Upsert in batches of 100
    for batch_start in range(0, len(vectors), 100):
        batch = vectors[batch_start:batch_start + 100]
        idx.upsert(vectors=batch, namespace=NAMESPACE_KNOWLEDGE)

    logging.info(f"Uploaded {len(chunks)} chunks for '{file.filename}' to Pinecone.")
    return {"filename": file.filename, "chunks": len(chunks)}


@app.get("/api/documents")
async def list_documents():
    """List uploaded documents (by filename) from the active index's KnowledgeStore."""
    try:
        idx = pinecone_client.Index(active_index_name)
        filenames: dict[str, int] = {}  # filename → chunk count

        for page in idx.list(namespace=NAMESPACE_KNOWLEDGE):
            for item in page:
                vid = item if isinstance(item, str) else getattr(item, "id", str(item))
                if "__chunk_" in vid:
                    fname = vid.rsplit("__chunk_", 1)[0]
                    filenames[fname] = filenames.get(fname, 0) + 1

        docs = [{"filename": f, "chunks": c} for f, c in sorted(filenames.items())]
        total = sum(filenames.values())
        return {"documents": docs, "total_chunks": total}
    except Exception as e:
        logging.error(f"List documents failed: {e}")
        return {"documents": [], "total_chunks": 0}


@app.delete("/api/documents/{filename:path}")
async def delete_document(filename: str):
    """Delete all vectors for a given source filename from Pinecone."""
    try:
        idx = pinecone_client.Index(active_index_name)
        # Delete by metadata filter
        idx.delete(
            filter={"source": {"$eq": filename}},
            namespace=NAMESPACE_KNOWLEDGE,
        )
        logging.info(f"Deleted vectors for '{filename}' from Pinecone.")
        return {"deleted_chunks": 1}  # Pinecone doesn't return count
    except Exception as e:
        logging.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")


def _extract_text(content: bytes, ext: str, filename: str) -> str:
    """Extract plain text from any supported file type."""
    # PDF
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except Exception as e:
            logging.error(f"PDF parse failed for {filename}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")

    # DOCX
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(io.BytesIO(content))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            logging.error(f"DOCX parse failed for {filename}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to parse DOCX: {e}")

    # XLSX / XLS — extract as CSV-like text
    if ext in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            lines = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                lines.append(f"=== Sheet: {sheet} ===")
                for row in ws.iter_rows(values_only=True):
                    lines.append("\t".join(str(c) if c is not None else "" for c in row))
            return "\n".join(lines)
        except Exception as e:
            logging.error(f"Excel parse failed for {filename}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to parse Excel: {e}")

    # Everything else — treat as UTF-8 text
    return content.decode("utf-8", errors="replace")


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]


# ── Underwriting Template ───────────────────────────────────────────────

def _safe_cell_value(val):
    """Convert cell value to a JSON-serializable type."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, float):
        if val != val:  # NaN
            return None
        return round(val, 2)
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        return val
    return str(val)


def _col_letter(col: int) -> str:
    """Convert 1-based column number to Excel column letter(s)."""
    result = ""
    while col > 0:
        col -= 1
        result = chr(65 + col % 26) + result
        col //= 26
    return result


@app.post("/api/underwriting/parse-template")
async def parse_underwriting_template(file: UploadFile = File(...)):
    """Upload an Excel underwriting template and return its parsed structure."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx / .xls) are supported")

    import openpyxl

    wb_vals = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    wb_fmls = openpyxl.load_workbook(io.BytesIO(content), data_only=False)

    sheets = []
    for name in wb_vals.sheetnames:
        ws_v = wb_vals[name]
        ws_f = wb_fmls[name]
        max_r = ws_v.max_row or 0
        max_c = ws_v.max_column or 0

        data = []
        for r in range(1, max_r + 1):
            row = []
            for c in range(1, max_c + 1):
                val = _safe_cell_value(ws_v.cell(r, c).value)
                fml = ws_f.cell(r, c).value
                is_formula = isinstance(fml, str) and fml.startswith("=")
                if val is None and not is_formula:
                    row.append(None)
                else:
                    cell = {"v": val if val is not None else 0, "r": r, "c": c}
                    if is_formula:
                        cell["f"] = True
                    row.append(cell)
            data.append(row)

        sheets.append({"name": name, "data": data, "maxRow": max_r, "maxCol": max_c})

    _template_store["current"] = {"filename": file.filename, "bytes": content}
    logging.info(f"Parsed underwriting template: {file.filename} ({len(sheets)} sheets)")
    return {"filename": file.filename, "sheets": sheets}


@app.post("/api/underwriting/extract")
async def extract_underwriting_values():
    """Use RAG to extract values from uploaded source documents for each template sheet."""
    if "current" not in _template_store:
        raise HTTPException(status_code=400, detail="No template uploaded yet")

    import openpyxl

    # Check if there are documents to extract from
    idx = _get_index()
    stats = idx.describe_index_stats()
    ns = stats.get("namespaces", {})
    knowledge_count = ns.get(NAMESPACE_KNOWLEDGE, {}).get("vector_count", 0)
    if knowledge_count == 0:
        return {"updates": {}, "message": "No documents uploaded. Upload source documents first."}

    wb = openpyxl.load_workbook(io.BytesIO(_template_store["current"]["bytes"]), data_only=True)
    wb_f = openpyxl.load_workbook(io.BytesIO(_template_store["current"]["bytes"]), data_only=False)

    all_updates: dict[str, dict] = {}

    for name in wb.sheetnames:
        # Skip auto-calculated sheets
        if "(auto)" in name.lower():
            continue

        ws = wb[name]
        ws_f_s = wb_f[name]
        max_r = ws.max_row or 0
        max_c = ws.max_column or 0

        labels: list[str] = []
        cell_descriptions: list[str] = []

        for r in range(1, max_r + 1):
            for c in range(1, max_c + 1):
                val = ws.cell(r, c).value
                fml = ws_f_s.cell(r, c).value
                if isinstance(fml, str) and fml.startswith("="):
                    continue
                if val is None:
                    continue
                coord = f"{_col_letter(c)}{r}"
                safe = _safe_cell_value(val)
                cell_descriptions.append(f"{coord}={safe}")
                if isinstance(val, str) and not val.replace(".", "").replace("-", "").replace(",", "").replace(" ", "").isdigit():
                    labels.append(val)

        if not cell_descriptions:
            continue

        # Query Pinecone with sheet labels as context
        query_text = f"UAP underwriting {name}: " + " ".join(labels[:40])
        query_embedding = get_embedding(query_text, client=openai_client, embedding_model=EMBEDDING_MODEL)

        results = idx.query(
            vector=query_embedding,
            top_k=30,
            namespace=NAMESPACE_KNOWLEDGE,
            include_metadata=True,
        )

        chunks = [
            m.get("metadata", {}).get("text", "")
            for m in results.get("matches", [])
            if m.get("metadata", {}).get("text")
        ]
        if not chunks:
            continue

        context_text = "\n---\n".join(chunks[:20])
        cells_desc = "\n".join(cell_descriptions[:300])

        prompt = (
            f'You are filling a UAP underwriting Excel spreadsheet from source documents.\n\n'
            f'Sheet: "{name}"\n'
            f'Current cell values (CellRef=CurrentValue):\n{cells_desc}\n\n'
            f'Source document excerpts:\n{context_text}\n\n'
            f'Extract updated values from the source documents above. '
            f'Return ONLY a JSON object mapping cell references (like "B5") to new values. '
            f'Only include cells where the documents provide a clear, specific value. '
            f'Use numbers for numeric fields. Omit cells with no clear value in the documents.'
        )

        try:
            response = openai_client.chat.completions.create(
                model=GENERATION_MODEL,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": "You extract structured data from documents into spreadsheet cells. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            result_text = response.choices[0].message.content.strip()
            updates = json.loads(result_text)
            if isinstance(updates, dict) and updates:
                all_updates[name] = {k: v for k, v in updates.items() if isinstance(k, str)}
        except Exception as e:
            logging.warning(f"RAG extraction failed for sheet '{name}': {e}")

    total_cells = sum(len(v) for v in all_updates.values())
    logging.info(f"RAG extraction complete: {total_cells} cells across {len(all_updates)} sheets")
    return {"updates": all_updates}


@app.post("/api/underwriting/download")
async def download_filled_template(req: dict):
    """Apply cell updates to the stored template and return the filled .xlsx file."""
    if "current" not in _template_store:
        raise HTTPException(status_code=400, detail="No template uploaded")

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(_template_store["current"]["bytes"]))

    updates = req.get("updates", {})
    for sheet_name, cells in updates.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        for ref, value in cells.items():
            try:
                ws[ref] = value
            except Exception:
                continue

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    base = os.path.splitext(_template_store["current"]["filename"])[0]
    filename = f"{base}_filled.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        port=int(os.getenv("BACKEND_PORT", "8000")),
        reload=True,
    )
