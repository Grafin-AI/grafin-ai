"""LLM narrative over the evidence, via plain httpx REST (no SDKs).

Providers: anthropic (Messages API), gemini (generateContent), ollama (/api/chat).
Any failure (transport, timeout, non-2xx, unparsable/invalid JSON) returns None and
the caller falls back to the rules narrative. The API key is never logged: failures
are logged by exception type only, because httpx error messages can embed the URL.
Gemini/Gemma (same API) get the key in the x-goog-api-key header, never in the URL.
"""

import json
from typing import Any

import httpx
import structlog

from garda_ai_backend.config import Settings
from garda_ai_backend.services.explain.knowledge import (
    REASON_CODES,
    KnowledgeEntry,
    normalize_confidence,
    normalize_reason_code,
)
from garda_ai_backend.services.explain.rules import ACTION_VERBS, NARRATIVE_FIELDS

log = structlog.get_logger()

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "gemini": "gemini-3.8-flash",
    "ollama": "llama3.1:8b",
}
DEFAULT_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "ollama": "http://host.docker.internal:11434",
}

SYSTEM_PROMPT = (
    "Anda adalah analis Anti Pencucian Uang (APU) senior yang menyusun penjelasan "
    "transaksi untuk konteks regulator Indonesia (OJK, Bank Indonesia, PPATK). "
    "Tulis dalam Bahasa Indonesia baku dan formal. "
    "Gunakan HANYA data pada JSON bukti (evidence), daftar faktor risiko, dan daftar "
    "rujukan (references) yang diberikan. Jangan pernah mengarang perangkat, alamat IP, "
    "lokasi, nama, nominal, nomor pasal, tenggat waktu, peraturan, atau fakta lain yang "
    "tidak tercantum. Jika mengacu pada regulasi, gunakan hanya isi rujukan yang diberikan. "
    "Skor berasal dari model graph neural network (GNN) yang menilai transaksi dalam "
    "graf rekening; jelaskan sinyal pola dan jaringan dengan istilah tersebut "
    "(keterhubungan rekening, fan-in, fan-out, velositas). "
    "Jangan menjadikan jam transaksi sebagai indikator risiko (data ini tidak memiliki "
    "pola harian yang bermakna). "
    "Setiap bidang naratif terdiri dari 2-4 kalimat. "
    "Balas HANYA dengan satu objek JSON valid tanpa teks lain, dengan kunci: "
    "\"pattern_matching\", \"behavior_analysis\", \"network_analysis\", "
    "\"recommendation\" (string), \"reason_code\" (salah satu kode alasan yang "
    "diberikan), \"confidence\" (\"Tinggi\", \"Sedang\", atau \"Rendah\"), dan "
    "\"references\" (array berisi id rujukan yang benar-benar Anda gunakan). "
    "Bidang \"recommendation\" WAJIB diawali kata kerja tindakan "
    "dalam huruf kapital yang diberikan (PROSES, TINJAU, TUNDA, atau BLOKIR)."
)


def _reference_payload(references: list[KnowledgeEntry]) -> list[dict[str, str]]:
    return [{"id": e["id"], "title": e["title"], "text": e["text"]} for e in references]


def build_user_prompt(
    evidence: dict[str, Any],
    factors: list[dict],
    action: str,
    references: list[KnowledgeEntry] | None = None,
) -> str:
    payload = {"evidence": evidence, "risk_factors": factors}
    refs = _reference_payload(references or [])
    return (
        "Data transaksi (JSON):\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Rujukan yang boleh digunakan (JSON):\n"
        f"{json.dumps(refs, ensure_ascii=False, indent=2)}\n\n"
        "Kode alasan yang tersedia (JSON):\n"
        f"{json.dumps(REASON_CODES, ensure_ascii=False)}\n\n"
        f"Tindakan sistem berdasarkan status: {action}. Awali \"recommendation\" dengan "
        f"kata \"{action}\".\n"
        "Kembalikan objek JSON dengan kunci pattern_matching, behavior_analysis, "
        "network_analysis, recommendation, reason_code, confidence, references."
    )


