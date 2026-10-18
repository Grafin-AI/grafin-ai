"""LTKM (Laporan Transaksi Keuangan Mencurigakan) draft from a persisted explanation.

A separate LLM call that reuses the provider functions. The model writes only the
narrative parts; the parties (``pihak``) are filled server-side from the transaction
detail, always with masked names when stored, so the LLM never sees or invents a name.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.api.masking import mask_name
from garda_ai_backend.config import Settings
from garda_ai_backend.repositories.explanations import explanations_repository
from garda_ai_backend.repositories.transactions import TransactionsRepository
from garda_ai_backend.schema import StoredExplanation
from garda_ai_backend.services.explain.knowledge import BY_ID, REPORTING_ID, KnowledgeEntry
from garda_ai_backend.services.explain.llm import complete, extract_json_object
from garda_ai_backend.services.explain.rules import NARRATIVE_FIELDS

CATATAN = "DRAF — perlu verifikasi analis sebelum dilaporkan ke PPATK"
MAX_INDICATORS = 8

STR_SYSTEM_PROMPT = (
    "Anda adalah analis kepatuhan Anti Pencucian Uang (APU) yang menyusun DRAF Laporan "
    "Transaksi Keuangan Mencurigakan (LTKM) untuk ditinjau analis sebelum disampaikan "
    "kepada PPATK. Tulis dalam Bahasa Indonesia baku dan formal. "
    "Gunakan HANYA data transaksi, penjelasan analisis, faktor risiko, dan rujukan yang "
    "diberikan. Jangan pernah mengarang nama, identitas, alamat, perangkat, nominal, "
    "tanggal, nomor pasal, tenggat waktu, peraturan, atau fakta lain yang tidak tercantum. "
    "Sebut para pihak hanya sebagai \"Pihak Pengirim\" dan \"Pihak Penerima\". "
    "Balas HANYA dengan satu objek JSON valid tanpa teks lain, dengan kunci: "
    "\"kronologi\" (string, 2-5 kalimat urutan kejadian), \"indikator\" (array string, "
    "1-6 indikator mencurigakan yang didukung data), \"analisis\" (string, 2-5 kalimat), "
    "dan \"rekomendasi\" (string, 1-3 kalimat tindak lanjut)."
)


class StrGenerationFailed(Exception):
    pass


def draft_number(transaction_id: int) -> str:
    return f"LTKM-DRAFT-{transaction_id}"


def _party(name: str | None, account: str, bank: str | None, unmask: bool) -> dict[str, Any]:
    shown = name if (unmask or name is None) else mask_name(name)
    return {"nama": shown, "rekening": account, "bank": bank}


def parties(detail: dict[str, Any], unmask: bool) -> dict[str, Any]:
    return {
        "pengirim": _party(
            detail["from_entity_name"], detail["from_account"],
            detail["from_bank_name"] or detail["from_bank"], unmask,
        ),
        "penerima": _party(
            detail["to_entity_name"], detail["to_account"],
            detail["to_bank_name"] or detail["to_bank"], unmask,
        ),
    }


def build_str_prompt(
    detail: dict[str, Any], row: StoredExplanation, references: list[KnowledgeEntry]
) -> str:
    transaksi = {
        "nomor_draf": draft_number(row.transaction_id),
        "waktu_transaksi": detail["event_time"],
        "nominal": detail["amount"],
        "mata_uang": detail["currency"],
        "kanal": detail["type"],
        "bank_pengirim": detail["from_bank_name"] or detail["from_bank"],
        "bank_penerima": detail["to_bank_name"] or detail["to_bank"],
        "status_sistem": detail["status"],
        "skor_risiko_gnn": detail["fraud_score"],
        "tipologi": detail["typology"],
    }
    analisis = {k: getattr(row, k) for k in NARRATIVE_FIELDS}
    analisis["reason_code"] = row.reason_code
    analisis["confidence"] = row.confidence
    payload = {
        "transaksi": transaksi,
        "penjelasan": analisis,
        "faktor_risiko": row.risk_factors,
        "bukti": row.evidence,
        "rujukan": [{"id": e["id"], "title": e["title"], "text": e["text"]} for e in references],
    }
    return (
        "Data untuk draf LTKM (JSON):\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Kembalikan objek JSON dengan kunci kronologi, indikator, analisis, rekomendasi."
    )


def parse_str_draft(text: str) -> dict[str, Any] | None:
    obj = extract_json_object(text)
    if obj is None:
        return None
    out: dict[str, Any] = {}
    for key in ("kronologi", "analisis", "rekomendasi"):
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        out[key] = value.strip()
    raw = obj.get("indikator")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return None
    indicators = [i.strip() for i in raw if isinstance(i, str) and i.strip()]
    if not indicators:
        return None
    out["indikator"] = indicators[:MAX_INDICATORS]
    return out


def _references_for(row: StoredExplanation) -> list[KnowledgeEntry]:
    ids = [r["id"] for r in row.references if r.get("id") in BY_ID]
    if REPORTING_ID not in ids:
        ids.append(REPORTING_ID)
    return [BY_ID[i] for i in ids]


async def _complete(
    client: httpx.AsyncClient | None, settings: Settings, user: str
) -> str | None:
    if client is not None:
        return await complete(client, settings, STR_SYSTEM_PROMPT, user, "str_draft")
    async with httpx.AsyncClient() as own:
        return await complete(own, settings, STR_SYSTEM_PROMPT, user, "str_draft")


async def generate_str_draft(
    session: AsyncSession,
    client: httpx.AsyncClient | None,
    settings: Settings,
    row: StoredExplanation,
) -> dict[str, Any]:
    """Return the stored draft or generate + store one. Raises StrGenerationFailed."""
    if row.str_draft is not None:
        return row.str_draft
    detail = await TransactionsRepository(session).detail(row.transaction_id)
    if detail is None or settings.llm_provider == "none":
        raise StrGenerationFailed
    text = await _complete(client, settings, build_str_prompt(detail, row, _references_for(row)))
    parsed = parse_str_draft(text) if text is not None else None
    if parsed is None:
        raise StrGenerationFailed
    draft = {
        "nomor_draf": draft_number(row.transaction_id),
        "pihak": parties(detail, unmask=False),  # stored masked, always
        "kronologi": parsed["kronologi"],
        "indikator": parsed["indikator"],
        "analisis": parsed["analisis"],
        "rekomendasi": parsed["rekomendasi"],
        "catatan": CATATAN,
    }
    stored = await explanations_repository(session, settings).set_str_draft_if_absent(
        row.transaction_id, draft, datetime.now(UTC)
    )
    assert stored.str_draft is not None
    return stored.str_draft


async def present_draft(
    session: AsyncSession, transaction_id: int, draft: dict[str, Any], unmask: bool
) -> dict[str, Any]:
    """Stored drafts carry masked names; an admin asking ?unmasked=true gets raw ones."""
    if not unmask:
        return draft
    detail = await TransactionsRepository(session).detail(transaction_id)
    if detail is None:
        return draft
    return {**draft, "pihak": parties(detail, unmask=True)}
