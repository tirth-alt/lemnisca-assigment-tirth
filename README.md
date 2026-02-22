# 🚀 ClearPath AI Assistant: Professional RAG Implementation

[![Live Demo](https://img.shields.io/badge/Live-Demo-brightgreen?style=for-the-badge)](https://clearpath-assistant-590138312966.us-central1.run.app)
[![Tech Stack](https://img.shields.io/badge/Stack-FastAPI_|_React_|_Groq_|_FAISS-blue?style=for-the-badge)](#tech-stack)

A robust, enterprise-grade RAG (Retrieval-Augmented Generation) chatbot designed for **ClearPath**, a project management SaaS. This system provides instant, faithful answers based on 30+ internal product documents, technical guides, and business protocols.

---

## 🌟 Key Features

### 1. **High-Performance Streaming UI**
- **Token-by-Token Streaming**: Leveraging SSE (Server-Sent Events) for real-time response generation.
- **Queue-Buffered Typewriter Effect**: Implemented a token drainage system to ensure a smooth, fluid reading experience without "jitter" from uneven network packets.
- **Premium Aesthetics**: Glassmorphism UI, responsive sidebar, and interactive markdown rendering.

### 2. **Deterministic Query Routing (Cost & Latency Optimized)**
Instead of using an expensive LLM call to classify queries, I implemented an **Additive Signal Classifier**:
- **Scoring Engine**: Analyzes word count, linguistic complexity (sub-clauses, negations), and specific intent keywords (comparison, explanation).
- **Dynamic Model Selection**: 
  - `score < 3`: Routed to **Llama 3.1 8B** (Instant, cost-efficient).
  - `score >= 3`: Routed to **Llama 3.3 70B** (Complex reasoning, multi-step logic).
- **Post-Retrieval Upgrade**: Automatically upgrades "simple" queries to the 70B model if retrieval spans multiple conflicting documents.

### 3. **Faithfulness & Grounding Evaluator**
To prevent hallucinations (the key challenge in RAG), every response undergoes an automated audit:
- **Grounding Score**: Calculates cosine similarity between the generated answer and the source context.
- **Refusal Detection**: Automatically flags responses where the LLM admits it doesn't know the answer.
- **Faithfulness Flags**: Alerts the user (or system admin) if the response has low semantic grounding in the provided documents.

### 4. **Professional RAG Pipeline**
- **Hierarchical Chunking**: Respects document structure and maintains context with sentence-level overlap.
- **Vector Search**: FAISS index with L2-normalized inner product for exact cosine similarity matching.
- **Context Re-ranking**: Prioritizes source documents based on dense vector relevance scores.

---

## 🏗 Architecture

```mermaid
graph TD
    User([User Query]) --> Router{Deterministic Router}
    Router -- Simple --> L1[Llama 3.1 8B]
    Router -- Complex --> L2[Llama 3.3 70B]
    User --> Retriever[FAISS Retriever]
    Retriever --> Context[(30+ PDF Source Docs)]
    Context --> L1
    Context --> L2
    L1 --> Evaluator[Output Evaluator]
    L2 --> Evaluator
    Evaluator --> UI([Streaming SSE Response])
```

---

## 🛠 Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend** | React 19, Vite, Tailwind-like CSS | Modern, fast, and highly responsive. |
| **Backend** | FastAPI (Python 3.10) | Asynchronous performance and native support for SSE. |
| **LLM Inference** | Groq Cloud | Hardware-accelerated inference for sub-second latency. |
| **Vector DB** | FAISS | Industry-standard for fast local vector search. |
| **Embeddings** | Sentence-Transformers | `multi-qa-MiniLM-L6-cos-v1` optimized for Q&A tasks. |
| **Deployment** | Google Cloud Run | Serverless, scalable monolith containerization. |

---

## 🚀 Rapid Deployment

### 1. Local Environment
```bash
# Clone and enter
git clone <repo-url>
cd lemnisca_takeHomeAssignment

# Backend Setup
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
touch .env # Add GROQ_API_KEY=your_key

# Run
uvicorn app.main:app --port 8080
```

### 2. Docker & GCP Cloud Run
The project is containerized as a **monolith** for simple deployment.
```bash
# Build & Push
gcloud builds submit --tag us-central1-docker.pkg.dev/[PROJECT]/monolith-repo/clearpath-monolith

# Deploy
gcloud run deploy clearpath-assistant --image us-central1-docker.pkg.dev/[PROJECT]/monolith-repo/clearpath-monolith --memory 2Gi
```

---

## 📊 Technical Notes & Trade-offs

- **Why Monolith?**: For this assignment, a unified Docker image (Backend + Static Frontend) prevents CORS issues and reduces deployment overhead on Cloud Run.
- **Cold Boot Optimization**: Embedding models are **pre-downloaded** during the Docker build phase to prevent runtime latency and Hugging Face rate-limiting.
- **Token Tracking**: Full billing/usage transparency is returned in the `done` event of the stream, including model latency and token breakdown.

---

**Developed by Tirth**  
*Submitted as the technical assignment for the AI Engineering Internship.*