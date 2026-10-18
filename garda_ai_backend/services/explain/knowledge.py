"""Small curated AML knowledge base for the Insight Narrator, plus deterministic mappings.

Entries are short PARAPHRASED summaries written for analyst context, not legal text:
they deliberately avoid citing article (pasal) numbers or deadlines. Retrieval is
deterministic (tag intersection with the risk-factor codes and the typology), so the
LLM only ever sees, and may only cite, entries the server chose.
"""

from collections.abc import Iterable
from typing import Any, TypedDict


class KnowledgeEntry(TypedDict):
    id: str
    title: str
    tags: tuple[str, ...]
    text: str


GENERAL_IDS = ("uu-tppu-umum", "ppatk-ltkm-indikator")
REPORTING_ID = "uu-tppu-pelaporan"
MAX_REFERENCES = 5

ENTRIES: tuple[KnowledgeEntry, ...] = (
    {
        "id": "uu-tppu-umum",
        "title": "UU No. 8 Tahun 2010 tentang Pencegahan dan Pemberantasan TPPU",
        "tags": ("general",),
        "text": (
            "Undang-undang ini menjadi dasar hukum pencegahan dan pemberantasan tindak "
            "pidana pencucian uang di Indonesia. Pencucian uang dipahami sebagai upaya "
            "menempatkan, mentransfer, atau menyamarkan harta kekayaan yang diketahui atau "
            "patut diduga berasal dari tindak pidana agar asal-usulnya tampak sah. "
            "Undang-undang ini juga menetapkan PPATK sebagai lembaga intelijen keuangan."
        ),
    },
    {
        "id": REPORTING_ID,
        "title": "Kewajiban pelaporan pihak pelapor kepada PPATK",
        "tags": ("reporting",),
        "text": (
            "Penyedia jasa keuangan sebagai pihak pelapor wajib menyampaikan laporan kepada "
            "PPATK, antara lain Laporan Transaksi Keuangan Mencurigakan (LTKM). Pihak "
            "pelapor dilarang memberitahukan kepada pengguna jasa atau pihak lain bahwa "
            "laporan sedang disusun atau telah disampaikan (anti tipping-off)."
        ),
    },
    {
        "id": "pojk-apuppt-cdd",
        "title": "POJK No. 8 Tahun 2023: CDD dan EDD berbasis risiko",
        "tags": ("high_risk_profile", "high_model_score"),
        "text": (
            "POJK tentang penerapan program APU-PPT di sektor jasa keuangan mewajibkan "
            "penyedia jasa keuangan melakukan uji tuntas nasabah (Customer Due Diligence) "
            "dengan pendekatan berbasis risiko. Untuk nasabah atau transaksi berisiko "
            "tinggi diterapkan uji tuntas yang ditingkatkan (Enhanced Due Diligence), "
            "termasuk pendalaman sumber dana dan tujuan transaksi."
        ),
    },
    {
        "id": "pojk-apuppt-pemantauan",
        "title": "POJK No. 8 Tahun 2023: pemantauan transaksi berkelanjutan",
        "tags": ("high_velocity", "unusual_amount", "flagged_counterparty"),
        "text": (
            "Penyedia jasa keuangan diharapkan memantau transaksi nasabah secara "
            "berkelanjutan dan memiliki sistem untuk mengidentifikasi transaksi yang tidak "
            "sesuai dengan profil, karakteristik, atau kebiasaan nasabah. Hasil pemantauan "
            "menjadi dasar analisis lanjutan dan keputusan pelaporan."
        ),
    },
    {
        "id": "ppatk-ltkm-indikator",
        "title": "Indikator Transaksi Keuangan Mencurigakan (PPATK)",
        "tags": ("general",),
        "text": (
            "Transaksi keuangan mencurigakan antara lain transaksi yang menyimpang dari "
            "profil, karakteristik, atau kebiasaan pola transaksi pengguna jasa; transaksi "
            "yang patut diduga dilakukan untuk menghindari pelaporan; serta transaksi "
            "dengan dana yang diduga berasal dari tindak pidana. Transaksi demikian "
            "dilaporkan kepada PPATK sebagai LTKM."
        ),
    },
    {
        "id": "tipologi-fan-in",
        "title": "Tipologi fan-in / rekening penampung (money mule)",
        "tags": ("high_fan_in", "typ:fan_in"),
        "text": (
            "Pola fan-in terjadi ketika satu rekening menerima dana dari banyak pengirim "
            "berbeda dalam waktu singkat. Pola ini sering dikaitkan dengan rekening "
            "penampung (money mule) yang mengumpulkan dana sebelum dipindahkan lebih lanjut."
        ),
    },
    {
        "id": "tipologi-fan-out",
        "title": "Tipologi fan-out / smurfing (structuring)",
        "tags": ("high_fan_out", "typ:fan_out"),
        "text": (
            "Pola fan-out terjadi ketika satu rekening mengirim dana ke banyak penerima "
            "berbeda. Smurfing atau structuring adalah pemecahan dana menjadi banyak "
            "transaksi atau rekening bernilai lebih kecil untuk menyamarkan jumlah total "
            "atau menghindari ambang pelaporan."
        ),
    },
    {
        "id": "tipologi-cycle",
        "title": "Tipologi siklus / round-tripping",
        "tags": ("typ:cycle",),
        "text": (
            "Pada pola siklus (round-tripping), dana berpindah melalui serangkaian rekening "
            "perantara dan akhirnya kembali ke rekening asal atau pihak terkait. Pola ini "
            "dapat digunakan untuk menciptakan kesan aktivitas usaha yang sah."
        ),
    },
    {
        "id": "tipologi-gather-scatter",
        "title": "Tipologi gather-scatter / layering",
        "tags": ("typ:gather_scatter", "typ:layering"),
        "text": (
            "Pada pola gather-scatter, dana dikumpulkan dari banyak sumber ke satu rekening "
            "lalu segera disebar ke banyak tujuan. Pola ini merupakan bentuk layering, yaitu "
            "pelapisan transaksi untuk memutus jejak asal-usul dana."
        ),
    },
    {
        "id": "faktor-velositas",
        "title": "Velositas transaksi tinggi",
        "tags": ("high_velocity", "typ:layering"),
        "text": (
            "Frekuensi transaksi yang tinggi dalam jangka waktu pendek, terutama dana yang "
            "masuk lalu segera keluar, dapat menandakan rekening transit yang dipakai untuk "
            "melapis transaksi, bukan untuk kebutuhan ekonomi yang wajar."
        ),
    },
    {
        "id": "faktor-nominal",
        "title": "Nominal tidak sesuai profil",
        "tags": ("unusual_amount",),
        "text": (
            "Nominal transaksi yang jauh di atas kebiasaan rekening merupakan penyimpangan "
            "dari profil transaksi dan perlu diverifikasi terhadap sumber dana serta tujuan "
            "transaksi yang dinyatakan nasabah."
        ),
    },
    {
        "id": "faktor-lintas-bank",
        "title": "Aliran dana lintas bank",
        "tags": ("cross_bank",),
        "text": (
            "Perpindahan dana antar bank membuat satu institusi hanya melihat sebagian "
            "rantai transaksi. Analisis jaringan lintas institusi membantu mengenali pola "
            "yang tidak tampak dari data satu bank saja."
        ),
    },
    {
        "id": "faktor-jaringan",
        "title": "Keterhubungan dengan rekening berisiko",
        "tags": ("flagged_counterparty", "typology_detected", "typ:network"),
        "text": (
            "Rekening yang bertransaksi dengan rekening lain yang telah terflag atau diblokir "
            "memiliki risiko lebih tinggi untuk menjadi bagian dari jaringan yang sama. "
            "Keterhubungan ini perlu dinilai bersama indikator lain, bukan sebagai bukti "
            "tunggal."
        ),
    },
)

