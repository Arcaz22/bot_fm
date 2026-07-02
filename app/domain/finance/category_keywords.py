"""Keyword lookup tables for the regex/rule-based fast path.

These are intentionally small and conservative. The fast path in
TransactionService only fires when a keyword here matches AND an amount
was found AND a wallet was mentioned explicitly — anything else falls
back to the LLM. Keep this list to high-confidence, unambiguous keywords;
resist the urge to make it "smart", that's what the LLM fallback is for.
"""

# category -> keywords that strongly imply that category (lowercase)
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food": [
        "makan", "makanan", "sarapan", "nasi", "kopi",
        "jajan", "snack", "minum", "restoran", "cafe", "kafe",
    ],
    "Transport": [
        "bensin", "gojek", "grab", "ojek", "ojol", "parkir", "tol",
        "bbm", "angkot", "busway", "krl", "mrt", "taksi",
    ],
    "Shopping": [
        "belanja", "beli baju", "sepatu", "indomaret", "mall",
    ],
    "Bills": [
        "listrik", "pln", "wifi", "internet", "pulsa", "token listrik",
        "bpjs", "cicilan", "tagihan",
    ],
    "Health": [
        "obat", "dokter", "apotek", "rumah sakit", "vitamin",
    ],
    "Entertainment": [
        "nonton", "bioskop", "netflix", "spotify", "game",
    ],
}

# wallet keyword -> canonical wallet name
WALLET_KEYWORDS: dict[str, str] = {
    "gopay": "Gopay",
    "ovo": "OVO",
    "dana": "Dana",
    "shopeepay": "ShopeePay",
    "shopee pay": "ShopeePay",
    "bca": "BCA",
    "mandiri": "Mandiri",
    "bri": "BRI",
    "bni": "BNI",
    "cash": "Cash",
    "tunai": "Cash",
    "seabank": "Seabank",
    "jenius": "Jenius",
    "linkaja": "LinkAja",
}


def guess_category(text: str) -> str | None:
    """Return a category if a keyword confidently matches, else None."""
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return category
    return None


def guess_wallet(text: str) -> str | None:
    """Return a canonical wallet name if a known wallet keyword is mentioned."""
    text_lower = text.lower()
    for keyword, canonical_name in WALLET_KEYWORDS.items():
        if keyword in text_lower:
            return canonical_name
    return None
