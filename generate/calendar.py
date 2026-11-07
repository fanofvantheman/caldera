"""The trading calendar: day → week → period, one calendar, declared once.

A 4-4-5 variant (or 4-5-4 / 5-4-4), fiscal year July–June, weeks Monday to Sunday, every week in
exactly one period and no split weeks. A fiscal year is 52 weeks; when the drift reaches a full
week the year carries 53 and its last period takes the extra week — declared on the row, not
hidden in a proration rule.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

VARIANTS = {
    "4-4-5": (4, 4, 5),
    "4-5-4": (4, 5, 4),
    "5-4-4": (5, 4, 4),
}


@dataclass(frozen=True)
class Week:
    week_id: str            # YYYYWW within the fiscal year, e.g. FY2027 week 1 = 2027W01
    fiscal_year: int
    fiscal_week: int        # 1..52 (53)
    period: str             # FY-period, e.g. 2027P01
    fiscal_period: int      # 1..12
    quarter: int            # 1..4
    week_start: dt.date     # Monday
    week_end: dt.date       # Sunday
    calendar_year: int
    calendar_month: int     # the month the week_start falls in — a reading only, never a grain
    is_53rd: bool


def fiscal_year_start(fy: int) -> dt.date:
    """The Monday nearest 1 July of the calendar year the fiscal year begins in (FY2027 begins July 2026)."""
    first_july = dt.date(fy - 1, 7, 1)
    offset = first_july.weekday()           # Monday = 0
    back = first_july - dt.timedelta(days=offset)
    forward = back + dt.timedelta(days=7)
    return back if (first_july - back).days <= 3 else forward


def build(first_fy: int, last_fy: int, variant: str = "4-4-5") -> list[Week]:
    pattern = VARIANTS[variant]
    weeks: list[Week] = []
    for fy in range(first_fy, last_fy + 1):
        start = fiscal_year_start(fy)
        end = fiscal_year_start(fy + 1)
        n_weeks = (end - start).days // 7
        assert n_weeks in (52, 53), (fy, n_weeks)
        # period boundaries: cumulative weeks per period; the 53rd week joins period 12
        bounds: list[int] = []
        cum = 0
        for q in range(4):
            for w in pattern:
                cum += w
                bounds.append(cum)
        for i in range(n_weeks):
            fw = i + 1
            fp = next((p + 1 for p, b in enumerate(bounds) if fw <= b), 12)
            ws = start + dt.timedelta(days=7 * i)
            we = ws + dt.timedelta(days=6)
            weeks.append(Week(
                week_id=f"{fy}W{fw:02d}", fiscal_year=fy, fiscal_week=fw,
                period=f"{fy}P{fp:02d}", fiscal_period=fp, quarter=(fp - 1) // 3 + 1,
                week_start=ws, week_end=we, calendar_year=ws.year, calendar_month=ws.month,
                is_53rd=(fw == 53),
            ))
    return weeks


def periods(weeks: list[Week]) -> list[dict]:
    seen: dict[str, dict] = {}
    for w in weeks:
        p = seen.setdefault(w.period, {
            "period": w.period, "fiscal_year": w.fiscal_year, "fiscal_period": w.fiscal_period,
            "quarter": w.quarter, "period_start": w.week_start, "period_end": w.week_end, "weeks": 0,
        })
        p["period_end"] = w.week_end
        p["weeks"] += 1
    return list(seen.values())
