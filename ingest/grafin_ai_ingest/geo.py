import hashlib

PROVINCES = [
    "DKI Jakarta", "Jawa Barat", "Jawa Timur", "Jawa Tengah", "Sumatera Utara",
    "Banten", "Bali", "Sulawesi Selatan", "Sumatera Selatan", "Riau",
    "Kalimantan Timur", "Lampung", "Yogyakarta", "Sumatera Barat", "Kalimantan Barat",
]

_WEIGHTS = [12, 9, 8, 7, 6, 5, 4, 4, 3, 3, 2, 2, 2, 1, 1]
_BUCKET = [p for p, w in zip(PROVINCES, _WEIGHTS) for _ in range(w)]


def province_for_entity(entity_id: str) -> str:
    """Stable, seeded province assignment from a hash of the entity id (synthetic)."""
    digest = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()
    return _BUCKET[int(digest, 16) % len(_BUCKET)]
