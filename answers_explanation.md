# Understanding Your Written Answers — Personal Explainer

This document breaks down each answer so you can confidently explain it during an interview or presentation.

---

## Q1 — Routing Logic (What You Should Know)

### How the router actually works (in plain English)

Think of it like a checklist. Every time a user asks something, the system runs through 7 checks. Each check adds points. If the total reaches 3 or more, the query is "complex" and goes to the big model (70B). Otherwise it uses the small, fast model (8B).

**The key insight**: A single signal is never enough. The word "why" alone gives +2, but you need at least one more signal (length, comparison, etc.) to hit the threshold of 3. This prevents short simple questions like "Why?" from being wastefully sent to the expensive model.

### The misclassification you describe

You describe "What is the pricing?" scoring 0 → simple. This is realistic because:
- It's only 4 words (needs 15 for length signal)
- No complex keywords like "compare" or "explain"
- No comparison words, no negation, no sub-clauses

But the *answer* needs to synthesize multiple pricing tiers. The 8B model gave a partial answer. This shows the gap between **query complexity** and **answer complexity** — your router only sees the former.

### The improvement you suggest

Topic-awareness: some topics are inherently complex regardless of how the question is phrased. You'd build a small dictionary mapping keywords to bonus points:
```
"pricing" → +2
"integration" → +1  
"migration" → +2
```
This is a pure rules-based fix — no LLM needed.

---

## Q2 — Retrieval Failures (What You Should Know)

### The core problem: vocabulary mismatch

Your embeddings model understands *meaning*, but it can be tricked when two chunks are semantically similar but serve different purposes:

1. **Security policy** chunk: "ClearPath supports SAML 2.0 SSO for Enterprise plans" — this *mentions* SSO
2. **Admin guide** chunk: "Step 1: Navigate to Settings > Identity Providers" — this *explains* SSO setup

The user asked "How do I configure SSO?" — semantically closer to the mention (both use "SSO" in a descriptive way) than the guide (which uses procedural/instructional language).

### Why hybrid retrieval fixes it

- **Dense search (FAISS)**: Good at understanding meaning, bad at exact keyword matching
- **Sparse search (BM25)**: Good at exact keyword matching ("configure" + "SSO"), bad at understanding meaning

Combining both with Reciprocal Rank Fusion gives you the best of both worlds. This is a standard technique in modern RAG systems.

---

## Q3 — Cost and Scale (What You Should Know)

### The math breakdown

You assumed 70/30 split (simple/complex). Here's the logic:

```
Simple queries:  3,500/day × 1,650 tokens/query = 5,775,000 tokens
Complex queries: 1,500/day × 2,850 tokens/query = 4,275,000 tokens
Total: ~10,050,000 tokens/day
```

For each query, tokens come from:
- **System prompt** (~200 tokens) — fixed cost
- **Retrieved chunks** (~800 tokens for 5 chunks) — the biggest chunk
- **Conversation history** (~500 tokens for 5 turns) — grows over conversation
- **Output** (150-350 tokens) — what the LLM generates

### Why caching is the best ROI

Support chatbots get the same questions repeatedly. "What are the pricing plans?" might be asked 200 times/day. With semantic caching:
- Compute the query embedding (cheap, local)
- Check if a similar query was answered in the last hour (cosine similarity > 0.95)
- If yes, return the cached response — **zero LLM tokens**

If 35% of queries are near-duplicates → saves ~3.5M tokens/day.

### Why reducing chunks is dangerous

You might think "use 2 chunks instead of 5 to save tokens." But:
- Complex questions need information from multiple sections
- Your evaluator's grounding score would drop
- The system would hallucinate more

The token savings (~600/query) aren't worth the quality loss.

---

## Q4 — What Is Broken (What You Should Know)

### The flaw: embedding similarity ≠ factual accuracy

Your evaluator checks if the answer's embedding is similar to the context's embedding. This catches gross errors (e.g., answering a pricing question with information about keyboard shortcuts). But it misses **subtle factual errors**:

**Example**:
- Context says: "Pro plan includes **50GB** storage"
- LLM says: "The Pro plan includes **100GB** storage"
- Embedding similarity: **HIGH** (both discuss Pro plan storage)
- `low_grounding` flag: **NOT triggered**
- User gets a hallucinated number with no warning

### Why this is the *right* flaw to mention

The interviewer wants to see that you understand real-world failure modes of RAG systems. This is THE canonical RAG failure — subtle hallucinations that pass quality checks. It shows:
1. You understand the limitation of vector similarity as a quality metric
2. You made a pragmatic engineering tradeoff (speed vs. accuracy)
3. You know the actual fix (NLI-based claim verification)

### The NLI fix explained simply

Natural Language Inference models classify pairs of sentences as:
- **Entailment**: sentence B follows from sentence A ✅
- **Contradiction**: sentence B contradicts sentence A ❌
- **Neutral**: can't determine the relationship 🟡

You'd run each claim in the answer against the source text. Any "contradiction" gets flagged. The model (`cross-encoder/nli-deberta-v3-small`) runs locally, no API cost, ~200ms extra latency.

---

## Interview Tips

If asked follow-up questions:

- **"Why not use an LLM to classify queries?"** → "It would add 200-500ms latency and cost tokens on every request. The deterministic router runs in <1ms and is predictable/debuggable."
- **"How would you test the router?"** → "I'd build a labeled dataset of 100+ queries (manually tagged simple/complex) and measure precision/recall. Adjust the threshold and signals based on false positive/negative rates."
- **"Why FAISS instead of a cloud vector DB?"** → "For 632 chunks and a single-instance deployment, FAISS in-memory is simpler, faster, and free. I'd switch to Pinecone/Weaviate if the corpus grew past ~50K chunks."
- **"What about prompt injection?"** → "Rule 6 in the system prompt explicitly tells the model to treat document content as data, not instructions. But this is a prompt-level defense, not a technical one — a more robust approach would sanitize retrieved chunks before injection."
