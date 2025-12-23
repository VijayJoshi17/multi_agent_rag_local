
# ===================== data_analyst.py =====================
import pandas as pd
import os
from app.agents.base import BaseAgent
from app.models.schemas import AgentState, DocumentChunk
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class DataAnalystAgent(BaseAgent):
    """
    Executes Pandas-based analysis on the most recently uploaded dataset.
    """

    def __init__(self):
        super().__init__(name="DataAnalyst")
        self.upload_dir = "data/uploaded_docs"

    def _get_latest_data_file(self):
        if not os.path.exists(self.upload_dir):
            return None

        files = [
            f for f in os.listdir(self.upload_dir)
            if f.endswith((".csv", ".xlsx"))
        ]
        if not files:
            return None

        files.sort(
            key=lambda x: os.path.getmtime(os.path.join(self.upload_dir, x)),
            reverse=True,
        )
        return os.path.join(self.upload_dir, files[0])

    async def run(self, state: AgentState) -> AgentState:
        logger.info(f"DataAnalyst received query: {state.query}")

        file_path = self._get_latest_data_file()
        if not file_path:
            state.retrieved_docs = [
                DocumentChunk(
                    content="No dataset found. Please upload a CSV or Excel file.",
                    metadata={"source": "system"},
                )
            ]
            return state

        try:
            df = (
                pd.read_csv(file_path)
                if file_path.endswith(".csv")
                else pd.read_excel(file_path)
            )

            columns = df.columns.tolist()

            history = ""
            if state.chat_history:
                history = "\n".join(
                    f"{m['role']}: {m['content']}" for m in state.chat_history[-3:]
                )

            prompt = f"""
You are a senior Python Pandas analyst.

DATAFRAME COLUMNS:
{columns}

RECENT CONTEXT:
{history}

USER QUESTION:
{state.query}

INSTRUCTIONS:
- Write valid pandas code only
- Store final output in a variable named `result`
- Do NOT print
- Assume df is already loaded
- No file I/O
- No plotting
- Wrap code in ```python```
"""

            response = await self.call_llm(prompt)

            code = response
            if "```" in code:
                code = code.split("```python")[-1].split("```")[0].strip()

            local_scope = {"df": df, "pd": pd}
            exec(code, {}, local_scope)
            result = local_scope.get("result", "NO RESULT")

            output = (
                result.to_markdown()
                if isinstance(result, pd.DataFrame)
                else str(result)
            )

            state.retrieved_docs = [
                DocumentChunk(
                    content=f"Code Executed:\n```python\n{code}\n```\n\nResult:\n{output}",
                    metadata={"source": os.path.basename(file_path), "type": "analysis"},
                )
            ]

        except Exception as e:
            logger.error(f"Data analysis error: {e}")
            state.retrieved_docs = [
                DocumentChunk(
                    content=f"Data analysis failed: {e}",
                    metadata={"source": "DataAnalyst"},
                )
            ]

        return state

