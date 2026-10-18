from pathlib import Path

from grafin_ai_scoring.scoring.label_replay import LabelReplayScorer
from grafin_ai_scoring.scoring.precomputed import PrecomputedScorer
from grafin_ai_scoring.scoring.types import ScoringProvider


def get_scorer(
    name: str,
    *,
    seed: str = "grafin",
    fn_rate: float = 0.05,
    fp_rate: float = 0.04,
    scores_path: Path | None = None,
) -> ScoringProvider:
    """Select the scoring provider by config name."""
    if name == "label_replay":
        return LabelReplayScorer(seed=seed, fn_rate=fn_rate, fp_rate=fp_rate)
    if name == "precomputed":
        if scores_path is None or not scores_path.is_file():
            raise ValueError(
                "scorer 'precomputed' needs GRAFIN_SCORES_PATH set to an existing scores.csv "
                f"(from `grafin-train export-scores`); got {scores_path}"
            )
        return PrecomputedScorer(scores_path)
    if name == "ml":
        raise ValueError("scorer 'ml' (MLModelScorer) is not yet implemented (Phase 2)")
    raise ValueError(f"unknown scorer: {name!r}")
