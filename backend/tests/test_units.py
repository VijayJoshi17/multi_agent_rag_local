import io
import zipfile

import pytest

from app.agents.data_analyst import extract_code
from app.agents.retriever import reciprocal_rank_fusion
from app.agents.verifier import parse_verdict
from app.core.errors import PayloadTooLargeError, UnsupportedFileError
from app.schemas.rag import Chunk
from app.services import parsing
from app.services.bm25 import tokenize


def _c(i: int) -> Chunk:
    return Chunk(text=f"t{i}", source="s", document_id="d", chunk_index=i)


def test_rrf_rewards_agreement():
    fused = reciprocal_rank_fusion([[_c(1), _c(2), _c(3)], [_c(3), _c(1)]], [1.0, 1.0])
    assert [c.chunk_index for c in fused] == [1, 3, 2]
    assert fused[0].score and fused[0].score > fused[-1].score  # type: ignore[operator]


@pytest.mark.parametrize("raw,verdict", [
    ('{"verdict": "supported", "reason": "fine"}', "supported"),
    ('```json\n{"verdict": "unsupported", "reason": "x"}\n```', "unsupported"),
    ("ACCURATE | matches", "supported"),
    ("garbage", "unsupported"),
])
def test_parse_verdict(raw, verdict):
    assert parse_verdict(raw)["verdict"] == verdict


def test_extract_code():
    assert extract_code("Here:\n```python\nresult = 1\n```\nDone") == "result = 1"
    assert extract_code("result = 2") == "result = 2"


def test_tokenize():
    assert tokenize("Hello, World! 2024") == ["hello", "world", "2024"]


def test_sniff_rejects_mismatched_types():
    with pytest.raises(UnsupportedFileError):
        parsing.sniff("a.pdf", b"hello")
    with pytest.raises(UnsupportedFileError):
        parsing.sniff("a.docx", b"%PDF-1.7")
    with pytest.raises(UnsupportedFileError):
        parsing.sniff("a.exe", b"MZ")
    assert parsing.sniff("notes.MD", b"# hi") == ".md"


def test_zip_member_limit():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(5):
            zf.writestr(f"{i}.txt", "x")
    with pytest.raises(PayloadTooLargeError):
        parsing.expand_zip("z.zip", buf.getvalue(), max_members=3, max_total_bytes=10**6)


def test_zip_bomb_guard():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.txt", "0" * 5_000_000)
    with pytest.raises(PayloadTooLargeError):
        parsing.expand_zip("z.zip", buf.getvalue(), max_members=10, max_total_bytes=1_000_000)


async def test_bm25_scores_terms_common_to_all_docs():
    """Regression: Okapi IDF went negative on tiny corpora and BM25 returned nothing."""
    from app.services.bm25 import LuceneBM25

    bm = LuceneBM25([tokenize("paris is the capital of france")])
    assert bm.get_scores(tokenize("capital of france"))[0] > 0
