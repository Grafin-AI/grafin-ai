import hashlib

TYPOLOGIES = [
    "Fan-Out", "Cycle", "Gather-Scatter", "Smurfing",
    "Mule Account", "Layering", "Trade-Based",
]

_BLOCK_THRESHOLD = 0.8
_FLAG_THRESHOLD = 0.5


def unit_hash(key: str) -> float:
    """Deterministic float in [0, 1) from a key (seeded sha256)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(16**16)


def status_for(score: float, block: float = _BLOCK_THRESHOLD, flag: float = _FLAG_THRESHOLD) -> str:
    if score >= block:
        return "blocked"
    if score >= flag:
        return "flagged"
    return "approved"


def typology_for(key: str) -> str:
    return TYPOLOGIES[int(unit_hash(key) * len(TYPOLOGIES))]
