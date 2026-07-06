"""Deteksi deterministik untuk caption/context di struk — dijalankan SEBELUM
mempertimbangkan panggilan LLM tambahan. Tujuannya: kasus simpel (mayoritas)
selesai dengan regex/substring match saja, LLM cuma dipanggil untuk sisa
yang benar-benar ambigu secara semantik.
"""
import re
from typing import List, Optional

from app.application.dtos.extraction import ReceiptItem

# Kata yang menandakan caption membatasi item mana yang relevan.
# Kalau tidak ada satupun kata ini, anggap tidak ada pembatasan sama
# sekali — skip semua proses filtering, semua item termasuk.
RESTRICTION_SIGNAL_WORDS = (
    "hanya", "cuma", "cuman", "saja", "aja", "doang", "sebagian",
)

# Kata umum yang muncul di nama item tapi tidak informatif untuk matching
# (unit, satuan, dsb) — diabaikan supaya tidak menyebabkan false-positive match.
_STOPWORDS = {"pcs", "set", "value", "lid", "oz", "ml", "gr", "kg", "the", "dan"}


def has_restriction_signal(caption: str) -> bool:
    """True kalau caption mengandung kata yang menandakan user hanya mau
    sebagian item dari struk dicatat."""
    caption_lower = caption.lower()
    return any(word in caption_lower for word in RESTRICTION_SIGNAL_WORDS)


def _significant_words(name: str) -> List[str]:
    """Pecah nama item jadi kata-kata bermakna (>=3 huruf, bukan stopword)."""
    tokens = re.split(r"[^a-zA-Z0-9]+", name.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def match_items_by_name(caption: str, items: List[ReceiptItem]) -> Optional[List[int]]:
    """Coba cocokkan nama item ke caption secara langsung (substring match).

    Return list index item yang match kalau ADA yang cocok (confident,
    deterministic — nama itemnya literally disebut di caption).
    Return None kalau tidak ada satupun yang match (berarti ambigu,
    perlu LLM untuk menafsirkan, mis. "cuma yang minuman aja").
    """
    caption_lower = caption.lower()
    matched_indices: List[int] = []

    for idx, item in enumerate(items):
        name = item.name if hasattr(item, "name") else item.get("name", "")
        words = _significant_words(name)
        if any(word in caption_lower for word in words):
            matched_indices.append(idx)

    return matched_indices if matched_indices else None
