from app.agents.base import BaseAgent
from app.models.schemas import AgentState
from app.utils.logger import setup_logger
import os

logger = setup_logger(__name__)

class ParserAgent(BaseAgent):
    """
    Formats the final answer into a user-friendly Markdown structure.
    """

    def __init__(self):
        super().__init__(name="Parser")
        self.prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/parser.txt")
        self._load_prompt()

    def _load_prompt(self):
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt_template = f.read()
        else:
            # Fallback
            self.system_prompt_template = "You are a formatter. Rewrite the answer in clean Markdown."

    async def run(self, state: AgentState) -> AgentState:
        if not state.generated_answer:
            self.log(state, "No answer to format. Skipping.")
            return state

        self.log(state, "Formatting final answer...")
        
        # Construct Prompt
        formatted_prompt = self.system_prompt_template.format(
            answer=state.generated_answer,
            query=state.query
        )
        
        # Call LLM
        formatted_answer = await self.call_llm(
            prompt="Format the answer provided in the system prompt.", 
            system_prompt=formatted_prompt,
            timeout=60
        )
        
        # Update State
        state.generated_answer = formatted_answer
        self.log(state, "Formatting complete.")
        
        return state
