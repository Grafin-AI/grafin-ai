import csv
import logging
from array import array
from bisect import bisect_left
from pathlib import Path

from garda_ai_scoring.scoring.types import ScoringContext, ScoringResult, TxnInput

log = logging.getLogger(__name__)

HEADER = ["transaction_id", "fraud_score", "prob", "status", "typology"]
STATUSES = frozenset({"approved", "flagged", "blocked"})
_MISS = ScoringResult(fraud_score=0.0, typology=None, status="approved")


class PrecomputedScorer:
    """Serves model scores exported offline (`garda-train export-scores`): a lookup by
    transaction_id in ``scores.csv``. Never reads ``is_laundering``. Unknown ids are approved
    with score 0.0 (never raises: one error would fail the backend's whole batch).

    Memory: sorted ids (int64) + scores (float64) + one byte per row indexing a small table of
    (status, typology) pairs, ~17 bytes/row (~40 MB for 2.3M rows)."""

    def __init__(self, path: Path) -> None:
        ids, scores, codes = array("q"), array("d"), array("B")
        kinds: dict[tuple[str, str | None], int] = {}
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if header != HEADER:
                raise ValueError(f"{path}: expected header {','.join(HEADER)}, got {header}")
            for line, row in enumerate(reader, start=2):
                try:
                    tid, score, _prob, status, typology = row
                    kind = (status, typology or None)
                    if status not in STATUSES:
                        raise ValueError(f"bad status {status!r}")
                    code = kinds.setdefault(kind, len(kinds))
                    ids.append(int(tid))
                    scores.append(float(score))
                    codes.append(code)
                except (ValueError, OverflowError) as exc:
                    raise ValueError(f"{path}:{line}: {exc}") from exc
        if any(ids[i] > ids[i + 1] for i in range(len(ids) - 1)):
            order = sorted(range(len(ids)), key=ids.__getitem__)
            ids = array("q", (ids[i] for i in order))
            scores = array("d", (scores[i] for i in order))
            codes = array("B", (codes[i] for i in order))
        self._ids, self._scores, self._codes = ids, scores, codes
        self._kinds = [k for k, _ in sorted(kinds.items(), key=lambda kv: kv[1])]
        self.misses = 0
        log.info("precomputed scorer: %d scores from %s", len(ids), path)

    def __len__(self) -> int:
        return len(self._ids)

    def lookup(self, transaction_id: int) -> ScoringResult | None:
        i = bisect_left(self._ids, transaction_id)
        if i == len(self._ids) or self._ids[i] != transaction_id:
            return None
        status, typology = self._kinds[self._codes[i]]
        return ScoringResult(fraud_score=self._scores[i], typology=typology, status=status)

    async def score(self, txn: TxnInput, ctx: ScoringContext) -> ScoringResult:
        hit = self.lookup(txn.transaction_id)
        if hit is not None:
            return hit
        self.misses += 1
        if self.misses % 1000 == 1:
            log.warning(
                "precomputed scorer: no score for transaction_id %d (%d misses so far)",
                txn.transaction_id,
                self.misses,
            )
        return _MISS