BY_ID: dict[str, KnowledgeEntry] = {e["id"]: e for e in ENTRIES}

# --- typology -> tag ------------------------------------------------------------------

_TYPOLOGY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("fan-in", "fan_in"), ("fan in", "fan_in"), ("mule", "fan_in"),
    ("fan-out", "fan_out"), ("fan out", "fan_out"), ("smurf", "fan_out"),
    ("cycle", "cycle"), ("round", "cycle"),
    ("gather", "gather_scatter"), ("scatter", "gather_scatter"),
    ("layering", "layering"),
)


def typology_tag(typology: str | None) -> str | None:
    """Normalise a free-text typology label to a KB tag key, e.g. 'Fan-Out' -> 'fan_out'."""
    if not typology:
        return None
    t = typology.lower()
    for kw, tag in _TYPOLOGY_KEYWORDS:
        if kw in t:
            return tag
    return "network"


def retrieve(
    factor_codes: Iterable[str], typology: str | None, extra_ids: Iterable[str] = ()
) -> list[KnowledgeEntry]:
    """Deterministic retrieval: typology/factor matches first, then the general entries.

    Always returns the two general entries; at most MAX_REFERENCES in total.
    """
    tags: list[str] = []
    tt = typology_tag(typology)
    if tt:
        tags.append(f"typ:{tt}")
    tags.extend(factor_codes)
    pinned = [*extra_ids, *GENERAL_IDS]
    specific_budget = max(0, MAX_REFERENCES - len(pinned))
    chosen: list[str] = []
    for tag in tags:  # priority order: typology, then factor order
        for e in ENTRIES:
            if len(chosen) >= specific_budget:
                break
            if tag in e["tags"] and e["id"] not in chosen and e["id"] not in pinned:
                chosen.append(e["id"])
    ids = chosen + [i for i in pinned if i in BY_ID]
    return [BY_ID[i] for i in ids[:MAX_REFERENCES]]


