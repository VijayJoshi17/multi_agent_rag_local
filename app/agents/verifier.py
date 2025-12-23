from app.agents.base import BaseAgent
from app.models.schemas import AgentState
from app.utils.logger import setup_logger
import os
import re

logger = setup_logger(__name__)


class VerifierAgent(BaseAgent):
    """
    VerifierAgent
    -------------
    Performs grounded verification of the generated answer against retrieved context.

    Responsibilities:
    - Detect hallucinations or unsupported claims
    - Check numerical and factual consistency
    - Return a STRICT machine-readable verdict for downstream logic
    """

    def __init__(self):
        super().__init__(name="Verifier")

    def _read_prompt(self) -> str:
        """Load verifier system prompt from prompts directory."""
        prompt_path = os.path.join(
            os.path.dirname(__file__), "../prompts/verifier.txt"
        )
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    async def run(self, state: AgentState) -> AgentState:
        logger.info("VerifierAgent: validating generated answer")

        system_prompt = self._read_prompt()

        # ------------------------------------------------------------------
        # 1. BUILD VERIFICATION CONTEXT (STRUCTURED & TOKEN-EFFICIENT)
        # ------------------------------------------------------------------
        context_blocks = []
        for i, doc in enumerate(state.retrieved_docs or []):
            context_blocks.append(
                f"[SOURCE {i + 1}]\n{doc.content.strip()}"
            )

        context = "\n\n".join(context_blocks) or "NO CONTEXT PROVIDED"

        verification_prompt = f"""
USER QUESTION:
{state.query}

RETRIEVED EVIDENCE:
{context}

PROPOSED ANSWER:
{state.generated_answer}

TASK:
Verify whether the proposed answer is fully supported by the retrieved evidence.
"""

        # ------------------------------------------------------------------
        # 2. LLM VERIFICATION CALL
        # ------------------------------------------------------------------
        response = await self.call_llm(
            verification_prompt,
            system_prompt=system_prompt
        )

        response = response.strip()

        # ------------------------------------------------------------------
        # 3. STRICT RESPONSE PARSING (FAIL-SAFE)
        # ------------------------------------------------------------------
        # Expected formats (enforced by prompt):
        # ACCURATE | short justification
        # INACCURATE | reason + what is missing/wrong

        match = re.match(r"^(ACCURATE|INACCURATE)\s*\|\s*(.*)$", response, re.I)

        if not match:
            # Hard fail-safe: treat malformed output as failure
            logger.warning("Verifier returned malformed response")
            state.verification_status = False
            state.verification_feedback = response
            return state

        verdict, feedback = match.groups()
        verdict = verdict.upper()
        feedback = feedback.strip()

        # ------------------------------------------------------------------
        # 4. UPDATE AGENT STATE
        # ------------------------------------------------------------------
        if verdict == "ACCURATE":
            state.verification_status = True
            state.verification_feedback = None
            logger.info("Verification PASSED")
        else:
            state.verification_status = False
            state.verification_feedback = feedback
            logger.warning(f"Verification FAILED: {feedback}")

        return state
