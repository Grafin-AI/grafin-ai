# garda-ai-dataset

A deterministic, validated localization of IBM's synthetic AML data (AMLworld,
[Kaggle](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml),
NeurIPS 2023) into Indonesian terms. It covers **HI-Small** (used by the platform demo) and
**HI-Medium** (used for training).

The design and its reasoning are in
`docs/superpowers/specs/2026-10-16-hi-dataset-localization-design.md`.

## Quick start

```bash
uv sync
make all DATASET=small KAGGLE_JSON=/path/to/kaggle.json    # fetch + localize + validate
make all DATASET=medium KAGGLE_JSON=/path/to/kaggle.json   # ~3.2 GB download
```

- `KAGGLE_JSON` defaults to `$GARDA_KAGGLE_JSON`, then `~/.kaggle/kaggle.json`.
- **Output** goes to `../garda-ai-data/HI-<Size>-ID/`. Override the location with `GARDA_DATA_ROOT` or `--data-root`.
- **Raw files** are stored in `../garda-ai-data/raw/HI-<Size>/`, alongside a `SHA256SUMS` file.
- **Re-runs are byte-identical**, except for the timestamps in `MANIFEST.json`.

## What changes, and what never does

| Kept exactly | Changed |
|---|---|
| Graph topology `(bank, account)` → `(bank, account)`, edge order, every `Is Laundering` label | Amounts converted to IDR at one fixed rate per currency (2025-09-04); never capped |
| Row count and rows per day | Payment formats renamed one-to-one to Indonesian channels (`ACH` → `BI-FAST`, …) |
| Day of week (dates shift by exactly 157 weeks) | Bank IDs keep their identity; names become real Indonesian institutions |
| | Entity names become Indonesian; the type comes from IBM's own prefix (PT/CV/UD/Lembaga/Perorangan) |

Every rule is a CSV in `mappings/`. Edit the CSV, re-run, and the manifest records the new hash.

## Outputs

- `HI-<X>_Trans_sorted.csv`: the same 11 columns as IBM, sorted by time. `transaction_id` is the 1-based row number.
- `HI-<X>_accounts.csv`: the same header as before. `risk_score` and `risk_category` are a transitional carry-over for Small and empty for Medium; real values come from the model.
- `HI-<X>_entities.csv`: entity type, province, city, registration date, KYC status and sector. These are **synthetic, display-only** fields for the Users tab and are never model features.
- `HI-<X>_typologies.csv`: the true IBM motif of each laundering transaction, or `UNATTRIBUTED`.
- `HI-<X>_Patterns.txt`: IBM's pattern file, re-expressed with the localized rows.
- `MANIFEST.json`: input, mapping and output hashes, counts and typology coverage.

## Validation

`localize` always ends with `validate`, which re-derives every invariant from the raw files and fails the build on any violation:
- row count, labels, graph keys and node merges;
- FX, time shift, order and channels;
- label independence: inverting every label must leave every non-label output byte-identical;
- patterns, entities, and manifest hashes.

## Using it on the platform

In `garda-ai-deploy/.env`, set `GARDA_DATA_HOST_DIR=../garda-ai-data/HI-Small-ID`, then reseed:
`make down`, `docker compose down -v`, `make up`, then `make demo-seed`.

The demo row offsets still land on day boundaries, because the number of rows per day is unchanged. The calendar dates move from Sep 3–9 to Sep 6–12.

## Honest framing for judges

> Synthetic data. Graph topology and laundering labels come from IBM AMLworld (NeurIPS 2023).
> Indonesian channels, institutions and currency are mapped with documented, verifiable rules.
> No real customer data is used, in line with UU PDP and bank secrecy. A production system would
> be trained on partner-bank data under an MoU.

QRIS, e-wallets and Indonesia-specific typologies (judi online, mule fan-in, pig-butchering) are not in this version. They are planned as a separate, injected-typology dataset.

## Verified builds

### HI-Small (2026-10-16)

`make all DATASET=small`: every validation check `PASS`, exit 0.

| Item | Value |
|---|---|
| Transactions | 5,078,345 |
| Laundering rows | 5,177 |
| Accounts / entities / banks | 518,581 / 166,207 / 30,470 |
| Days | 18 (2025-09-04 to 2025-09-21) |
| Typology | 370 attempts, 3,209 of 3,209 pattern rows matched, laundering coverage 0.6199 |
| Risk source | `legacy-carryover` |
| Wall time | 15.8 s end to end (6.9 s for `localize`) |
| Peak RSS | 1.98 GB |

Consumer smoke tests (read-only):
- **garda-ai-sim reader**: PASS. The first 1,000 rows stream with `payment_currency` = `IDR`.
- **garda-ai-ingest seed parser**: PASS. `LoadCounts(banks=30470, entities=166207, accounts=518581)`, and the account count equals the manifest.
- **Multi-GNN formatter** (`format_kaggle_files.py`): NOT RUN. `datatable==1.1.0` installs on this machine but its native library is x86_64 and will not load on arm64 (`dlopen ... incompatible architecture (have 'x86_64', need 'arm64')`).
