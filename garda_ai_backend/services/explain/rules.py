"""Deterministic risk factors and Indonesian narrative built only from evidence.

Nothing here may assert a fact that is not in the evidence dict (no devices, IPs,
geolocation, names). The rules narrative is the fallback whenever the LLM path is
disabled or fails, so it must always produce all four fields.
"""

from typing import Any

from garda_ai_backend.services.explain.evidence import Evidence

HIGH_SCORE = 0.7
FAN_THRESHOLD = 5
VELOCITY_THRESHOLD = 10
AMOUNT_RATIO_THRESHOLD = 5.0
DELAY_SCORE = 0.85

ACTION_VERBS = ("PROSES", "TINJAU", "TUNDA", "BLOKIR")
NARRATIVE_FIELDS = ("pattern_matching", "behavior_analysis", "network_analysis", "recommendation")


def fmt_num(value: float, decimals: int = 0) -> str:
    """Indonesian number format: 15000000.5 -> '15.000.000,50'."""
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_money(amount: float, currency: str | None) -> str:
    cur = "Rp" if (currency or "").upper() in ("IDR", "RP", "RUPIAH") else (currency or "")
    return f"{cur} {fmt_num(amount)}".strip()


def fmt_score(score: float) -> str:
    return fmt_num(score, 2)


def _factor(code: str, label: str, detail: str) -> dict[str, str]:
    return {"code": code, "label": label, "detail": detail}


def risk_factors(ev: Evidence) -> list[dict[str, str]]:
    f: list[dict[str, str]] = []
    if ev["fraud_score"] >= HIGH_SCORE:
        f.append(_factor(
            "high_model_score", "Skor Model Tinggi",
            f"Skor risiko GNN {fmt_score(ev['fraud_score'])} (ambang {fmt_score(HIGH_SCORE)})",
        ))
    if ev.get("typology"):
        f.append(_factor(
            "typology_detected", "Pola Tipologi Terdeteksi",
            f"Pola jaringan di sekitar transaksi: {ev['typology']}",
        ))
    if ev["receiver_distinct_senders_24h"] >= FAN_THRESHOLD:
        f.append(_factor(
            "high_fan_in", "Fan-in Tinggi",
            f"{ev['receiver_distinct_senders_24h']} pengirim berbeda ke rekening penerima "
            "dalam 24 jam",
        ))
    if ev["sender_distinct_receivers_24h"] >= FAN_THRESHOLD:
        f.append(_factor(
            "high_fan_out", "Fan-out Tinggi",
            f"{ev['sender_distinct_receivers_24h']} penerima berbeda dari rekening pengirim "
            "dalam 24 jam",
        ))
    out_n, in_n = ev["sender_out_count_24h"], ev["receiver_in_count_24h"]
    if max(out_n, in_n) >= VELOCITY_THRESHOLD:
        f.append(_factor(
            "high_velocity", "Velositas Tinggi",
            f"{out_n} transaksi keluar pengirim dan {in_n} transaksi masuk penerima dalam 24 jam",
        ))
    # No time-of-day factor: the IBM AML data has a flat hourly profile (night-time laundering
    # rate == daytime rate), so "unusual hour" would fire on ~30% of transactions with no signal.
    ratio = ev.get("amount_vs_sender_median")
    if ratio is not None and ratio >= AMOUNT_RATIO_THRESHOLD:
        f.append(_factor(
            "unusual_amount", "Nominal Tidak Biasa",
            f"Nominal {fmt_num(ratio, 1)}x median transaksi keluar pengirim dalam 24 jam",
        ))
    if ev["cross_bank"]:
        f.append(_factor(
            "cross_bank", "Antar Bank", "Rekening pengirim dan penerima berada di bank berbeda",
        ))
    s_flag, r_flag = ev["sender_flagged_24h"], ev["receiver_flagged_24h"]
    if s_flag > 0 or r_flag > 0:
        f.append(_factor(
            "flagged_counterparty", "Rekanan Terflag",
            f"{s_flag} transaksi lain pengirim dan {r_flag} transaksi lain penerima "
            "berstatus terflag/diblokir dalam 24 jam",
        ))
    high = [
        role for role, key in (("pengirim", "sender_risk_category"),
                               ("penerima", "receiver_risk_category"))
        if (ev.get(key) or "").lower() == "high"
    ]
    if high:
        f.append(_factor(
            "high_risk_profile", "Profil Risiko Tinggi",
            f"Kategori risiko rekening {' dan '.join(high)}: High",
        ))
    return f


def action_verb(ev: Evidence) -> str:
    status = ev["status"]
    if status == "blocked":
        return "BLOKIR"
    if status == "flagged":
        return "TUNDA" if ev["fraud_score"] >= DELAY_SCORE else "TINJAU"
    return "PROSES"


def _cap(sentences: list[str], n: int = 4) -> str:
    return " ".join(sentences[:n])


