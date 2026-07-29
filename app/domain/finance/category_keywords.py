"""Keyword lookup tables for the regex/rule-based fast path.

These are intentionally small and conservative. The fast path in
TransactionService only fires when a keyword here matches AND an amount
was found AND a wallet was mentioned explicitly — anything else falls
back to the LLM. Keep this list to high-confidence, unambiguous keywords;
resist the urge to make it "smart", that's what the LLM fallback is for.
"""

EXPENSE_CATEGORIES: tuple[str, ...] = (
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Health",
    "Entertainment",
    "Education",
    "Other",
)

INCOME_CATEGORIES: tuple[str, ...] = (
    "Salary",
    "Bonus",
    "Investment",
    "Refund",
    "Other",
)

TRANSFER_CATEGORIES: tuple[str, ...] = (
    "Transfer",
    "Cash Withdrawal",
)

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
    "Education": [
        "sekolah", "kuliah", "kursus", "buku", "kelas",
    ],
}

CATEGORY_ALIASES: dict[str, str] = {
    "food": "Food",
    "makanan": "Food",
    "minuman": "Food",
    "restaurant": "Food",
    "restoran": "Food",
    "coffee": "Food",
    "kopi": "Food",
    "grocery": "Shopping",
    "groceries": "Shopping",
    "belanja": "Shopping",
    "transport": "Transport",
    "transportation": "Transport",
    "transportasi": "Transport",
    "shopping": "Shopping",
    "bills": "Bills",
    "bill": "Bills",
    "tagihan": "Bills",
    "utilities": "Bills",
    "health": "Health",
    "medical": "Health",
    "kesehatan": "Health",
    "entertainment": "Entertainment",
    "hiburan": "Entertainment",
    "education": "Education",
    "pendidikan": "Education",
    "salary": "Salary",
    "gaji": "Salary",
    "bonus": "Bonus",
    "investment": "Investment",
    "investasi": "Investment",
    "dividend": "Investment",
    "dividen": "Investment",
    "refund": "Refund",
    "cashback": "Refund",
    "transfer": "Transfer",
    "cash withdrawal": "Cash Withdrawal",
    "tarik tunai": "Cash Withdrawal",
    "lain-lain": "Other",
    "lain lain": "Other",
    "other": "Other",
    "uncategorized": "Other",
    # Keep leisure/travel-style labels intentionally broad.
    "travel": "Other",
    "vacation": "Other",
    "holiday": "Other",
    "liburan": "Other",
    "wisata": "Other",
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


def normalize_category(category: str | None, transaction_type: str | None) -> str:
    """Collapse arbitrary LLM labels into the small category set used by the app."""
    trx_type = (transaction_type or "EXPENSE").strip().lower()
    allowed = {
        "income": INCOME_CATEGORIES,
        "transfer": TRANSFER_CATEGORIES,
    }.get(trx_type, EXPENSE_CATEGORIES)

    fallback = "Transfer" if trx_type == "transfer" else "Other"
    if not category:
        return fallback

    normalized = " ".join(category.strip().split())
    normalized = CATEGORY_ALIASES.get(normalized.lower(), normalized.title())
    if normalized in allowed:
        return normalized
    return fallback


def guess_wallet(text: str) -> str | None:
    """Return a canonical wallet name if a known wallet keyword is mentioned."""
    text_lower = text.lower()
    for keyword, canonical_name in WALLET_KEYWORDS.items():
        if keyword in text_lower:
            return canonical_name
    return None
