"""
ClearPath Chatbot — FastAPI Application
"""

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
import json

from app.config import INDEX_DIR
from app.pdf_parser import parse_all_pdfs
from app.chunker import chunk_blocks
from app.embeddings import build_index, load_index, index_exists
from app.retriever import retrieve
from app.router import classify_query, maybe_upgrade_after_retrieval
from app.llm_client import generate, generate_stream
from app.prompts import build_prompt
from app.evaluator import evaluate
from app.conversation import (
    get_or_create_id, add_message, get_messages_for_llm,
    get_all_messages, list_conversations,
)

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s",
)
logger = logging.getLogger("clearpath")

# ── Global state (populated on startup) ───────────────────────────────
faiss_index = None
chunks_store: list[dict] = []


# ── Startup / Shutdown ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build or load the FAISS index on startup."""
    global faiss_index, chunks_store

    if index_exists():
        logger.info("Loading existing index from disk...")
        faiss_index, chunks_store = load_index()
    else:
        logger.info("No existing index found — building from PDFs...")
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        raw_blocks = parse_all_pdfs()
        if not raw_blocks:
            logger.error("No content extracted from PDFs!")
        else:
            chunks_store = chunk_blocks(raw_blocks)
            faiss_index = build_index(chunks_store)
            logger.info("Index ready: %d chunks indexed", len(chunks_store))

    yield  # App runs here

    logger.info("Shutting down ClearPath Chatbot.")


# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="ClearPath Chatbot API",
    description="RAG-powered customer support chatbot for ClearPath SaaS",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Models ──────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's query")
    conversation_id: Optional[str] = Field(
        None, description="Optional conversation ID for multi-turn"
    )


class TokenUsage(BaseModel):
    input: int
    output: int


