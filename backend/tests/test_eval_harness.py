"""Guards for the evaluation harness itself — a buggy matcher silently reports perfect scores."""

from eval.common import contains_any, has_evidence, load_questions, normalize
from eval.distractors import check_no_leaks, generate
from eval.retrieval import score


def test_normalize_numbers_and_dashes():
    assert normalize("Payload: 1,200 kg — `E4031`") == "payload: 1200 kg - e4031"


def test_matchers_never_match_on_empty_alternatives():
    assert not contains_any("anything at all", "missing|")
    assert not has_evidence("anything at all", "missing||")
    assert has_evidence("Lost or stolen equipment ...", "nope||lost or stolen")


def test_dataset_is_valid_and_distractors_do_not_leak():
    questions = load_questions()
    assert len(questions) >= 30
    check_no_leaks(generate(), questions)


def test_retrieval_scoring():
    q = next(q for q in load_questions() if q.id == "m01")  # two evidence groups
    texts = ["unrelated", "Firmware 4.2.3, containing the fix, released", "noise",
             "37 LR-200 units at the Rotterdam site were affected."]
    r = score(q, texts)
    assert r.first_hit_rank == 2
    assert r.recall == {1: 0.0, 3: 0.5, 5: 1.0}
    assert r.full_coverage_at_5
