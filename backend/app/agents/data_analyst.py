import re
from typing import Any

from app.agents.base import Agent, format_history, load_prompt
from app.core.errors import NotFoundError
from app.graph.context import NodeContext
from app.graph.state import GraphState
from app.schemas.rag import Chunk
from app.services.datasets import DatasetService
from app.services.llm import LLMClient
from app.services.sandbox import SandboxClient

_CODE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def describe_columns(columns: list[dict[str, str]]) -> str:
    """Column list for the prompt; multi-sheet workbooks are grouped per sheet."""
    sheets = list(dict.fromkeys(c["sheet"] for c in columns if "sheet" in c))
    if not sheets:
        return "\n".join(f"- {c['name']} ({c['dtype']})" for c in columns)
    return "\n".join(
        f"sheets[{name!r}]" + (" (also `df`)" if i == 0 else "") + ":\n"
        + "\n".join(f"  - {c['name']} ({c['dtype']})" for c in columns if c.get("sheet") == name)
        for i, name in enumerate(sheets)
    )


def extract_code(text: str) -> str:
    match = _CODE_RE.search(text)
    return (match.group(1) if match else text).strip()


class DataAnalystAgent(Agent):
    """Writes pandas code for the question and runs it in the isolated sandbox service.
    On failure, the error is fed back to the LLM for one self-repair attempt."""

    name = "data_analyst"
    max_attempts = 2

    def __init__(self, llm: LLMClient, datasets: DatasetService, sandbox: SandboxClient):
        self.llm, self.datasets, self.sandbox = llm, datasets, sandbox

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        try:
            ds = await self.datasets.get(state.get("dataset_id"))
        except NotFoundError as e:
            await ctx.log(str(e))
            return {"evidence": [Chunk(text=str(e), source="system", kind="system")]}

        schema = describe_columns(ds.columns)
        sample = await self.datasets.sample(ds)
        await ctx.log(f"Dataset: {ds.filename} ({ds.row_count:,} rows, {len(ds.columns)} cols)")

        base_prompt = (
            f"DATAFRAME `df` — {ds.row_count} rows.\nCOLUMNS:\n{schema}\n\n"
            f"SAMPLE ROWS:\n{sample}\n\n"
            f"RECENT CONVERSATION:\n{format_history(state.get('history') or [], 4) or '(none)'}\n\n"
            f"QUESTION:\n{state['query']}"
        )
        prompt, code, result = base_prompt, "", None
        for attempt in range(1, self.max_attempts + 1):
            code = extract_code(await self.llm.complete(prompt, system=load_prompt("data_analyst"),
                                                        temperature=0))
            await ctx.event({"type": "code", "node": self.name, "code": code, "attempt": attempt})
            result = await self.sandbox.execute(code, ds.stored_name)
            if result.ok:
                await ctx.log(f"Executed in sandbox ({result.duration_ms} ms).")
                break
            await ctx.log(f"Attempt {attempt} failed: {result.error}")
            prompt = (f"{base_prompt}\n\nYOUR PREVIOUS CODE:\n```python\n{code}\n```\n"
                      f"FAILED WITH:\n{result.error}\n\nFix the code.")

        assert result is not None
        if not result.ok:
            text = f"Analysis failed after {self.max_attempts} attempts: {result.error}"
        else:
            text = (
                f"Code executed on {ds.filename}:\n{code}\n\n"
                f"Computed result (exact, from running the code):\n{result.output}"
            )
        chunk = Chunk(text=text, source=ds.filename, kind="analysis", extra={"code": code})
        return {
            "evidence": [chunk],
            "analysis": {"code": code, "ok": result.ok, "output": result.output,
                         "error": result.error, "dataset_id": ds.id, "table": result.table},
        }

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        a = update.get("analysis") or {}
        return "Code executed" if a.get("ok") else "Analysis failed"
