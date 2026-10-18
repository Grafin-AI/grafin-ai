"""Entity names, types, display-only profile fields, and the accounts file (spec 6.4).

Nothing here reads the Is Laundering label. Profile fields are for the Users tab only and
are never model features.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from faker import Faker

from grafin_ai_dataset.errors import MappingError, RawInputError
from grafin_ai_dataset.geo import province_for_entity
from grafin_ai_dataset.hashing import stable_int, weighted_pick
from grafin_ai_dataset.mappings import Mappings

ENTITY_COLUMNS = (
    "Entity ID",
    "Entity Name",
    "Entity Type",
    "Province",
    "City",
    "Registration Date",
    "KYC Status",
    "Sector",
)
ACCOUNT_COLUMNS = (
    "Bank Name",
    "Bank ID",
    "Account Number",
    "Entity ID",
    "Entity Name",
    "risk_score",
    "risk_category",
)
BUSINESS_SUFFIXES = (
    "Jaya", "Abadi", "Sejahtera", "Makmur", "Mandiri",
    "Sentosa", "Utama", "Perkasa", "Nusantara", "Lestari",
)
MIN_ACCOUNT_AGE_DAYS = 30
MAX_ACCOUNT_AGE_DAYS = 3650
_PREFIX = re.compile(r"^(?P<prefix>.+?) #\d+$")


def entity_prefix(ibm_name: str) -> str:
    match = _PREFIX.match(ibm_name)
    if match is None:
        raise MappingError(f"entity name {ibm_name!r} has no '<Prefix> #<n>' marker")
    return match.group("prefix")


def localized_name(entity_id: str, entity_type: str, kind: str, fake: Faker) -> str:
    fake.seed_instance(stable_int("name", entity_id))
    if kind == "individual":
        return f"{fake.first_name()} {fake.last_name()}"
    suffix = BUSINESS_SUFFIXES[stable_int("suffix", entity_id) % len(BUSINESS_SUFFIXES)]
    return f"{entity_type} {fake.last_name()} {suffix}"


def first_seen_by_entity(trans: pl.LazyFrame, raw_accounts: pl.DataFrame) -> dict[str, date]:
    """Earliest localized transaction date per entity, as sender OR receiver.

    ``trans`` needs Int64 ``from_bank``/``to_bank``, text accounts, and a datetime ``ts``.
    """
    sides = pl.concat(
        [
            trans.select(pl.col("from_bank").alias("bank"), pl.col("from_account").alias("account"), "ts"),
            trans.select(pl.col("to_bank").alias("bank"), pl.col("to_account").alias("account"), "ts"),
        ]
    )
    per_account = sides.group_by("bank", "account").agg(pl.col("ts").min())
    owners = raw_accounts.lazy().select(
        pl.col("Bank ID").cast(pl.Int64).alias("bank"),
        pl.col("Account Number").alias("account"),
        "Entity ID",
    )
    per_entity = (
        per_account.join(owners, on=["bank", "account"], how="inner")
        .group_by("Entity ID")
        .agg(pl.col("ts").min().dt.date().alias("first_seen"))
        .collect()
    )
    return dict(
        zip(per_entity["Entity ID"].to_list(), per_entity["first_seen"].to_list(), strict=True)
    )


def check_entity_prefixes(raw_accounts: pl.DataFrame, maps: Mappings) -> None:
    """Fail early, naming every IBM entity prefix the mapping table doesn't cover."""
    names = raw_accounts.group_by("Entity ID").agg(pl.col("Entity Name").min())["Entity Name"]
    prefixes = {entity_prefix(name) for name in names.to_list()}
    unknown = sorted(prefixes - maps.entity_types.keys())
    if unknown:
        raise MappingError(f"entity prefixes missing from mappings/entity_types.csv: {unknown}")


def build_entities(
    raw_accounts: pl.DataFrame,
    first_seen: dict[str, date],
    fallback_day: date,
    maps: Mappings,
) -> pl.DataFrame:
    check_entity_prefixes(raw_accounts, maps)
    entities = raw_accounts.group_by("Entity ID").agg(pl.col("Entity Name").min()).sort("Entity ID")
    fake = Faker("id_ID")
    rows: list[tuple[str, ...]] = []
    for entity_id, ibm_name in entities.iter_rows():
        entity_type, kind = maps.entity_types[entity_prefix(ibm_name)]
        province = province_for_entity(entity_id)
        cities = maps.cities[province]
        age_days = MIN_ACCOUNT_AGE_DAYS + stable_int("registration", entity_id) % (
            MAX_ACCOUNT_AGE_DAYS - MIN_ACCOUNT_AGE_DAYS + 1
        )
        registered = first_seen.get(entity_id, fallback_day) - timedelta(days=age_days)
        rows.append(
            (
                entity_id,
                localized_name(entity_id, entity_type, kind, fake),
                entity_type,
                province,
                cities[stable_int("city", entity_id) % len(cities)],
                registered.isoformat(),
                weighted_pick(maps.kyc, stable_int("kyc", entity_id)),
                weighted_pick(maps.sectors[kind], stable_int("sector", entity_id)),
            )
        )
    return pl.DataFrame(rows, schema={c: pl.String for c in ENTITY_COLUMNS}, orient="row")


def read_legacy_accounts(path: Path) -> pl.DataFrame:
    """Risk columns of the old hand-made copy, keyed by (bank_id, account) (spec 5)."""
    if not path.exists():
        raise RawInputError(f"legacy accounts file not found: {path}")
    df = pl.read_csv(path, infer_schema=False)
    needed = ("Bank ID", "Account Number", "risk_score", "risk_category")
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise RawInputError(f"{path.name}: missing columns {missing}")
    out = df.select(
        pl.col("Bank ID").cast(pl.Int64).alias("bank_id"),
        pl.col("Account Number").alias("account"),
        "risk_score",
        "risk_category",
    )
    if out.select(pl.struct("bank_id", "account").is_duplicated().any()).item():
        raise RawInputError(f"{path.name}: duplicate (Bank ID, Account Number) keys")
    return out


def build_accounts(
    raw_accounts: pl.DataFrame,
    bank_names: dict[int, str],
    entities: pl.DataFrame,
    legacy: pl.DataFrame | None,
) -> pl.DataFrame:
    """Raw accounts in their original order, with Indonesian bank and entity names."""
    df = raw_accounts.with_columns(pl.col("Bank ID").cast(pl.Int64)).with_columns(
        pl.col("Bank ID").replace_strict(bank_names, return_dtype=pl.String).alias("Bank Name")
    )
    df = df.drop("Entity Name").join(
        entities.select("Entity ID", "Entity Name"), on="Entity ID", how="left",
        maintain_order="left",
    )
    if legacy is None:
        df = df.with_columns(
            pl.lit(None, dtype=pl.String).alias("risk_score"),
            pl.lit(None, dtype=pl.String).alias("risk_category"),
        )
    else:
        df = df.join(
            legacy, left_on=["Bank ID", "Account Number"], right_on=["bank_id", "account"],
            how="left", maintain_order="left",
        )
    return df.select(ACCOUNT_COLUMNS)
