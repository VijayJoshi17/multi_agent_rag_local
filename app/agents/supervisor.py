from app.agents.retriever import RetrieverAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.reasoner import ReasonerAgent
from app.agents.verifier import VerifierAgent
from app.agents.optimizer import OptimizerAgent
from app.agents.contextualizer import ContextualizerAgent
from app.agents.router import RouterAgent
from app.agents.web_search import WebSearchAgent
from app.agents.data_analyst import DataAnalystAgent
from app.agents.parser import ParserAgent # Added
from app.models.schemas import AgentState, Answer, Source, AgentGraphState
from app.utils.logger import setup_logger
import uuid
from datetime import datetime
from langgraph.graph import StateGraph, END
from typing import AsyncIterator
import json

logger = setup_logger(__name__)

class SupervisorAgent:
    def __init__(self):
        self.retriever = RetrieverAgent()
        # self.summarizer = SummarizerAgent() # Optimization: Removed to save time
        self.reasoner = ReasonerAgent()
        self.verifier = VerifierAgent()
        self.optimizer = OptimizerAgent()
        self.contextualizer = ContextualizerAgent()
        self.router = RouterAgent()
        self.web_search = WebSearchAgent()
        self.data_analyst = DataAnalystAgent()
        self.parser = ParserAgent() # Added
        self.app = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentGraphState)

        # 1. Define Nodes
        # 1. Define Nodes
        # 1. Define Nodes
        async def retrieve_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = [] # Reset logs to capture only this step
            result = await self.retriever.run(pydantic_state)
            return {"retrieved_docs": result.retrieved_docs, "logs": result.logs}

        async def summarize_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.summarizer.run(pydantic_state)
            return {"summary": result.summary, "logs": result.logs}

        async def reason_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.reasoner.run(pydantic_state)
            return {
                "generated_answer": result.generated_answer, 
                "reasoning_trace": result.reasoning_trace,
                "logs": result.logs
            }

        async def verify_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.verifier.run(pydantic_state)
            return {
                "verification_status": result.verification_status,
                "verification_feedback": result.verification_feedback,
                "logs": result.logs
            }
            
        async def optimize_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.optimizer.run(pydantic_state)
            return {"logs": result.logs}

        async def parser_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.parser.run(pydantic_state)
            return {"generated_answer": result.generated_answer, "logs": result.logs}

        async def contextualize_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            # Contextualizer is the first step, so logs might be fresh anyway, but good practice
            pydantic_state.logs = [] 
            result = await self.contextualizer.run(pydantic_state)
            return {"query": result.query, "logs": result.logs}

        async def router_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.router.run(pydantic_state)
            return {"route": result.route, "logs": result.logs}

        async def web_search_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.web_search.run(pydantic_state)
            return {"retrieved_docs": result.retrieved_docs, "logs": result.logs}

        async def data_analyst_node(state: AgentGraphState):
            pydantic_state = AgentState(**state)
            pydantic_state.logs = []
            result = await self.data_analyst.run(pydantic_state)
            return {"retrieved_docs": result.retrieved_docs, "logs": result.logs}

        workflow.add_node("contextualize", contextualize_node)
        workflow.add_node("router", router_node)
        workflow.add_node("web_search", web_search_node)
        workflow.add_node("data_analyst", data_analyst_node)
        workflow.add_node("retrieve", retrieve_node)
        # workflow.add_node("summarize", summarize_node)
        workflow.add_node("reason", reason_node)
        workflow.add_node("verify", verify_node)
        workflow.add_node("optimize", optimize_node)
        workflow.add_node("parser", parser_node) # Added

        # 2. Define Edges
        workflow.set_entry_point("contextualize")
        
        # Mode Check after Contextualize (or even before?)
        # Let's check mode after contextualize
        def mode_routing(state: AgentGraphState):
            if state.get("mode") == "data_analyst":
                return "data_analyst"
            elif state.get("mode") == "web_search":
                return "web_search"
            return "router"

        workflow.add_conditional_edges(
            "contextualize",
            mode_routing,
            {
                "data_analyst": "data_analyst",
                "web_search": "web_search",
                "router": "router"
            }
        )
        
        # Conditional Routing for Router
        def route_decision(state: AgentGraphState):
            return state.get("route", "retrieve")

        workflow.add_conditional_edges(
            "router",
            route_decision,
            {
                "retrieve": "retrieve",
                "web_search": "web_search"
            }
        )

        # All retrievers feed into reasoner
        workflow.add_edge("retrieve", "reason")
        workflow.add_edge("web_search", "reason")
        workflow.add_edge("data_analyst", "reason")
        
        # Determine if we should verify or skip
        def check_verification_request(state: AgentGraphState):
            # Data Analyst result (code execution) is ground truth, usually doesn't need LLM verification
            # But "reason" node runs after it.
            # If mode is data_analyst, maybe skip verify?
            if state.get("mode") == "data_analyst":
                return "optimize"
                
            if state.get("run_verification", True):
                return "verify"
            else:
                return "optimize"

        workflow.add_conditional_edges(
            "reason",
            check_verification_request,
            {
                "verify": "verify",
                "optimize": "optimize"
            }
        )
        
        # Post-verification check
        def check_verification_status(state: AgentGraphState):
            # If we reached here, verification ran.
            if state.get("verification_status"):
                return "optimize"
            else:
                return "optimize" # In future, could route to "reason" for retry
        
        workflow.add_conditional_edges(
            "verify",
            check_verification_status,
            {
                "optimize": "optimize"
            }
        )
        
        # Optimize -> Parser -> End
        workflow.add_edge("optimize", "parser")
        workflow.add_edge("parser", END)

        return workflow.compile()

    async def stream_run(self, query: str, chat_history: list = [], run_verification: bool = True, mode: str = "general") -> AsyncIterator[dict]:
        trace_id = str(uuid.uuid4())
        logger.info(f"Starting LangGraph streaming for trace_id: {trace_id} (verification={run_verification})")
        
        initial_state = AgentGraphState(
            query=query,
            chat_history=chat_history,
            retrieved_docs=[],
            summary=None,
            reasoning_trace=[],
            generated_answer=None,
            verification_status=False,
            verification_feedback=None,
            retry_count=0,
            run_verification=run_verification,
            mode=mode,
            logs=[] # Initialize logs
        )
        
        # Yield start event
        yield {
            "type": "start", 
            "trace_id": trace_id, 
            "timestamp": datetime.now().isoformat()
        }
        
        # Yield initial status
        yield {
            "type": "status",
            "agent": "contextualize",
            "status": "starting",
            "details": "Reviewing chat history..."
        }
        
        # REMOVED: Hardcoded Router yield which was confusing in Data Analyst mode
        
        final_state = initial_state
        # Stream updates from the graph
        async for event in self.app.astream(initial_state):
            for node_name, result in event.items():
                # Update our local view of state (simplified)
                if isinstance(result, dict):
                    final_state.update(result)
                
                # Yield Completion Event for current node
                status_event = {
                    "type": "status",
                    "agent": node_name,
                    "status": "complete",
                    "result": str(result)[:100] + "...",
                    "logs": result.get("logs", [])
                }
                
                # Add specific completion details
                if node_name == "contextualize":
                    status_event["details"] = "Query refined"
                elif node_name == "router":
                    route = result.get('route', 'unknown')
                    status_event["details"] = f"Selected route: {route}"
                elif node_name == "web_search":
                    doc_count = len(result.get('retrieved_docs', []))
                    status_event["details"] = f"Found {doc_count} web results"
                elif node_name == "retrieve":
                    doc_count = len(result.get('retrieved_docs', []))
                    status_event["details"] = f"Found {doc_count} relevant documents"
                # elif node_name == "summarize":
                #     status_event["details"] = "Context condensation complete"
                elif node_name == "reason":
                    status_event["details"] = "Answer formulated"
                elif node_name == "verify":
                    status_event["details"] = f"Verification: {result.get('verification_status')}"
                elif node_name == "data_analyst":
                    status_event["details"] = "Data Analysis execution complete"
                    
                yield status_event
                
                # Yield Start Event for NEXT node (Predictive Feedback)
                # Yield Start Event for NEXT node (Predictive Feedback)
                if node_name == "contextualize":
                     # Check mode to see where we are going
                     mode = final_state.get("mode", "general")
                     
                     if mode == "data_analyst":
                         target_agent = "data_analyst"
                         details = "Routing to Data Analyst..."
                     elif mode == "web_search":
                         target_agent = "web_search"
                         details = "Routing to Web Search..."
                     else:
                        target_agent = "router"
                        new_query = result.get('query', query)
                        details = f"Looking for: '{new_query}'" if new_query != query else "Using original query"
                     
                     yield {
                        "type": "status",
                        "agent": target_agent,
                        "status": "starting",
                        "details": details
                    }
                elif node_name == "router":
                     route = result.get('route', 'retrieve')
                     target_agent = "web_search" if route == "web_search" else "retrieve"
                     yield {
                        "type": "status",
                        "agent": target_agent,
                        "status": "starting",
                        "details": f"Routing to {target_agent}..."
                    }
                elif node_name in ["retrieve", "web_search", "data_analyst"]:
                     doc_count = len(result.get('retrieved_docs', []))
                     yield {
                        "type": "status",
                        "agent": "reason",
                        "status": "starting",
                        "details": f"Analyzing {doc_count} documents to formulate answer..."
                    }
                elif node_name == "reason":
                    # Check if we are verifying next
                    if run_verification and mode != "data_analyst": # Skip verify for data analyst?
                         yield {
                            "type": "status",
                            "agent": "verify",
                            "status": "starting",
                            "details": "Fact-checking answer against verified sources..."
                        }
                    else:
                         yield {
                            "type": "status",
                            "agent": "optimize",
                            "status": "starting",
                            "details": "Finalizing response..."
                        }
                elif node_name == "verify":
                     yield {
                        "type": "status",
                        "agent": "optimize",
                        "status": "starting",
                        "details": "Finalizing response..."
                    }
                elif node_name == "optimize":
                     yield {
                        "type": "status",
                        "agent": "parser",
                        "status": "starting",
                        "details": "Formatting final answer..."
                    }
                elif node_name == "parser":
                     # Completion of parser is the end
                     pass

        # Construct final answer after loop
        # Note: final_state might not be fully complete if we just did .update(), 
        # but the specific node outputs are what we need. 
        # Actually LangGraph аstream updates keys in the state.
        
        # We need to construct the Answer object to send as the final payload
        
        # Re-construct Answer logic similar to run()
        sources = [
            Source(text=doc.content, metadata=doc.metadata) 
            for doc in final_state.get("retrieved_docs", [])
        ]
        
        final_answer = final_state.get("generated_answer", "") or "Failed to generate."
        if run_verification and not final_state.get("verification_status", False):
             # Only show warning if we actually ran verification and it failed
             final_answer += f"\n\n[WARNING: Verification Failed. Logic: {final_state.get('verification_feedback')}]"
             
        answer_payload = Answer(
            response=final_answer,
            sources=sources,
            confidence_score=1.0 if final_state.get("verification_status") else 0.5,
            trace_id=trace_id
        ).model_dump() # Convert to dict for JSON serialization
        
        yield {
            "type": "final",
            "data": answer_payload
        }

    async def run(self, query: str) -> Answer:
        trace_id = str(uuid.uuid4())
        logger.info(f"Starting LangGraph execution for trace_id: {trace_id}")
        
        initial_state = AgentGraphState(
            query=query,
            retrieved_docs=[],
            summary=None,
            reasoning_trace=[],
            generated_answer=None,
            verification_status=False,
            verification_feedback=None,
            retry_count=0
        )
        
        # Use ainvoke for async graph execution
        final_state = await self.app.ainvoke(initial_state)
        
        sources = [
            Source(text=doc.content, metadata=doc.metadata) 
            for doc in final_state["retrieved_docs"]
        ]
        
        final_answer = final_state["generated_answer"]
        if not final_state["verification_status"]:
            final_answer += f"\n\n[WARNING: Verification Failed. Logic: {final_state['verification_feedback']}]"

        return Answer(
            response=final_answer or "Failed to generate answer.",
            sources=sources,
            confidence_score=1.0 if final_state["verification_status"] else 0.5,
            trace_id=trace_id
        )