def reference_refs(entries: Iterable[KnowledgeEntry]) -> list[dict[str, str]]:
    return [{"id": e["id"], "title": e["title"]} for e in entries]


def filter_references(raw: Any, allowed: list[KnowledgeEntry]) -> list[dict[str, str]] | None:
    """Keep only ids the server provided, de-duplicated, titles filled server-side.

    None when the field is unusable (missing, wrong type, or nothing valid left) so the
    caller can fall back deterministically.
    """
    if not isinstance(raw, list):
        return None
    allowed_ids = {e["id"] for e in allowed}
    out: list[dict[str, str]] = []
    for item in raw:
        rid = item.get("id") if isinstance(item, dict) else item
        if isinstance(rid, str) and rid in allowed_ids and all(r["id"] != rid for r in out):
            out.append({"id": rid, "title": BY_ID[rid]["title"]})
    return out or None


# --- reason codes and confidence -------------------------------------------------------

REASON_CODES: dict[str, str] = {
    "GA-FANIN": "Pola fan-in / rekening penampung",
    "GA-FANOUT": "Pola fan-out / smurfing",
    "GA-CYCLE": "Pola siklus / round-tripping",
    "GA-GATHER": "Pola gather-scatter / layering",
    "GA-VELOCITY": "Velositas transaksi tinggi",
    "GA-AMOUNT": "Nominal tidak sesuai profil",
    "GA-NETWORK": "Keterhubungan jaringan berisiko",
    "GA-NORMAL": "Tidak ada indikator signifikan",
}

_TYPOLOGY_REASON = {
    "fan_in": "GA-FANIN", "fan_out": "GA-FANOUT", "cycle": "GA-CYCLE",
    "gather_scatter": "GA-GATHER", "layering": "GA-GATHER",
}
_NETWORK_FACTORS = frozenset(
    {"flagged_counterparty", "typology_detected", "high_model_score", "high_risk_profile"}
)
_FACTOR_REASON = (
    ("high_fan_in", "GA-FANIN"), ("high_fan_out", "GA-FANOUT"),
    ("high_velocity", "GA-VELOCITY"), ("unusual_amount", "GA-AMOUNT"),
)


def deterministic_reason_code(typology: str | None, factor_codes: Iterable[str]) -> str:
    """Typology label first, then structural factors, then any factor -> GA-NETWORK."""
    codes = set(factor_codes)
    tt = typology_tag(typology)
    if tt in _TYPOLOGY_REASON:
        return _TYPOLOGY_REASON[tt]
    if {"high_fan_in", "high_fan_out"} <= codes:
        return "GA-GATHER"
    for code, reason in _FACTOR_REASON:
        if code in codes:
            return reason
    return "GA-NETWORK" if codes & _NETWORK_FACTORS else "GA-NORMAL"


def normalize_reason_code(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    code = raw.strip().upper()
    return code if code in REASON_CODES else None


CONFIDENCE_LEVELS = ("Tinggi", "Sedang", "Rendah")


def confidence_from_score(score: float) -> str:
    if score >= 0.85:
        return "Tinggi"
    if score >= 0.6:
        return "Sedang"
    return "Rendah"


def normalize_confidence(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip().capitalize()
    return value if value in CONFIDENCE_LEVELS else None
