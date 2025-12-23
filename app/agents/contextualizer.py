
# ===================== contextualizer.py =====================
from app.agents.base import BaseAgent
from app.models.schemas import AgentState


class ContextualizerAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Contextualizer")
        self.system_prompt = """
You are a query contextualization engine.

TASK:
Rewrite the user's latest query into a fully standalone question.

RULES:
- Resolve pronouns (he, she, it, they, this, that) using chat history
- Preserve the user's original intent exactly
- If the query is already standalone, return it unchanged
- Do NOT answer the question
- Output ONLY the rewritten query
"""

    async def run(self, state: AgentState) -> AgentState:
        if not state.chat_history:
            return state

        history_text = "\n".join(
            f"{m.get('role')}: {m.get('content')}" for m in state.chat_history[-4:]
        )

        prompt = f"""
CHAT HISTORY:
{history_text}

LATEST USER QUERY:
{state.query}

STANDALONE QUERY:
"""

        rewritten = await self.call_llm(prompt, system_prompt=self.system_prompt)
        rewritten = rewritten.strip().strip('"')

        if rewritten:
            state.query = rewritten

        return state

