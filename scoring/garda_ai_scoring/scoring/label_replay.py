from garda_ai_scoring.scoring.deterministic import status_for, typology_for, unit_hash
from garda_ai_scoring.scoring.types import ScoringContext, ScoringResult, TxnInput


class LabelReplayScorer:
    """Phase-1 scorer: derive a realistic score/typology/status from the ground-truth
    ``is_laundering`` label, with controlled FP/FN noise so detection metrics aren't a
    perfect 1.0. Fully deterministic (seeded by transaction identity)."""

    def __init__(
        self,
        seed: str = "garda",
        fn_rate: float = 0.05,
        fp_rate: float = 0.04,
    ) -> None:
        self._seed = seed
        self._fn_rate = fn_rate
        self._fp_rate = fp_rate

    def _key(self, txn: TxnInput, salt: str = "") -> str:
        return f"{self._seed}:{txn.transaction_id}:{txn.from_account}:{txn.to_account}:{salt}"

    async def score(self, txn: TxnInput, ctx: ScoringContext) -> ScoringResult:
        base = unit_hash(self._key(txn))
        noise = unit_hash(self._key(txn, "noise"))

        if txn.is_laundering:
            if noise < self._fn_rate:
                score, typology = 0.10 + 0.30 * base, None
            else:
                score, typology = 0.70 + 0.29 * base, typology_for(self._key(txn, "typ"))
        else:
            if noise < self._fp_rate:
                score, typology = 0.55 + 0.40 * base, typology_for(self._key(txn, "typ"))
            else:
                score, typology = 0.01 + 0.40 * base, None

        if ctx.from_risk_category == "High":
            score = min(0.99, score + 0.05)
        elif ctx.from_risk_category == "Medium":
            score = min(0.99, score + 0.02)

        status = status_for(score)
        if status == "approved":
            typology = None
        elif typology is None:
            typology = typology_for(self._key(txn, "typ"))
        return ScoringResult(fraud_score=round(score, 4), typology=typology, status=status)
