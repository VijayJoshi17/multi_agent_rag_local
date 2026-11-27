"""Executes one untrusted pandas snippet. Runs as a short-lived subprocess.

Reads {"code", "dataset_path"} as JSON from stdin, writes {"ok", "output", "error"} to stdout.
This static validation is one layer only — real isolation comes from the subprocess resource
limits and the locked-down container (no network, read-only FS, non-root).
"""

import ast
import builtins
import contextlib
import io
import json
import sys

ALLOWED_MODULES = {
    "pandas", "numpy", "math", "statistics", "datetime", "re", "collections", "itertools",
    "functools", "operator", "decimal", "fractions", "string",
}
BLOCKED_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr",
    "setattr", "delattr", "input", "breakpoint", "help", "exit", "quit", "memoryview",
    "__builtins__", "__loader__", "__spec__",
}
BLOCKED_ATTRS = {
    # pandas / numpy I/O and escape hatches
    "to_csv", "to_excel", "to_parquet", "to_pickle", "to_json", "to_sql", "to_hdf",
    "to_feather", "to_html", "to_clipboard", "to_latex", "to_stata", "to_xml", "to_gbq",
    "to_orc", "read_pickle", "load", "save", "savez", "savez_compressed", "savetxt", "loadtxt",
    "fromfile", "tofile", "genfromtxt", "memmap", "ctypeslib", "f2py", "testing", "eval",
    "query",  # string-evaluated expressions would bypass this AST validation
    "system", "popen", "spawn",
}
SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float",
        "format", "frozenset", "int", "isinstance", "len", "list", "map", "max", "min",
        "next", "print", "range", "repr", "reversed", "round", "set", "slice", "sorted",
        "str", "sum", "tuple", "zip", "ValueError", "KeyError", "TypeError",
        "IndexError", "ZeroDivisionError", "Exception", "True", "False", "None", "hasattr",
        "iter", "callable", "chr", "ord", "hex", "bin", "pow", "type",
    )
    if hasattr(builtins, name)
}


class ValidationError(Exception):
    pass


def validate(code: str) -> ast.Module:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise ValidationError(f"SyntaxError: {e.msg} (line {e.lineno})") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [
                node.module or ""
            ]
            for n in names:
                if n.split(".")[0] not in ALLOWED_MODULES:
                    raise ValidationError(f"Import of '{n}' is not allowed")
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise ValidationError(f"Use of '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValidationError(f"Access to private attribute '{node.attr}' is not allowed")
            if node.attr in BLOCKED_ATTRS or node.attr.startswith("read_"):
                raise ValidationError(f"'.{node.attr}' is not allowed in the sandbox")
        elif isinstance(node, ast.Global | ast.Nonlocal | ast.AsyncFunctionDef | ast.Await):
            raise ValidationError(f"'{type(node).__name__}' statements are not allowed")
    return tree


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
    if level != 0 or name.split(".")[0] not in ALLOWED_MODULES:
        raise ImportError(f"Import of '{name}' is not allowed")
    return __import__(name, globals, locals, fromlist, level)


def render(result: object, pd) -> str:  # noqa: ANN001
    max_rows = 50
    if isinstance(result, pd.DataFrame):
        out = result.head(max_rows).to_markdown()
        if len(result) > max_rows:
            out += f"\n\n… {len(result) - max_rows} more rows ({len(result)} total)"
        return out
    if isinstance(result, pd.Series):
        name = result.name if result.name is not None else "value"
        return render(result.to_frame(name=str(name)), pd)
    text = repr(result) if not isinstance(result, str) else result
    return text[:8000]


def run(code: str, dataset_path: str) -> dict:
    import numpy as np
    import pandas as pd

    tree = validate(code)
    df = pd.read_csv(dataset_path) if dataset_path.endswith(".csv") else pd.read_excel(dataset_path)

    safe_builtins = dict(SAFE_BUILTINS, __import__=_restricted_import)
    scope = {"__builtins__": safe_builtins, "df": df, "pd": pd, "np": np}
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exec(compile(tree, "<analysis>", "exec"), scope)  # noqa: S102 - validated + isolated

    printed = stdout.getvalue().strip()
    if "result" in scope:
        output = render(scope["result"], pd)
        if printed:
            output = f"{output}\n\nPrinted output:\n{printed[:4000]}"
    elif printed:
        output = printed[:8000]
    else:
        raise ValidationError("Code did not assign a `result` variable")
    return {"ok": True, "output": output, "error": None}


def main() -> None:
    req = json.loads(sys.stdin.read())
    try:
        resp = run(req["code"], req["dataset_path"])
    except ValidationError as e:
        resp = {"ok": False, "output": "", "error": str(e)}
    except MemoryError:
        resp = {"ok": False, "output": "", "error": "MemoryError: analysis used too much memory"}
    except Exception as e:  # noqa: BLE001 - report user-code errors back to the LLM
        resp = {"ok": False, "output": "", "error": f"{type(e).__name__}: {e}"[:2000]}
    sys.stdout.write(json.dumps(resp, default=str))


if __name__ == "__main__":
    main()
