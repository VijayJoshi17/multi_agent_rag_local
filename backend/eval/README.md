# Evaluation

Two harnesses measure the system on a fixed, versioned dataset, so changes to retrieval, prompts or
models can be compared with numbers instead of impressions.

| | `eval.retrieval` | `eval.answers` |
|---|---|---|
| What it measures | Retrieval only (each stage ablated) | The full agent graph, end to end |
| Needs an LLM | No | Yes (any OpenAI-compatible endpoint) |
| Runtime | ~1 min on CPU | ~2–3 LLM calls per question |
| In CI | Yes, as a quality gate (`--check`) | No (costs money / rate limits); run manually |
| Output | `results/retrieval-latest.{md,json}` | `results/answers-<model>.{md,json}` |

```bash
cd backend
python -m eval.retrieval            # add --check to enforce CI thresholds
python -m eval.answers --delay 3    # uses LLM_* from backend/.env
```

## Dataset

**Corpus.** Eight documents from *Larkspur Robotics*, a fictional company (`corpus/`): an employee
handbook, two robot spec sheets, an incident review, a security policy, a quarterly business review,
an API reference and an onboarding FAQ. Because the company is fictional, the LLM cannot answer from
pre-training: a correct answer has to come from retrieval.

**Hard negatives.** A tiny corpus makes every retriever look perfect. `distractors.py` generates
~70 seeded look-alike documents: other robot models' spec sheets, incident reviews for other sites
and firmware versions, other quarters' business reviews, other APIs' error codes. They share the
gold documents' vocabulary and layout but carry different facts, so the retriever has to match the
*right* entity (LR-200 vs LR-250, INC-2291 vs INC-2217, Q3 FY2025 vs Q3 FY2024).
`check_no_leaks` guarantees no distractor contains a gold evidence passage or answers an
unanswerable question.

**Questions** (`questions.json`, 36):

| Type | n | What it tests |
|---|---:|---|
| `fact` | 12 | Direct lookups with the document's own wording |
| `paraphrase` | 7 | Different vocabulary from the source ("desk and chair at home" → "home office allowance") |
| `distractor` | 5 | Facts that differ between look-alike documents (LR-200 vs LR-400 specs) |
| `exact_code` | 3 | Identifiers that embeddings handle poorly (`E4031`, `INC-2291`) |
| `multi_hop` | 4 | Facts from two passages or documents |
| `unanswerable` | 5 | Not in the corpus; the correct behaviour is to decline |

Each answerable question lists its **evidence**: verbatim passages that answer it (alternatives
separated by `||`). Retrieval relevance is judged by whether a retrieved chunk contains an evidence
passage, so no manual chunk-ID labelling is needed and the labels survive chunking changes.
Each question also lists **must_include** facts for a deterministic answer check.

## Retrieval metrics

- **Recall@k**: share of a question's evidence passages found in the top k chunks (averaged).
- **MRR**: mean reciprocal rank of the first relevant chunk.
- **nDCG@5**: rank-discounted gain of the first relevant chunk.
- **All evidence @5**: share of questions whose evidence is *all* in the top 5 (matters for multi-hop).

The production configuration must stay above `THRESHOLDS` in `retrieval.py`, or CI fails.

## Answer metrics

- **Accuracy (LLM judge)**: a judge model compares the answer with the human reference answer.
  Pass `--judge-model` to grade with a stronger or different model than the one under test.
- **Accuracy (required facts)**: deterministic: every `must_include` string appears in the answer.
  A cross-check on the judge.
- **Refusal rate**: share of unanswerable questions the system correctly declined (1 − hallucination rate).
- **Citation rate**, **verifier agreement** (verifier verdict vs judge), **regeneration rate**,
  **LLM calls per question**, **latency p50/p95**.

## Findings that changed the code

The harness has already caught four problems. Each is now fixed and covered by a test:

1. **Matcher bug in the harness itself.** An empty alternative matched every string, so the first
   run reported perfect scores everywhere. Fixed, with a regression test (`tests/test_eval_harness.py`).
2. **Reranker score cut-off dropped correct passages.** The retriever discarded candidates with a
   cross-encoder logit below −5. Logits are not calibrated across query styles: for paraphrased
   questions *every* candidate scored below −5, including the correct one. Removing the cut-off raised
   production MRR from 0.92 to 0.97 and Recall@5 from 0.92 to 0.98.
3. **Rerank pool size.** Reranking the top 10 fused candidates matched top 20/40 in quality at
   about half the latency, so `RERANK_CANDIDATES` defaults to 10.
4. **Wasted verification on refusals.** The verifier flagged correct "not found" answers as
   unsupported, which triggered a regeneration (4 LLM calls instead of 2). Refusals now begin with a
   fixed sentence and skip verification.

## Caveats

36 questions over a synthetic corpus is a regression suite, not a benchmark. It reliably detects
when a change makes things worse, but absolute numbers will differ on real document collections.