def resolve_model(settings: Settings) -> str:
    return settings.llm_model or DEFAULT_MODELS.get(settings.llm_provider, "")


def _base_url(settings: Settings) -> str:
    return (settings.llm_base_url or DEFAULT_BASE_URLS[settings.llm_provider]).rstrip("/")


async def _anthropic(client: httpx.AsyncClient, s: Settings, system: str, user: str) -> str:
    resp = await client.post(
        f"{_base_url(s)}/v1/messages",
        headers={
            "x-api-key": s.llm_api_key.get_secret_value(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": resolve_model(s),
            "max_tokens": 1500,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=s.llm_timeout_s,
    )
    resp.raise_for_status()
    blocks = resp.json().get("content") or []
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


async def _gemini(client: httpx.AsyncClient, s: Settings, system: str, user: str) -> str:
    model = resolve_model(s)
    body: dict[str, Any]
    if model.startswith("gemma"):
        # Gemma on the Gemini API rejects systemInstruction and JSON mode: fold the system
        # prompt into the user turn and rely on parse_narrative to pull out the JSON.
        body = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {"temperature": 0.2},
        }
    else:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        }
    resp = await client.post(
        f"{_base_url(s)}/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": s.llm_api_key.get_secret_value()},
        json=body,
        timeout=s.llm_timeout_s,
    )
    resp.raise_for_status()
    parts = resp.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


async def _ollama(client: httpx.AsyncClient, s: Settings, system: str, user: str) -> str:
    resp = await client.post(
        f"{_base_url(s)}/api/chat",
        json={
            "model": resolve_model(s),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        },
        timeout=s.llm_timeout_s,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


_PROVIDERS = {"anthropic": _anthropic, "gemini": _gemini, "ollama": _ollama}


def extract_json_object(text: str) -> dict[str, Any] | None:
    """One JSON object from model output, tolerating ``` fences and surrounding prose."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    try:
        obj = json.loads(t)
    except ValueError:
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(t[start:end + 1])
        except ValueError:
            return None
    return obj if isinstance(obj, dict) else None


def parse_narrative(text: str, action: str) -> dict[str, Any] | None:
    """The 4 narrative fields are mandatory (else None -> rules fallback). The extra
    fields are best-effort: ``reason_code``/``confidence`` are None when invalid and
    ``references`` is the raw list (or None); the service fills deterministic fallbacks."""
    obj = extract_json_object(text)
    if obj is None:
        return None
    out: dict[str, Any] = {}
    for key in NARRATIVE_FIELDS:
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        out[key] = value.strip()
    first = out["recommendation"].split(maxsplit=1)[0].strip(".,:;-")
    if first not in ACTION_VERBS:
        out["recommendation"] = f"{action}: {out['recommendation']}"
    out["reason_code"] = normalize_reason_code(obj.get("reason_code"))
    out["confidence"] = normalize_confidence(obj.get("confidence"))
    refs = obj.get("references")
    out["references"] = refs if isinstance(refs, list) else None
    return out


async def complete(
    client: httpx.AsyncClient, settings: Settings, system: str, user: str, purpose: str
) -> str | None:
    """Raw model text, or None on any provider failure (logged by exception type only)."""
    provider = _PROVIDERS.get(settings.llm_provider)
    if provider is None:
        return None
    try:
        return await provider(client, settings, system, user)
    except Exception as exc:  # noqa: BLE001 — any provider failure means fallback
        log.warning(
            f"{purpose}.llm_failed", provider=settings.llm_provider,
            model=resolve_model(settings), error=type(exc).__name__,
        )
        return None


async def llm_narrative(
    client: httpx.AsyncClient,
    settings: Settings,
    evidence: dict[str, Any],
    factors: list[dict],
    action: str,
    references: list[KnowledgeEntry] | None = None,
) -> dict[str, Any] | None:
    text = await complete(
        client, settings, SYSTEM_PROMPT,
        build_user_prompt(evidence, factors, action, references), "explain",
    )
    if text is None:
        return None
    parsed = parse_narrative(text, action)
    if parsed is None:
        log.warning(
            "explain.llm_invalid_output", provider=settings.llm_provider,
            model=resolve_model(settings),
        )
    return parsed
