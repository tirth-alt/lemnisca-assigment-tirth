# ClearPath RAG Chatbot

A full-stack RAG-powered customer support chatbot for **ClearPath** — a project management SaaS platform.

## Architecture

```
User Query → Deterministic Router → Retriever (FAISS) → LLM (Groq) → Evaluator → Response
```

| Component | Tech |
|---|---|
| Backend | Python 3.11, FastAPI |
| PDF Parsing | pdfplumber |
| Embeddings | multi-qa-MiniLM-L6-cos-v1 (384-dim) |
| Vector Store | FAISS (local) |
| LLM | Groq — llama-3.1-8b-instant / llama-3.3-70b-versatile |
| Frontend | React, Vite, react-markdown |

## Quick Start

### 1. Backend

```bash
cd backend

# Create .env with your Groq API key
echo "GROQ_API_KEY=your_key_here" > .env

# Create venv and install deps
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start the server (first run will index all PDFs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ | — | Your Groq API key |
| `PORT` | ❌ | 8000 | Backend port |

## API Endpoint

### POST `/query`

**Request:**
```json
{
  "question": "What is the price of the Pro plan?",
  "conversation_id": "optional-id"
}
```

**Response:**
```json
{
  "answer": "...",
  "metadata": {
    "model_used": "llama-3.3-70b-versatile",
    "classification": "complex",
    "tokens": { "input": 1234, "output": 156 },
    "latency_ms": 847,
    "chunks_retrieved": 5,
    "evaluator_flags": []
  },
  "sources": [
    { "document": "14_Pricing_Sheet_2024.pdf", "page": 1, "relevance_score": 0.92 }
  ],
  "conversation_id": "conv_abc123"
}
```

## Router Logic

Deterministic, additive-signal scoring (no LLM calls):

| Signal | Points |
|---|---|
| Word count ≥ 15 | +2 |
| Complex keywords (compare, explain, why, how does…) | +2 |
| Multiple question marks | +1 |
| Comparison words (vs, better, or…) | +1 |
| Negation in question | +1 |
| Sub-clause indicators (;, however, but…) | +1 |
| Multiple entities (and, both, all…) | +1 |

**Threshold:** score ≥ 3 → **complex** → `llama-3.3-70b-versatile`  
**Post-retrieval override:** simple + chunks from ≥ 3 docs → upgraded to complex

## Evaluator Flags

| Flag | Trigger |
|---|---|
| `no_context` | LLM answered but 0 chunks retrieved |
| `refusal` | LLM explicitly refused/said "I don't know" |
| `low_grounding` | Cosine similarity between response and context < 0.35 (hallucination) |

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + /query endpoint
│   │   ├── config.py        # Central configuration
│   │   ├── pdf_parser.py    # PDF text extraction
│   │   ├── chunker.py       # Hierarchical chunking
│   │   ├── embeddings.py    # Sentence-transformer + FAISS
│   │   ├── retriever.py     # Top-K vector search
│   │   ├── router.py        # Deterministic query classifier
│   │   ├── llm_client.py    # Groq API wrapper
│   │   ├── prompts.py       # System prompt template
│   │   ├── evaluator.py     # Output quality checks
│   │   └── conversation.py  # Multi-turn memory
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Chat UI
│   │   ├── index.css        # Premium dark theme
│   │   └── main.jsx         # Entry point
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
└── clearpath_docs/           # 30 PDF documents
```