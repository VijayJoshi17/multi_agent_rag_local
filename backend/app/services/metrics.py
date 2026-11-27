from prometheus_client import Counter, Histogram

LLM_LATENCY = Histogram(
    "rag_llm_request_seconds", "LLM request latency", ["mode"],
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 120),
)
NODE_LATENCY = Histogram(
    "rag_agent_node_seconds", "Latency per agent graph node", ["node"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64),
)
ROUTE_COUNTER = Counter("rag_route_total", "Routing decisions", ["route"])
VERIFICATION_COUNTER = Counter("rag_verification_total", "Verifier verdicts", ["verdict"])
INGESTED_CHUNKS = Counter("rag_ingested_chunks_total", "Chunks written to the vector store")