class Metadata(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_used: str
    classification: str
    tokens: TokenUsage
    latency_ms: int
    chunks_retrieved: int
    evaluator_flags: list[str]


class Source(BaseModel):
    document: str
    page: int
    relevance_score: float


class QueryResponse(BaseModel):
    answer: str
    metadata: Metadata
    sources: list[Source]
    conversation_id: str


# ── Main Query Endpoint ──────────────────────────────────────────────
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """Main RAG query endpoint with multi-turn conversation support."""
    start_time = time.time()

    try:
        # 0. Conversation ID
        conv_id = get_or_create_id(request.conversation_id)

        # 1. Retrieve relevant chunks
        if faiss_index is None or not chunks_store:
            retrieved = []
        else:
            retrieved = retrieve(request.question, faiss_index, chunks_store)

        # 2. Initial routing classification
        route_result = classify_query(request.question)

        # 3. Post-retrieval upgrade check
        route_result = maybe_upgrade_after_retrieval(route_result, retrieved)

        # 4. Build the system prompt (context only, no history)
        system_prompt = build_prompt(retrieved)

        # 5. Get conversation history for multi-turn
        conversation_history = get_messages_for_llm(conv_id)

        # 6. Generate LLM response with multi-turn context
        llm_result = generate(
            model=route_result["model"],
            system_prompt=system_prompt,
            user_message=request.question,
            conversation_history=conversation_history,
        )

        # 7. Run evaluator
        evaluator_flags = evaluate(
            answer=llm_result["answer"],
            retrieved_chunks=retrieved,
            chunks_retrieved_count=len(retrieved),
        )

        # 8. Build sources list
        sources = []
        sources_dicts = []  # for storage
        seen = set()
        for item in retrieved:
            chunk = item["chunk"]
            doc = chunk["source_file"]
            page = chunk["page_number"]
            key = (doc, page)
            if key not in seen:
                seen.add(key)
                sources.append(Source(
                    document=doc,
                    page=page,
                    relevance_score=round(item["score"], 4),
                ))
                sources_dicts.append({
                    "document": doc,
                    "page": page,
                    "relevance_score": round(item["score"], 4),
                })

        latency_ms = int((time.time() - start_time) * 1000)

        metadata_dict = {
            "model_used": route_result["model"],
            "classification": route_result["classification"],
            "tokens": {
                "input": llm_result["input_tokens"],
                "output": llm_result["output_tokens"],
            },
            "latency_ms": latency_ms,
            "chunks_retrieved": len(retrieved),
            "evaluator_flags": evaluator_flags,
        }

        # 9. Update conversation memory (store with sources/metadata)
        add_message(conv_id, "user", request.question)
        add_message(
            conv_id, "assistant", llm_result["answer"],
            sources=sources_dicts,
            metadata=metadata_dict,
        )

        return QueryResponse(
            answer=llm_result["answer"],
            metadata=Metadata(**metadata_dict),
            sources=sources,
            conversation_id=conv_id,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )

# ── Streaming Endpoint ───────────────────────────────────────────────
@app.post("/query/stream")
async def query_stream_endpoint(request: QueryRequest):
    """
    SSE streaming endpoint — tokens arrive in real-time.

    Structured output parsing CANNOT work mid-stream because:
    1. Evaluator needs the FULL answer to compute grounding cosine similarity
    2. Token usage is only available in the final Groq stream chunk
    3. A complete JSON response can't be assembled until all tokens are collected

    Solution: stream raw tokens, then send structured metadata in a final event.
    """
    start_time = time.time()

    # Pre-stream work: retrieval, routing, prompt building
    conv_id = get_or_create_id(request.conversation_id)

    if faiss_index is None or not chunks_store:
        retrieved = []
    else:
        retrieved = retrieve(request.question, faiss_index, chunks_store)

    route_result = classify_query(request.question)
    route_result = maybe_upgrade_after_retrieval(route_result, retrieved)
    system_prompt = build_prompt(retrieved)
    conversation_history = get_messages_for_llm(conv_id)

    # Build sources list (available before streaming)
    sources_dicts = []
    seen = set()
    for item in retrieved:
        chunk = item["chunk"]
        doc = chunk["source_file"]
        page = chunk["page_number"]
        key = (doc, page)
        if key not in seen:
            seen.add(key)
            sources_dicts.append({
                "document": doc,
                "page": page,
                "relevance_score": round(item["score"], 4),
            })

    def sse_generator():
        full_answer = []
        input_tokens = 0
        output_tokens = 0

        # Stream tokens from LLM
        for event in generate_stream(
            model=route_result["model"],
            system_prompt=system_prompt,
            user_message=request.question,
            conversation_history=conversation_history,
        ):
            if event["type"] == "token":
                full_answer.append(event["content"])
                yield f"data: {json.dumps(event)}\n\n"

            elif event["type"] == "done":
                input_tokens = event["input_tokens"]
                output_tokens = event["output_tokens"]

            elif event["type"] == "error":
                yield f"data: {json.dumps(event)}\n\n"
                return

        # Post-stream: evaluator runs on the COMPLETE answer
        answer_text = "".join(full_answer)
        evaluator_flags = evaluate(
            answer=answer_text,
            retrieved_chunks=retrieved,
            chunks_retrieved_count=len(retrieved),
        )

        latency_ms = int((time.time() - start_time) * 1000)

        metadata_dict = {
            "model_used": route_result["model"],
            "classification": route_result["classification"],
            "tokens": {"input": input_tokens, "output": output_tokens},
            "latency_ms": latency_ms,
            "chunks_retrieved": len(retrieved),
            "evaluator_flags": evaluator_flags,
        }

        # Save to conversation memory
        add_message(conv_id, "user", request.question)
        add_message(
            conv_id, "assistant", answer_text,
            sources=sources_dicts,
            metadata=metadata_dict,
        )

        # Final structured event
        done_event = {
            "type": "done",
            "metadata": metadata_dict,
            "sources": sources_dicts,
            "conversation_id": conv_id,
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

# ── Conversation Endpoints ───────────────────────────────────────────
@app.get("/conversations")
async def get_conversations():
    """List all conversations with IDs and titles."""
    return list_conversations()


@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get all messages for a specific conversation."""
    messages = get_all_messages(conversation_id)
    if not messages and conversation_id not in [c["id"] for c in list_conversations()]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "messages": messages}


# ── Health Check ──────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "index_loaded": faiss_index is not None,
        "chunks_count": len(chunks_store),
    }
