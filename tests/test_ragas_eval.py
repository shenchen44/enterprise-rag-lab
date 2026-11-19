import pandas as pd

from src.eval.run_ragas_eval import generate_answer, metric_scores
from src.retrieval.evidence_package import EvidenceDecision, EvidencePackage


def test_metric_scores_accepts_mode_suffix() -> None:
    frame = pd.DataFrame(
        {"noise_sensitivity(mode=irrelevant)": [0.25, 0.5]}
    )

    assert metric_scores(frame, "noise_sensitivity").tolist() == [0.25, 0.5]


def test_generation_is_blocked_for_conflicting_evidence() -> None:
    package = EvidencePackage(
        decision=EvidenceDecision.CONFLICT,
        completeness=0,
        slots=[],
        conflicts=["headcount differs"],
    )

    answer = generate_answer("What is headcount?", "evidence", package)

    assert "no unconditional answer" in answer
    assert "headcount differs" in answer
