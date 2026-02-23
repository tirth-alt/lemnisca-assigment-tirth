# Written Answers

## Q1 — Routing Logic

My router uses additive signal scoring with 7 rules. Each signal adds points, and a total score ≥ 3 triggers the "complex" classification:

1. **Long query**: **+2**
   - **Condition:** Word count ≥ 15  

2. **Complex keywords**: **+2**
   - **Condition:** Contains keywords like `compare`, `explain`, `why`, `how does`, `analyze`, `pros and cons`, `trade-off`, etc.  

3. **Multiple question marks**: **+1**
   - **Condition:** `?` count ≥ 2  

4. **Comparison words**: **+1**
   - **Condition:** Contains `vs`, `better`, `worse`, `or`, `compared to`, `differ`  

5. **Negation in question**: **+1**
   - **Condition:** Contains a `?` AND negation words like `not`, `don't`, `can't`, `won't`, etc.  

6. **Sub-clause indicators**: **+1**
   - **Condition:** Contains `;`, `—`, `however`, `but`, `although`, `whereas`, etc.  

7. **Multi-entity**: **+1**
   - **Condition:** Contains `and`, `both`, `all`, `each` AND word count ≥ 8  

**Post-retrieval**: If a query is initially classified as "simple" but the retrieved chunks come from ≥ 3 distinct source documents, it is automatically upgraded to "complex" since answering across multiple documents requires synthesis.

The threshold of 3 was chosen as we wanted at least two meaningful signals before escalating to the expensive model. A single signal might be misleading in some cases. This also prevents short reasoning queries from being routed instant model while being multi layered question.

### A real misclassification

**Query**: *"What is the pricing?"*
**Router score**: 0 (no signals triggered) → classified as **simple**.

This was correct for the query's surface form, but the *answer* required synthesizing information from multiple pricing tiers, discount policies, and enterprise plans across several pages of the Pricing Sheet PDF. The 8B model gave a partial answer covering only the first tier it found. The 70B model, when manually tested, gave a comprehensive breakdown of all plans. The post-retrieval upgrade did trigger in some cases (when chunks came from 3+ docs), but since pricing is concentrated in one document, it didn't fire here.

One improvment that can be done here is to add **topic-awareness scoring**. Certain topics (pricing, integrations, architecture) automaticly is classified as complex. 
Anorther is to analyze retrieval *spread* — if the top-5 chunks cover very different sections within the same document (measured by page distance), that can be a signal for complexity.

---

## Q2 — Retrieval Failures

### Query
**What are the pricing plans for ClearPath?**

### Observation
I passed this query multiple times. For the most of it retrived correct information, and genrated correct answer and didn't genrate any flag saying "not covered in document".
But in some cases it retrived similar information as the correct answer but triggered the flag saying "This question may not be covered in our document".

This failure might have been caused due to embedding similarity ambiguity and chunking, where pricing information was either inside larger chunks or ranked below other semantically similar sections.
To fix this issue, I would improve structure-aware chunking to keep pricing tables intact, increase top-K retrieval to reduce instability. Additionally, refining the coverage detection logic to require stronger evidence before flagging would reduce false negatives.
---

## Q3 — Cost and Scale

### Daily token estimate (5,000 queries/day)
Assumptions
- 70% Simple (3,500 queries)
- 30% Complex (1,500 queries)

Input tokens (context + prompt + history) 
- Simple: ~1,500 -> Output tokens: ~150
- Complex: ~2,500 -> Output tokens: ~350

Breakdown per model:
Simple
- Input: 3,500 × 1,500 = 5,250,000  
- Output: 3,500 × 150 = 525,000  
- **Total: 5,775,000 tokens/day**
Complex
- Input: 1,500 × 2,500 = 3,750,000  
- Output: 1,500 × 350 = 525,000  
- **Total: 4,275,000 tokens/day**

- **Total**:≈ 10,050,000 tokens/day (~10M tokens)

The largest cost driver is **input tokens (~9M/day)**.
- Context + retrieval chunks dominate usage.
- Output tokens are only ~10% of total.

**Highest-ROI Cost Reduction**
Reduce Retrieved Context Size
If we reduce average input tokens:
- Simple: 1,500 → 1,000  
- Complex: 2,500 → 1,800  

Savings
- New input: 6,200,000  
- **Savings: 2,800,000 tokens/day (~31% reduction in input tokens)**  
- Overall daily savings ≈ **~28% total tokens**

Instead of sending 3–5 large chunks (~2,500 tokens), switch to 2 smaller, more targeted chunks or apply reranking before final context assembly.

**Optimisations I Would Avoid**
1. Downgrading to simple model for all queries
2. Aggressively Reducing System Prompt or Conversation History
- System prompt defines tone, guardrails, and structure.
- History preserves conversational coherence.
We can refine prompts to be more concise, but not aggressively shrink them.

**Other ROI Idea:** 
**History Summarisation**
Instead of passing 2–3 full previous turns:
- Use a small LLM to generate a short summary ("conversation gist").
- Pass only the summary to the main model.
Potentially reduce ~500 tokens per turn i.e ~2.5M tokens saved daily.

Problem:
- Extra LLM call for summary generation.
- Additional latency for summary generation.

## Q4 — What Is Broken

### The most significant flaw

**The system has no grounding verification against the actual source text** — it only checks *embedding similarity*, which is a weak proxy. The evaluator computes cosine similarity between the LLM's answer embedding and the context embedding, with a threshold of 0.35. But this is not a strong enough check to catch subtle but breaking hallucinations.

For example, if a user asks "What is the storage limit on the Pro plan?" and the context says "Pro plan includes 50GB storage", the LLM could respond "The Pro plan includes 100GB storage." The embeddings of both the correct and incorrect answers would be very similar to the context (both discuss Pro plan storage), so the grounding check would pass. There won't be any flag.

Reason for not implementing a proper fact-verification system (extractive validation, or a second LLM call to verify claims against source text) is that it would add large latency and cost. The embedding-based grounding check was to catche *large* hallucinations (completely off-topic answers) at zero additional LLM cost, while accepting that *subtle* numerical or factual hallucinations slip through. Given the scope of the assignment, implementing a full claim-extraction pipeline felt like over-engineering.

Future Scope:
I would implement **extractive claim verification**: after generation, use a lightweight NLI (Natural Language Inference) model like `cross-encoder/nli-deberta-v3-small` to check if each factual statement in the answer is *entailed* by the source chunks. Any claim that scores as "contradiction" or "neutral" would be flagged as potentially hallucinated. This runs locally and catches the exact class of subtle factual errors that the current system misses.
