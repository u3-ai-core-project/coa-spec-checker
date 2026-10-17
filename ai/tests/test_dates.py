"""[담당: 고도영] 날짜 표기 → YYYY-MM-DD"""
import pytest

from coa_ai.dates import find_dates, parse_date


@pytest.mark.parametrize("text, expected", [
    ("2026-02-21", "2026-02-21"),
    ("2026/2/1", "2026-02-01"),
    ("2026年02月24日", "2026-02-24"),
    ("27-Dec-2025", "2025-12-27"),
    ("10/Mar/2026", "2026-03-10"),
    ("27 Dec 2025", "2025-12-27"),
    ("Aug 19, 2025", "2025-08-19"),
    ("Sept 3, 2024", "2024-09-03"),
    ("03/07/2026", "2026-03-07"),      # 숫자만이면 월/일/년
    ("27/12/2025", "2025-12-27"),      # 앞 숫자가 12보다 크면 일/월/년
    ("02-16-2021", "2021-02-16"),
    ("Issued: 08-02-2013", "2013-08-02"),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["08-2025", "2025", "13/13/2025", "Lot A0266047", "", "Rev 4 2026"])
def test_parse_date_none(text):
    assert parse_date(text) is None


def test_find_dates_keeps_order():
    assert find_dates("03/04/2026 / 03/05/2026") == ["2026-03-04", "2026-03-05"]
