import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import runner  # noqa: E402

DATASET = "0123456789abcdef0123456789abcdef.csv"


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / DATASET).write_text("region,revenue\nEU,4\nEU,6\nUS,5\n")
    monkeypatch.setenv("DATASETS_DIR", str(tmp_path))
    import importlib

    import app as sandbox_app

    importlib.reload(sandbox_app)
    return TestClient(sandbox_app.app)


@pytest.mark.parametrize("code", [
    "import os\nresult = os.listdir('/')",
    "import subprocess",
    "from socket import socket",
    "result = open('/etc/passwd').read()",
    "result = ().__class__.__bases__[0].__subclasses__()",
    "result = eval('1+1')",
    "result = getattr(df, 'to_csv')",
    "df.to_csv('/tmp/x.csv')",
    "result = pd.read_csv('/etc/passwd')",
    "result = df.query('revenue > 1')",
    "result = __import__('os')",
])
def test_validator_blocks_escapes(code):
    with pytest.raises(runner.ValidationError):
        runner.validate(code)


def test_validator_allows_normal_analysis():
    runner.validate(
        "import numpy as np\n"
        "g = df.groupby('region')['revenue'].sum().sort_values(ascending=False)\n"
        "result = g.head(10)"
    )


def test_execute_success(client):
    r = client.post("/execute", json={
        "code": "result = df.groupby('region')['revenue'].sum()", "dataset": DATASET,
    })
    body = r.json()
    assert body["ok"] is True, body
    assert "EU" in body["output"] and "10" in body["output"]


def test_execute_reports_runtime_errors(client):
    body = client.post("/execute", json={"code": "result = df['Revenue']",
                                         "dataset": DATASET}).json()
    assert body["ok"] is False
    assert "KeyError" in body["error"]


def test_execute_blocks_validation_failures(client):
    body = client.post("/execute", json={"code": "import os", "dataset": DATASET}).json()
    assert body == {**body, "ok": False}
    assert "not allowed" in body["error"]


def test_execute_timeout(client):
    body = client.post("/execute", json={
        "code": "x = 0\nwhile True:\n    x += 1", "dataset": DATASET, "timeout_s": 1,
    }).json()
    assert body["ok"] is False
    assert "timed out" in body["error"]


@pytest.mark.parametrize("name", ["../secrets.csv", "x.csv", "0123456789abcdef0123456789abcdef.py"])
def test_rejects_bad_dataset_names(client, name):
    assert client.post("/execute", json={"code": "result=1", "dataset": name}).status_code == 400


def test_execute_returns_chartable_table(client):
    body = client.post("/execute", json={
        "code": "result = df.groupby('region')['revenue'].sum()", "dataset": DATASET,
    }).json()
    assert body["ok"] is True
    assert body["table"] == {"columns": ["region", "revenue"], "rows": [["EU", 10], ["US", 5]]}


def test_scalar_result_has_no_table(client):
    body = client.post("/execute", json={"code": "result = len(df)", "dataset": DATASET}).json()
    assert body["ok"] is True and body["table"] is None


def test_excel_sheets_are_available(tmp_path, monkeypatch):
    import importlib

    import pandas as pd

    name = "abcdefabcdefabcdefabcdefabcdef12.xlsx"
    with pd.ExcelWriter(tmp_path / name) as xw:
        pd.DataFrame({"a": [1, 2]}).to_excel(xw, sheet_name="first", index=False)
        pd.DataFrame({"b": [10, 20, 30]}).to_excel(xw, sheet_name="second", index=False)
    monkeypatch.setenv("DATASETS_DIR", str(tmp_path))
    import app as sandbox_app

    importlib.reload(sandbox_app)
    from fastapi.testclient import TestClient

    body = TestClient(sandbox_app.app).post("/execute", json={
        "code": "result = int(df['a'].sum() + sheets['second']['b'].sum())", "dataset": name,
    }).json()
    assert body["ok"] is True, body
    assert body["output"] == "63"
