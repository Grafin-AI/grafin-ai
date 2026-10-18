"""Load and validate the versioned mapping tables in ``mappings/`` (the localization recipe)."""

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from garda_ai_dataset.errors import MappingError
from garda_ai_dataset.geo import PROVINCES
from garda_ai_dataset.hashing import sha256_file

MAPPINGS_DIR = Path(__file__).resolve().parent.parent / "mappings"
INSTITUTION_KINDS = ("bank", "crypto_exchange")
ENTITY_KINDS = ("individual", "business")


@dataclass(frozen=True)
class Institution:
    name: str
    short_name: str
    kind: str
    group: str
    weight: int


@dataclass(frozen=True)
class Mappings:
    fx: dict[str, float]  # IBM currency name -> IDR per unit
    channels: dict[str, str]  # IBM payment format -> Indonesian channel
    entity_types: dict[str, tuple[str, str]]  # IBM prefix -> (entity type, kind)
    institutions: tuple[Institution, ...]
    cities: dict[str, tuple[str, ...]]  # province -> cities
    kyc: tuple[tuple[str, int], ...]
    sectors: dict[str, tuple[tuple[str, int], ...]]  # kind -> weighted labels
    hashes: dict[str, str]  # table file name -> sha256


def _read(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        raise MappingError(f"mapping table missing: {path}")
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
            if missing:
                raise MappingError(f"{path.name}: missing columns {missing}")
            rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise MappingError(f"{path.name}: {exc}") from None
    for line, row in enumerate(rows, start=2):
        if None in row:
            raise MappingError(f"{path.name}:{line}: too many fields (unquoted comma?)")
    if not rows:
        raise MappingError(f"{path.name}: has no rows")
    cleaned: list[dict[str, str]] = []
    for line, row in enumerate(rows, start=2):
        values: dict[str, str] = {}
        for column in columns:
            value = (row.get(column) or "").strip()
            if not value:
                raise MappingError(f"{path.name}:{line}: empty value for {column!r}")
            if "," in value:
                raise MappingError(f"{path.name}:{line}: comma in {column!r} value {value!r}")
            values[column] = value
        cleaned.append(values)
    return cleaned


def _positive_int(path: Path, line: int, value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise MappingError(f"{path.name}:{line}: weight {value!r} is not an integer") from None
    if number <= 0:
        raise MappingError(f"{path.name}:{line}: weight must be positive, got {number}")
    return number


def _unique(path: Path, values: list[str], what: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise MappingError(f"{path.name}: duplicate {what} {value!r}")
        seen.add(value)


def _choice(path: Path, line: int, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise MappingError(f"{path.name}:{line}: {value!r} is not one of {allowed}")
    return value


def _load_fx(path: Path) -> dict[str, float]:
    rows = _read(path, ("currency", "iso_code", "idr_per_unit", "rate_date", "source"))
    _unique(path, [r["currency"] for r in rows], "currency")
    fx: dict[str, float] = {}
    for line, row in enumerate(rows, start=2):
        try:
            rate = float(row["idr_per_unit"])
        except ValueError:
            raise MappingError(
                f"{path.name}:{line}: rate {row['idr_per_unit']!r} is not a number"
            ) from None
        if not math.isfinite(rate) or rate <= 0:
            raise MappingError(f"{path.name}:{line}: rate must be positive")
        fx[row["currency"]] = rate
    return fx


def _load_institutions(path: Path) -> tuple[Institution, ...]:
    rows = _read(path, ("name", "short_name", "kind", "group", "weight"))
    _unique(path, [r["name"] for r in rows], "institution name")
    institutions = tuple(
        Institution(
            name=r["name"],
            short_name=r["short_name"],
            kind=_choice(path, line, r["kind"], INSTITUTION_KINDS),
            group=r["group"],
            weight=_positive_int(path, line, r["weight"]),
        )
        for line, r in enumerate(rows, start=2)
    )
    for kind in INSTITUTION_KINDS:
        if not any(i.kind == kind for i in institutions):
            raise MappingError(f"{path.name}: needs at least one {kind!r} row")
    return institutions


def _load_cities(path: Path) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for row in _read(path, ("province", "city")):
        grouped.setdefault(row["province"], []).append(row["city"])
    if set(grouped) != set(PROVINCES):
        raise MappingError(
            f"{path.name}: provinces must equal geo.PROVINCES; "
            f"missing {sorted(set(PROVINCES) - set(grouped))}, "
            f"unknown {sorted(set(grouped) - set(PROVINCES))}"
        )
    return {province: tuple(cities) for province, cities in grouped.items()}


def _load_sectors(path: Path) -> dict[str, tuple[tuple[str, int], ...]]:
    grouped: dict[str, list[tuple[str, int]]] = {kind: [] for kind in ENTITY_KINDS}
    for line, row in enumerate(_read(path, ("applies_to", "label", "weight")), start=2):
        kind = _choice(path, line, row["applies_to"], ENTITY_KINDS)
        grouped[kind].append((row["label"], _positive_int(path, line, row["weight"])))
    for kind, items in grouped.items():
        if not items:
            raise MappingError(f"{path.name}: needs at least one {kind!r} row")
    return {kind: tuple(items) for kind, items in grouped.items()}


def load_mappings(directory: Path = MAPPINGS_DIR) -> Mappings:
    fx_path = directory / "fx_rates.csv"
    channels_path = directory / "channels.csv"
    types_path = directory / "entity_types.csv"
    institutions_path = directory / "institutions.csv"
    cities_path = directory / "provinces_cities.csv"
    kyc_path = directory / "kyc_status.csv"
    sectors_path = directory / "sectors_occupations.csv"

    fx = _load_fx(fx_path)

    channel_rows = _read(channels_path, ("ibm_format", "channel"))
    _unique(channels_path, [r["ibm_format"] for r in channel_rows], "ibm_format")
    _unique(channels_path, [r["channel"] for r in channel_rows], "channel")
    channels = {r["ibm_format"]: r["channel"] for r in channel_rows}

    type_rows = _read(types_path, ("ibm_prefix", "entity_type", "kind"))
    _unique(types_path, [r["ibm_prefix"] for r in type_rows], "ibm_prefix")
    entity_types = {
        r["ibm_prefix"]: (r["entity_type"], _choice(types_path, line, r["kind"], ENTITY_KINDS))
        for line, r in enumerate(type_rows, start=2)
    }

    kyc_rows = _read(kyc_path, ("status", "weight"))
    _unique(kyc_path, [r["status"] for r in kyc_rows], "status")
    kyc = tuple(
        (r["status"], _positive_int(kyc_path, line, r["weight"]))
        for line, r in enumerate(kyc_rows, start=2)
    )

    files = (fx_path, channels_path, types_path, institutions_path, cities_path, kyc_path,
             sectors_path)
    return Mappings(
        fx=fx,
        channels=channels,
        entity_types=entity_types,
        institutions=_load_institutions(institutions_path),
        cities=_load_cities(cities_path),
        kyc=kyc,
        sectors=_load_sectors(sectors_path),
        hashes={f.name: sha256_file(f) for f in files},
    )
