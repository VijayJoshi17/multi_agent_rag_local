"""LangGraph workflow wiring the agents together.

    contextualize → router ─┬─ retrieve ──(no hits, auto mode)──┐
                            ├─ web_search  ←────────────────────┘
                            └─ data_analyst
                 all three → reason → verify ──(unsupported, retries left)──→ reason
                                         └──→ END
"""

import time
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agents.base import Agent
from app.agents.reasoner import is_refusal
from app.graph.context import Emit, NodeContext
from app.graph.state import GraphState
from app.services.metrics import NODE_LATENCY


@dataclass(slots=True)
class Agents:
    contextualize: Agent
    router: Agent
    retrieve: Agent
    web_search: Agent
    data_analyst: Agent
    reason: Agent
    verify: Agent


def _node(agent: Agent):
    async def run(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
        emit: Emit = config["configurable"]["emit"]
        await emit({"type": "node_start", "node": agent.name})
        start = time.perf_counter()
        update = await agent(state, NodeContext(agent.name, emit))
        elapsed = time.perf_counter() - start
        NODE_LATENCY.labels(node=agent.name).observe(elapsed)
        await emit({
            "type": "node_end", "node": agent.name,
            "duration_ms": int(elapsed * 1000), "summary": agent.summary(update),
        })
        return update

    run.__name__ = f"node_{agent.name}"
    return run


def build_workflow(agents: Agents, max_verify_retries: int):
    g = StateGraph(GraphState)
    for agent in (agents.contextualize, agents.router, agents.retrieve, agents.web_search,
                  agents.data_analyst, agents.reason, agents.verify):
        g.add_node(agent.name, _node(agent))

    g.add_edge(START, "contextualize")
    g.add_edge("contextualize", "router")
    g.add_conditional_edges("router", lambda s: s["route"],
                            ["retrieve", "web_search", "data_analyst"])

    def can_try_web(s: GraphState) -> bool:
        """Auto mode, unscoped, and the web hasn't been tried yet for this question."""
        return (s.get("mode", "auto") == "auto" and not s.get("document_ids")
                and not s.get("web_fallback"))

    def after_retrieve(s: GraphState) -> str:
        if not s.get("evidence") and can_try_web(s):
            return "web_search"  # nothing relevant locally -> fall back to the web
        return "reason"

    g.add_conditional_edges("retrieve", after_retrieve, ["web_search", "reason"])
    g.add_edge("web_search", "reason")
    g.add_edge("data_analyst", "reason")

    def after_reason(s: GraphState) -> str:
        evidence = s.get("evidence") or []
        grounded = [c for c in evidence if c.kind != "system"]
        if is_refusal(s.get("answer", "")):
            # The documents didn't answer it: try the web once, keeping the document passages.
            if s.get("route") == "retrieve" and can_try_web(s):
                return "web_search"
            return END  # nothing to fact-check in "not found"
        if s.get("verify", True) and grounded and s.get("route") != "data_analyst":
            return "verify"
        return END

    g.add_conditional_edges("reason", after_reason, ["verify", "web_search", END])

    def after_verify(s: GraphState) -> str:
        v = s.get("verification") or {}
        if v.get("verdict") == "unsupported" and s.get("attempts", 1) <= max_verify_retries:
            return "reason"
        return END

    g.add_conditional_edges("verify", after_verify, ["reason", END])
    return g.compile()
