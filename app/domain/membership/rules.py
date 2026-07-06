from datetime import date, timedelta
from typing import Optional, Tuple


def resolve_usage_period(limit_period: Optional[str], today: Optional[date] = None) -> Tuple[date, date]:
    """Terjemahkan limit_period plan_feature (daily/monthly/lifetime/None)
    jadi rentang tanggal periode berjalan, dipakai sebagai key baris
    MbrUsageCounter. Dipakai bareng oleh bot (saat cek/increment kuota)
    dan endpoint dashboard (saat menampilkan sisa kuota)."""
    today = today or date.today()

    if limit_period == "daily":
        return today, today

    if limit_period == "monthly":
        start = today.replace(day=1)
        next_month = (start.month % 12) + 1
        next_month_year = start.year + (1 if start.month == 12 else 0)
        end = start.replace(year=next_month_year, month=next_month, day=1) - timedelta(days=1)
        return start, end

    # "lifetime" atau None: satu periode tetap yang tidak pernah berganti.
    return date(2000, 1, 1), date(2999, 12, 31)
