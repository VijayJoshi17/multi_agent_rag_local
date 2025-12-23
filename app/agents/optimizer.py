
# ===================== optimizer.py =====================
from app.agents.base import BaseAgent
from app.models.schemas import AgentState, ToolFeedback
from app.utils.logger import setup_logger
import json
import os

logger = setup_logger(__name__)


class OptimizerAgent(BaseAgent):
    """
    Logs verifier feedback for offline prompt and agent tuning.
    """

    def __init__(self):
        super().__init__(name="Optimizer")
        self.feedback_file = "feedback_log.jsonl"

    async def run(self, state: AgentState) -> AgentState:
        feedback = ToolFeedback(
            agent_name="Verifier",
            success=bool(state.verification_status),
            feedback=state.verification_feedback or "OK",
        )

        self._log_feedback(feedback, state)

        if not state.verification_status:
            logger.info("Optimizer logged a failed interaction")

        return state

    def _log_feedback(self, feedback: ToolFeedback, state: AgentState):
        entry = {
            "timestamp": feedback.timestamp.isoformat(),
            "query": state.query,
            "success": feedback.success,
            "feedback": feedback.feedback,
            "answer": state.generated_answer,
            "agent": feedback.agent_name,
        }

        os.makedirs(os.path.dirname(self.feedback_file) or ".", exist_ok=True)
        with open(self.feedback_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