def rules_narrative(ev: Evidence, factors: list[dict[str, Any]]) -> dict[str, str]:
    score = fmt_score(ev["fraud_score"])
    codes = {f["code"] for f in factors}

    # --- pattern matching
    pm = [
        f"Model graph neural network (GNN) memberikan skor risiko {score} untuk transaksi ini"
        + (", di atas ambang risiko tinggi." if "high_model_score" in codes
           else ", di bawah ambang risiko tinggi.")
    ]
    if ev.get("typology"):
        pm.append(
            f"Pola keterhubungan transaksi diklasifikasikan sebagai tipologi {ev['typology']}."
        )
    else:
        pm.append("Tidak ada tipologi pencucian uang spesifik yang teridentifikasi oleh model.")
    network_codes = codes & {"high_fan_in", "high_fan_out", "high_velocity"}
    if network_codes:
        pm.append(
            "Sinyal struktur jaringan (konsentrasi pengirim/penerima dan frekuensi transaksi) "
            "turut memperkuat penilaian ini."
        )

    # --- behaviour
    money = fmt_money(ev["amount"], ev.get("currency"))
    ba = [
        f"Transaksi senilai {money} melalui kanal {ev['channel']} terjadi pukul "
        f"{ev['hour_of_day']:02d}:00."
    ]
    ba.append(
        f"Dalam 24 jam hingga transaksi ini, rekening pengirim melakukan "
        f"{ev['sender_out_count_24h']} transaksi keluar dengan total "
        f"{fmt_money(ev['sender_out_amount_24h'], ev.get('currency'))}."
    )
    ratio = ev.get("amount_vs_sender_median")
    if ratio is None and ev["sender_out_count_24h"] < 3:
        ba.append(
            "Riwayat transaksi keluar pengirim dalam jendela tersebut belum cukup "
            "(kurang dari 3 transaksi) untuk membandingkan nominal."
        )
    elif ratio is None:
        ba.append("Nominal tidak dapat dibandingkan dengan median transaksi keluar pengirim.")
    else:
        ba.append(
            f"Nominal ini setara {fmt_num(ratio, 1)}x median transaksi keluar pengirim"
            + (", sehingga tergolong tidak biasa." if "unusual_amount" in codes else ".")
        )
    if ev["self_transfer"]:
        ba.append("Transaksi merupakan pemindahan dana antar rekening milik pihak yang sama.")

    # --- network
    na = [
        f"Dalam 24 jam, pengirim mengirim dana ke {ev['sender_distinct_receivers_24h']} "
        f"penerima berbeda, sedangkan penerima menerima dana dari "
        f"{ev['receiver_distinct_senders_24h']} pengirim berbeda "
        f"({ev['receiver_in_count_24h']} transaksi masuk, total "
        f"{fmt_money(ev['receiver_in_amount_24h'], ev.get('currency'))})."
    ]
    if ev["cross_bank"]:
        na.append("Aliran dana melintasi bank yang berbeda.")
    if "flagged_counterparty" in codes:
        na.append(
            f"Pengirim terlibat dalam {ev['sender_flagged_24h']} dan penerima dalam "
            f"{ev['receiver_flagged_24h']} transaksi lain berstatus terflag atau diblokir "
            "pada periode yang sama."
        )
    else:
        na.append(
            "Tidak ada transaksi lain berstatus terflag atau diblokir yang melibatkan "
            "rekening pengirim maupun penerima dalam 24 jam."
        )
    cats = [
        f"{role} {ev[key]}" for role, key in (("pengirim", "sender_risk_category"),
                                              ("penerima", "receiver_risk_category"))
        if ev.get(key)
    ]
    if cats:
        na.append(f"Kategori risiko rekening: {', '.join(cats)}.")

    # --- recommendation
    verb = action_verb(ev)
    labels = [f["label"] for f in factors]
    if verb == "BLOKIR":
        rec = [
            "BLOKIR transaksi dan eskalasikan ke tim kepatuhan untuk evaluasi pelaporan "
            "Transaksi Keuangan Mencurigakan (TKM) kepada PPATK."
        ]
    elif verb == "TUNDA":
        rec = [
            "TUNDA transaksi dan lakukan uji tuntas yang ditingkatkan (Enhanced Due "
            "Diligence) terhadap rekening pengirim dan penerima."
        ]
    elif verb == "TINJAU":
        rec = [
            "TINJAU transaksi secara manual dan verifikasi tujuan serta sumber dana "
            "sebelum diteruskan."
        ]
    elif len(factors) >= 2:
        rec = ["PROSES transaksi, namun pantau aktivitas kedua rekening secara berkala."]
    else:
        rec = ["PROSES transaksi; tidak ditemukan indikator risiko yang signifikan."]
    if labels:
        rec.append(f"Faktor risiko yang teridentifikasi: {', '.join(labels)}.")

    return {
        "pattern_matching": _cap(pm),
        "behavior_analysis": _cap(ba),
        "network_analysis": _cap(na),
        "recommendation": _cap(rec),
    }
